"""
Stream Service Factory - MediaFlow passthrough and optional transcode services.

Passthrough streaming always uses MediaFlow Proxy. Per-client transcoding uses a
local FFmpeg subprocess (see transcode_stream_service).
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from flask import Flask

    from services.mediaflow_stream_service import MediaFlowStreamService
    from services.transcode_stream_service import TranscodeStreamService

logger = logging.getLogger(__name__)


def get_stream_service(app: Optional["Flask"] = None) -> "MediaFlowStreamService":
    """Return the MediaFlow passthrough stream service."""
    from services.mediaflow_stream_service import get_mediaflow_service

    return get_mediaflow_service(app=app)


def get_transcode_stream_service(app: Optional["Flask"] = None) -> "TranscodeStreamService":
    """Return the FFmpeg transcode stream service."""
    from services.transcode_stream_service import get_transcode_service

    return get_transcode_service(app=app)


def get_stream_backend_name() -> str:
    """Return the passthrough backend name (always mediaflow)."""
    return "mediaflow"
