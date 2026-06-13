"""
MediaFlow Proxy-based Stream Service - robust HLS/MPEG-TS proxying

This service uses MediaFlow Proxy (https://github.com/mhdzumair/mediaflow-proxy)
for stream proxying, which provides:
- HLS pre-buffering for smoother playback
- Memory-managed caching
- Real-time manifest manipulation
- Proper handling of IPTV M3U streams

MediaFlow Proxy runs as a separate service and we generate proxy URLs that
route through it. This approach:
1. Offloads stream handling to a dedicated, optimized proxy
2. Provides better buffering than direct ffmpeg piping
3. Supports both HLS and direct TS streams

Multiplexing model (mirrors FFmpegStreamService):
A single background reader thread per stream key pulls from MediaFlow/upstream
exactly once and fans the bytes out to every subscriber's queue. Additional
clients watching the same channel share that one upstream connection instead of
each opening their own, conserving provider connection slots.
"""

import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import TYPE_CHECKING, Callable, Dict, Generator, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from services.hls_manifest_service import rewrite_hls_manifest

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# Configuration from environment
MEDIAFLOW_PROXY_URL = os.environ.get("MEDIAFLOW_PROXY_URL", "http://localhost:8888")
MEDIAFLOW_API_PASSWORD = os.environ.get("MEDIAFLOW_API_PASSWORD", "")

# Streaming configuration
CHUNK_SIZE = 65536  # 64KB chunks
SUBSCRIBER_QUEUE_SIZE = 100
SUBSCRIBER_TIMEOUT = 10
# Seconds with no subscribers before closing the shared upstream. Configurable
# via env; default 0 closes immediately on the last subscriber leaving so the
# credential slot frees right away (see idle-timeout-policy).
STREAM_IDLE_TIMEOUT = int(os.environ.get("STREAM_IDLE_TIMEOUT", "0"))


class _MediaFlowSourceError(Exception):
    """Raised when a single MediaFlow upstream source fails."""


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
class MediaFlowStream:
    """A stream being proxied through MediaFlow Proxy."""

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

    # MediaFlow proxy URL (constructed from upstream)
    proxy_url: Optional[str] = None
    # Base URL clients use to reach this proxy (for HLS manifest rewriting).
    proxy_base_url: Optional[str] = None

    # Failover chain: list of (stream_id, upstream_url)
    fallback_sources: List[tuple[str, str]] = field(default_factory=list)
    active_source_index: int = 0
    failover_lock: threading.Lock = field(default_factory=threading.Lock)

    # Single shared upstream reader
    reader_thread: Optional[threading.Thread] = None
    reader_started: bool = False

    # Thread safety
    lock: threading.Lock = field(default_factory=threading.Lock)

    # Subscribers
    subscribers: Dict[str, StreamSubscriber] = field(default_factory=dict)
    last_subscriber_left_at: Optional[datetime] = None

    # Cleanup callback
    on_stream_closed: Optional[Callable[["MediaFlowStream"], None]] = None

    def __hash__(self):
        return hash(self.stream_key)


class MediaFlowStreamService:
    """
    Manages streams using MediaFlow Proxy for HLS/TS handling.

    A single reader thread per stream pulls bytes from MediaFlow once and fans
    them out to all subscribers, so multiple clients on the same channel share
    one upstream connection.

    Usage:
        service = MediaFlowStreamService(app=app)
        service.start()

        stream, subscriber = service.subscribe(...)
        for chunk in service.stream_chunks(stream, subscriber):
            yield chunk
        service.unsubscribe(stream, subscriber)
    """

    def __init__(self, app: Optional["Flask"] = None):
        self._streams: Dict[str, MediaFlowStream] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
        self._app = app

        # Verify MediaFlow Proxy is reachable
        self._mediaflow_available = self._check_mediaflow_available()
        if not self._mediaflow_available:
            logger.warning(
                f"MediaFlow Proxy not available at {MEDIAFLOW_PROXY_URL}. "
                "Streams will be proxied directly (without pre-buffering)."
            )

    def _check_mediaflow_available(self) -> bool:
        """Check if MediaFlow Proxy is running and accessible."""
        try:
            requests.get(f"{MEDIAFLOW_PROXY_URL}/", timeout=5)
            logger.info(f"MediaFlow Proxy available at {MEDIAFLOW_PROXY_URL}")
            return True
        except Exception as e:
            logger.warning(f"MediaFlow Proxy check failed: {e}")
            return False

    def start(self):
        """Start the background cleanup thread."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._shutdown = False
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, name="MediaFlowStreamCleanup", daemon=True
            )
            self._cleanup_thread.start()
            logger.info("MediaFlowStreamService cleanup thread started")

    def stop(self):
        """Stop all streams and cleanup."""
        self._shutdown = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)

        with self._lock:
            for stream in list(self._streams.values()):
                self._close_stream(stream)
            self._streams.clear()

        logger.info("MediaFlowStreamService stopped")

    def _get_stream_key(self, account_id: int, stream_id: str, format: str) -> str:
        return f"{account_id}:{stream_id}:{format}"

    def get_active_stream(self, account_id: int, stream_id: str, format: str) -> Optional[MediaFlowStream]:
        """Check if a stream is already active."""
        stream_key = self._get_stream_key(account_id, stream_id, format)
        with self._lock:
            stream = self._streams.get(stream_key)
            if stream and stream.is_active:
                return stream
            return None

    def _build_mediaflow_url(self, upstream_url: str, user_agent: str, format: str) -> str:
        """
        Build a MediaFlow Proxy URL for the upstream stream.

        For HLS (.m3u8), we use the HLS manifest endpoint.
        For TS streams, we use the generic stream endpoint.
        """
        if not self._mediaflow_available:
            # Fall back to direct URL if MediaFlow is not available
            return upstream_url

        # Build query parameters
        params = {
            "d": upstream_url,  # destination URL
            "h_user-agent": user_agent,
        }

        if MEDIAFLOW_API_PASSWORD:
            params["api_password"] = MEDIAFLOW_API_PASSWORD

        # Choose endpoint based on format
        if format == "m3u8":
            # HLS stream - use manifest endpoint with pre-buffering
            endpoint = "/proxy/hls/manifest.m3u8"
            # Force playlist proxy for IPTV streams
            params["force_playlist_proxy"] = "true"
        else:
            # TS stream - use generic stream endpoint
            endpoint = "/proxy/stream"

        proxy_url = f"{MEDIAFLOW_PROXY_URL}{endpoint}?{urlencode(params)}"
        return proxy_url

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
        on_stream_started: Optional[Callable[[MediaFlowStream], None]] = None,
        on_stream_closed: Optional[Callable[[MediaFlowStream], None]] = None,
        fallback_sources: Optional[List[Tuple[str, str]]] = None,
        active_source_index: int = 0,
    ) -> tuple[MediaFlowStream, StreamSubscriber]:
        """Subscribe to a stream, creating it if needed."""
        stream_key = self._get_stream_key(account_id, stream_id, format)
        chain = fallback_sources or [(stream_id, upstream_url)]
        if active_source_index >= len(chain):
            active_source_index = 0
        active_stream_id, active_url = chain[active_source_index]
        proxy_url = self._build_mediaflow_url(active_url, user_agent, format)

        with self._lock:
            stream = self._streams.get(stream_key)

            if stream and stream.is_active:
                logger.info(
                    "stream_join backend=mediaflow stream_key=%s worker_pid=%s credential_id=%s "
                    "subscriber_count=%s client=%s",
                    stream_key,
                    os.getpid(),
                    stream.credential_id,
                    len(stream.subscribers),
                    client_ip,
                )
            else:
                if stream and not stream.is_active:
                    self._close_stream(stream, invoke_callback=False)
                    del self._streams[stream_key]

                content_type = "application/vnd.apple.mpegurl" if format == "m3u8" else "video/mp2t"

                stream = MediaFlowStream(
                    stream_key=stream_key,
                    account_id=account_id,
                    stream_id=stream_id,
                    format=format,
                    upstream_url=active_url,
                    proxy_url=proxy_url,
                    credential_id=credential_id,
                    session_token=session_token,
                    user_agent=user_agent,
                    content_type=content_type,
                    fallback_sources=list(chain),
                    active_source_index=active_source_index,
                    on_stream_closed=on_stream_closed,
                )
                self._streams[stream_key] = stream

                logger.info(
                    "stream_create backend=mediaflow stream_key=%s worker_pid=%s credential_id=%s "
                    "source_index=%s upstream_stream=%s client=%s",
                    stream_key,
                    os.getpid(),
                    credential_id,
                    active_source_index,
                    active_stream_id,
                    client_ip,
                )
                logger.debug(f"MediaFlow proxy URL: {proxy_url[:100]}...")

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
                stream.last_subscriber_left_at = None

            logger.info(
                f"Subscriber {subscriber.subscriber_id[:8]}... joined MediaFlow stream {stream_key} "
                f"(total: {len(stream.subscribers)})"
            )

            return stream, subscriber

    def unsubscribe(self, stream: MediaFlowStream, subscriber: StreamSubscriber) -> None:
        """Unsubscribe from a stream."""
        with stream.lock:
            subscriber.active = False
            if subscriber.subscriber_id in stream.subscribers:
                del stream.subscribers[subscriber.subscriber_id]

            # Track when last subscriber left for idle detection
            if not stream.subscribers:
                stream.last_subscriber_left_at = datetime.now(timezone.utc).replace(tzinfo=None)

        logger.info(
            f"Subscriber {subscriber.subscriber_id[:8]}... left MediaFlow stream {stream.stream_key} "
            f"(remaining: {len(stream.subscribers)}, bytes: {subscriber.bytes_sent})"
        )

    def stream_chunks(
        self,
        stream: MediaFlowStream,
        subscriber: StreamSubscriber,
        proxy_base_url: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        """
        Yield chunks for a subscriber by draining its queue.

        The shared reader thread (started on the first subscriber) performs the
        single upstream pull and pushes bytes into every subscriber's queue.
        """
        # Mark ready before starting the reader so the first subscriber never
        # misses the opening bytes.
        subscriber.ready = True
        self._ensure_reader_started(stream, proxy_base_url)

        try:
            while subscriber.active:
                try:
                    chunk = subscriber.queue.get(timeout=SUBSCRIBER_TIMEOUT)
                    if chunk is None:
                        logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... received end signal")
                        break
                    subscriber.bytes_sent += len(chunk)
                    yield chunk
                except Empty:
                    # Drain any buffered chunks first; only stop once the queue is
                    # empty AND the shared reader has gone inactive.
                    if not stream.is_active:
                        break
                    # Otherwise keep waiting for the next chunk
        except GeneratorExit:
            logger.debug(f"Subscriber {subscriber.subscriber_id[:8]}... generator closed")
        finally:
            subscriber.active = False

    def _ensure_reader_started(self, stream: MediaFlowStream, proxy_base_url: Optional[str]) -> None:
        """Start the single shared upstream reader thread exactly once."""
        with stream.lock:
            if proxy_base_url and not stream.proxy_base_url:
                stream.proxy_base_url = proxy_base_url
            if stream.reader_started:
                return
            stream.reader_started = True

        thread = threading.Thread(
            target=self._reader_loop,
            args=(stream,),
            name=f"MediaFlow-{stream.stream_key}",
            daemon=True,
        )
        stream.reader_thread = thread
        thread.start()

    def _reader_loop(self, stream: MediaFlowStream) -> None:
        """Pull from the upstream once and fan bytes out to all subscribers."""
        start_index = stream.active_source_index
        last_error: Optional[str] = None
        success = False

        for source_index in range(start_index, len(stream.fallback_sources)):
            source_stream_id, upstream_url = stream.fallback_sources[source_index]
            if source_index != start_index:
                with stream.failover_lock:
                    stream.active_source_index = source_index
                    stream.upstream_url = upstream_url
                    stream.proxy_url = self._build_mediaflow_url(upstream_url, stream.user_agent, stream.format)
                    logger.info(
                        "MediaFlow stream %s failing over to source %s (index %s)",
                        stream.stream_key,
                        source_stream_id,
                        source_index,
                    )

            url = stream.proxy_url or upstream_url
            logger.info(f"MediaFlow reader pulling {stream.stream_key} from {url[:100]}...")

            try:
                if self._pull_source(stream, url):
                    success = True
                    break
            except _MediaFlowSourceError as e:
                last_error = str(e)
                logger.warning(
                    "MediaFlow source %s failed for %s: %s",
                    source_stream_id,
                    stream.stream_key,
                    last_error,
                )
                continue

        if not success:
            stream.error = last_error or "All stream sources unavailable"

        stream.is_active = False
        self._signal_end(stream)
        logger.info(
            "stream_reader_end backend=mediaflow stream_key=%s bytes=%s error=%s",
            stream.stream_key,
            stream.bytes_received,
            stream.error,
        )

    @staticmethod
    def _is_placeholder_response(stream: MediaFlowStream, response_headers) -> bool:
        """Heuristic: a live MPEG-TS stream is chunked with no fixed length.

        A response carrying a fixed ``Content-Length`` together with
        ``Accept-Ranges: bytes`` on a non-HLS request is almost certainly a
        static placeholder file (the provider's "channel unavailable" clip)
        rather than a live stream, so it should trigger failover.
        """
        if stream.format == "m3u8":
            return False
        has_length = "Content-Length" in response_headers
        accepts_ranges = response_headers.get("Accept-Ranges", "").lower() == "bytes"
        return has_length and accepts_ranges

    def _pull_source(self, stream: MediaFlowStream, url: str) -> bool:
        """Pull from a single MediaFlow/upstream URL, fanning out to subscribers.

        Returns True when the source produced data (or completed a manifest).
        Raises _MediaFlowSourceError when the source should be failed over.
        """
        headers = {
            "User-Agent": stream.user_agent,
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        try:
            with requests.get(url, headers=headers, stream=True, timeout=(30, 120), allow_redirects=True) as response:
                logger.info(f"MediaFlow response status: {response.status_code}, headers: {dict(response.headers)}")

                if response.status_code != 200:
                    raise _MediaFlowSourceError(f"Upstream returned {response.status_code}")

                if self._is_placeholder_response(stream, response.headers):
                    logger.warning(
                        "upstream_placeholder backend=mediaflow stream_key=%s content_length=%s "
                        "last_modified=%s content_type=%s",
                        stream.stream_key,
                        response.headers.get("Content-Length"),
                        response.headers.get("Last-Modified"),
                        response.headers.get("Content-Type"),
                    )
                    raise _MediaFlowSourceError("upstream_placeholder: static file served instead of live stream")

                if "Content-Type" in response.headers:
                    stream.content_type = response.headers["Content-Type"]

                rewrite_manifest = stream.format == "m3u8" and stream.proxy_base_url and self._mediaflow_available
                chunk_count = 0
                manifest_parts: list[bytes] = []

                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not stream.is_active:
                        return True

                    if chunk:
                        chunk_count += 1
                        stream.bytes_received += len(chunk)
                        stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)

                        if rewrite_manifest:
                            manifest_parts.append(chunk)
                            continue

                        self._distribute(stream, chunk)

                if rewrite_manifest and manifest_parts and stream.proxy_base_url:
                    manifest_bytes = b"".join(manifest_parts)
                    try:
                        manifest_text = manifest_bytes.decode("utf-8")
                        manifest_text = rewrite_hls_manifest(manifest_text, MEDIAFLOW_PROXY_URL, stream.proxy_base_url)
                        manifest_bytes = manifest_text.encode("utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to rewrite HLS manifest, sending original: {e}")

                    stream.bytes_received = len(manifest_bytes)
                    self._distribute(stream, manifest_bytes)
                    return True

                if chunk_count == 0:
                    raise _MediaFlowSourceError("No data received from upstream")

                return True

        except _MediaFlowSourceError:
            raise
        except requests.exceptions.Timeout as e:
            raise _MediaFlowSourceError(f"Timeout: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise _MediaFlowSourceError(f"Connection error: {e}") from e
        except Exception as e:
            raise _MediaFlowSourceError(str(e)) from e
        finally:
            logger.info(f"MediaFlow source stream ended for {stream.stream_key} ({stream.bytes_received} bytes)")

    def _distribute(self, stream: MediaFlowStream, chunk: bytes) -> None:
        """Push a chunk to every ready subscriber, dropping for slow ones."""
        with stream.lock:
            any_ready = any(s.ready and s.active for s in stream.subscribers.values())
            if not any_ready:
                # No subscriber consuming yet - drop (live stream resyncs at next segment)
                return

            dead_subscribers = []
            for sub_id, subscriber in stream.subscribers.items():
                if not subscriber.active:
                    dead_subscribers.append(sub_id)
                    continue
                if not subscriber.ready:
                    continue
                try:
                    subscriber.queue.put_nowait(chunk)
                except Exception:
                    # Queue full - drop this chunk for this subscriber; they catch up
                    pass

            for sub_id in dead_subscribers:
                stream.subscribers.pop(sub_id, None)

    def _signal_end(self, stream: MediaFlowStream) -> None:
        """Signal end-of-stream to all subscribers so their generators finish.

        We only enqueue the ``None`` sentinel here; we deliberately do not flip
        ``subscriber.active`` so a consumer that has not yet entered its drain
        loop still drains any buffered chunks before seeing the sentinel.
        """
        with stream.lock:
            for subscriber in stream.subscribers.values():
                try:
                    subscriber.queue.put_nowait(None)
                except Exception:
                    pass

    def _close_stream(self, stream: MediaFlowStream, invoke_callback: bool = True, reason: str = "closed") -> None:
        """Close a stream and cleanup resources."""
        stream.is_active = False
        self._signal_end(stream)

        # Call cleanup callback
        if invoke_callback and stream.on_stream_closed:
            try:
                if self._app:
                    with self._app.app_context():
                        stream.on_stream_closed(stream)
                else:
                    stream.on_stream_closed(stream)
            except Exception as e:
                logger.error(f"Error in stream closed callback: {e}")

        logger.info(
            "stream_close backend=mediaflow stream_key=%s worker_pid=%s reason=%s subscriber_count=%s bytes=%s",
            stream.stream_key,
            os.getpid(),
            reason,
            len(stream.subscribers),
            stream.bytes_received,
        )

    def _cleanup_loop(self) -> None:
        """Background thread that cleans up idle streams."""
        logger.info("MediaFlow cleanup thread started")
        while not self._shutdown:
            try:
                self._cleanup_idle_streams()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

            # Sleep in small increments to allow quick shutdown (~1s between cleanups)
            for _ in range(10):
                if self._shutdown:
                    break
                time.sleep(0.1)

    def _cleanup_idle_streams(self) -> None:
        """Close streams that have no subscribers or have errored out."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        with self._lock:
            streams_to_close: list[tuple[str, str]] = []

            for stream_key, stream in self._streams.items():
                # Close streams whose last subscriber has left.
                if not stream.subscribers and stream.last_subscriber_left_at:
                    idle_seconds = (now - stream.last_subscriber_left_at).total_seconds()
                    if idle_seconds >= STREAM_IDLE_TIMEOUT:
                        streams_to_close.append((stream_key, "idle"))
                        continue

                # Also close streams that have errored or gone inactive.
                if not stream.is_active or stream.error:
                    streams_to_close.append((stream_key, "upstream_end" if stream.error else "inactive"))

            for stream_key, reason in streams_to_close:
                closing_stream = self._streams.pop(stream_key, None)
                if closing_stream is not None:
                    self._close_stream(closing_stream, reason=reason)

    def get_idle_stream_count(self, account_id: int) -> int:
        """MediaFlow has no multiplexer idle release; always report zero idle streams."""
        return 0

    def release_idle_streams_for_account(
        self, account_id: int, credential_id: Optional[int] = None, max_to_release: int = 1
    ) -> int:
        """Release idle (subscriber-less) streams to free a credential slot."""
        released = 0
        with self._lock:
            for stream in list(self._streams.values()):
                if released >= max_to_release:
                    break
                if stream.account_id == account_id and not stream.subscribers:
                    if credential_id is None or stream.credential_id == credential_id:
                        self._streams.pop(stream.stream_key, None)
                        self._close_stream(stream, reason="released")
                        released += 1
        return released

    def get_stats(self) -> dict:
        """Get service statistics (shape matches FFmpegStreamService.get_stats)."""
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
_mediaflow_service: Optional[MediaFlowStreamService] = None


def get_mediaflow_service(app: Optional["Flask"] = None) -> MediaFlowStreamService:
    """Get the global MediaFlowStreamService instance.

    Args:
        app: Flask app instance (optional, but required for database operations in callbacks)
    """
    global _mediaflow_service
    if _mediaflow_service is None:
        _mediaflow_service = MediaFlowStreamService(app=app)
        _mediaflow_service.start()
    return _mediaflow_service
