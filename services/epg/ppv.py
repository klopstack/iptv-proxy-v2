"""
EPG PPV detection helpers — backward-compatible re-exports.

Canonical implementations live in ``services.ppv.detection``.
"""

from services.ppv.detection import (
    get_ppv_event_title,
    is_generic_channel_name,
    is_ppv_category,
    is_ppv_channel,
    is_ppv_placeholder_name,
)

__all__ = [
    "get_ppv_event_title",
    "is_generic_channel_name",
    "is_ppv_category",
    "is_ppv_channel",
    "is_ppv_placeholder_name",
]
