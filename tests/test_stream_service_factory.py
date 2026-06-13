"""
Unit tests for stream service factory.

Passthrough streaming always uses MediaFlow; transcoding uses TranscodeStreamService.
"""

from unittest.mock import patch

import services.stream_service_factory as stream_service_factory


class TestStreamServiceFactory:
    def test_backend_name_is_mediaflow(self):
        assert stream_service_factory.get_stream_backend_name() == "mediaflow"

    def test_get_stream_service_returns_mediaflow(self):
        with patch("services.mediaflow_stream_service.get_mediaflow_service") as mock_get:
            mock_get.return_value = object()
            result = stream_service_factory.get_stream_service()
            mock_get.assert_called_once()
            assert result is mock_get.return_value

    def test_get_transcode_stream_service(self):
        with patch("services.transcode_stream_service.get_transcode_service") as mock_get:
            mock_get.return_value = object()
            result = stream_service_factory.get_transcode_stream_service()
            mock_get.assert_called_once()
            assert result is mock_get.return_value
