"""
Unit tests for stream service factory (STREAM_BACKEND selection).

Environment variables (see .env.example):
- STREAM_BACKEND: "ffmpeg" (default) or "mediaflow"
- MEDIAFLOW_PROXY_URL: MediaFlow Proxy base URL (when backend is mediaflow)
- MEDIAFLOW_API_PASSWORD: optional API password for MediaFlow Proxy
"""
import importlib
from unittest.mock import patch

import pytest

import services.stream_service_factory as stream_service_factory


@pytest.fixture
def factory_module(monkeypatch):
    """Reload factory module so STREAM_BACKEND reflects current environment."""
    monkeypatch.delenv("STREAM_BACKEND", raising=False)
    importlib.reload(stream_service_factory)
    yield stream_service_factory
    # Module-level STREAM_BACKEND survives monkeypatch undo; reset for other tests.
    monkeypatch.delenv("STREAM_BACKEND", raising=False)
    importlib.reload(stream_service_factory)


class TestStreamServiceFactory:
    def test_default_backend_is_ffmpeg(self, monkeypatch, factory_module):
        monkeypatch.delenv("STREAM_BACKEND", raising=False)
        importlib.reload(factory_module)
        assert factory_module.get_stream_backend_name() == "ffmpeg"

    def test_ffmpeg_backend_selected(self, monkeypatch, factory_module):
        monkeypatch.setenv("STREAM_BACKEND", "ffmpeg")
        importlib.reload(factory_module)
        with patch("services.ffmpeg_stream_service.get_ffmpeg_service") as mock_get:
            mock_get.return_value = object()
            result = factory_module.get_stream_service()
            mock_get.assert_called_once()
            assert result is mock_get.return_value

    def test_mediaflow_backend_selected(self, monkeypatch, factory_module):
        monkeypatch.setenv("STREAM_BACKEND", "mediaflow")
        importlib.reload(factory_module)
        with patch("services.mediaflow_stream_service.get_mediaflow_service") as mock_get:
            mock_get.return_value = object()
            result = factory_module.get_stream_service()
            mock_get.assert_called_once()
            assert result is mock_get.return_value

    def test_unknown_backend_falls_back_to_ffmpeg(self, monkeypatch, factory_module, caplog):
        monkeypatch.setenv("STREAM_BACKEND", "invalid")
        importlib.reload(factory_module)
        assert factory_module.get_stream_backend_name() == "ffmpeg"
        with caplog.at_level("WARNING"):
            with patch("services.ffmpeg_stream_service.get_ffmpeg_service") as mock_get:
                mock_get.return_value = object()
                factory_module.get_stream_service()
        assert "Unknown STREAM_BACKEND 'invalid'" in caplog.text
        mock_get.assert_called_once()

    def test_backend_name_normalizes_case(self, monkeypatch, factory_module):
        monkeypatch.setenv("STREAM_BACKEND", "MediaFlow")
        importlib.reload(factory_module)
        assert factory_module.get_stream_backend_name() == "mediaflow"
