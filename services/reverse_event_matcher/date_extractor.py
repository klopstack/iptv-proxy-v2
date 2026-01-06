"""
Date Extraction Component

Extracts dates from channel names using the dateparser library.
Much more robust and handles more formats than custom regex patterns.
"""

import re
from datetime import datetime, timezone
from typing import Optional

import dateparser  # type: ignore
from dateparser.search import search_dates  # type: ignore


class DateExtractor:
    """
    Extracts dates from channel names using the dateparser library.

    This replaces custom regex patterns with a battle-tested library that:
    - Handles many more date formats automatically
    - Better handles ambiguous dates
    - Provides timezone support
    - Reduces code complexity and maintenance
    """

    def __init__(self):
        """Initialize with dateparser settings optimized for channel names."""
        # Settings optimized for extracting dates from messy channel names
        # Default settings for general date parsing (uses future preference)
        self.dateparser_settings = {
            "PREFER_DATES_FROM": "future",  # Sports events are typically upcoming
            "RELATIVE_BASE": datetime.now(timezone.utc).replace(tzinfo=None),
            "RETURN_AS_TIMEZONE_AWARE": False,  # Return naive datetime for consistency
            "STRICT_PARSING": False,  # Be lenient with formats
            "PARSERS": ["absolute-time", "timestamp", "relative-time", "custom-formats"],
        }

        # Settings specifically for ISO dates (YYYY-MM-DD) - unambiguous format
        self.iso_dateparser_settings = {
            **self.dateparser_settings,
            "DATE_ORDER": "YMD",  # ISO format is always Year-Month-Day
        }

        # Pre-compiled patterns for various date formats
        # Priority order: ISO dates, then explicit timestamps, then DD/MM, then natural language
        self.iso_date_pattern = re.compile(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)\b")
        self.timestamp_pattern = re.compile(
            r"(?:start:|stop:)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)", re.IGNORECASE
        )
        # Pattern for DD/MM HH:MM or DD/MM time format (e.g., "23/10 19:05", "15/11 8:00pm")
        self.ddmm_time_pattern = re.compile(
            r"\b(\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b", re.IGNORECASE
        )
        # Pattern to find a leading year (e.g., "2025 Ottawa 67s vs Windsor...")
        # Matches 4-digit year at start or after common prefixes, followed by non-digit
        self.leading_year_pattern = re.compile(r"^(\d{4})\s+\D", re.IGNORECASE)

    def extract_date(self, channel_name: str) -> Optional[datetime]:
        """
        Extract a date/time from a channel name.

        Uses multiple strategies in priority order:
        1. Look for explicit start:/stop: timestamps (most reliable)
        2. Look for ISO-format dates (YYYY-MM-DD)
        3. Look for DD/MM time format (e.g., "23/10 19:05")
        4. Search for dates embedded in text (handles natural language)

        Args:
            channel_name: Channel name that may contain date information

        Returns:
            datetime if found, None otherwise (naive datetime, no timezone)
        """
        if not channel_name:
            return None

        # Strategy 1: Try explicit start:/stop: timestamps first (most reliable)
        timestamp_match = self.timestamp_pattern.search(channel_name)
        if timestamp_match:
            date_str = timestamp_match.group(1)
            # Timestamps are in ISO format, use YMD order
            parsed = dateparser.parse(date_str, settings=self.iso_dateparser_settings)
            if parsed and self._validate_date_range(parsed):
                return parsed

        # Strategy 2: Look for ISO-format dates (YYYY-MM-DD with optional time)
        iso_match = self.iso_date_pattern.search(channel_name)
        if iso_match:
            date_str = iso_match.group(1)
            # ISO dates use YMD order explicitly
            parsed = dateparser.parse(date_str, settings=self.iso_dateparser_settings)
            if parsed and self._validate_date_range(parsed):
                return parsed

        # Strategy 3: Look for DD/MM time format (e.g., "23/10 19:05")
        # This format is common in channel names but dateparser may miss it
        # Check for a leading year first (e.g., "2025 Ottawa 67s vs Windsor - 23/10 19:05")
        ddmm_match = self.ddmm_time_pattern.search(channel_name)
        if ddmm_match:
            day, month, hour, minute, ampm = ddmm_match.groups()
            day, month, hour, minute = int(day), int(month), int(hour), int(minute)

            # Handle AM/PM
            if ampm:
                ampm = ampm.lower()
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

            # Determine year - first check for leading year in channel name
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            leading_year_match = self.leading_year_pattern.match(channel_name)

            if leading_year_match:
                # Use the year from the beginning of the string
                year = int(leading_year_match.group(1))
            else:
                # Fall back to current year with rollover logic
                year = now.year

            try:
                parsed = datetime(year, month, day, hour, minute)

                # Only apply rollover logic if we didn't find an explicit year
                # If date is more than 7 days in the past, try next year
                if not leading_year_match and (parsed - now).days < -7:
                    parsed = datetime(year + 1, month, day, hour, minute)

                if self._validate_date_range(parsed):
                    return parsed
            except ValueError:
                pass  # Invalid date, continue to other strategies

        # Strategy 4: Use search_dates to find dates embedded in text
        # This handles formats like "Sat 15 Mar 21:00", "28 Dec 8:00pm", etc.
        found_dates = search_dates(channel_name, settings=self.dateparser_settings, languages=["en"])

        if found_dates:
            # search_dates returns list of (date_string, datetime) tuples
            # Take the first match
            _, parsed = found_dates[0]
            # Convert to naive datetime if timezone-aware
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            if self._validate_date_range(parsed):
                return parsed

        return None

    def _validate_date_range(self, date: datetime) -> bool:
        """
        Validate that a parsed date is within a reasonable range.

        Args:
            date: Parsed datetime to validate

        Returns:
            True if date is within reasonable range (±1 year), False otherwise
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_diff = abs((date - now).days)
        return days_diff <= 365
