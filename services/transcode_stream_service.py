"""
FFmpeg transcode stream service - per-profile hardware/software encode to MPEG-TS.

Mirrors the subscriber fan-out model of MediaFlowStreamService but runs FFmpeg with
encode settings from TranscodeProfile instead of passthrough remux.
"""

import logging
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import TYPE_CHECKING, Callable, Dict, Generator, List, Optional, Tuple

from services.transcode_profile import TranscodeProfile

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_DEFAULT_TRANSCODE_CHUNK_SIZE = 8192


def _parse_transcode_chunk_size() -> int:
    raw = os.environ.get("TRANSCODE_CHUNK_SIZE")
    if raw is None:
        return _DEFAULT_TRANSCODE_CHUNK_SIZE
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Invalid TRANSCODE_CHUNK_SIZE %r; using default %d",
            raw,
            _DEFAULT_TRANSCODE_CHUNK_SIZE,
        )
        return _DEFAULT_TRANSCODE_CHUNK_SIZE
    if value <= 0:
        logger.warning(
            "TRANSCODE_CHUNK_SIZE must be positive; got %d, using default %d",
            value,
            _DEFAULT_TRANSCODE_CHUNK_SIZE,
        )
        return _DEFAULT_TRANSCODE_CHUNK_SIZE
    return value


TRANSCODE_CHUNK_SIZE = _parse_transcode_chunk_size()
SUBSCRIBER_QUEUE_SIZE = 100
SUBSCRIBER_TIMEOUT = 10
STREAM_IDLE_TIMEOUT = int(os.environ.get("STREAM_IDLE_TIMEOUT", "0"))
# Seconds with no subscribers before tearing down FFmpeg. Separate from passthrough
# STREAM_IDLE_TIMEOUT so transcode can stay warm briefly after channel zaps.
TRANSCODE_STREAM_IDLE_TIMEOUT = int(os.environ.get("TRANSCODE_STREAM_IDLE_TIMEOUT", "30"))


@dataclass
class StreamSubscriber:
    subscriber_id: str
    client_ip: Optional[str]
    queue: "Queue[Optional[bytes]]"
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    bytes_sent: int = 0
    active: bool = True
    ready: bool = False


@dataclass
class TranscodeStream:
    stream_key: str
    account_id: int
    stream_id: str
    format: str
    upstream_url: str
    credential_id: Optional[int]
    session_token: str
    transcode_profile: TranscodeProfile
    user_agent: str = "okhttp/3.14.9"

    fallback_sources: List[tuple[str, str]] = field(default_factory=list)
    active_source_index: int = 0
    failover_lock: threading.Lock = field(default_factory=threading.Lock)

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    bytes_received: int = 0
    is_active: bool = True
    error: Optional[str] = None
    content_type: str = "video/mp2t"

    process: Optional[subprocess.Popen] = None
    reader_thread: Optional[threading.Thread] = None
    ffmpeg_started: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    subscribers: Dict[str, StreamSubscriber] = field(default_factory=dict)
    last_subscriber_left_at: Optional[datetime] = None
    last_client_ip: Optional[str] = None
    on_stream_closed: Optional[Callable[["TranscodeStream"], None]] = None

    def __hash__(self):
        return hash(self.stream_key)


class TranscodeStreamService:
    def __init__(self, app: Optional["Flask"] = None):
        self._streams: Dict[str, TranscodeStream] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
        self._app = app

    def start(self):
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._shutdown = False
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, name="TranscodeStreamCleanup", daemon=True
            )
            self._cleanup_thread.start()
            logger.info("TranscodeStreamService cleanup thread started")

    def stop(self):
        self._shutdown = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        with self._lock:
            for stream in list(self._streams.values()):
                self._close_stream(stream)
            self._streams.clear()

    def _get_stream_key(self, account_id: int, stream_id: str, profile: TranscodeProfile) -> str:
        return f"{account_id}:{stream_id}:ts:t:{profile.fingerprint()}"

    def get_active_stream(
        self,
        account_id: int,
        stream_id: str,
        format: str,
        transcode_profile: TranscodeProfile,
    ) -> Optional[TranscodeStream]:
        stream_key = self._get_stream_key(account_id, stream_id, transcode_profile)
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
        transcode_profile: TranscodeProfile,
        client_ip: Optional[str] = None,
        user_agent: str = "okhttp/3.14.9",
        on_stream_started: Optional[Callable[[TranscodeStream], None]] = None,
        on_stream_closed: Optional[Callable[[TranscodeStream], None]] = None,
        fallback_sources: Optional[List[Tuple[str, str]]] = None,
        active_source_index: int = 0,
    ) -> tuple[TranscodeStream, StreamSubscriber]:
        stream_key = self._get_stream_key(account_id, stream_id, transcode_profile)
        chain = fallback_sources or [(stream_id, upstream_url)]
        if active_source_index >= len(chain):
            active_source_index = 0
        active_stream_id, active_url = chain[active_source_index]

        with self._lock:
            stream = self._streams.get(stream_key)

            if stream and stream.is_active:
                logger.info(
                    "stream_join backend=transcode stream_key=%s worker_pid=%s " "subscriber_count=%s client=%s",
                    stream_key,
                    os.getpid(),
                    len(stream.subscribers),
                    client_ip,
                )
            else:
                if stream and not stream.is_active:
                    self._close_stream(stream, invoke_callback=False)

                stream = TranscodeStream(
                    stream_key=stream_key,
                    account_id=account_id,
                    stream_id=stream_id,
                    format="ts",
                    upstream_url=active_url,
                    credential_id=credential_id,
                    session_token=session_token,
                    transcode_profile=transcode_profile,
                    user_agent=user_agent,
                    fallback_sources=list(chain),
                    active_source_index=active_source_index,
                    on_stream_closed=on_stream_closed,
                )
                self._streams[stream_key] = stream

                logger.info(
                    "stream_create backend=transcode stream_key=%s worker_pid=%s "
                    "source_index=%s upstream_stream=%s profile=%s client=%s",
                    stream_key,
                    os.getpid(),
                    active_source_index,
                    active_stream_id,
                    transcode_profile.fingerprint(),
                    client_ip,
                )

                if on_stream_started:
                    on_stream_started(stream)

            subscriber = StreamSubscriber(
                subscriber_id=secrets.token_hex(16),
                client_ip=client_ip,
                queue=Queue(maxsize=SUBSCRIBER_QUEUE_SIZE),
                ready=True,
            )
            with stream.lock:
                stream.subscribers[subscriber.subscriber_id] = subscriber

            return stream, subscriber

    def unsubscribe(self, stream: TranscodeStream, subscriber: StreamSubscriber) -> None:
        with stream.lock:
            subscriber.active = False
            stream.subscribers.pop(subscriber.subscriber_id, None)
            if not stream.subscribers:
                stream.last_subscriber_left_at = datetime.now(timezone.utc).replace(tzinfo=None)
                stream.last_client_ip = subscriber.client_ip

    def stream_chunks(
        self,
        stream: TranscodeStream,
        subscriber: StreamSubscriber,
        proxy_base_url: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        # Mirror MediaFlow: mark ready and start the encoder only when a client
        # generator is consuming, so PAT/PMT and the first keyframe are not dropped.
        subscriber.ready = True
        self._ensure_ffmpeg_started(stream)
        try:
            while subscriber.active and stream.is_active:
                try:
                    chunk = subscriber.queue.get(timeout=SUBSCRIBER_TIMEOUT)
                    if chunk is None:
                        break
                    subscriber.bytes_sent += len(chunk)
                    yield chunk
                except Empty:
                    if not stream.is_active:
                        break
        finally:
            subscriber.active = False

    def _ensure_ffmpeg_started(self, stream: TranscodeStream) -> None:
        """Start FFmpeg exactly once when the first subscriber begins consuming."""
        with stream.lock:
            if stream.ffmpeg_started or not stream.is_active:
                return
            stream.ffmpeg_started = True
        self._start_ffmpeg(stream)

    def _start_ffmpeg(self, stream: TranscodeStream) -> None:
        cmd = stream.transcode_profile.build_ffmpeg_args(stream.upstream_url, stream.user_agent)
        logger.info("Starting transcode ffmpeg for %s", stream.stream_key)

        try:
            stream.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=TRANSCODE_CHUNK_SIZE,
            )
            stream.reader_thread = threading.Thread(
                target=self._ffmpeg_reader,
                args=(stream,),
                name=f"Transcode-{stream.stream_key}",
                daemon=True,
            )
            stream.reader_thread.start()
            threading.Thread(
                target=self._ffmpeg_error_monitor,
                args=(stream,),
                name=f"TranscodeErr-{stream.stream_key}",
                daemon=True,
            ).start()
        except Exception as e:
            logger.error("Failed to start transcode ffmpeg for %s: %s", stream.stream_key, e)
            stream.error = str(e)
            stream.is_active = False

    def _ffmpeg_reader(self, stream: TranscodeStream) -> None:
        try:
            while stream.is_active and stream.process and stream.process.poll() is None:
                if stream.process.stdout is None:
                    break
                chunk = stream.process.stdout.read(TRANSCODE_CHUNK_SIZE)
                if not chunk:
                    break
                stream.bytes_received += len(chunk)
                stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)

                with stream.lock:
                    any_ready = any(s.ready and s.active for s in stream.subscribers.values())
                    if not any_ready:
                        continue
                    for sub_id, subscriber in list(stream.subscribers.items()):
                        if not subscriber.active or not subscriber.ready:
                            continue
                        try:
                            subscriber.queue.put_nowait(chunk)
                        except Exception:
                            pass
        except Exception as e:
            logger.error("Transcode reader error for %s: %s", stream.stream_key, e)
            stream.error = str(e)
        finally:
            if not self._try_failover(stream):
                stream.is_active = False
                with stream.lock:
                    for subscriber in stream.subscribers.values():
                        try:
                            subscriber.queue.put_nowait(None)
                        except Exception:
                            pass
                        subscriber.active = False

    def _try_failover(self, stream: TranscodeStream) -> bool:
        with stream.failover_lock:
            if not stream.subscribers:
                return False
            next_index = stream.active_source_index + 1
            if next_index >= len(stream.fallback_sources):
                return False
            next_stream_id, next_url = stream.fallback_sources[next_index]
            logger.info(
                "Transcode stream %s failing over to source %s (index %s)",
                stream.stream_key,
                next_stream_id,
                next_index,
            )
            self._terminate_ffmpeg_process(stream)
            stream.active_source_index = next_index
            stream.upstream_url = next_url
            stream.error = None
            stream.is_active = True
            stream.bytes_received = 0
            with stream.lock:
                stream.ffmpeg_started = False
            self._ensure_ffmpeg_started(stream)
            return True

    def _terminate_ffmpeg_process(self, stream: TranscodeStream) -> None:
        if stream.process:
            try:
                stream.process.terminate()
                try:
                    stream.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    stream.process.kill()
            except Exception as e:
                logger.debug("Error terminating transcode ffmpeg: %s", e)
            stream.process = None

    def _ffmpeg_error_monitor(self, stream: TranscodeStream) -> None:
        if not stream.process or not stream.process.stderr:
            return
        try:
            for line in stream.process.stderr:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if "error" in line.lower():
                    logger.error("Transcode %s: %s", stream.stream_key, line)
                elif "warning" in line.lower():
                    logger.warning("Transcode %s: %s", stream.stream_key, line)
                else:
                    logger.debug("Transcode %s: %s", stream.stream_key, line)
        except Exception:
            pass

    def _close_stream(self, stream: TranscodeStream, invoke_callback: bool = True, reason: str = "closed") -> None:
        stream.is_active = False
        self._terminate_ffmpeg_process(stream)
        with stream.lock:
            for subscriber in stream.subscribers.values():
                try:
                    subscriber.queue.put_nowait(None)
                except Exception:
                    pass
                subscriber.active = False
            stream.subscribers.clear()
        with self._lock:
            self._streams.pop(stream.stream_key, None)
        if invoke_callback and stream.on_stream_closed:
            try:
                if self._app:
                    with self._app.app_context():
                        stream.on_stream_closed(stream)
                else:
                    stream.on_stream_closed(stream)
            except Exception as e:
                logger.error("Error in transcode stream close callback: %s", e)
        logger.info(
            "stream_close backend=transcode stream_key=%s reason=%s bytes=%s",
            stream.stream_key,
            reason,
            stream.bytes_received,
        )

    def _cleanup_loop(self) -> None:
        while not self._shutdown:
            try:
                self._cleanup_idle_streams()
            except Exception as e:
                logger.exception("Error in transcode cleanup loop: %s", e)
            for _ in range(10):
                if self._shutdown:
                    break
                time.sleep(0.1)

    def _cleanup_idle_streams(self) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._lock:
            to_close = []
            for stream_key, stream in self._streams.items():
                if not stream.subscribers:
                    if not stream.is_active or stream.error:
                        to_close.append((stream, "upstream_end" if stream.error else "inactive"))
                        continue
                    idle_time = stream.last_subscriber_left_at or stream.last_activity
                    if (now - idle_time).total_seconds() >= TRANSCODE_STREAM_IDLE_TIMEOUT:
                        to_close.append((stream, "idle"))
                elif not stream.is_active:
                    to_close.append((stream, "upstream_end"))
            for stream, reason in to_close:
                self._close_stream(stream, reason=reason)

    def find_idle_stream_for_client(
        self,
        account_id: int,
        client_ip: Optional[str],
        exclude_stream_id: str,
        transcode_profile: Optional[TranscodeProfile] = None,
    ) -> Optional[TranscodeStream]:
        """Return an idle-pending stream from the same client suitable for credential reuse."""
        if not client_ip or STREAM_IDLE_TIMEOUT <= 0:
            return None

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._lock:
            for stream in self._streams.values():
                if stream.account_id != account_id:
                    continue
                if stream.stream_id == exclude_stream_id:
                    continue
                if stream.subscribers or not stream.is_active:
                    continue
                if stream.last_client_ip != client_ip:
                    continue
                if transcode_profile and stream.transcode_profile.fingerprint() != transcode_profile.fingerprint():
                    continue
                idle_since = stream.last_subscriber_left_at
                if not idle_since:
                    continue
                if STREAM_IDLE_TIMEOUT > 0 and (now - idle_since).total_seconds() >= STREAM_IDLE_TIMEOUT:
                    continue
                return stream
        return None

    def close_idle_stream_for_reuse(self, stream: TranscodeStream) -> None:
        """Close an idle stream without releasing its credential slot."""
        self._close_stream(stream, invoke_callback=False, reason="channel_switch_reuse")

    def get_idle_stream_count(self, account_id: int) -> int:
        count = 0
        with self._lock:
            for stream in self._streams.values():
                if stream.account_id == account_id and not stream.subscribers:
                    count += 1
        return count

    def release_idle_streams_for_account(
        self, account_id: int, credential_id: Optional[int] = None, max_to_release: int = 1
    ) -> int:
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
                        "transcode_profile": s.transcode_profile.fingerprint(),
                    }
                    for s in self._streams.values()
                ],
            }


_transcode_service: Optional[TranscodeStreamService] = None


def get_transcode_service(app: Optional["Flask"] = None) -> TranscodeStreamService:
    global _transcode_service
    if _transcode_service is None:
        _transcode_service = TranscodeStreamService(app=app)
        _transcode_service.start()
    return _transcode_service
