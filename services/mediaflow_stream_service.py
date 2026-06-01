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
"""

import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
STREAM_IDLE_TIMEOUT = 30


class _MediaFlowSourceError(Exception):
    """Raised when a single MediaFlow upstream source fails."""


@dataclass
class StreamSubscriber:
    """A client subscribed to a stream."""

    subscriber_id: str
    client_ip: Optional[str]
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    bytes_sent: int = 0
    active: bool = True


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

    # Failover chain: list of (stream_id, upstream_url)
    fallback_sources: List[tuple[str, str]] = field(default_factory=list)
    active_source_index: int = 0
    failover_lock: threading.Lock = field(default_factory=threading.Lock)

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

    This service generates proxy URLs that route streams through MediaFlow Proxy,
    which handles buffering, reconnection, and stream manipulation.

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
                    f"Client {client_ip} joining existing MediaFlow stream {stream_key} "
                    f"({len(stream.subscribers)} existing subscribers)"
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
                    f"Created new MediaFlow stream {stream_key} "
                    f"(source index {active_source_index}, upstream stream {active_stream_id})"
                )
                logger.debug(f"MediaFlow proxy URL: {proxy_url[:100]}...")

                if on_stream_started:
                    on_stream_started(stream)

            # Create subscriber
            subscriber = StreamSubscriber(
                subscriber_id=secrets.token_hex(16),
                client_ip=client_ip,
            )

            with stream.lock:
                stream.subscribers[subscriber.subscriber_id] = subscriber

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
        Generator that yields chunks for a subscriber by proxying through MediaFlow.

        Tries fallback sources in order on connection failure.
        """
        start_index = stream.active_source_index
        last_error: Optional[str] = None

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
            logger.info(
                f"Starting MediaFlow stream for subscriber {subscriber.subscriber_id[:8]}... " f"URL: {url[:100]}..."
            )

            try:
                yielded = yield from self._stream_chunks_from_url(stream, subscriber, url, proxy_base_url)
                if yielded:
                    return
            except _MediaFlowSourceError as e:
                last_error = str(e)
                logger.warning(
                    "MediaFlow source %s failed for %s: %s",
                    source_stream_id,
                    stream.stream_key,
                    last_error,
                )
                continue

        stream.error = last_error or "All stream sources unavailable"
        stream.is_active = False
        subscriber.active = False

    def _stream_chunks_from_url(
        self,
        stream: MediaFlowStream,
        subscriber: StreamSubscriber,
        url: str,
        proxy_base_url: Optional[str],
    ) -> Generator[bytes, None, bool]:
        """Stream from a single MediaFlow/upstream URL. Raises _MediaFlowSourceError on failure."""
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

                if "Content-Type" in response.headers:
                    stream.content_type = response.headers["Content-Type"]

                rewrite_manifest = stream.format == "m3u8" and proxy_base_url and self._mediaflow_available
                chunk_count = 0
                manifest_parts: list[bytes] = []

                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not subscriber.active or not stream.is_active:
                        return True

                    if chunk:
                        chunk_count += 1
                        stream.bytes_received += len(chunk)
                        stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)

                        if rewrite_manifest:
                            manifest_parts.append(chunk)
                            continue

                        subscriber.bytes_sent += len(chunk)
                        yield chunk

                if rewrite_manifest and manifest_parts and proxy_base_url:
                    manifest_bytes = b"".join(manifest_parts)
                    try:
                        manifest_text = manifest_bytes.decode("utf-8")
                        manifest_text = rewrite_hls_manifest(manifest_text, MEDIAFLOW_PROXY_URL, proxy_base_url)
                        manifest_bytes = manifest_text.encode("utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to rewrite HLS manifest, sending original: {e}")

                    subscriber.bytes_sent += len(manifest_bytes)
                    stream.bytes_received = len(manifest_bytes)
                    yield manifest_bytes
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
            logger.info(
                f"Subscriber {subscriber.subscriber_id[:8]}... source stream ended "
                f"({subscriber.bytes_sent} bytes sent)"
            )

    def _close_stream(self, stream: MediaFlowStream, invoke_callback: bool = True) -> None:
        """Close a stream and cleanup resources."""
        stream.is_active = False

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

        logger.info(f"Closed MediaFlow stream {stream.stream_key} " f"(received: {stream.bytes_received} bytes)")

    def _cleanup_loop(self) -> None:
        """Background thread that cleans up idle streams."""
        logger.info("MediaFlow cleanup thread started")
        while not self._shutdown:
            try:
                self._cleanup_idle_streams()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(10):
                if self._shutdown:
                    break
                time.sleep(1)

    def _cleanup_idle_streams(self) -> None:
        """Close streams that have been idle (no subscribers) for too long."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        with self._lock:
            streams_to_close = []

            for stream_key, stream in self._streams.items():
                # Check if stream has no subscribers and has been idle
                if not stream.subscribers and stream.last_subscriber_left_at:
                    idle_seconds = (now - stream.last_subscriber_left_at).total_seconds()
                    if idle_seconds > STREAM_IDLE_TIMEOUT:
                        streams_to_close.append(stream_key)
                        logger.info(f"Stream {stream_key} idle for {idle_seconds:.0f}s, marking for closure")

                # Also close streams that have errors
                if not stream.is_active or stream.error:
                    if stream_key not in streams_to_close:
                        streams_to_close.append(stream_key)
                        logger.info(f"Stream {stream_key} has error or inactive, marking for closure")

            for stream_key in streams_to_close:
                if stream_key in self._streams:
                    stream = self._streams.pop(stream_key)
                    self._close_stream(stream)

    def get_idle_stream_count(self, account_id: int) -> int:
        """MediaFlow has no multiplexer idle release; always report zero idle streams."""
        return 0

    def release_idle_streams_for_account(
        self, account_id: int, credential_id: Optional[int] = None, max_to_release: int = 1
    ) -> int:
        """No-op — credential shortage handling uses other strategies for MediaFlow."""
        return 0


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
