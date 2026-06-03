"""
Date Extraction Component

Extracts dates from channel names using shared PPV date strategies,
with a guarded dateparser fallback for legacy natural-language formats.
"""

from datetime import datetime, timezone
from typing import List, Optional

import dateparser  # type: ignore
from dateparser.search import search_dates  # type: ignore

from services.ppv.extraction.date_anchor import (
    START_STOP_PATTERN,
    has_date_signal,
    is_within_reasonable_range,
    make_far_future_guard,
)
from services.ppv.extraction.date_strategies import DEFAULT_DATE_STRATEGIES
from services.ppv.extraction.date_strategies.base import DateParseStrategy, parse_date_with_strategies


def _to_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class DateExtractor:
    """
    Extracts dates from channel names.

    Uses the same ordered strategy chain as ``PPVEventExtractor`` so enrichment
    and reverse matching bucket channels on the same calendar day.
    """

    def __init__(
        self, reference_date: Optional[datetime] = None, date_strategies: Optional[List[DateParseStrategy]] = None
    ):
        self.reference_date = reference_date or datetime.now(timezone.utc).replace(tzinfo=None)
        self._strategies: List[DateParseStrategy] = (
            date_strategies if date_strategies is not None else DEFAULT_DATE_STRATEGIES
        )
        self.dateparser_settings = {
            "PREFER_DATES_FROM": "current_period",
            "RELATIVE_BASE": self.reference_date,
            "RETURN_AS_TIMEZONE_AWARE": False,
            "STRICT_PARSING": False,
            "PARSERS": ["absolute-time", "timestamp", "relative-time", "custom-formats"],
        }
        self.iso_dateparser_settings = {
            **self.dateparser_settings,
            "DATE_ORDER": "YMD",
        }

    def extract_date(self, channel_name: str) -> Optional[datetime]:
        """
        Extract a date/time from a channel name.

        Priority:
        1. Explicit start:/stop: timestamps
        2. Shared PPV date strategies (ISO, DD/MM, month/day, time-only today, …)
        3. Guarded dateparser search for remaining natural-language formats
        """
        if not channel_name or not channel_name.strip():
            return None

        timestamp_match = START_STOP_PATTERN.search(channel_name)
        if timestamp_match:
            parsed = dateparser.parse(timestamp_match.group(1), settings=self.iso_dateparser_settings)
            if parsed and self._validate_date_range(_to_naive(parsed)):
                return _to_naive(parsed)

        parsed = parse_date_with_strategies(
            channel_name,
            self._strategies,
            current_date=self.reference_date,
            current_year=self.reference_date.year,
            is_date_far_future=make_far_future_guard(self.reference_date),
        )
        if parsed:
            return parsed

        if not has_date_signal(channel_name):
            return None

        found_dates = search_dates(channel_name, settings=self.dateparser_settings, languages=["en"])
        if found_dates:
            _, parsed = found_dates[0]
            parsed = _to_naive(parsed)
            if self._validate_date_range(parsed):
                return parsed

        return None

    def _validate_date_range(self, date: datetime) -> bool:
        return is_within_reasonable_range(date, self.reference_date)
