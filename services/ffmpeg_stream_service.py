"""
FFmpeg-based Stream Service - robust stream proxying with proper remuxing

This service uses ffmpeg to handle MPEG-TS stream proxying, which automatically:
- Preserves original stream timestamps for smooth playback (no backward jumps)
- Injects SPS/PPS at every frame via dump_extra=freq=all (enables mid-stream joins)
- Supports multiple subscribers via shared output
- Handles upstream reconnection gracefully

The key insight is that ffmpeg with `-c copy` remuxes without re-encoding,
so it's very fast while still fixing stream container issues.

IMPORTANT: We preserve original timestamps (-copyts, -mpegts_copyts 1) rather than
regenerating them. The previous approach of using +genpts+igndts caused periodic
backward jumps when ffmpeg's generated timestamps drifted from the original stream.

No buffering is needed - ffmpeg's dump_extra ensures decoders can sync at any keyframe.
"""

import logging
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import TYPE_CHECKING, Callable, Dict, Generator, Optional

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# Configuration
CHUNK_SIZE = 65536  # 64KB chunks - matches ffmpeg's typical output buffer
SUBSCRIBER_QUEUE_SIZE = 100  # Max chunks buffered per subscriber (~6.4MB)
SUBSCRIBER_TIMEOUT = 10  # Seconds to wait for a chunk before checking stream status
STREAM_IDLE_TIMEOUT = 30  # Seconds with no subscribers before closing stream


@dataclass
class StreamSubscriber:
    """A client subscribed to a stream."""

    subscriber_id: str
    client_ip: Optional[str]
    queue: "Queue[Optional[bytes]]"
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    bytes_sent: int = 0
    active: bool = True
    ready: bool = False  # Set to True when stream_chunks() starts consuming


@dataclass
class FFmpegStream:
    """A stream being proxied through ffmpeg."""

    stream_key: str
    account_id: int
    stream_id: str
    format: str
    upstream_url: str
    credential_id: Optional[int]
    session_token: str
    user_agent: str = "okhttp/3.14.9"

    # State
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    bytes_received: int = 0
    is_active: bool = True
    error: Optional[str] = None
    content_type: str = "video/mp2t"

    # FFmpeg process
    process: Optional[subprocess.Popen] = None
    reader_thread: Optional[threading.Thread] = None

    # Thread safety
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Subscribers
    subscribers: Dict[str, StreamSubscriber] = field(default_factory=dict)
    last_subscriber_left_at: Optional[datetime] = None

    # Cleanup callback
    on_stream_closed: Optional[Callable[["FFmpegStream"], None]] = None

    def __hash__(self):
        return hash(self.stream_key)


class FFmpegStreamService:
    """
    Manages streams using ffmpeg for proper MPEG-TS handling.

    Usage:
        service = FFmpegStreamService(app=app)
        service.start()

        stream, subscriber = service.subscribe(...)
        for chunk in service.stream_chunks(stream, subscriber):
            yield chunk
        service.unsubscribe(stream, subscriber)
    """

    def __init__(self, app: Optional["Flask"] = None):
        self._streams: Dict[str, FFmpegStream] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
        self._app = app

    def start(self):
        """Start the background cleanup thread."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._shutdown = False
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, name="FFmpegStreamCleanup", daemon=True)
            self._cleanup_thread.start()
            logger.info("FFmpegStreamService cleanup thread started")

    def stop(self):
        """Stop all streams and cleanup."""
        self._shutdown = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

        with self._lock:
            for stream in list(self._streams.values()):
                self._close_stream(stream)
            self._streams.clear()

        logger.info("FFmpegStreamService stopped")

    def _get_stream_key(self, account_id: int, stream_id: str, format: str) -> str:
        return f"{account_id}:{stream_id}:{format}"

    def get_active_stream(self, account_id: int, stream_id: str, format: str) -> Optional[FFmpegStream]:
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
        on_stream_started: Optional[Callable[[FFmpegStream], None]] = None,
        on_stream_closed: Optional[Callable[[FFmpegStream], None]] = None,
    ) -> tuple[FFmpegStream, StreamSubscriber]:
        """Subscribe to a stream, creating it if needed."""
        stream_key = self._get_stream_key(account_id, stream_id, format)

        with self._lock:
            stream = self._streams.get(stream_key)

            if stream and stream.is_active:
                logger.info(
                    f"Client {client_ip} joining existing ffmpeg stream {stream_key} "
                    f"({len(stream.subscribers)} existing subscribers)"
                )
            else:
                # Create new stream with ffmpeg
                stream = FFmpegStream(
                    stream_key=stream_key,
                    account_id=account_id,
                    stream_id=stream_id,
                    format=format,
                    upstream_url=upstream_url,
                    credential_id=credential_id,
                    session_token=session_token,
                    user_agent=user_agent,
                    on_stream_closed=on_stream_closed,
                )
                self._streams[stream_key] = stream

                # Start ffmpeg process
                self._start_ffmpeg(stream)

                logger.info(f"Created new ffmpeg stream {stream_key}")

                if on_stream_started:
                    on_stream_started(stream)

            # Create subscriber
            subscriber = StreamSubscriber(
                subscriber_id=secrets.token_hex(16),
                client_ip=client_ip,
                queue=Queue(maxsize=SUBSCRIBER_QUEUE_SIZE),
            )

            with stream.lock:
                stream.subscribers[subscriber.subscriber_id] = subscriber

            logger.info(
                f"Subscriber {subscriber.subscriber_id[:8]}... joined ffmpeg stream {stream_key} "
                f"(total: {len(stream.subscribers)})"
            )

            return stream, subscriber

    def unsubscribe(self, stream: FFmpegStream, subscriber: StreamSubscriber) -> None:
        """Unsubscribe from a stream."""
        with stream.lock:
            subscriber.active = False
            if subscriber.subscriber_id in stream.subscribers:
                del stream.subscribers[subscriber.subscriber_id]

            # Track when last subscriber left for idle detection
            if not stream.subscribers:
                stream.last_subscriber_left_at = datetime.now(timezone.utc).replace(tzinfo=None)

        logger.info(
            f"Subscriber {subscriber.subscriber_id[:8]}... left ffmpeg stream {stream.stream_key} "
            f"(remaining: {len(stream.subscribers)}, bytes: {subscriber.bytes_sent})"
        )

    def stream_chunks(
        self,
        stream: FFmpegStream,
        subscriber: StreamSubscriber,
        proxy_base_url: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """Generator that yields chunks for a subscriber."""
        # Mark subscriber as ready - now the reader thread can send data directly
        subscriber.ready = True
        logger.info(f"Subscriber {subscriber.subscriber_id[:8]}... marked ready")

        try:
            while subscriber.active and stream.is_active:
                try:
                    chunk = subscriber.queue.get(timeout=SUBSCRIBER_TIMEOUT)

                    if chunk is None:
                        logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... received end signal")
                        break

                    subscriber.bytes_sent += len(chunk)
                    yield chunk

                except Empty:
                    if not stream.is_active:
                        logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... stream became inactive")
                        break
                    # Otherwise continue waiting

        except GeneratorExit:
            logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... generator closed")
        finally:
            subscriber.active = False

    def _start_ffmpeg(self, stream: FFmpegStream) -> None:
        """Start ffmpeg process for a stream."""
        # Build ffmpeg command
        # -i: Input URL
        # -c copy: Copy streams without re-encoding (fast, preserves quality)
        # -bsf:v dump_extra=freq=all: Inject SPS/PPS into every frame for H.264
        #   This ensures decoders can start at any keyframe without needing
        #   initialization data from the stream start
        # -f mpegts: Output format
        #
        # TIMESTAMP HANDLING (critical for avoiding backward jumps):
        # We preserve original timestamps from the source stream. The previous
        # approach of regenerating timestamps with +genpts+igndts caused periodic
        # backward jumps when ffmpeg's generated timestamps drifted from the
        # original stream timing.
        #
        # -mpegts_copyts 1: Copy timestamps from input to output
        # -fflags +discardcorrupt: Only discard corrupt packets, don't mess with timestamps
        # -copyts: Preserve timestamps during copy
        #
        # Reconnect handling: We use reconnect options with short delays to handle
        # temporary network issues while keeping the stream alive. The -rw_timeout
        # controls individual read/write operations, while -reconnect_* handle
        # connection drops.

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            # HTTP input options (must come before -i)
            "-user_agent",
            stream.user_agent,
            "-headers",
            "Accept: */*\r\nConnection: keep-alive\r\n",
            # Network timeout options
            "-rw_timeout",
            "30000000",  # 30 seconds for read/write operations (microseconds)
            "-timeout",
            "30000000",  # 30 seconds connection timeout (microseconds)
            # Reconnection options for robustness
            "-reconnect",
            "1",  # Enable reconnection
            "-reconnect_streamed",
            "1",  # Reconnect even for streamed content
            "-reconnect_delay_max",
            "5",  # Max 5 seconds between reconnect attempts
            "-reconnect_on_network_error",
            "1",  # Reconnect on network errors
            "-reconnect_on_http_error",
            "5xx",  # Reconnect on 5xx server errors
            # TCP options for better network handling
            "-tcp_nodelay",
            "1",  # Disable Nagle's algorithm for lower latency
            "-i",
            stream.upstream_url,
            # Input processing options (after -i)
            "-fflags",
            "+discardcorrupt",  # Only discard corrupt packets, preserve timestamps
            "-copyts",  # Preserve timestamps during stream copy
            "-c",
            "copy",
            "-bsf:v",
            "dump_extra=freq=all",
            "-f",
            "mpegts",
            "-mpegts_copyts",
            "1",  # Copy timestamps from input (critical for live streams)
            "-avioflags",
            "direct",
            "-flush_packets",
            "1",
            "-mpegts_flags",
            "+pat_pmt_at_frames",  # Still insert PAT/PMT at keyframes for mid-stream joins
            "pipe:1",
        ]

        logger.info(f"Starting ffmpeg for {stream.stream_key}")
        logger.debug(f"FFmpeg command: {' '.join(cmd[:5])}... (URL hidden)")

        try:
            stream.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=CHUNK_SIZE,
            )

            # Start reader thread
            stream.reader_thread = threading.Thread(
                target=self._ffmpeg_reader,
                args=(stream,),
                name=f"FFmpeg-{stream.stream_key}",
                daemon=True,
            )
            stream.reader_thread.start()

            # Start error monitor thread
            threading.Thread(
                target=self._ffmpeg_error_monitor,
                args=(stream,),
                name=f"FFmpegErr-{stream.stream_key}",
                daemon=True,
            ).start()

        except Exception as e:
            logger.error(f"Failed to start ffmpeg for {stream.stream_key}: {e}")
            stream.error = str(e)
            stream.is_active = False

    def _ffmpeg_reader(self, stream: FFmpegStream) -> None:
        """Read from ffmpeg stdout and distribute to subscribers.

        Data is only sent to ready subscribers. Any data received before a subscriber
        is ready is discarded - this is fine for live streams since ffmpeg's
        dump_extra=freq=all ensures decoders can sync at the next keyframe.
        """
        logger.info(f"FFmpeg reader started for {stream.stream_key}")

        chunks_read = 0
        chunks_distributed = 0

        try:
            logger.debug(
                f"Reader {stream.stream_key}: Entering main loop, is_active={stream.is_active}, process={stream.process is not None}"
            )
            while stream.is_active and stream.process and stream.process.poll() is None:
                if stream.process.stdout is None:
                    logger.error(f"FFmpeg {stream.stream_key}: stdout is None")
                    break

                chunk = stream.process.stdout.read(CHUNK_SIZE)

                if not chunk:
                    logger.info(f"FFmpeg stream {stream.stream_key} ended (no more data)")
                    break

                chunks_read += 1
                stream.bytes_received += len(chunk)
                stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)

                # Distribute to all subscribers
                with stream.lock:
                    # Check if any subscriber is ready
                    any_ready = any(s.ready and s.active for s in stream.subscribers.values())

                    if not any_ready:
                        # No subscribers ready yet - discard data (live stream, they'll sync at next keyframe)
                        continue

                    chunks_distributed += 1
                    dead_subscribers = []
                    for sub_id, subscriber in stream.subscribers.items():
                        if not subscriber.active:
                            dead_subscribers.append(sub_id)
                            continue

                        # Skip subscribers that aren't ready yet (Flask hasn't started consuming)
                        if not subscriber.ready:
                            continue

                        try:
                            # Use put_nowait and drop chunks if queue is full
                            # This prevents blocking and allows slow subscribers to catch up
                            subscriber.queue.put_nowait(chunk)
                        except Exception:
                            # Queue full - drop this chunk for this subscriber
                            # Don't kill the subscriber, just skip this chunk
                            # They may be temporarily slow but can catch up
                            pass

                    for sub_id in dead_subscribers:
                        if sub_id in stream.subscribers:
                            del stream.subscribers[sub_id]

                # Log periodically
                if stream.bytes_received % (10 * 1024 * 1024) < CHUNK_SIZE:  # Every ~10MB
                    logger.debug(
                        f"Stream {stream.stream_key}: {stream.bytes_received // 1024 // 1024}MB received, "
                        f"{len(stream.subscribers)} subscribers"
                    )

        except Exception as e:
            logger.error(f"FFmpeg reader error for {stream.stream_key}: {e}")
            stream.error = str(e)
        finally:
            stream.is_active = False

            # Signal end to all subscribers
            with stream.lock:
                for subscriber in stream.subscribers.values():
                    try:
                        subscriber.queue.put_nowait(None)
                    except Exception:
                        pass
                    subscriber.active = False

            logger.info(
                f"FFmpeg reader ended for {stream.stream_key} "
                f"(bytes: {stream.bytes_received}, error: {stream.error})"
            )

    def _ffmpeg_error_monitor(self, stream: FFmpegStream) -> None:
        """Monitor ffmpeg stderr for errors."""
        if not stream.process or not stream.process.stderr:
            return

        # Patterns for non-critical errors that are normal for live streams
        # These occur when joining mid-stream before decoder has full context
        non_critical_patterns = [
            "decode_slice_header error",  # Normal when joining mid-GOP
            "non-existing pps",  # Missing parameter sets (will be sent at next keyframe)
            "no frame!",  # Decoder waiting for keyframe
            "concealing errors",  # FFmpeg auto-recovering from errors
            "missing picture",  # Gap in stream (common with IPTV)
        ]

        try:
            for line in stream.process.stderr:
                line = line.decode("utf-8", errors="replace").strip()
                if line:
                    # Check if this is a non-critical error
                    is_non_critical = any(pattern in line.lower() for pattern in non_critical_patterns)

                    # Log ffmpeg messages at appropriate levels
                    if is_non_critical:
                        # Log non-critical errors at DEBUG level to reduce noise
                        logger.debug(f"FFmpeg {stream.stream_key}: {line}")
                    elif "error" in line.lower():
                        logger.error(f"FFmpeg {stream.stream_key}: {line}")
                    elif "warning" in line.lower():
                        logger.warning(f"FFmpeg {stream.stream_key}: {line}")
                    else:
                        logger.debug(f"FFmpeg {stream.stream_key}: {line}")
        except Exception as e:
            logger.debug(f"FFmpeg error monitor ended for {stream.stream_key}: {e}")

    def _close_stream(self, stream: FFmpegStream) -> None:
        """Close a stream and cleanup."""
        logger.info(f"Closing ffmpeg stream {stream.stream_key}")

        stream.is_active = False

        # Kill ffmpeg process
        if stream.process:
            try:
                stream.process.terminate()
                try:
                    stream.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    stream.process.kill()
            except Exception as e:
                logger.debug(f"Error terminating ffmpeg: {e}")

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

        # Trigger cleanup callback (e.g., to release connection)
        if stream.on_stream_closed:
            try:
                # Wrap in app context if available (needed for database access)
                if self._app:
                    with self._app.app_context():
                        stream.on_stream_closed(stream)
                else:
                    stream.on_stream_closed(stream)
            except Exception as e:
                logger.error(f"Error in stream close callback: {e}")

    def _cleanup_loop(self) -> None:
        """Background loop to clean up idle streams."""
        while not self._shutdown:
            try:
                self._cleanup_idle_streams()
            except Exception as e:
                logger.exception(f"Error in cleanup loop: {e}")

            for _ in range(10):
                if self._shutdown:
                    break
                time.sleep(1)

    def _cleanup_idle_streams(self) -> None:
        """Clean up streams with no subscribers."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        with self._lock:
            streams_to_close = []

            for stream_key, stream in self._streams.items():
                if not stream.subscribers:
                    # Use last_subscriber_left_at if available, otherwise fall back to last_activity
                    # This ensures streams close even if ffmpeg is still trying to reconnect
                    idle_time = stream.last_subscriber_left_at or stream.last_activity
                    idle_seconds = (now - idle_time).total_seconds()
                    if idle_seconds > STREAM_IDLE_TIMEOUT:
                        logger.info(f"FFmpeg stream {stream_key} idle for {idle_seconds:.1f}s, closing")
                        streams_to_close.append(stream)
                elif not stream.is_active:
                    streams_to_close.append(stream)

            for stream in streams_to_close:
                self._close_stream(stream)

    # Compatibility methods to match StreamMultiplexer interface
    def get_idle_stream_count(self, account_id: int) -> int:
        """Get count of idle streams for an account."""
        count = 0
        with self._lock:
            for stream in self._streams.values():
                if stream.account_id == account_id and not stream.subscribers:
                    count += 1
        return count

    def release_idle_streams_for_account(
        self, account_id: int, credential_id: Optional[int] = None, max_to_release: int = 1
    ) -> int:
        """Release idle streams for an account."""
        released = 0
        with self._lock:
            for stream in list(self._streams.values()):
                if released >= max_to_release:
                    break
                if stream.account_id == account_id and not stream.subscribers:
                    if credential_id is None or stream.credential_id == credential_id:
                        self._close_stream(stream)
                        released += 1
        return released

    def get_stats(self) -> dict:
        """Get service statistics."""
        with self._lock:
            total_subscribers = sum(len(s.subscribers) for s in self._streams.values())
            total_bytes = sum(s.bytes_received for s in self._streams.values())
            return {
                "active_streams": len(self._streams),
                "total_subscribers": total_subscribers,
                "total_bytes_received": total_bytes,
                "streams": [
                    {
                        "key": s.stream_key,
                        "subscribers": len(s.subscribers),
                        "bytes_received": s.bytes_received,
                        "is_active": s.is_active,
                    }
                    for s in self._streams.values()
                ],
            }


# Global instance
_ffmpeg_service: Optional[FFmpegStreamService] = None


def get_ffmpeg_service(app: Optional["Flask"] = None) -> FFmpegStreamService:
    """Get the global FFmpegStreamService instance.

    Args:
        app: Flask app instance (optional, but required for database operations in callbacks)
    """
    global _ffmpeg_service
    if _ffmpeg_service is None:
        _ffmpeg_service = FFmpegStreamService(app=app)
        _ffmpeg_service.start()
    return _ffmpeg_service
