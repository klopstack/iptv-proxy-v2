"""
Unit tests for MediaFlow stream service with mocked HTTP.

No live MediaFlow Proxy container is required. Environment variables
(see .env.example):
- STREAM_BACKEND=mediaflow selects this backend via stream_service_factory
- MEDIAFLOW_PROXY_URL: base URL for proxy requests (default http://localhost:8888)
- MEDIAFLOW_API_PASSWORD: optional password appended to proxy query string
"""
import threading
import time
from queue import Empty
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import services.mediaflow_stream_service as mediaflow_module
from services.mediaflow_stream_service import MediaFlowStreamService, get_mediaflow_service


def _make_stream_response(status_code=200, chunks=None, headers=None):
    """Build a mock context-manager response for requests.get(stream=True)."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.headers = headers or {}
    mock_response.iter_content = lambda chunk_size: iter(chunks or [])
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)
    return mock_response


@pytest.fixture
def reset_mediaflow_singleton(monkeypatch):
    """Ensure each test gets an isolated MediaFlow service singleton."""
    monkeypatch.setattr(mediaflow_module, "_mediaflow_service", None)
    yield
    monkeypatch.setattr(mediaflow_module, "_mediaflow_service", None)


@pytest.fixture
def mediaflow_available(monkeypatch):
    """MediaFlow service with availability check mocked as reachable."""
    monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_PROXY_URL", "http://mediaflow.test:8888")
    monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_API_PASSWORD", "")

    with patch("services.mediaflow_stream_service.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200)
        service = MediaFlowStreamService()
        service.start()
        yield service, mock_get
        service.stop()


@pytest.fixture
def mediaflow_unavailable(monkeypatch):
    """MediaFlow service with availability check failing."""
    monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_PROXY_URL", "http://mediaflow.test:8888")

    with patch(
        "services.mediaflow_stream_service.requests.get",
        side_effect=requests.exceptions.ConnectionError("connection refused"),
    ):
        service = MediaFlowStreamService()
        service.start()
        yield service
        service.stop()


class TestMediaFlowStreamServiceBasic:
    def test_service_starts_and_stops(self, mediaflow_available):
        service, _ = mediaflow_available
        assert service._cleanup_thread is not None
        assert service._cleanup_thread.is_alive()
        service.stop()
        assert service._shutdown is True

    def test_get_stream_key(self, mediaflow_available):
        service, _ = mediaflow_available
        assert service._get_stream_key(1, "12345", "ts") == "1:12345:ts"

    def test_get_active_stream_not_found(self, mediaflow_available):
        service, _ = mediaflow_available
        assert service.get_active_stream(1, "missing", "ts") is None


class TestMediaFlowUrlConstruction:
    def test_build_ts_proxy_url(self, mediaflow_available, monkeypatch):
        service, _ = mediaflow_available
        monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_PROXY_URL", "http://proxy.example:8888")

        url = service._build_mediaflow_url("http://upstream.example/stream.ts", "okhttp/3.14.9", "ts")

        parsed = urlparse(url)
        assert parsed.scheme == "http"
        assert parsed.netloc == "proxy.example:8888"
        assert parsed.path == "/proxy/stream"
        params = parse_qs(parsed.query)
        assert params["d"] == ["http://upstream.example/stream.ts"]
        assert params["h_user-agent"] == ["okhttp/3.14.9"]
        assert "force_playlist_proxy" not in params

    def test_build_hls_proxy_url_includes_force_playlist_proxy(self, mediaflow_available, monkeypatch):
        service, _ = mediaflow_available
        monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_PROXY_URL", "http://proxy.example:8888")

        url = service._build_mediaflow_url("http://upstream.example/live.m3u8", "okhttp/3.14.9", "m3u8")

        parsed = urlparse(url)
        assert parsed.path == "/proxy/hls/manifest.m3u8"
        params = parse_qs(parsed.query)
        assert params["force_playlist_proxy"] == ["true"]

    def test_build_url_includes_api_password(self, mediaflow_available, monkeypatch):
        service, _ = mediaflow_available
        monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_API_PASSWORD", "secret-token")

        url = service._build_mediaflow_url("http://upstream.example/stream.ts", "okhttp/3.14.9", "ts")
        params = parse_qs(urlparse(url).query)
        assert params["api_password"] == ["secret-token"]

    def test_build_url_fallback_when_mediaflow_unavailable(self, mediaflow_unavailable):
        service = mediaflow_unavailable
        upstream = "http://upstream.example/direct.ts"
        assert service._build_mediaflow_url(upstream, "okhttp/3.14.9", "ts") == upstream


class TestMediaFlowSubscribe:
    def test_subscribe_creates_stream_with_proxy_url(self, mediaflow_available, monkeypatch):
        service, _ = mediaflow_available
        monkeypatch.setattr(mediaflow_module, "MEDIAFLOW_PROXY_URL", "http://proxy.example:8888")

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="abc",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=10,
            session_token="session-token",
            client_ip="127.0.0.1",
        )

        assert stream.is_active
        assert stream.proxy_url.startswith("http://proxy.example:8888/proxy/stream")
        assert stream.content_type == "video/mp2t"
        assert subscriber.client_ip == "127.0.0.1"
        assert subscriber.subscriber_id in stream.subscribers

    def test_subscribe_m3u8_content_type(self, mediaflow_available):
        service, _ = mediaflow_available
        stream, _ = service.subscribe(
            account_id=1,
            stream_id="hls",
            format="m3u8",
            upstream_url="http://upstream.example/live.m3u8",
            credential_id=1,
            session_token="session",
        )
        assert stream.content_type == "application/vnd.apple.mpegurl"

    def test_subscribe_reuses_active_stream(self, mediaflow_available):
        service, _ = mediaflow_available
        started = Mock()

        stream1, sub1 = service.subscribe(
            account_id=1,
            stream_id="shared",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session1",
            on_stream_started=started,
        )
        stream2, sub2 = service.subscribe(
            account_id=1,
            stream_id="shared",
            format="ts",
            upstream_url="http://upstream.example/other.ts",
            credential_id=1,
            session_token="session2",
        )

        assert stream1 is stream2
        assert sub1.subscriber_id != sub2.subscriber_id
        assert len(stream1.subscribers) == 2
        started.assert_called_once()

    def test_unsubscribe_tracks_last_subscriber_left(self, mediaflow_available):
        service, _ = mediaflow_available
        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="solo",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        service.unsubscribe(stream, subscriber)

        assert len(stream.subscribers) == 0
        assert stream.last_subscriber_left_at is not None
        assert not subscriber.active


class TestMediaFlowStreamChunks:
    def test_stream_chunks_rewrites_m3u8_manifest(self, mediaflow_available):
        service, mock_get = mediaflow_available
        manifest = (
            "#EXTM3U\n#EXTINF:10.0,\n" "http://localhost:8888/proxy/stream?d=https%3A%2F%2Fprovider.example%2Fseg.ts\n"
        )
        mock_get.return_value = _make_stream_response(
            chunks=[manifest.encode("utf-8")],
            headers={"Content-Type": "application/vnd.apple.mpegurl"},
        )

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="hls",
            format="m3u8",
            upstream_url="http://upstream.example/live.m3u8",
            credential_id=1,
            session_token="session",
        )

        received = b"".join(service.stream_chunks(stream, subscriber, proxy_base_url="http://iptv-proxy:8000"))

        assert b"http://iptv-proxy:8000/stream/mediaflow/proxy/stream" in received
        assert b"localhost:8888" not in received

    def test_stream_chunks_yields_data_on_success(self, mediaflow_available):
        service, mock_get = mediaflow_available
        chunks = [b"chunk-one", b"chunk-two"]
        mock_get.return_value = _make_stream_response(chunks=chunks, headers={"Content-Type": "video/mp2t"})

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="live",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        received = list(service.stream_chunks(stream, subscriber))

        assert received == chunks
        assert subscriber.bytes_sent == sum(len(c) for c in chunks)
        assert stream.bytes_received == subscriber.bytes_sent
        assert stream.content_type == "video/mp2t"
        mock_get.assert_called()
        request_kwargs = mock_get.call_args.kwargs
        assert request_kwargs["stream"] is True
        assert request_kwargs["headers"]["User-Agent"] == "okhttp/3.14.9"

    def test_stream_chunks_non_200_deactivates_stream(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.return_value = _make_stream_response(status_code=502)

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="bad",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        received = list(service.stream_chunks(stream, subscriber))

        assert received == []
        assert not stream.is_active
        assert stream.error == "Upstream returned 502"

    def test_stream_chunks_timeout_sets_error(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.side_effect = requests.exceptions.Timeout("read timed out")

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="timeout",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        list(service.stream_chunks(stream, subscriber))

        assert not stream.is_active
        assert "Timeout" in stream.error

    def test_stream_chunks_connection_error_sets_error(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="conn",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        list(service.stream_chunks(stream, subscriber))

        assert not stream.is_active
        assert "Connection error" in stream.error


class TestMediaFlowFanOut:
    """Two subscribers on the same stream must share a single upstream pull."""

    def _drain(self, queue):
        items = []
        while True:
            try:
                item = queue.get_nowait()
            except Empty:
                break
            if item is None:
                break
            items.append(item)
        return items

    def test_two_subscribers_share_single_upstream_pull(self, mediaflow_available):
        service, mock_get = mediaflow_available
        # Ignore the availability-probe call made during construction.
        mock_get.reset_mock()
        chunks = [b"aaaa", b"bbbb"]
        mock_get.return_value = _make_stream_response(chunks=chunks, headers={"Content-Type": "video/mp2t"})

        stream, sub1 = service.subscribe(
            account_id=1,
            stream_id="shared",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session-1",
        )
        stream2, sub2 = service.subscribe(
            account_id=1,
            stream_id="shared",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session-2",
        )

        # Both subscribers attached to the same in-memory stream object.
        assert stream2 is stream
        assert len(stream.subscribers) == 2

        # Mark both ready and drive a single upstream pull directly so the test
        # is deterministic (no dependence on reader-thread scheduling).
        sub1.ready = True
        sub2.ready = True
        assert service._pull_source(stream, stream.proxy_url) is True

        # Exactly one upstream request was made for the two subscribers.
        assert mock_get.call_count == 1
        # Both subscribers received the full byte stream.
        assert self._drain(sub1.queue) == chunks
        assert self._drain(sub2.queue) == chunks

    def test_stream_chunks_two_consumers_single_get(self, mediaflow_available):
        service, mock_get = mediaflow_available
        data = [b"x" * 100 for _ in range(40)]

        def _slow_response():
            response = Mock()
            response.status_code = 200
            response.headers = {"Content-Type": "video/mp2t"}

            def _iter(chunk_size):
                for chunk in data:
                    time.sleep(0.005)
                    yield chunk

            response.iter_content = _iter
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response

        # Ignore the availability-probe call made during construction.
        mock_get.reset_mock()
        mock_get.return_value = _slow_response()

        stream, sub1 = service.subscribe(
            account_id=2,
            stream_id="shared2",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="s1",
        )
        _, sub2 = service.subscribe(
            account_id=2,
            stream_id="shared2",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="s2",
        )

        out1, out2 = [], []
        t1 = threading.Thread(target=lambda: out1.extend(service.stream_chunks(stream, sub1)))
        t2 = threading.Thread(target=lambda: out2.extend(service.stream_chunks(stream, sub2)))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # One shared reader → one upstream connection for both consumers.
        assert mock_get.call_count == 1
        assert len(out1) > 0
        assert len(out2) > 0


class TestMediaFlowPlaceholderDetection:
    """A static placeholder TS file must be rejected and trigger failover."""

    def test_placeholder_response_rejected(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.reset_mock()
        # Static file: fixed Content-Length + Accept-Ranges on a TS request.
        mock_get.return_value = _make_stream_response(
            chunks=[b"junk"],
            headers={
                "Content-Type": "video/mp2t",
                "Content-Length": "14000000",
                "Accept-Ranges": "bytes",
                "Last-Modified": "Tue, 01 Aug 2023 12:00:00 GMT",
            },
        )

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="placeholder",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        received = list(service.stream_chunks(stream, subscriber))

        assert received == []
        assert not stream.is_active
        assert "upstream_placeholder" in (stream.error or "")

    def test_placeholder_fails_over_to_next_source(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.reset_mock()

        placeholder = _make_stream_response(
            chunks=[b"junk"],
            headers={
                "Content-Type": "video/mp2t",
                "Content-Length": "14000000",
                "Accept-Ranges": "bytes",
            },
        )
        live = _make_stream_response(
            chunks=[b"live-data"],
            headers={"Content-Type": "video/mp2t"},
        )
        mock_get.side_effect = [placeholder, live]

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="primary",
            format="ts",
            upstream_url="http://upstream.example/primary.ts",
            credential_id=1,
            session_token="session",
            fallback_sources=[
                ("primary", "http://upstream.example/primary.ts"),
                ("backup", "http://upstream.example/backup.ts"),
            ],
        )

        received = list(service.stream_chunks(stream, subscriber))

        assert received == [b"live-data"]
        assert mock_get.call_count == 2
        assert stream.active_source_index == 1

    def test_live_chunked_ts_not_flagged_as_placeholder(self, mediaflow_available):
        service, mock_get = mediaflow_available
        mock_get.reset_mock()
        # Live stream: no Content-Length, chunked transfer.
        mock_get.return_value = _make_stream_response(
            chunks=[b"live-chunk"],
            headers={"Content-Type": "video/mp2t", "Transfer-Encoding": "chunked"},
        )

        stream, subscriber = service.subscribe(
            account_id=1,
            stream_id="livets",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        received = list(service.stream_chunks(stream, subscriber))

        assert received == [b"live-chunk"]
        assert stream.error is None


class TestMediaFlowStats:
    def test_get_stats_reports_active_streams(self, mediaflow_available):
        service, _ = mediaflow_available
        service.subscribe(
            account_id=1,
            stream_id="stats",
            format="ts",
            upstream_url="http://upstream.example/stream.ts",
            credential_id=1,
            session_token="session",
        )

        stats = service.get_stats()

        assert stats["active_streams"] == 1
        assert stats["total_subscribers"] == 1
        assert len(stats["streams"]) == 1
        assert stats["streams"][0]["key"] == "1:stats:ts"


class TestMediaFlowServiceSingleton:
    def test_get_mediaflow_service_returns_same_instance(self, reset_mediaflow_singleton):
        with patch("services.mediaflow_stream_service.requests.get", return_value=Mock(status_code=200)):
            service1 = get_mediaflow_service()
            service2 = get_mediaflow_service()
        assert service1 is service2
        assert service1._cleanup_thread is not None
        service1.stop()
