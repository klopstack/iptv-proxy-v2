"""Classify PPV channels as enrichable vs skippable before calendar matching."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.epg.ppv import is_ppv_placeholder_name
from services.ppv.detection import is_generic_channel_name
from services.ppv.extraction import PPVEventExtractor

# Section headers / category dividers in IPTV feeds (e.g. "##### DAZN PPV #####")
PPV_SECTION_HEADER_PATTERN = re.compile(r"^#+\s*.+\s*#+\s*$", re.IGNORECASE)

_extractor = PPVEventExtractor()


def is_ppv_section_header(name: str) -> bool:
    """Return True for hash-wrapped section headers with no event content."""
    if not name:
        return False
    stripped = name.strip()
    return bool(PPV_SECTION_HEADER_PATTERN.match(stripped))


def classify_ppv_enrichment(channel_name: str) -> Optional[str]:
    """
    Return a skip reason if the channel cannot be calendar-enriched, else None.

    Reasons align with enrichment filter keys: generic_name, placeholder_name,
    section_header, placeholder, inactive, no_competitors, date_but_no_competitors,
    far_future.
    """
    if not channel_name or not channel_name.strip():
        return "inactive"

    if is_generic_channel_name(channel_name):
        return "generic_name"

    if is_ppv_placeholder_name(channel_name):
        return "placeholder_name"

    if is_ppv_section_header(channel_name):
        return "section_header"

    if _extractor.is_placeholder(channel_name):
        return "placeholder"

    if _extractor.is_inactive_channel(channel_name):
        return "inactive"

    extraction = _extractor.extract_all(channel_name)

    if extraction.get("inferred_how") == "date_too_far_future":
        return "far_future"

    if not extraction.get("competitors"):
        if extraction.get("date") or extraction.get("time_only"):
            return "date_but_no_competitors"
        return "no_competitors"

    event_date = extraction.get("date")
    if isinstance(event_date, datetime):
        far_future_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=31)
        if event_date.replace(tzinfo=None) > far_future_cutoff:
            return "far_future"

    return None


def skip_error_message(reason: str) -> str:
    return f"skip:{reason}"
