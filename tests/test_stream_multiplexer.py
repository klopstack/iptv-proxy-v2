"""
Unit tests for StreamMultiplexer.

These tests verify the core functionality of the stream multiplexer,
including the simplified architecture without buffering.

Key behaviors tested:
- Multiple subscribers can share a single upstream connection
- Late-joining subscribers receive live data (no buffering needed)
- Subscriber lifecycle management (join, leave, cleanup)
"""
from queue import Queue
from unittest.mock import MagicMock, patch

from services.stream_multiplexer import (
    SharedStream,
    StreamMultiplexer,
    StreamSubscriber,
    get_multiplexer,
    shutdown_multiplexer,
)


class TestStreamSubscriber:
    """Tests for StreamSubscriber dataclass."""

    def test_subscriber_defaults(self):
        """Test subscriber has correct default values."""
        subscriber = StreamSubscriber(
            subscriber_id="test123",
            client_ip="127.0.0.1",
            queue=Queue(maxsize=50),
        )

        assert subscriber.subscriber_id == "test123"
        assert subscriber.client_ip == "127.0.0.1"
        assert subscriber.bytes_sent == 0
        assert subscriber.active is True
        assert subscriber.ready is False  # Not ready until stream_chunks starts

    def test_subscriber_ready_flag(self):
        """Test the ready flag controls when subscriber receives data."""
        subscriber = StreamSubscriber(
            subscriber_id="test456",
            client_ip="127.0.0.1",
            queue=Queue(maxsize=50),
        )

        # Not ready by default
        assert not subscriber.ready

        # Can be set to ready
        subscriber.ready = True
        assert subscriber.ready


class TestSharedStream:
    """Tests for SharedStream dataclass."""

    def test_shared_stream_defaults(self):
        """Test shared stream has correct default values."""
        stream = SharedStream(
            stream_key="1:12345:ts",
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://example.com/stream.ts",
            credential_id=1,
            session_token="test_token",
        )

        assert stream.stream_key == "1:12345:ts"
        assert stream.is_active is True
        assert stream.bytes_received == 0
        assert stream.error is None
        assert len(stream.subscribers) == 0

    def test_shared_stream_no_buffer_fields(self):
        """Verify SharedStream no longer has buffer-related fields."""
        stream = SharedStream(
            stream_key="1:test:ts",
            account_id=1,
            stream_id="test",
            format="ts",
            upstream_url="http://example.com/test.ts",
            credential_id=1,
            session_token="token",
        )

        # These fields should NOT exist after cleanup
        assert not hasattr(stream, "init_data")
        assert not hasattr(stream, "init_data_complete")
        assert not hasattr(stream, "init_data_lock")
        assert not hasattr(stream, "keyframe_buffer")
        assert not hasattr(stream, "keyframe_buffer_lock")


class TestStreamMultiplexerBasic:
    """Basic unit tests for StreamMultiplexer."""

    def test_multiplexer_starts_and_stops(self):
        """Test multiplexer can start and stop cleanly."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()

        assert multiplexer._cleanup_thread is not None
        assert multiplexer._cleanup_thread.is_alive()

        multiplexer.stop()
        assert multiplexer._shutdown is True

    def test_get_stream_key(self):
        """Test stream key generation."""
        multiplexer = StreamMultiplexer()
        key = multiplexer._get_stream_key(1, "12345", "ts")
        assert key == "1:12345:ts"

    def test_get_active_stream_not_found(self):
        """Test getting a non-existent stream returns None."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()
        try:
            stream = multiplexer.get_active_stream(1, "nonexistent", "ts")
            assert stream is None
        finally:
            multiplexer.stop()

    def test_get_stats_empty(self):
        """Test stats for empty multiplexer."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()
        try:
            stats = multiplexer.get_stats()
            assert stats["active_streams"] == 0
            assert stats["total_subscribers"] == 0
            assert stats["streams"] == []
        finally:
            multiplexer.stop()


class TestStreamMultiplexerSubscription:
    """Tests for subscription management."""

    @patch("services.stream_multiplexer.requests.get")
    def test_subscribe_creates_stream(self, mock_get):
        """Test that subscribing creates a new stream."""
        # Mock response that streams some data
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_response.iter_content.return_value = iter([b"chunk1", b"chunk2"])
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()
        multiplexer.start()

        try:
            stream, subscriber = multiplexer.subscribe(
                account_id=1,
                stream_id="test123",
                format="ts",
                upstream_url="http://example.com/stream.ts",
                credential_id=1,
                session_token="test_session",
                client_ip="127.0.0.1",
            )

            assert stream is not None
            assert subscriber is not None
            assert stream.stream_key == "1:test123:ts"
            assert subscriber.subscriber_id is not None
            assert not subscriber.ready  # Not ready until stream_chunks called

        finally:
            multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_second_subscriber_joins_existing_stream(self, mock_get):
        """Test that second subscriber joins existing stream."""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}
        # Make it return chunks indefinitely
        mock_response.iter_content.return_value = iter([b"chunk"] * 100)
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()
        multiplexer.start()

        try:
            # First subscriber
            stream1, sub1 = multiplexer.subscribe(
                account_id=1,
                stream_id="shared",
                format="ts",
                upstream_url="http://example.com/stream.ts",
                credential_id=1,
                session_token="session1",
                client_ip="127.0.0.1",
            )

            # Second subscriber
            stream2, sub2 = multiplexer.subscribe(
                account_id=1,
                stream_id="shared",
                format="ts",
                upstream_url="http://example.com/stream.ts",
                credential_id=1,
                session_token="session2",
                client_ip="127.0.0.2",
            )

            # Both should reference the same stream
            assert stream1.stream_key == stream2.stream_key
            # But different subscribers
            assert sub1.subscriber_id != sub2.subscriber_id

        finally:
            multiplexer.stop()

    def test_unsubscribe_removes_subscriber(self):
        """Test that unsubscribing removes the subscriber."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()

        try:
            # Create a stream manually for testing
            stream = SharedStream(
                stream_key="1:test:ts",
                account_id=1,
                stream_id="test",
                format="ts",
                upstream_url="http://example.com/test.ts",
                credential_id=1,
                session_token="token",
            )

            subscriber = StreamSubscriber(
                subscriber_id="sub123",
                client_ip="127.0.0.1",
                queue=Queue(maxsize=50),
            )

            stream.subscribers[subscriber.subscriber_id] = subscriber

            # Unsubscribe
            multiplexer.unsubscribe(stream, subscriber)

            assert subscriber.subscriber_id not in stream.subscribers
            assert not subscriber.active

        finally:
            multiplexer.stop()


class TestStreamMultiplexerNoBuffering:
    """
    Tests verifying the multiplexer no longer uses buffering.

    These tests ensure that after removing init_data and keyframe_buffer,
    the multiplexer still functions correctly with direct chunk forwarding.
    """

    def test_subscriber_no_needs_keyframe_buffer_field(self):
        """Verify StreamSubscriber no longer has needs_keyframe_buffer field."""
        subscriber = StreamSubscriber(
            subscriber_id="test",
            client_ip="127.0.0.1",
            queue=Queue(maxsize=50),
        )

        # This field should NOT exist after cleanup
        assert not hasattr(subscriber, "needs_keyframe_buffer")

    def test_stream_chunks_marks_ready_immediately(self):
        """Test that stream_chunks marks subscriber ready immediately."""
        multiplexer = StreamMultiplexer()

        # Create stream and subscriber manually
        stream = SharedStream(
            stream_key="1:test:ts",
            account_id=1,
            stream_id="test",
            format="ts",
            upstream_url="http://example.com/test.ts",
            credential_id=1,
            session_token="token",
        )

        subscriber = StreamSubscriber(
            subscriber_id="sub123",
            client_ip="127.0.0.1",
            queue=Queue(maxsize=50),
        )

        stream.subscribers[subscriber.subscriber_id] = subscriber

        # Start stream_chunks generator
        gen = multiplexer.stream_chunks(stream, subscriber)

        # Put a chunk in the queue so the generator can yield something
        subscriber.queue.put(b"test chunk")
        subscriber.queue.put(None)  # End signal

        # Consume first chunk
        chunk = next(gen)

        # Subscriber should be marked ready
        assert subscriber.ready
        assert chunk == b"test chunk"


class TestStreamMultiplexerSingleton:
    """Test the singleton getter functions."""

    def test_get_multiplexer_returns_instance(self):
        """Test that get_multiplexer returns a working instance."""
        # Ensure clean state
        shutdown_multiplexer()

        multiplexer = get_multiplexer()
        assert multiplexer is not None
        assert multiplexer._cleanup_thread is not None

        # Cleanup
        shutdown_multiplexer()

    def test_get_multiplexer_returns_same_instance(self):
        """Test that get_multiplexer returns the same instance."""
        shutdown_multiplexer()

        m1 = get_multiplexer()
        m2 = get_multiplexer()
        assert m1 is m2

        shutdown_multiplexer()

    def test_shutdown_multiplexer(self):
        """Test that shutdown_multiplexer cleans up properly."""
        get_multiplexer()  # Create instance
        shutdown_multiplexer()

        # After shutdown, getting multiplexer should create a new one
        m = get_multiplexer()
        assert m is not None

        shutdown_multiplexer()


class TestStreamMultiplexerIdleManagement:
    """Tests for idle stream management."""

    def test_get_idle_stream_count(self):
        """Test counting idle streams."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()

        try:
            # Create an idle stream (no subscribers)
            stream = SharedStream(
                stream_key="1:idle:ts",
                account_id=1,
                stream_id="idle",
                format="ts",
                upstream_url="http://example.com/idle.ts",
                credential_id=1,
                session_token="token",
            )
            multiplexer._streams[stream.stream_key] = stream

            count = multiplexer.get_idle_stream_count(1)
            assert count == 1

            # Different account should return 0
            count2 = multiplexer.get_idle_stream_count(2)
            assert count2 == 0

        finally:
            multiplexer.stop()

    def test_release_idle_streams_for_account(self):
        """Test releasing idle streams."""
        multiplexer = StreamMultiplexer()
        multiplexer.start()

        try:
            # Create an idle stream
            stream = SharedStream(
                stream_key="1:release:ts",
                account_id=1,
                stream_id="release",
                format="ts",
                upstream_url="http://example.com/release.ts",
                credential_id=1,
                session_token="token",
            )
            multiplexer._streams[stream.stream_key] = stream

            # Release it
            released = multiplexer.release_idle_streams_for_account(1)
            assert released == 1

            # Should be gone
            assert multiplexer.get_idle_stream_count(1) == 0

        finally:
            multiplexer.stop()
