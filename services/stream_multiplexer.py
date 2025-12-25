"""
Stream Multiplexer Service - shares upstream connections across multiple clients

This service enables multiple downstream clients to receive data from a single
upstream connection. When a new client requests a stream that's already active,
they join the existing stream instead of creating a new upstream connection.

Key concepts:
- SharedStream: An active upstream connection with multiple subscribers
- StreamSubscriber: A client receiving data from a shared stream
- Ring buffer: Each subscriber gets chunks via a queue

Thread-safety:
- Uses threading locks to protect shared state
- Each subscriber has its own queue to avoid blocking
"""

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Callable, Dict, Generator, Optional

import requests

logger = logging.getLogger(__name__)

# Configuration
CHUNK_SIZE = 65536  # 64KB chunks
SUBSCRIBER_QUEUE_SIZE = 50  # Max chunks buffered per subscriber
UPSTREAM_CONNECT_TIMEOUT = 60
UPSTREAM_READ_TIMEOUT = 120
STREAM_IDLE_TIMEOUT = 30  # Seconds with no subscribers before closing stream
SUBSCRIBER_TIMEOUT = 5  # Seconds to wait for a chunk before checking stream status


@dataclass
class StreamSubscriber:
    """A client subscribed to a shared stream."""

    subscriber_id: str
    client_ip: Optional[str]
    queue: "Queue[Optional[bytes]]"  # None signals end of stream
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_read: datetime = field(default_factory=datetime.utcnow)
    bytes_sent: int = 0
    active: bool = True


@dataclass
class SharedStream:
    """A shared upstream stream with multiple subscribers."""

    stream_key: str  # Unique key: "{account_id}:{stream_id}:{format}"
    account_id: int
    stream_id: str
    format: str
    upstream_url: str
    credential_id: Optional[int]
    session_token: str
    content_type: str = "video/mp2t"

    # State
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    bytes_received: int = 0
    is_active: bool = True
    error: Optional[str] = None

    # Thread management
    thread: Optional[threading.Thread] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Subscribers
    subscribers: Dict[str, StreamSubscriber] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.stream_key)


class StreamMultiplexer:
    """
    Manages shared upstream streams and distributes data to subscribers.

    Usage:
        multiplexer = StreamMultiplexer()

        # Get or create a shared stream
        shared_stream, subscriber = multiplexer.subscribe(
            account_id=1,
            stream_id="12345",
            format="ts",
            upstream_url="http://...",
            credential_id=1,
            session_token="abc",
            client_ip="192.168.1.1"
        )

        # Read chunks in a generator
        for chunk in multiplexer.stream_chunks(subscriber):
            yield chunk

        # When done
        multiplexer.unsubscribe(shared_stream, subscriber)
    """

    def __init__(self):
        self._streams: Dict[str, SharedStream] = {}
        self._lock = threading.RLock()  # Protects _streams dict
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False

    def start(self):
        """Start the background cleanup thread."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._shutdown = False
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, name="StreamMultiplexerCleanup", daemon=True
            )
            self._cleanup_thread.start()
            logger.info("StreamMultiplexer cleanup thread started")

    def stop(self):
        """Stop the multiplexer and all streams."""
        self._shutdown = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

        with self._lock:
            for stream in list(self._streams.values()):
                self._close_stream(stream)
            self._streams.clear()

        logger.info("StreamMultiplexer stopped")

    def _get_stream_key(self, account_id: int, stream_id: str, format: str) -> str:
        """Generate a unique key for a stream."""
        return f"{account_id}:{stream_id}:{format}"

    def get_active_stream(self, account_id: int, stream_id: str, format: str) -> Optional[SharedStream]:
        """Check if a stream is already active."""
        stream_key = self._get_stream_key(account_id, stream_id, format)
        with self._lock:
            stream = self._streams.get(stream_key)
            if stream and stream.is_active:
                return stream
            return None

    def subscribe(
        self,
        account_id: int,
        stream_id: str,
        format: str,
        upstream_url: str,
        credential_id: Optional[int],
        session_token: str,
        client_ip: Optional[str] = None,
        user_agent: str = "okhttp/3.14.9",
        on_stream_started: Optional[Callable[[SharedStream], None]] = None,
    ) -> tuple[SharedStream, StreamSubscriber]:
        """
        Subscribe to a stream. Creates the stream if it doesn't exist.

        Args:
            account_id: The account ID
            stream_id: The stream ID
            format: Stream format (ts, m3u8)
            upstream_url: Full URL to the upstream stream
            credential_id: Credential being used (for tracking)
            session_token: Session token from ConnectionManager
            client_ip: Client's IP address
            user_agent: User agent for upstream requests
            on_stream_started: Callback when a new stream starts

        Returns:
            Tuple of (SharedStream, StreamSubscriber)
        """
        stream_key = self._get_stream_key(account_id, stream_id, format)

        with self._lock:
            # Check for existing stream
            shared_stream = self._streams.get(stream_key)

            if shared_stream and shared_stream.is_active:
                # Join existing stream
                logger.info(
                    f"Client {client_ip} joining existing stream {stream_key} "
                    f"({len(shared_stream.subscribers)} existing subscribers)"
                )
            else:
                # Create new stream
                shared_stream = SharedStream(
                    stream_key=stream_key,
                    account_id=account_id,
                    stream_id=stream_id,
                    format=format,
                    upstream_url=upstream_url,
                    credential_id=credential_id,
                    session_token=session_token,
                )
                self._streams[stream_key] = shared_stream

                # Start upstream reader thread
                shared_stream.thread = threading.Thread(
                    target=self._upstream_reader,
                    args=(shared_stream, user_agent),
                    name=f"Stream-{stream_key}",
                    daemon=True,
                )
                shared_stream.thread.start()

                logger.info(f"Created new shared stream {stream_key}")

                if on_stream_started:
                    on_stream_started(shared_stream)

            # Create subscriber
            subscriber = StreamSubscriber(
                subscriber_id=secrets.token_hex(16),
                client_ip=client_ip,
                queue=Queue(maxsize=SUBSCRIBER_QUEUE_SIZE),
            )

            with shared_stream.lock:
                shared_stream.subscribers[subscriber.subscriber_id] = subscriber

            logger.info(
                f"Subscriber {subscriber.subscriber_id[:8]}... joined stream {stream_key} "
                f"(total: {len(shared_stream.subscribers)})"
            )

            return shared_stream, subscriber

    def unsubscribe(self, stream: SharedStream, subscriber: StreamSubscriber) -> None:
        """
        Unsubscribe from a stream.

        Args:
            stream: The shared stream
            subscriber: The subscriber to remove
        """
        with stream.lock:
            subscriber.active = False
            if subscriber.subscriber_id in stream.subscribers:
                del stream.subscribers[subscriber.subscriber_id]

        logger.info(
            f"Subscriber {subscriber.subscriber_id[:8]}... left stream {stream.stream_key} "
            f"(remaining: {len(stream.subscribers)}, bytes: {subscriber.bytes_sent})"
        )

        # Stream cleanup happens in _cleanup_loop

    def stream_chunks(self, stream: SharedStream, subscriber: StreamSubscriber) -> Generator[bytes, None, None]:
        """
        Generator that yields chunks for a subscriber.

        Args:
            stream: The shared stream
            subscriber: The subscriber

        Yields:
            bytes: Chunks of stream data
        """
        try:
            while subscriber.active and stream.is_active:
                try:
                    chunk = subscriber.queue.get(timeout=SUBSCRIBER_TIMEOUT)

                    if chunk is None:
                        # End of stream signal
                        logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... received end signal")
                        break

                    subscriber.last_read = datetime.utcnow()
                    subscriber.bytes_sent += len(chunk)
                    yield chunk

                except Empty:
                    # Timeout - check if stream is still active
                    if not stream.is_active:
                        logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... stream became inactive")
                        break
                    # Otherwise continue waiting

        except GeneratorExit:
            logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... generator closed")
        finally:
            subscriber.active = False

    def _upstream_reader(self, stream: SharedStream, user_agent: str) -> None:
        """
        Background thread that reads from upstream and distributes to subscribers.

        Args:
            stream: The shared stream to read
            user_agent: User agent for the request
        """
        logger.info(f"Upstream reader started for {stream.stream_key}")
        response = None

        try:
            response = requests.get(
                stream.upstream_url,
                stream=True,
                headers={"User-Agent": user_agent},
                timeout=(UPSTREAM_CONNECT_TIMEOUT, UPSTREAM_READ_TIMEOUT),
            )
            response.raise_for_status()

            # Get content type from response
            stream.content_type = response.headers.get(
                "Content-Type",
                "video/mp2t" if stream.format == "ts" else "application/x-mpegURL",
            )

            logger.info(f"Upstream connected for {stream.stream_key}, content_type={stream.content_type}")

            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue

                if not stream.is_active:
                    logger.info(f"Stream {stream.stream_key} marked inactive, stopping reader")
                    break

                stream.bytes_received += len(chunk)
                stream.last_activity = datetime.utcnow()

                # Distribute chunk to all subscribers
                with stream.lock:
                    dead_subscribers = []

                    for sub_id, subscriber in stream.subscribers.items():
                        if not subscriber.active:
                            dead_subscribers.append(sub_id)
                            continue

                        try:
                            # Non-blocking put - if queue is full, subscriber is too slow
                            subscriber.queue.put_nowait(chunk)
                        except Exception:
                            # Queue full - subscriber too slow, mark for removal
                            logger.warning(f"Subscriber {sub_id[:8]}... queue full, dropping")
                            subscriber.active = False
                            dead_subscribers.append(sub_id)

                    # Clean up dead subscribers
                    for sub_id in dead_subscribers:
                        if sub_id in stream.subscribers:
                            del stream.subscribers[sub_id]

                # Check if we still have subscribers
                if not stream.subscribers:
                    logger.info(f"Stream {stream.stream_key} has no subscribers, will close soon")
                    # Don't immediately stop - give a grace period for reconnects
                    # The cleanup loop will handle this

        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on upstream {stream.stream_key}: {e}")
            stream.error = f"Upstream timeout: {e}"
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on upstream {stream.stream_key}: {e}")
            stream.error = f"Connection error: {e}"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            logger.error(f"HTTP error {status} on upstream {stream.stream_key}: {e}")
            stream.error = f"HTTP error: {status}"
        except Exception as e:
            logger.exception(f"Unexpected error on upstream {stream.stream_key}: {e}")
            stream.error = str(e)
        finally:
            stream.is_active = False

            # Signal end of stream to all subscribers
            with stream.lock:
                for subscriber in stream.subscribers.values():
                    try:
                        subscriber.queue.put_nowait(None)  # End signal
                    except Exception:
                        pass
                    subscriber.active = False

            if response:
                response.close()

            logger.info(
                f"Upstream reader ended for {stream.stream_key} "
                f"(bytes: {stream.bytes_received}, error: {stream.error})"
            )

    def _close_stream(self, stream: SharedStream) -> None:
        """Close a stream and clean up resources."""
        logger.info(f"Closing stream {stream.stream_key}")

        stream.is_active = False

        # Signal all subscribers
        with stream.lock:
            for subscriber in stream.subscribers.values():
                try:
                    subscriber.queue.put_nowait(None)
                except Exception:
                    pass
                subscriber.active = False
            stream.subscribers.clear()

        # Remove from active streams
        with self._lock:
            if stream.stream_key in self._streams:
                del self._streams[stream.stream_key]

    def _cleanup_loop(self) -> None:
        """Background loop to clean up idle streams."""
        while not self._shutdown:
            try:
                self._cleanup_idle_streams()
            except Exception as e:
                logger.exception(f"Error in cleanup loop: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(10):
                if self._shutdown:
                    break
                time.sleep(1)

    def _cleanup_idle_streams(self) -> None:
        """Clean up streams with no subscribers."""
        now = datetime.utcnow()

        with self._lock:
            streams_to_close = []

            for stream_key, stream in self._streams.items():
                # Check for streams with no subscribers
                if not stream.subscribers:
                    idle_seconds = (now - stream.last_activity).total_seconds()
                    if idle_seconds > STREAM_IDLE_TIMEOUT:
                        logger.info(f"Stream {stream_key} idle for {idle_seconds:.1f}s, closing")
                        streams_to_close.append(stream)

                # Check for dead streams
                elif not stream.is_active:
                    streams_to_close.append(stream)

            for stream in streams_to_close:
                self._close_stream(stream)

    def release_idle_streams_for_account(
        self, account_id: int, credential_id: Optional[int] = None, max_to_release: int = 1
    ) -> int:
        """
        Release idle streams (with 0 subscribers) for a specific account to free up credentials.

        This is called when a new stream is requested but no credentials are available.
        Releasing idle streams allows the credential to be reused for the new stream.

        Args:
            account_id: The account to release streams for
            credential_id: Optional specific credential ID to target
            max_to_release: Maximum number of streams to release (default 1)

        Returns:
            Number of streams released
        """
        released = 0

        with self._lock:
            # Find idle streams for this account (sorted by last_activity, oldest first)
            idle_streams = []
            for stream in self._streams.values():
                if stream.account_id == account_id and not stream.subscribers and stream.is_active:
                    # If credential_id specified, only target that credential
                    if credential_id is not None and stream.credential_id != credential_id:
                        continue
                    idle_streams.append(stream)

            # Sort by last activity (oldest first - release those first)
            idle_streams.sort(key=lambda s: s.last_activity)

            # Release up to max_to_release streams
            for stream in idle_streams[:max_to_release]:
                logger.info(
                    f"Releasing idle stream {stream.stream_key} to free credential "
                    f"(idle since {stream.last_activity.isoformat()})"
                )
                self._close_stream(stream)
                released += 1

        return released

    def get_idle_stream_count(self, account_id: int) -> int:
        """
        Get count of idle streams (0 subscribers) for an account.

        Args:
            account_id: The account to check

        Returns:
            Number of idle streams
        """
        with self._lock:
            return sum(
                1
                for stream in self._streams.values()
                if stream.account_id == account_id and not stream.subscribers and stream.is_active
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get multiplexer statistics."""
        with self._lock:
            streams_info = []
            total_subscribers = 0

            for stream in self._streams.values():
                sub_count = len(stream.subscribers)
                total_subscribers += sub_count

                streams_info.append(
                    {
                        "stream_key": stream.stream_key,
                        "account_id": stream.account_id,
                        "stream_id": stream.stream_id,
                        "format": stream.format,
                        "subscribers": sub_count,
                        "bytes_received": stream.bytes_received,
                        "is_active": stream.is_active,
                        "started_at": stream.started_at.isoformat(),
                        "error": stream.error,
                    }
                )

            return {
                "active_streams": len(self._streams),
                "total_subscribers": total_subscribers,
                "streams": streams_info,
            }


# Global multiplexer instance
_multiplexer: Optional[StreamMultiplexer] = None


def get_multiplexer() -> StreamMultiplexer:
    """Get or create the global multiplexer instance."""
    global _multiplexer
    if _multiplexer is None:
        _multiplexer = StreamMultiplexer()
        _multiplexer.start()
    return _multiplexer


def shutdown_multiplexer() -> None:
    """Shutdown the global multiplexer."""
    global _multiplexer
    if _multiplexer is not None:
        _multiplexer.stop()
        _multiplexer = None
