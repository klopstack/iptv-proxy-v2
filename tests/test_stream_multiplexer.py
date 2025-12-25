"""
Tests for stream multiplexer service

Tests the core functionality of sharing upstream connections across multiple subscribers.
"""
import time
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
    """Tests for StreamSubscriber dataclass"""

    def test_subscriber_creation(self):
        """Test creating a subscriber"""
        queue: "Queue[bytes | None]" = Queue()
        subscriber = StreamSubscriber(
            subscriber_id="test-123",
            client_ip="192.168.1.1",
            queue=queue,
        )

        assert subscriber.subscriber_id == "test-123"
        assert subscriber.client_ip == "192.168.1.1"
        assert subscriber.bytes_sent == 0
        assert subscriber.active is True

    def test_subscriber_queue(self):
        """Test subscriber queue functionality"""
        queue: "Queue[bytes | None]" = Queue()
        subscriber = StreamSubscriber(
            subscriber_id="test-123",
            client_ip="192.168.1.1",
            queue=queue,
        )

        # Put data in queue
        subscriber.queue.put(b"test data")
        assert subscriber.queue.get() == b"test data"


class TestSharedStream:
    """Tests for SharedStream dataclass"""

    def test_shared_stream_creation(self):
        """Test creating a shared stream"""
        stream = SharedStream(
            stream_key="1:12345:ts",
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/live/user/pass/12345.ts",
            credential_id=1,
            session_token="token-123",
        )

        assert stream.stream_key == "1:12345:ts"
        assert stream.account_id == 1
        assert stream.stream_id == "12345"
        assert stream.format == "ts"
        assert stream.is_active is True
        assert stream.bytes_received == 0
        assert len(stream.subscribers) == 0

    def test_shared_stream_hash(self):
        """Test that shared streams can be used in sets"""
        stream1 = SharedStream(
            stream_key="1:12345:ts",
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream1",
            credential_id=1,
            session_token="token1",
        )
        stream2 = SharedStream(
            stream_key="1:12345:ts",
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream2",
            credential_id=1,
            session_token="token2",
        )

        # Same stream_key should have same hash
        assert hash(stream1) == hash(stream2)


class TestStreamMultiplexer:
    """Tests for StreamMultiplexer"""

    def test_multiplexer_creation(self):
        """Test creating a multiplexer"""
        multiplexer = StreamMultiplexer()
        assert multiplexer._streams == {}
        assert multiplexer._shutdown is False

    def test_get_stream_key(self):
        """Test stream key generation"""
        multiplexer = StreamMultiplexer()
        key = multiplexer._get_stream_key(1, "12345", "ts")
        assert key == "1:12345:ts"

    def test_get_active_stream_not_found(self):
        """Test getting non-existent stream"""
        multiplexer = StreamMultiplexer()
        stream = multiplexer.get_active_stream(1, "12345", "ts")
        assert stream is None

    @patch("services.stream_multiplexer.requests.get")
    def test_subscribe_creates_new_stream(self, mock_get):
        """Test subscribing creates a new stream"""
        # Mock upstream response - use a blocking generator to keep stream alive
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def blocking_generator():
            # Yield one chunk, then wait (simulating a live stream)
            yield b"initial_data"
            time.sleep(1)  # Keep stream alive

        mock_response.iter_content.return_value = blocking_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/live/user/pass/12345.ts",
            credential_id=1,
            session_token="token-123",
            client_ip="192.168.1.1",
        )

        assert stream is not None
        assert subscriber is not None
        assert stream.stream_key == "1:12345:ts"
        assert subscriber.subscriber_id in stream.subscribers
        assert len(stream.subscribers) == 1

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_multiple_subscribers_share_stream(self, mock_get):
        """Test multiple subscribers join the same stream"""
        # Mock upstream response - use a blocking generator to keep stream alive
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def blocking_generator():
            # Yield chunks slowly to keep stream alive during test
            for i in range(10):
                yield f"chunk{i}".encode()
                time.sleep(0.1)

        mock_response.iter_content.return_value = blocking_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        # First subscriber creates stream
        stream1, subscriber1 = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/live/user/pass/12345.ts",
            credential_id=1,
            session_token="token-123",
            client_ip="192.168.1.1",
        )

        # Give the stream a moment to start
        time.sleep(0.05)

        # Second subscriber joins same stream
        stream2, subscriber2 = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/live/user/pass/12345.ts",
            credential_id=1,
            session_token="token-123",
            client_ip="192.168.1.2",
        )

        # Should be the same stream
        assert stream1 is stream2
        assert len(stream1.subscribers) == 2
        assert subscriber1.subscriber_id != subscriber2.subscriber_id

        # Only one upstream connection (one call to requests.get)
        assert mock_get.call_count == 1

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_unsubscribe_removes_subscriber(self, mock_get):
        """Test unsubscribing removes subscriber from stream"""
        # Mock upstream response
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_response.iter_content.return_value = iter([])
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        assert len(stream.subscribers) == 1

        multiplexer.unsubscribe(stream, subscriber)

        assert len(stream.subscribers) == 0
        assert subscriber.active is False

        # Cleanup
        multiplexer.stop()

    def test_get_stats_empty(self):
        """Test getting stats with no streams"""
        multiplexer = StreamMultiplexer()
        stats = multiplexer.get_stats()

        assert stats["active_streams"] == 0
        assert stats["total_subscribers"] == 0
        assert stats["streams"] == []

    @patch("services.stream_multiplexer.requests.get")
    def test_get_stats_with_streams(self, mock_get):
        """Test getting stats with active streams"""
        # Mock upstream response
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_response.iter_content.return_value = iter([])
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        stats = multiplexer.get_stats()

        assert stats["active_streams"] == 1
        assert stats["total_subscribers"] == 1
        assert len(stats["streams"]) == 1
        assert stats["streams"][0]["stream_key"] == "1:12345:ts"

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_stream_chunks_receives_data(self, mock_get):
        """Test that stream_chunks yields data correctly"""
        # Mock upstream response with data that streams slowly
        # First chunk is a "warmup" that might be missed due to timing
        # The subsequent chunks should all be received
        all_data = [b"chunk1", b"chunk2", b"chunk3", b"chunk4", b"chunk5"]
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def slow_generator():
            # Yield chunks with delays to keep stream alive
            for chunk in all_data:
                yield chunk
                time.sleep(0.02)

        mock_response.iter_content.return_value = slow_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        # Collect chunks (reader starts immediately in subscribe)
        received_chunks = []

        for chunk in multiplexer.stream_chunks(stream, subscriber):
            received_chunks.append(chunk)
            if len(received_chunks) >= 3:  # Get at least 3 chunks
                break

        # We should receive at least some chunks (may miss first due to timing)
        assert len(received_chunks) >= 3
        # All received chunks should be valid data from the stream
        for chunk in received_chunks:
            assert chunk in all_data

        # Cleanup
        multiplexer.stop()

    def test_multiplexer_start_stop(self):
        """Test starting and stopping multiplexer"""
        multiplexer = StreamMultiplexer()

        multiplexer.start()
        assert multiplexer._cleanup_thread is not None
        assert multiplexer._cleanup_thread.is_alive()

        multiplexer.stop()
        assert multiplexer._shutdown is True

    @patch("services.stream_multiplexer.requests.get")
    def test_different_formats_create_different_streams(self, mock_get):
        """Test that different formats create separate streams"""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_response.iter_content.return_value = iter([])
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        # Subscribe to ts format
        stream_ts, _ = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream.ts",
            credential_id=1,
            session_token="token-1",
        )

        # Subscribe to m3u8 format
        stream_m3u8, _ = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="m3u8",
            upstream_url="http://test.com/stream.m3u8",
            credential_id=1,
            session_token="token-2",
        )

        # Should be different streams
        assert stream_ts is not stream_m3u8
        assert stream_ts.stream_key != stream_m3u8.stream_key

        # Cleanup
        multiplexer.stop()


class TestGlobalMultiplexer:
    """Tests for global multiplexer instance"""

    def test_get_multiplexer_returns_singleton(self):
        """Test that get_multiplexer returns the same instance"""
        # Clean up any existing instance
        shutdown_multiplexer()

        multiplexer1 = get_multiplexer()
        multiplexer2 = get_multiplexer()

        assert multiplexer1 is multiplexer2

        # Cleanup
        shutdown_multiplexer()

    def test_shutdown_multiplexer(self):
        """Test shutting down the global multiplexer"""
        # Get instance
        get_multiplexer()

        # Shutdown
        shutdown_multiplexer()

        # Getting again should create new instance
        import services.stream_multiplexer as module

        assert module._multiplexer is None


class TestIdleStreamRelease:
    """Tests for releasing idle streams to free credentials"""

    @patch("services.stream_multiplexer.requests.get")
    def test_get_idle_stream_count(self, mock_get):
        """Test counting idle streams for an account"""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def blocking_generator():
            for i in range(100):
                yield f"chunk{i}".encode()
                time.sleep(0.05)

        mock_response.iter_content.return_value = blocking_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        # Create a stream and then unsubscribe to make it idle
        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream1",
            credential_id=1,
            session_token="token-1",
        )

        # Wait for stream to start
        time.sleep(0.05)

        # Initially has a subscriber
        assert multiplexer.get_idle_stream_count(1) == 0

        # Unsubscribe to make it idle
        multiplexer.unsubscribe(stream, subscriber)

        # Now it should be idle
        assert multiplexer.get_idle_stream_count(1) == 1

        # Different account should have 0
        assert multiplexer.get_idle_stream_count(999) == 0

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_release_idle_streams_for_account(self, mock_get):
        """Test releasing idle streams to free credentials"""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def blocking_generator():
            for i in range(100):
                yield f"chunk{i}".encode()
                time.sleep(0.05)

        mock_response.iter_content.return_value = blocking_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        # Create a stream and make it idle
        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream1",
            credential_id=1,
            session_token="token-1",
        )
        time.sleep(0.05)
        multiplexer.unsubscribe(stream, subscriber)

        assert multiplexer.get_idle_stream_count(1) == 1

        # Release idle streams
        released = multiplexer.release_idle_streams_for_account(1)

        assert released == 1
        assert multiplexer.get_idle_stream_count(1) == 0

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_release_idle_streams_respects_max(self, mock_get):
        """Test that release respects max_to_release parameter"""
        call_count = [0]

        def mock_get_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            mock_response.headers = {"Content-Type": "video/mp2t"}

            def blocking_generator():
                for i in range(100):
                    yield f"chunk{i}".encode()
                    time.sleep(0.05)

            mock_response.iter_content.return_value = blocking_generator()
            mock_response.raise_for_status.return_value = None
            return mock_response

        mock_get.side_effect = mock_get_side_effect

        multiplexer = StreamMultiplexer()

        # Create multiple idle streams
        streams = []
        for i in range(3):
            stream, subscriber = multiplexer.subscribe(
                account_id=1,
                stream_id=f"stream{i}",
                format="ts",
                upstream_url=f"http://test.com/stream{i}",
                credential_id=1,
                session_token=f"token-{i}",
            )
            time.sleep(0.05)
            multiplexer.unsubscribe(stream, subscriber)
            streams.append(stream)

        assert multiplexer.get_idle_stream_count(1) == 3

        # Release only 1
        released = multiplexer.release_idle_streams_for_account(1, max_to_release=1)

        assert released == 1
        assert multiplexer.get_idle_stream_count(1) == 2

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_release_does_not_affect_active_subscribers(self, mock_get):
        """Test that release doesn't close streams with active subscribers"""
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "video/mp2t"}

        def blocking_generator():
            for i in range(100):
                yield f"chunk{i}".encode()
                time.sleep(0.05)

        mock_response.iter_content.return_value = blocking_generator()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        # Create a stream with an active subscriber
        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream1",
            credential_id=1,
            session_token="token-1",
        )
        time.sleep(0.05)

        # Don't unsubscribe - stream has active subscriber
        assert multiplexer.get_idle_stream_count(1) == 0

        # Try to release - should release nothing
        released = multiplexer.release_idle_streams_for_account(1)

        assert released == 0
        assert stream.is_active is True

        # Cleanup
        multiplexer.stop()


class TestUpstreamErrors:
    """Tests for handling upstream connection errors"""

    @patch("services.stream_multiplexer.requests.get")
    def test_upstream_timeout(self, mock_get):
        """Test handling upstream timeout"""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        # Wait for the upstream reader to fail
        time.sleep(0.2)

        assert stream.is_active is False
        assert "timeout" in stream.error.lower()

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_upstream_connection_error(self, mock_get):
        """Test handling upstream connection error"""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        # Wait for the upstream reader to fail
        time.sleep(0.2)

        assert stream.is_active is False
        assert "connection" in stream.error.lower()

        # Cleanup
        multiplexer.stop()

    @patch("services.stream_multiplexer.requests.get")
    def test_upstream_http_error(self, mock_get):
        """Test handling upstream HTTP error"""
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        multiplexer = StreamMultiplexer()

        stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://test.com/stream",
            credential_id=1,
            session_token="token-123",
        )

        # Wait for the upstream reader to fail
        time.sleep(0.2)

        assert stream.is_active is False
        assert "http" in stream.error.lower() or "404" in stream.error

        # Cleanup
        multiplexer.stop()
