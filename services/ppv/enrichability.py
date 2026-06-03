"""Classify PPV channels as enrichable vs skippable before calendar matching."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.ppv.constants import FAR_FUTURE_VISIBILITY_DAYS, STALE_ARCHIVE_ENRICHMENT_DAYS
from services.ppv.detection import is_generic_channel_name, is_ppv_placeholder_name
from services.ppv.extraction import PPVEventExtractor

# Section headers / category dividers in IPTV feeds (e.g. "##### DAZN PPV #####")
PPV_SECTION_HEADER_PATTERN = re.compile(r"^#+\s*.+\s*#+\s*$", re.IGNORECASE)
# ESPN Play / archive feeds: "| 11-09-2023" or "| 01-18-2024" (US month-day-year)
US_ARCHIVE_DATE_PATTERN = re.compile(r"(?:\||\s)(\d{1,2})-(\d{1,2})-(\d{4})\b")

_extractor = PPVEventExtractor()


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_stale_archive_date(event_date: datetime) -> bool:
    naive = event_date.replace(tzinfo=None) if event_date.tzinfo else event_date
    cutoff = _naive_utc_now() - timedelta(days=STALE_ARCHIVE_ENRICHMENT_DAYS)
    return naive < cutoff


def _parse_us_archive_date(channel_name: str) -> Optional[datetime]:
    match = US_ARCHIVE_DATE_PATTERN.search(channel_name)
    if not match:
        return None
    month, day, year = (int(match.group(i)) for i in (1, 2, 3))
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def stale_archive_date_from_title(channel_name: str) -> Optional[datetime]:
    """Return an explicit past archive date embedded in the title, if any."""
    return _parse_us_archive_date(channel_name)


def is_ppv_section_header(name: str) -> bool:
    """Return True for hash-wrapped section headers with no event content."""
    if not name:
        return False
    stripped = name.strip()
    return bool(PPV_SECTION_HEADER_PATTERN.match(stripped))


def classify_ppv_enrichment(
    channel_name: str,
    extraction: Optional[dict] = None,
    *,
    cheap_only: bool = False,
) -> Optional[str]:
    """
    Return a skip reason if the channel cannot be calendar-enriched, else None.

    Reasons align with enrichment filter keys: generic_name, placeholder_name,
    section_header, placeholder, inactive, no_competitors, date_but_no_competitors,
    far_future, stale_archive.

    When ``extraction`` is provided (e.g. from a prior ``extract_all`` call), it is
    used for competitor/date checks instead of re-extracting from the channel name.

    With ``cheap_only=True``, only name-pattern checks run (no ``extract_all``).
    Use in orchestrator batch selection; enrichment runs the full classify pass.
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

    archive_date = stale_archive_date_from_title(channel_name)
    if archive_date and _is_stale_archive_date(archive_date):
        return "stale_archive"

    if cheap_only:
        return None

    if extraction is None:
        extraction = _extractor.extract_all(channel_name)

    if extraction.get("inferred_how") == "date_too_far_future":
        return "far_future"

    if not extraction.get("competitors"):
        if extraction.get("date") or extraction.get("time_only"):
            return "date_but_no_competitors"
        return "no_competitors"

    event_date = extraction.get("date")
    if isinstance(event_date, datetime):
        if _is_stale_archive_date(event_date):
            return "stale_archive"
        far_future_cutoff = _naive_utc_now() + timedelta(days=FAR_FUTURE_VISIBILITY_DAYS)
        if event_date.replace(tzinfo=None) > far_future_cutoff:
            return "far_future"

    return None


def skip_error_message(reason: str) -> str:
    return f"skip:{reason}"
