"""
Shared date anchoring helpers for PPV and reverse-event date extraction.

Both ``PPVEventExtractor`` and ``DateExtractor`` use these utilities so
month/day and time-only parsing stay aligned.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple

from services.ppv.extraction.patterns import (
    DATE_PATTERN,
    DDMM_DATE_PATTERN,
    ISO_DATE_PATTERN,
    ISO_PAREN_DATETIME_PATTERN,
    ISO_PIPE_DATE_PATTERN,
    MONTH_ABBR_TO_NUM,
    TIME_ONLY_PATTERN,
    WEEKDAY_PATTERN,
)

# Optional @ before month abbreviation (e.g. "@ Jun 4 01:55")
MONTH_DAY_ANCHOR_PATTERN = re.compile(
    r"@?\s*"
    + DATE_PATTERN,
    re.IGNORECASE,
)

START_STOP_PATTERN = re.compile(
    r"(?:start:|stop:)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)",
    re.IGNORECASE,
)

ISO_DATE_LOOSE_PATTERN = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)\b"
)

_MONTH_SIGNAL = r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b"
_DAY_MONTH_SIGNAL = r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b"
_FULL_MONTH_SIGNAL = (
    r"\b(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2}\b"
)


def apply_ampm(hour: int, minute: int, ampm: Optional[str]) -> Tuple[int, int]:
    """Convert 12-hour clock to 24-hour."""
    if ampm:
        ampm = ampm.upper()
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
    return hour % 24, minute % 60


def resolve_month_day_datetime(
    month: int,
    day: int,
    hour: int,
    minute: int,
    *,
    ampm: Optional[str] = None,
    reference: datetime,
) -> Optional[datetime]:
    """
    Build a datetime for an explicit month/day (+ time) anchor.

    Picks the nearest occurrence within ±1 year of ``reference`` so titles
    like ``@ Jun 3`` on 2026-06-03 stay on that calendar day (not 2027).
    """
    hour, minute = apply_ampm(int(hour), int(minute), ampm)

    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidates.append(datetime(year, month, day, hour, minute))
        except ValueError:
            continue

    if not candidates:
        return None

    # Prefer same calendar day as reference when month/day match
    same_day = [c for c in candidates if c.date() == reference.date()]
    if same_day:
        return same_day[0]

    future = [c for c in candidates if c >= reference]
    if future:
        return min(future)

    return max(candidates)


def parse_month_day_anchor(channel_name: str, reference: datetime) -> Optional[datetime]:
    """Parse ``Jun 4 01:55`` or ``@ Jun 3 11:00 AM`` style anchors."""
    match = MONTH_DAY_ANCHOR_PATTERN.search(channel_name)
    if not match:
        return None
    month_str, day, hour, minute, ampm = match.groups()
    month = MONTH_ABBR_TO_NUM.get(month_str.lower())
    if not month:
        return None
    return resolve_month_day_datetime(
        month,
        int(day),
        int(hour),
        int(minute),
        ampm=ampm,
        reference=reference,
    )


def parse_trailing_time_only(channel_name: str) -> Optional[Tuple[int, int, Optional[str]]]:
    """Return the last clock time in the string (avoids provider slot numbers)."""
    matches = list(re.finditer(TIME_ONLY_PATTERN, channel_name, re.IGNORECASE))
    if not matches:
        return None
    match = matches[-1]
    return int(match.group(1)), int(match.group(2)), (match.group(3).lower() if match.group(3) else None)


def time_only_on_reference_day(channel_name: str, reference: datetime) -> Optional[datetime]:
    """
    Attach a trailing time to the reference calendar day (no next-day rollover).

    Used for live listings such as ``... 12:30pm`` without an explicit date.
    """
    if parse_month_day_anchor(channel_name, reference) is not None:
        return None
    if re.search(ISO_DATE_PATTERN, channel_name, re.IGNORECASE):
        return None
    if re.search(ISO_PAREN_DATETIME_PATTERN, channel_name, re.IGNORECASE):
        return None
    if re.search(ISO_PIPE_DATE_PATTERN, channel_name, re.IGNORECASE):
        return None
    if re.search(DDMM_DATE_PATTERN, channel_name, re.IGNORECASE):
        return None
    if START_STOP_PATTERN.search(channel_name):
        return None
    if re.search(WEEKDAY_PATTERN, channel_name, re.IGNORECASE):
        return None

    parsed = parse_trailing_time_only(channel_name)
    if not parsed:
        return None
    hour, minute, ampm = parsed
    hour, minute = apply_ampm(hour, minute, ampm)
    if hour >= 24:
        return None
    return reference.replace(hour=hour, minute=minute, second=0, microsecond=0)


def has_date_signal(channel_name: str) -> bool:
    """True when the title plausibly contains a date/time (not just team names)."""
    if not channel_name or not channel_name.strip():
        return False
    if START_STOP_PATTERN.search(channel_name):
        return True
    if ISO_DATE_LOOSE_PATTERN.search(channel_name):
        return True
    if re.search(_MONTH_SIGNAL, channel_name, re.IGNORECASE):
        return True
    if re.search(_DAY_MONTH_SIGNAL, channel_name, re.IGNORECASE):
        return True
    if re.search(_FULL_MONTH_SIGNAL, channel_name, re.IGNORECASE):
        return True
    if re.search(DDMM_DATE_PATTERN, channel_name, re.IGNORECASE):
        return True
    if re.search(WEEKDAY_PATTERN, channel_name, re.IGNORECASE):
        return True
    if re.search(TIME_ONLY_PATTERN, channel_name, re.IGNORECASE):
        return True
    return False


def is_date_far_future(event_date: datetime, reference: datetime, *, max_days: int = 365) -> bool:
    """Reject placeholder or garbage dates far beyond the reference window."""
    if event_date.year >= 2098:
        return True
    max_future = reference + timedelta(days=max_days)
    return event_date > max_future


def is_within_reasonable_range(
    date: datetime,
    reference: datetime,
    *,
    max_days: int = 365,
) -> bool:
    """True when ``date`` is within ±max_days of ``reference``."""
    return abs((date - reference).days) <= max_days


def make_far_future_guard(reference: datetime) -> Callable[[datetime], bool]:
    return lambda dt: is_date_far_future(dt, reference)
