"""
PPV Event-Aware Filtering Service

This module provides intelligent filtering for PPV channels based on scheduled events.
Each provider has different encoding for event information - this service abstracts
those differences and provides a unified interface.

Usage:
    service = PPVFilterService(db)
    should_show, event_meta = service.should_show_channel(channel)
"""

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PPVFilterService:
    """
    Intelligent filtering for PPV channels based on event scheduling.

    Supports multiple filtering strategies:
    - ISO_DATETIME: Extract datetime and compare (ESPN+, B1G+, Fanatiz)
    - TEXT_BASED: Check for keywords like "NO EVENT" or "24/7"
    - ALWAYS_SHOW: Traditional channels with no event gating
    - ALWAYS_HIDE: Placeholder/header channels
    """

    def __init__(
        self,
        db=None,
        current_time: Optional[datetime] = None,
        sync_date: Optional[date] = None,
        default_rules: Optional[Dict] = None,
    ):
        """
        Initialize with optional database connection for rule lookup.

        Args:
            db: Database connection (for rule lookup)
            current_time: Current datetime for comparison (defaults to now). Useful for testing.
            sync_date: Date when playlist was last synced. Used for events without explicit dates.
                      Defaults to today. Should be passed from playlist sync timestamp.
            default_rules: Dict of default rules to use when database lookup fails.
                          If not provided, DEFAULT_FILTER_RULES will be used.
        """
        self.db = db
        self.pattern_cache: Dict[str, Any] = {}
        self.compiled_regexes: Dict[str, Any] = {}
        self.current_time = current_time or datetime.now()
        # Use sync_date or default to today
        self.sync_date = sync_date or self.current_time.date()
        # Use provided rules or fall back to class defaults
        self._default_rules = default_rules or getattr(self.__class__, "_class_default_rules", {})

    def should_show_channel(
        self, channel_name: str, category: str, filter_rule: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Determine if a PPV channel should be shown based on its content.

        CRITICAL: This defaults to HIDE for unknown providers to avoid showing
        non-events. For PPV channels, we must be conservative: only show if we
        can confirm an event exists and is in the future.

        Args:
            channel_name: Full channel name from IPTV provider
            category: Category from provider (e.g., "US| ESPN+ PPV")
            filter_rule: PPVEventFilter rule dict. If None, will attempt lookup.

        Returns:
            Tuple of (should_show: bool, event_metadata: dict or None)
            event_metadata contains:
            {
                'event_name': str,
                'start_datetime': datetime,
                'suggested_duration': timedelta,
                'confidence': float (0.0-1.0),
            }
        """

        # First, check for obvious non-event indicators (universal markers)
        if self._is_non_event_channel(channel_name):
            logger.debug(f"Channel marked as non-event (universal patterns): {channel_name[:60]}")
            return False, None

        # If no rule provided, try to look it up
        if filter_rule is None:
            filter_rule = self._get_filter_rule(category)

        # Fall back to default rules if database lookup failed
        if filter_rule is None and hasattr(self, "_default_rules"):
            filter_rule = self._default_rules.get(category)

        # If still no rule, default to HIDE for PPV (conservative)
        if filter_rule is None:
            logger.debug(f"No filter rule for category '{category}', defaulting to HIDE (unknown provider)")
            return False, None

        filter_type = filter_rule.get("filter_type", "ALWAYS_SHOW")

        try:
            if filter_type == "ALWAYS_SHOW":
                return self._handle_always_show(channel_name, filter_rule)

            elif filter_type == "ALWAYS_HIDE":
                return self._handle_always_hide(channel_name, filter_rule)

            elif filter_type == "TEXT_BASED":
                return self._handle_text_based(channel_name, filter_rule)

            elif filter_type == "ISO_DATETIME":
                return self._handle_iso_datetime(channel_name, filter_rule)

            elif filter_type == "RELATIVE_TIME":
                return self._handle_relative_time(channel_name, filter_rule)

            elif filter_type == "DATETIME_24HR":
                return self._handle_datetime_24hr(channel_name, filter_rule)

            else:
                logger.warning(f"Unknown filter type: {filter_type}")
                return False, None  # Hide on unknown filter type

        except Exception as e:
            logger.error(f"Error filtering channel '{channel_name}': {e}")
            # Conservative for PPV: hide on error (don't show potentially non-events)
            logger.debug(f"  Channel: {channel_name[:60]}")
            return False, None

    # ============================================================================
    # Handler Methods for Each Filter Type
    # ============================================================================

    def _is_non_event_channel(self, channel_name: str) -> bool:
        """
        Detect universal non-event indicators that apply across all providers.

        Returns True if channel clearly has no event content.
        These patterns are provider-agnostic and should ALWAYS result in hiding.
        """

        if not channel_name:
            return True

        # Clean the channel name for analysis
        name_lower = channel_name.lower()

        # Universal non-event patterns (provider-agnostic)
        non_event_patterns = [
            r"\bno\s+event\b",  # "NO EVENT"
            r"\bno\s+streaming\b",  # "NO EVENT STREAMING"
            r"\boffline\b",  # "Offline"
            r"\btbd\b",  # "TBD"
            r"^-\s*$",  # Just a dash
            r"^\s*-\s*$",  # Dash with spaces
            r"^\s*\|\s*-\s*",  # Pipe followed by dash (empty slot format)
            r"^\s*\|\s*$",  # Just pipe (completely empty)
            r"[|]\s*-\s*[|]?$",  # Pipe-dash-pipe at end (empty content)
            r"^\s*#+\s*",  # Header marker (#####)
            r"^\s*###\s+",  # Comment/header marker (###)
            r"^:",  # Starts with colon (slot number only)
            r"^\w+\s+\d+\s*:\s*$",  # "Channel 01:" with nothing after
            r"^\w+\s+\|\s+\d+\s+-\s*$",  # "Provider | 01 -" (empty)
        ]

        for pattern in non_event_patterns:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return True

        # Check for mostly empty content after provider/slot prefix
        # E.g., "Rugby 16:|" or "NFL | 01 -"
        # Pattern: content ends with just punctuation/whitespace
        if re.search(r"[\d\s:]+\|\s*-?\s*$", channel_name):
            # Ends with pipe and optional dash - likely empty slot
            return True

        return False

    def _handle_always_show(self, channel_name: str, rule: Dict) -> Tuple[bool, None]:
        """Always show this channel (e.g., Bally Sports regional channels)."""
        return True, None

    def _handle_always_hide(self, channel_name: str, rule: Dict) -> Tuple[bool, None]:
        """Always hide this channel (e.g., header/placeholder channels)."""
        return False, None

    def _handle_text_based(self, channel_name: str, rule: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Text-based filtering with multi-pattern support.

        Rules can define:
        - placeholder_text: Hide if this text found (string or list of strings)
                           Examples: "NO EVENT", "NO EVENT STREAMING", "OFFLINE"
        - always_show_pattern: Show if this text found (string or list)
                             Examples: "24/7", "CONTINUOUS"

        For PPV, defaults to HIDE if neither pattern matches (conservative).
        """

        # Check for "always hide" patterns first (highest priority)
        hide_patterns = rule.get("placeholder_text", [])
        if isinstance(hide_patterns, str):
            hide_patterns = [hide_patterns]

        for hide_pattern in hide_patterns:
            if hide_pattern.lower() in channel_name.lower():
                logger.debug(f"Channel hidden (placeholder pattern '{hide_pattern}'): {channel_name[:60]}")
                return False, None

        # Check for "always show" patterns (second priority)
        show_patterns = rule.get("always_show_pattern", [])
        if isinstance(show_patterns, str):
            show_patterns = [show_patterns]

        for show_pattern in show_patterns:
            if show_pattern.lower() in channel_name.lower():
                logger.debug(f"Channel shown (always-show pattern '{show_pattern}'): {channel_name[:60]}")
                return True, None

        # Default: HIDE for text-based (no explicit event indicator found)
        # This is conservative - we only show if we find proof of event ("24/7") or
        # nothing that indicates missing event
        logger.debug(f"Channel hidden (text-based default - no event indicator): {channel_name[:60]}")
        return False, None

    def _handle_iso_datetime(self, channel_name: str, rule: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Extract ISO datetime from channel name and determine visibility.

        Handles:
        - Placeholder dates (e.g., 2098-12-31 = not scheduled)
        - Past events (should be hidden)
        - Future events (should be shown with EPG metadata)

        CRITICAL: Returns False (HIDE) if datetime cannot be extracted or is invalid.
        For PPV, we must be conservative - only show if we successfully parse a valid future datetime.
        """

        # Extract datetime from channel name
        pattern = rule.get("date_field_pattern")
        if not pattern:
            logger.warning("No date_field_pattern in rule")
            return False, None  # Conservative: HIDE if no pattern

        datetime_str = self.extract_datetime_string(channel_name, pattern)
        if not datetime_str or not datetime_str.strip():
            logger.debug(f"Could not extract datetime from: {channel_name}")
            return False, None  # Conservative: HIDE if can't extract

        # Check for placeholder date (e.g., 2098-12-31)
        placeholder = rule.get("placeholder_date")
        if placeholder and datetime_str.startswith(placeholder):
            logger.debug(f"Placeholder date detected: {datetime_str}")
            return False, None

        # Parse datetime
        event_datetime = self.parse_iso_datetime(datetime_str)
        if not event_datetime:
            logger.warning(f"Could not parse datetime: {datetime_str}")
            return False, None  # Conservative: HIDE if can't parse

        # Check if event is in the past
        if event_datetime < self.current_time:
            logger.debug(f"Event is in the past: {event_datetime}")
            return False, None

        # Event is in the future - show it
        event_meta = self._build_event_metadata(channel_name, event_datetime, rule)
        return True, event_meta

    def _handle_relative_time(self, channel_name: str, rule: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Extract relative time (HH:MM[am/pm] with optional day name).

        Format examples:
        - "1:30pm" → Today at 1:30 PM
        - "5:35am Sun" → Sunday at 5:35 AM
        - "12:00am Wed" → Wednesday at midnight

        Rules should define:
        - time_pattern: Regex to extract time+day (e.g., r'(\\d{1,2}:\\d{2}(?:am|pm|AM|PM))(?:\\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?')

        CRITICAL: Returns False (HIDE) if time cannot be extracted or is empty.
        For PPV, we must be conservative - only show if we successfully parse a valid time.
        """

        pattern = rule.get("time_pattern")
        if not pattern:
            logger.warning("No time_pattern in RELATIVE_TIME rule")
            return False, None  # Conservative: HIDE if no pattern defined

        # Extract time and optional day name
        match = re.search(pattern, channel_name, re.IGNORECASE)
        if not match:
            logger.debug(f"Could not extract relative time from: {channel_name}")
            return False, None  # Conservative: HIDE if no time found

        time_str = match.group(1).strip() if match.group(1) else ""
        day_name = (
            match.group(2).strip().capitalize()
            if match.lastindex is not None and match.lastindex >= 2 and match.group(2)
            else None
        )

        # CRITICAL: Validate extracted time is not empty/whitespace
        if not time_str or not time_str.strip():
            logger.debug(f"Empty time extracted from: {channel_name}")
            return False, None  # Conservative: HIDE empty times

        # Parse time to get hour and minute
        try:
            # Handle both am/pm and AM/PM
            time_parts = re.match(r"(\d{1,2}):(\d{2})(am|pm|AM|PM)", time_str, re.IGNORECASE)
            if not time_parts:
                logger.debug(f"Invalid time format: {time_str}")
                return False, None  # Conservative: HIDE invalid formats

            hour = int(time_parts.group(1))
            minute = int(time_parts.group(2))
            period = time_parts.group(3).lower()

            # Validate hour/minute ranges
            if not (0 <= hour <= 12 and 0 <= minute <= 59):
                logger.debug(f"Time values out of range: {hour}:{minute:02d}{period}")
                return False, None

            # Convert to 24-hour format
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            # Determine the date
            if day_name:
                # Event is on a specific day of the week
                event_date = self._get_next_weekday(day_name)
            else:
                # Event is today
                event_date = self.current_time.date()

            # Combine date and time
            event_datetime = datetime.combine(event_date, datetime.min.time().replace(hour=hour, minute=minute))

            # Check if event is in the past
            if event_datetime < self.current_time:
                logger.debug(f"Relative time event is in the past: {event_datetime}")
                return False, None

            # Event is in the future - show it
            event_meta = self._build_event_metadata(channel_name, event_datetime, rule)
            return True, event_meta

        except (ValueError, AttributeError) as e:
            logger.error(f"Error parsing relative time '{time_str}': {e}")
            return False, None  # Conservative: HIDE on parse error

    def _get_next_weekday(self, day_name: str) -> date:
        """
        Get the next occurrence of a weekday from current_time.

        Args:
            day_name: Day name (e.g., "Mon", "Sun", "Wednesday")

        Returns:
            datetime.date object for the next occurrence of that weekday
        """
        days_map = {
            "monday": 0,
            "mon": 0,
            "tuesday": 1,
            "tue": 1,
            "wednesday": 2,
            "wed": 2,
            "thursday": 3,
            "thu": 3,
            "friday": 4,
            "fri": 4,
            "saturday": 5,
            "sat": 5,
            "sunday": 6,
            "sun": 6,
        }

        target_day = days_map.get(day_name.lower())
        if target_day is None:
            logger.warning(f"Unknown day name: {day_name}")
            return self.current_time.date()

        # Get current weekday (0=Monday, 6=Sunday)
        current_weekday = self.current_time.weekday()

        # Calculate days until target weekday
        days_ahead = target_day - current_weekday

        # If day has already occurred this week, schedule for next week
        if days_ahead <= 0:
            days_ahead += 7

        # Special case: if we're looking for the same day and time hasn't passed,
        # use today (days_ahead = 0)
        if target_day == current_weekday:
            # Same weekday - check if time has passed
            # This will be handled by the past/future check in the caller
            days_ahead = 0

        return self.current_time.date() + timedelta(days=days_ahead)

    def _handle_datetime_24hr(self, channel_name: str, rule: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Handle DATETIME_24HR filter type (Phase 1 & 2).

        Parses both ISO datetime and 24-hour time formats.
        If only time is found (no date), uses sync_date (last playlist sync).

        Rule parameters:
        - allow_no_date: If True, events without explicit dates are shown using sync_date
                        (default: False, hide events without dates for safety)
        - time_pattern: Optional regex pattern to extract time (defaults to internal parsing)

        Returns:
            (True, event_metadata) if event is valid and in the future
            (False, None) otherwise
        """
        rule = rule or {}

        # Extract datetime from channel name
        event_datetime = self.parse_iso_datetime_with_24hr(channel_name)

        if event_datetime is None:
            # No datetime found
            if not rule.get("allow_no_date", False):
                logger.debug(f"No datetime found and allow_no_date=False: {channel_name[:60]}")
                return False, None

            # Phase 1: For certain categories (boxing, wrestling, etc), show even without time
            # This lets us include these events in playlists for manual inspection
            logger.debug(f"No datetime but allow_no_date=True: {channel_name[:60]}")
            event_meta = self._build_event_metadata(
                channel_name,
                datetime.combine(self.sync_date, datetime.min.time()),  # Use sync_date at midnight
                rule,
            )
            return True, event_meta

        # Check if event is in the past
        if event_datetime < self.current_time:
            logger.debug(f"Event datetime is in the past: {event_datetime}")
            return False, None

        # Event is in the future - show it
        event_meta = self._build_event_metadata(channel_name, event_datetime, rule)
        return True, event_meta

    # ============================================================================
    # Utility Methods
    # ============================================================================

    def extract_datetime_string(self, channel_name: str, pattern: str) -> Optional[str]:
        """
        Extract datetime string from channel name using regex pattern.

        Args:
            channel_name: Full channel name
            pattern: Regex pattern with one capture group for datetime

        Returns:
            Extracted datetime string or None if not found

        Example:
            >>> pattern = r'\\((\\d{4}-\\d{2}-\\d{2}\\s[\\d:]+)\\)'
            >>> name = 'Event (2025-12-27 03:35:06)'
            >>> extract_datetime_string(name, pattern)
            '2025-12-27 03:35:06'
        """
        try:
            # Use compiled regex from cache if available
            if pattern not in self.compiled_regexes:
                self.compiled_regexes[pattern] = re.compile(pattern)

            regex = self.compiled_regexes[pattern]
            match = regex.search(channel_name)

            if match:
                return match.group(1).strip()

            return None

        except re.error as e:
            logger.error(f"Invalid regex pattern: {pattern} - {e}")
            return None

    def parse_iso_datetime(self, datetime_str: str) -> Optional[datetime]:
        """
        Parse datetime string to datetime object.

        Handles formats:
        - "2025-12-27 03:35:06" (ISO with space)
        - "2025-12-27T03:35:06" (ISO with T)
        - "2025-12-27T03:35:06Z" (ISO with Z timezone)
        - "2025-12-27T03:35:06+00:00" (ISO with timezone offset)
        - "22/10 19:00" (DD/MM HH:MM - FLO Sports format)
        - "10/22 19:00" (MM/DD HH:MM - US format variant)
        - "2025-12-27 03:35"

        Returns:
            datetime object or None if parsing fails

        Note: For DD/MM formats without year, assumes current or next year.
        """
        if not datetime_str:
            return None

        datetime_str = datetime_str.strip()

        # Try common datetime formats (order matters - more specific first)
        formats = [
            "%Y-%m-%d %H:%M:%S",  # 2025-12-27 03:35:06
            "%Y-%m-%dT%H:%M:%S",  # 2025-12-27T03:35:06
            "%Y-%m-%d %H:%M",  # 2025-12-27 03:35
            "%Y-%m-%dT%H:%M:%S.%f",  # 2025-12-27T03:35:06.123
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(datetime_str, fmt)
                return dt
            except ValueError:
                continue

        # Handle formats without year (DD/MM or MM/DD) with explicit year
        # to avoid deprecation warning about ambiguous leap day parsing
        current_year = self.current_time.year
        year_formats = [
            ("%d/%m %H:%M", True),  # 22/10 19:00 (DD/MM HH:MM) - European format
            ("%m/%d %H:%M", False),  # 10/22 19:00 (MM/DD HH:MM) - US format
        ]

        for fmt, is_european in year_formats:
            try:
                # Parse with explicit year to avoid deprecation warning
                dt = datetime.strptime(f"{current_year} {datetime_str}", f"%Y {fmt}")

                # If month/day is in the past this year, use next year
                if dt < self.current_time:
                    dt = datetime.strptime(f"{current_year + 1} {datetime_str}", f"%Y {fmt}")

                return dt
            except ValueError:
                continue

        # Try Python's fromisoformat (handles ISO 8601 with timezone)
        try:
            return datetime.fromisoformat(datetime_str.replace(" ", "T").rstrip("Z"))
        except (ValueError, AttributeError):
            pass

        logger.warning(f"Could not parse datetime: {datetime_str}")
        return None

    def parse_24hour_time(self, text: str) -> Optional[time]:
        """
        Parse 24-hour time formats from text.

        Supports formats like:
        - "20:30" or "20:30:00" (HH:MM or HH:MM:SS)
        - "20.30" or "20.30.00" (European format)

        Returns the time as datetime.time object, or None if not found.
        """
        # Pattern for HH:MM or HH:MM:SS (colon-separated)
        colon_match = re.search(r"\b([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b", text)
        if colon_match:
            hour = int(colon_match.group(1))
            minute = int(colon_match.group(2))
            second = int(colon_match.group(3)) if colon_match.group(3) else 0
            return time(hour, minute, second)

        # Pattern for HH.MM or HH.MM.SS (dot-separated, European format)
        dot_match = re.search(r"\b([01]\d|2[0-3])\.([0-5]\d)(?:\.([0-5]\d))?\b", text)
        if dot_match:
            hour = int(dot_match.group(1))
            minute = int(dot_match.group(2))
            second = int(dot_match.group(3)) if dot_match.group(3) else 0
            return time(hour, minute, second)

        return None

    def parse_month_day_time(self, text: str) -> Optional[datetime]:
        """
        Parse month-day-time format: "Oct 18 : 11PM" or "October 18 : 11PM".

        Supports:
        - 3-letter abbreviations: Jan, Feb, Mar, ... Dec
        - Full names: January, February, ... December
        - Time in 12-hour format: HH[AM|PM], H[AM|PM]
        - Various separators: space, colon, dash

        Returns datetime with current year (or next year if month/day is in past).
        Uses current_time for year/comparison context.

        Returns:
            datetime object or None if format not found
        """
        # Pattern: Month (abbr or full) Day : Time(am/pm)
        # Example: "Oct 18 : 11PM UK / 6PM ET" → extract "Oct 18 : 11PM"
        month_pattern = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})\s*[:/-]\s*(\d{1,2})\s*([APap][Mm])"

        match = re.search(month_pattern, text)
        if not match:
            return None

        month_str = match.group(1)
        day_str = match.group(2)
        hour_str = match.group(3)
        period = match.group(4).lower()

        # Map month name to number
        months = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }

        month_num = months.get(month_str.lower())
        if not month_num:
            return None

        try:
            day = int(day_str)
            hour = int(hour_str)

            # Validate day range
            if not (1 <= day <= 31):
                return None

            # Validate hour range (12-hour format: 1-12)
            if not (1 <= hour <= 12):
                return None

            # Convert to 24-hour format
            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            # Determine year
            current_year = self.current_time.year
            event_date = date(current_year, month_num, day)

            # If date is in the past this year, use next year
            if event_date < self.current_time.date():
                event_date = date(current_year + 1, month_num, day)

            return datetime.combine(event_date, time(hour, 0, 0))

        except (ValueError, TypeError):
            return None

    def parse_iso_datetime_with_24hr(self, text: str, sync_date_override: Optional[date] = None) -> Optional[datetime]:
        """
        Parse datetime from text, supporting ISO, month-day-time, and 24-hour formats.

        Parsing order (by specificity):
        1. ISO datetime: 2025-01-20 14:00:00
        2. Month-day-time: Oct 18 : 11PM
        3. 24-hour time: 20:30 or 20.30 (uses sync_date)

        If a 24-hour time is found but no date, uses sync_date (last playlist sync)
        or sync_date_override as the reference date.

        Args:
            text: Text to parse
            sync_date_override: Override the instance sync_date for this parse

        Returns:
            datetime object or None if no valid datetime found
        """
        # First try ISO datetime (most specific)
        iso_dt = self.parse_iso_datetime(text)
        if iso_dt:
            return iso_dt

        # Try month-day-time format (Oct 18 : 11PM)
        month_dt = self.parse_month_day_time(text)
        if month_dt:
            return month_dt

        # Try 24-hour time format (20:30 or 20.30)
        time_obj = self.parse_24hour_time(text)
        if time_obj:
            # Use sync_date_override if provided, otherwise use instance sync_date
            reference_date = sync_date_override or self.sync_date

            # Combine date with parsed time
            return datetime.combine(reference_date, time_obj)

        return None

    def extract_event_name(self, channel_name: str, pattern: Optional[str] = None) -> Optional[str]:
        """
        Extract event name from channel name.

        Common patterns:
        - "Provider Name | Event Name (datetime)" → "Event Name"
        - "Provider: Event Name (datetime)" → "Event Name"

        Falls back to extracting text before first datetime/parenthesis.
        """

        if not channel_name:
            return None

        # Try extracting between pipe and datetime
        match = re.search(r"\|\s*([^(]+)\s*\(", channel_name)
        if match:
            return match.group(1).strip()

        # Try extracting before first parenthesis
        match = re.search(r"^(.+?)\s*\(", channel_name)
        if match:
            text = match.group(1).strip()
            # Remove provider prefix if present
            if "|" in text:
                text = text.split("|")[-1].strip()
            return text

        return None

    def _build_event_metadata(self, channel_name: str, event_datetime: datetime, rule: Dict) -> Dict[str, Any]:
        """Build event metadata for EPG generation."""

        event_name = self.extract_event_name(channel_name) or "Event"

        # Determine suggested EPG duration based on event type
        duration = self._estimate_event_duration(channel_name, rule)

        return {
            "event_name": event_name,
            "start_datetime": event_datetime,
            "suggested_duration": duration,
            "confidence": 0.9,  # High confidence for explicit datetime
        }

    def _estimate_event_duration(self, channel_name: str, rule: Dict) -> timedelta:
        """
        Estimate event duration based on sport/category.

        Defaults to 4 hours (most sports events).
        Override for specific providers/sports.
        """

        # Check for sport type hints in channel name
        if any(sport in channel_name.lower() for sport in ["basketball", "soccer", "football", "ice hockey", "hockey"]):
            return timedelta(hours=2.5)

        if "wrestling" in channel_name.lower():
            return timedelta(hours=4)

        if "baseball" in channel_name.lower():
            return timedelta(hours=3)

        # Default
        return timedelta(hours=4)

    def _get_filter_rule(self, category: str) -> Optional[Dict]:
        """
        Look up filter rule from database by category.

        To be implemented with actual database query.
        For now, returns None (caller should provide rule).
        """
        if not self.db:
            return None

        # TODO: Implement database lookup
        # from models import PPVEventFilter
        # rule = PPVEventFilter.query.filter_by(category=category).first()
        # return rule.to_dict() if rule else None

        return None


# ============================================================================
# Predefined Filter Rules (for bootstrapping)
# ============================================================================

DEFAULT_FILTER_RULES = {
    "US| ESPN+ PPV": {
        "filter_type": "ISO_DATETIME",
        "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
        "placeholder_date": "2098-12-31",
        "provider_name": "ESPN+",
    },
    "US| B1G+ PPV": {
        "filter_type": "ISO_DATETIME",
        "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
        "placeholder_date": None,  # No placeholder - always populated
        "provider_name": "B1G+",
    },
    "US| DAZN PPV": {
        "filter_type": "TEXT_BASED",
        "placeholder_text": "NO EVENT STREAMING",
        "provider_name": "DAZN",
    },
    "US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ": {
        "filter_type": "TEXT_BASED",
        "always_show_pattern": "24/7",
        "provider_name": "Entertainment",
    },
    "US| BALLY SPORTS PPV": {
        "filter_type": "ALWAYS_SHOW",
        "provider_name": "Bally Sports",
    },
    "BR| FANATIZ PPV": {
        "filter_type": "ISO_DATETIME",
        "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
        "placeholder_date": None,
        "provider_name": "Fanatiz",
    },
    "US| RUGBY PPV": {
        "filter_type": "RELATIVE_TIME",
        "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
        "provider_name": "Rugby",
    },
    "AU| NRL TV PPV": {
        "filter_type": "RELATIVE_TIME",
        "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
        "provider_name": "NRL",
    },
    "AU| AFL PPV": {
        "filter_type": "RELATIVE_TIME",
        "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Sunday|Saturday))?",
        "provider_name": "AFL",
    },
    "US| LIVE FOOTBALL PPV": {
        "filter_type": "RELATIVE_TIME",
        "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
        "provider_name": "Live Football",
    },
    # Phase 1: Category-specific rules for events without explicit dates
    # These categories show events even without explicit dates (using sync_date)
    "UK| PPV EVENT": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,  # Use sync_date if no date found
        "provider_name": "UK PPV",
    },
    "UK| BOXING PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "Boxing",
    },
    "UK| WRESTLING PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "Wrestling",
    },
    "US| WRESTLING PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "Wrestling",
    },
    "US| MMA PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "MMA",
    },
    "US| UFC PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "UFC",
    },
    "US| WWE PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "WWE",
    },
    "US| AEW PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "AEW",
    },
}

# Set DEFAULT_FILTER_RULES as the class-level default for all instances
PPVFilterService._class_default_rules: Dict[str, Any] = DEFAULT_FILTER_RULES  # type: ignore


# ============================================================================
# Example Usage & Tests
# ============================================================================

if __name__ == "__main__":
    import sys
    from datetime import timedelta

    # Configure logging
    logging.basicConfig(level=logging.DEBUG)

    # Use a mock current time for testing (2025-12-27 to make events "future")
    test_current_time = datetime(2025, 12, 27, 0, 0, 0)
    service = PPVFilterService(current_time=test_current_time)

    print("Testing with current_time = {test_current_time}")

    # Test cases from PPV.list
    test_cases = [
        # ESPN+ PPV
        (
            "US (ESPN+ 001) | Adelaide United vs. Western Sydney Wanderers FC Dec 27 3:35AM ET (2025-12-27 03:35:06)",
            "US| ESPN+ PPV",
            True,
            "ESPN+ - future event (ISO with space)",
        ),
        ("US (ESPN+ 046) |  (2098-12-31 08:00:01)", "US| ESPN+ PPV", False, "ESPN+ - placeholder date"),
        # B1G+ PPV
        (
            "US (BTN+ 001) | Basketball (W): Rutgers at Michigan State (2025-12-28 13:50:00)",
            "US| B1G+ PPV",
            True,
            "B1G+ - future event (ISO with space)",
        ),
        # DAZN PPV
        ("AT: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE", "AT| DAZN PPV", False, "DAZN - NO EVENT marker"),
        # 24/7 Entertainment
        ("US: 24/7  COMEDY MOVIES", "US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ", True, "24/7 - always show"),
        # Bally Sports
        ("US: BALLY SPORTS ARIZONA HD", "US| BALLY SPORTS PPV", True, "Bally Sports - always show"),
        # Fanatiz
        (
            "(Fanatiz 001) | Benin vs Botswana (2025-12-27 07:30:00)",
            "BR| FANATIZ PPV",
            True,
            "Fanatiz - future event (ISO with space)",
        ),
        # FLO Sports with DD/MM format (would be in past, so use future date)
        ("Flo (FLSP) 100: Event - 25/12 19:00", "US| FLO SPORTS PPV", True, "FLO Sports - DD/MM format (future date)"),
        # RUGBY PPV - Time only (today)
        (
            "Rugby 1: Stormers vs Lions 1:30pm",
            "US| RUGBY PPV",
            True,
            "Rugby - time only (today at 1:30pm, future relative time)",
        ),
        # RUGBY PPV - Time with day name (Sunday)
        (
            "Rugby 10: Southland vs Counties Manukau 5:35am Sun",
            "US| RUGBY PPV",
            True,
            "Rugby - time with day (Sunday 5:35am, future relative time)",
        ),
        # NRL TV - Time with day
        (
            "NRL TV 01: Panthers @ Sharks 4:30am Sun UK // 11:30pm Sat ET",
            "AU| NRL TV PPV",
            True,
            "NRL - time with day (Sunday 4:30am, future relative time)",
        ),
    ]

    print("=" * 80)
    print("PPV Filter Service - Test Cases")
    print("=" * 80)

    passed = 0
    failed = 0

    for channel_name, category, expected_show, description in test_cases:
        rule = DEFAULT_FILTER_RULES.get(category)
        if not rule:
            print(f"SKIP: No rule for category '{category}'")
            continue

        should_show, event_meta = service.should_show_channel(channel_name, category, dict(rule))  # type: ignore

        status = "✅ PASS" if should_show == expected_show else "❌ FAIL"

        print(f"\n{status}: {description}")
        print(f"  Category: {category}")
        print(f"  Channel: {channel_name[:70]}...")
        print(f"  Expected: {expected_show}, Got: {should_show}")

        if event_meta:
            print(f"  Event: {event_meta['event_name']} at {event_meta['start_datetime']}")

        if should_show == expected_show:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)

    sys.exit(0 if failed == 0 else 1)
