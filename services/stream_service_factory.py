"""
Stream Service Factory - provides the appropriate stream service based on configuration

This module allows switching between different stream backends:
- ffmpeg: Uses FFmpeg for MPEG-TS remuxing (default, requires ffmpeg binary)
- mediaflow: Uses MediaFlow Proxy for HLS/TS proxying (requires mediaflow-proxy service)

Configure via STREAM_BACKEND environment variable.
"""

import logging
import os
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from flask import Flask

    from services.ffmpeg_stream_service import FFmpegStreamService
    from services.mediaflow_stream_service import MediaFlowStreamService

logger = logging.getLogger(__name__)

# Stream backend configuration
STREAM_BACKEND = os.environ.get("STREAM_BACKEND", "ffmpeg").lower()

# Type alias for stream services
StreamService = Union["FFmpegStreamService", "MediaFlowStreamService"]


def get_stream_service(app: Optional["Flask"] = None) -> StreamService:
    """
    Get the appropriate stream service based on configuration.

    Args:
        app: Flask application instance (optional, used for callbacks)

    Returns:
        Stream service instance (FFmpegStreamService or MediaFlowStreamService)

    Environment Variables:
        STREAM_BACKEND: "ffmpeg" (default) or "mediaflow"
        MEDIAFLOW_PROXY_URL: URL of MediaFlow Proxy (default: http://localhost:8888)
        MEDIAFLOW_API_PASSWORD: API password for MediaFlow Proxy (optional)
    """
    if STREAM_BACKEND == "mediaflow":
        logger.info("Using MediaFlow Proxy stream backend")
        from services.mediaflow_stream_service import get_mediaflow_service

        return get_mediaflow_service(app=app)
    else:
        if STREAM_BACKEND != "ffmpeg":
            logger.warning(f"Unknown STREAM_BACKEND '{STREAM_BACKEND}', defaulting to ffmpeg")
        logger.info("Using FFmpeg stream backend")
        from services.ffmpeg_stream_service import get_ffmpeg_service

        return get_ffmpeg_service(app=app)


def get_stream_backend_name() -> str:
    """Get the name of the currently configured stream backend."""
    return STREAM_BACKEND if STREAM_BACKEND in ("ffmpeg", "mediaflow") else "ffmpeg"
