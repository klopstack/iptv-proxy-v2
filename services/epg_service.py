"""Backward compatibility — use services.epg instead."""

import warnings

warnings.warn(
    "Import from services.epg (or services.epg submodules) instead of services.epg_service",
    DeprecationWarning,
    stacklevel=2,
)

from services.epg.constants import (
    EAST_TAGS,
    MAJOR_BROADCAST_NETWORKS,
    NETWORK_FALLBACK_EPG_IDS,
    PPV_CATEGORY_PATTERNS,
    PPV_PLACEHOLDER_PATTERNS,
    STRIP_WORDS,
    WEST_TAGS,
)
from services.epg.facade import EpgService
from services.epg.ppv import get_ppv_event_title, is_ppv_category, is_ppv_channel, is_ppv_placeholder_name
from services.epg.utils import (
    copy_element,
    decompress_content,
    extract_callsign_from_xmltv_id,
    get_decompressing_stream,
    make_sd_xmltv_id,
    normalize_channel_name,
    normalize_xmltv_url,
    parse_xmltv_time,
    shift_xmltv_time,
)

__all__ = [
    "EpgService",
    "MAJOR_BROADCAST_NETWORKS",
    "NETWORK_FALLBACK_EPG_IDS",
    "PPV_CATEGORY_PATTERNS",
    "PPV_PLACEHOLDER_PATTERNS",
    "EAST_TAGS",
    "WEST_TAGS",
    "STRIP_WORDS",
    "extract_callsign_from_xmltv_id",
    "make_sd_xmltv_id",
    "normalize_xmltv_url",
    "shift_xmltv_time",
    "decompress_content",
    "get_decompressing_stream",
    "copy_element",
    "parse_xmltv_time",
    "normalize_channel_name",
    "is_ppv_channel",
    "is_ppv_category",
    "is_ppv_placeholder_name",
    "get_ppv_event_title",
]
