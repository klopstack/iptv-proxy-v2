"""
PPV Event Extraction and Matching Service

Extracts event information from PPV channel names and matches them to
TheSportsDB events using configurable strategies.

Strategies:
1. Direct Search: Parse channel name, search TheSportsDB with team names
2. Calendar Browse: Extract date, browse TheSportsDB calendar events
3. Skip: Channel doesn't have enough info to match
"""

import logging
import re
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PPVEventExtractor:
    """Extracts event information from PPV channel names using regex patterns."""

    # Sport/event type patterns - extracted first to clean up channel names
    # Common sports and event types
    SPORT_PATTERN = r"\b(Field\s+Hockey|Ice\s+Hockey|NCAA\s+Football|College\s+Football|NFL|NBA|MLB|MILB|MiLB|NHL|Soccer|Football|Basketball|Volleyball|Tennis|Golf|Cricket|Rugby|Lacrosse|Curling|Skating|Weightlifting|Boxing|MMA|UFC|Wrestling|Judo|Karate|Taekwondo|Gymnastics|Swimming|Track\s+and\s+Field|Cross\s+Country|Rowing|Sailing|Cycling|Triathlon|Badminton|Squash|Table\s+Tennis|Handball|Netball|Australian\s+Rules|American\s+Football|Australian\s+Football)\b"

    # Tournament structure pattern - removes "Round 4 - Game 1" style patterns
    # Matched BEFORE competitor extraction to prevent false matches
    # Matches: Round/Semi/Final + number/letter + dash + Game/Final/etc
    TOURNAMENT_STRUCTURE_PATTERN = r"\b(Round|Quarter|Semi|Final|Group|Stage|Match|Game|Heat|Leg|Lap)\s+(?:\d+[a-z]?|[A-Z])\s*-\s*(?:Final|Game|Match|Heat|Leg|Lap)\b"

    # Competitor pattern: team names separated by vs/at/@/- with optional periods
    # Special handling for 'vs' to allow comma-separated player names (tennis, etc.)
    # Allows commas in team names for multi-player events, non-greedy second group for 'vs'
    # For other separators (at/@/versus/-), uses greedy matching with different lookahead
    # Three-branch pattern:
    # Branch 1 (groups 1,2): "vs" with optional commas (tennis: "Federer, Roger vs Nadal, Rafael")
    # Branch 2 (groups 3,4): "at/@/versus" (most sports)
    # Branch 3 (groups 5,6): "-" separator for teams like "NORTHAMPTON SAINTS - HARLEQUINS"
    # Branch 4 (groups 7,8): "x" separator common in MLB feeds (e.g., "Giants x Rockies")
    # NOTE: Tournament structure (Round 4 - Game 1) is removed via _clean_channel_name() BEFORE matching
    # NOTE: The group capturing team names can include trailing time which gets cleaned by _clean_team_name
    # Uses \w (unicode-aware) instead of [A-Za-z0-9] to support accented characters (Grêmio, São Paulo, etc.)
    # Branch 3 (dash): Uses non-greedy first team and greedy second team to match rightmost pair
    #   when multiple dashes exist (e.g., "PPV 1 - TEAM A - TEAM B" matches "TEAM A - TEAM B")
    COMPETITOR_PATTERN = (
        r"([#\w\s&\'\-,]+?)\s+(?:vs\.?)\s+([#\w\s&\'\-,\.:]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$)"
        r"|([#\w\s&\'-]+?)\s+(?:at\.?|versus|@)\s+([#\w\s&\'-\-\.]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$)"
        r"|([A-Z][A-Za-z\s&\'\-]+?)\s+-\s+([A-Z][A-Za-z\s&\'\-]+)(?=\s*[|@()\[\]]|\s*$)"
        r"|([#\w\s&\'\-,]+?)\s+x\s+([#\w\s&\'\-,\.:]+?)(?=\s*[|@()\[\]]|-\s+[A-Z]|-\s+\d|\s+\d|\s*$|start:)"
    )

    # Pattern to strip trailing time from team names (e.g., "Sudan 16:00pm" -> "Sudan")
    TRAILING_TIME_PATTERN = r"\s+\d{1,2}:\d{2}\s*(?:am|pm)?$"

    # Placeholder pattern: channels marked as "NO EVENT STREAMING"
    NO_EVENT_PATTERN = r"NO EVENT STREAMING"

    # Date pattern: "Month DD HH:MM" or "Month DD HH:MM AM/PM" or "Month DDth HH:MM AM/PM"
    # Handles ordinal suffixes (st, nd, rd, th) optionally
    DATE_PATTERN = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{1,2}):(\d{2})(?:\s+(AM|PM))?"

    # ISO date pattern: "YYYY-MM-DD HH:MM"
    ISO_DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})"

    # DD/MM date pattern: "DD/MM HH:MM" (common in Europe, e.g., "24/10 16:00")
    # Can optionally have year before it: "2025 24/10 16:00"
    # Interprets as day/month, infers year from context or current year
    DDMM_DATE_PATTERN = r"(?:(\d{4})\s+)?(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})"

    # Day of week pattern: "Mon", "Tue", "Wed", etc.
    WEEKDAY_PATTERN = r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b"

    # Time-only pattern: "HH:MM", "HH:MMam", "9:00am"
    TIME_ONLY_PATTERN = r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b"

    # Stop-time token: "stop:YYYY-MM-DD HH:MM[:SS]" — provider-supplied broadcast end time
    STOP_TIME_PATTERN = r"stop:(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"

    # Pipe-delimited weekday+date: "| Sat 31 May 19:05" or "| Tue 23 Dec 01:50"
    # Captures: (day_int, month_abbr, hour, minute)
    PIPE_DATE_PATTERN = (
        r"\|\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}):(\d{2})"
    )

    # Provider/country prefix patterns stripped before competitor extraction
    # Applied iteratively: country code first, then provider+slot
    _COUNTRY_PREFIX_RE = re.compile(r"^[A-Z]{2,3}:\s*", re.IGNORECASE)
    _PROVIDER_SLOT_RE = re.compile(
        r"^(?:DAZN|ESPN\s*(?:PLUS?|\+?)|MAX|TNT|FOX|SKY|BT\s*SPORT|beIN|ELEVEN)\s*(?:PPV\s*)?\d+\s*[-\u2013]\s*",
        re.IGNORECASE,
    )
    _BARE_PPV_SLOT_RE = re.compile(r"^PPV\s*\d+\s*[-\u2013]\s*", re.IGNORECASE)

    def __init__(self, current_date: Optional[datetime] = None):
        """Initialize the extractor.

        Args:
            current_date: Reference date for inferring event dates. Defaults to today.
        """
        self.current_date = current_date or datetime.now()
        self.current_year = self.current_date.year

    def is_placeholder(self, channel_name: str) -> bool:
        """Check if channel is a placeholder (NO EVENT STREAMING)."""
        return bool(re.search(self.NO_EVENT_PATTERN, channel_name, re.IGNORECASE))

    def is_inactive_channel(self, channel_name: str) -> bool:
        """
        Check if channel appears to be inactive (not broadcasting).

        Inactive channels include:
        - Just provider names like "(Fanatiz 012)" with no event info
        - Channels with only generic/placeholder text
        - Channels that are essentially empty of content

        Args:
            channel_name: Channel name to check

        Returns: True if channel looks inactive/not broadcasting
        """
        # Strip whitespace
        name = channel_name.strip()

        # If it's mostly just a provider indicator or empty
        if not name or len(name) < 5:
            return True

        # If it's just parentheses with provider info (e.g., "(Fanatiz 012)")
        if re.match(r"^\([^)]*\)$", name):
            return True

        # If it's just numbers or very generic placeholder-like text
        if re.match(r"^[:\s\d]+$", name):
            return True

        # If it's just a section header with no content (all caps/symbols)
        if re.match(r"^[#*_\s:]+$", name):
            return True

        return False

    def is_date_far_future(self, event_date: datetime) -> bool:
        """
        Check if event date is too far in the future (>1 year) or is a placeholder date.

        Events more than a year away are likely placeholders or
        not actually being broadcast. Also catches common placeholder
        dates used by providers (2098-12-31, 2099-01-01).

        Args:
            event_date: Event datetime to check

        Returns: True if date is more than 1 year in the future or is a placeholder
        """
        from datetime import timedelta

        # Check for common placeholder dates (2098-12-31, 2099-01-01)
        # Providers use these far-future dates to mark inactive/empty slots
        if event_date.year >= 2098:
            return True

        max_future = self.current_date + timedelta(days=365)
        return event_date > max_future

    def extract_sport(self, channel_name: str) -> Tuple[Optional[str], str]:
        """
        Extract sport/event type from channel name.

        Returns: (sport_name, cleaned_name) or (None, original_name) if no match

        Examples:
        - "Regis College vs Mount Holyoke - Field Hockey - 23/10" -> ("Field Hockey", "Regis College vs Mount Holyoke - 23/10")
        - "NCAA Football: Ohio State vs Michigan" -> ("NCAA Football", "Ohio State vs Michigan")
        """
        match = re.search(self.SPORT_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None, channel_name

        sport = match.group(0)
        # Remove the sport from the name, cleaning up extra dashes/spaces
        cleaned = channel_name[: match.start()] + channel_name[match.end() :]
        # Clean up extra dashes and spaces around the removal
        cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)  # Replace multiple dashes
        cleaned = re.sub(r"\s+", " ", cleaned).strip()  # Normalize whitespace

        return sport, cleaned

    def _clean_tournament_structure(self, channel_name: str) -> str:
        """
        Remove tournament structure patterns like "Round 4 - Game 1" from channel name.

        These patterns can be mistaken for competitor matches (e.g., "Round 4 - Game"
        looks like "TEAM A - TEAM B" without proper context).

        Examples:
        - "Round 4 - Game 1: SPO @ MH" -> "SPO @ MH"
        - "Semi - Final: Team A vs Team B" -> "Team A vs Team B"
        """
        cleaned = re.sub(self.TOURNAMENT_STRUCTURE_PATTERN, "", channel_name, flags=re.IGNORECASE)
        # Clean up extra dashes and spaces
        cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)  # Replace multiple dashes
        cleaned = re.sub(r"\s+", " ", cleaned).strip()  # Normalize whitespace
        return cleaned

    @staticmethod
    def _strip_provider_prefix(name: str) -> str:
        """
        Remove provider/country prefix tokens that appear before competitor names.

        Applied iteratively so that "US: DAZN PPV 3 - ..." strips the country code
        first then the provider+slot prefix.

        Examples:
        - "US: DAZN PPV 3 - KANSAS CITY ROYALS @ TEXAS RANGERS"
          -> "KANSAS CITY ROYALS @ TEXAS RANGERS"
        - "UK: ESPN+ 1 - Liverpool @ Manchester City"
          -> "Liverpool @ Manchester City"
        - "PPV 2 - Fury vs Joshua"
          -> "Fury vs Joshua"
        """
        prev = None
        result = name
        while result != prev:
            prev = result
            result = PPVEventExtractor._COUNTRY_PREFIX_RE.sub("", result).strip()
            result = PPVEventExtractor._PROVIDER_SLOT_RE.sub("", result).strip()
            result = PPVEventExtractor._BARE_PPV_SLOT_RE.sub("", result).strip()
        return result

    def extract_competitors(self, channel_name: str) -> Optional[Tuple[str, str]]:
        """
        Extract competitor/team names from channel name.

        Returns (competitor1, competitor2) or None if no match found.

        Examples:
        - "Arsenal vs Brighton @ Dec 27" -> ("Arsenal", "Brighton")
        - "Vegas Golden Knights @ Colorado Avalanche" -> ("Vegas Golden Knights", "Colorado Avalanche")
        - "Federer, Roger vs Nadal, Rafael" -> ("Federer, Roger", "Nadal, Rafael")
        - "NORTHAMPTON SAINTS - HARLEQUINS" -> ("NORTHAMPTON SAINTS", "HARLEQUINS")
        - "MLB 11 | Giants x Rockies start:2026-05-31" -> ("Giants", "Rockies")
        """
        # Skip placeholders
        if self.is_placeholder(channel_name):
            return None

        # First extract sport type to clean up the name
        _, cleaned_name = self.extract_sport(channel_name)

        # Strip provider/country prefixes (e.g. "US: DAZN PPV 3 - ") before matching
        cleaned_name = self._strip_provider_prefix(cleaned_name)

        # Remove tournament structure patterns (Round 4 - Game 1, etc.) to avoid false matches
        cleaned_name = self._clean_tournament_structure(cleaned_name)

        # Try to find competitor match
        match = re.search(self.COMPETITOR_PATTERN, cleaned_name, re.IGNORECASE)
        if not match:
            return None

        # Handle alternate patterns: vs (1,2), at/@ (3,4), dash (5,6), x (7,8)
        if match.group(1) is not None:
            comp1 = match.group(1).strip()
            comp2 = match.group(2).strip()
        elif match.group(3) is not None:
            comp1 = match.group(3).strip()
            comp2 = match.group(4).strip()
        elif match.group(5) is not None:
            comp1 = match.group(5).strip()
            comp2 = match.group(6).strip()
        else:
            comp1 = match.group(7).strip()
            comp2 = match.group(8).strip()

        # Clean up competitor names
        comp1 = self._clean_team_name(comp1)
        comp2 = self._clean_team_name(comp2)

        # Filter out junk matches (e.g., "PPV 1" vs "TEXANS")
        if not self._is_valid_team_name(comp1) or not self._is_valid_team_name(comp2):
            return None

        return (comp1, comp2)

    def extract_date(self, channel_name: str) -> Optional[datetime]:
        """
        Extract date/time from channel name.

        Supports:
        - "YYYY-MM-DD HH:MM" -> ISO format date
        - "Month DD HH:MM" -> This year, specified time
        - "Month DD HH:MM AM/PM" -> This year, specified time with AM/PM
        - "DD/MM HH:MM" -> Day/Month format (European), infers year
        - Day of week + time -> Next occurrence of that day

        Returns datetime object.
        """
        # Try ISO format first: YYYY-MM-DD HH:MM
        iso_match = re.search(self.ISO_DATE_PATTERN, channel_name, re.IGNORECASE)
        if iso_match:
            year, month, day, hour, minute = iso_match.groups()
            try:
                dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                # Check if date is too far in future
                if self.is_date_far_future(dt):
                    return None
                return dt
            except ValueError:
                pass

        # Try DD/MM format: "24/10 16:00" (with optional year anywhere before it)
        ddmm_match = re.search(self.DDMM_DATE_PATTERN, channel_name, re.IGNORECASE)
        if ddmm_match:
            year_str, day, month, hour, minute = ddmm_match.groups()
            try:
                # Use extracted year if directly before date, otherwise look for any year before
                if year_str:
                    year = int(year_str)
                else:
                    # Look for most recent 4-digit year before the DD/MM pattern
                    text_before_date = channel_name[: ddmm_match.start()]
                    year_match = None
                    for m in re.finditer(r"\b(\d{4})\b", text_before_date):
                        year_match = m

                    year = int(year_match.group(1)) if year_match else self.current_year

                dt = datetime(year, int(month), int(day), int(hour), int(minute))

                # Check if date is too far in future
                if self.is_date_far_future(dt):
                    return None

                return dt
            except ValueError:
                # Invalid date (e.g., month > 12)
                pass

        # Try pipe-delimited weekday + "DD Month HH:MM" format:
        # "| Sat 31 May 19:05", "| Tue 23 Dec 01:50"
        pipe_match = re.search(self.PIPE_DATE_PATTERN, channel_name, re.IGNORECASE)
        if pipe_match:
            day_str, month_abbr, hour_str, minute_str = pipe_match.groups()
            month = self._month_to_num(month_abbr)
            try:
                dt = datetime(self.current_year, month, int(day_str), int(hour_str), int(minute_str))
                today = self.current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                if dt.replace(hour=0, minute=0, second=0, microsecond=0) < today:
                    dt = dt.replace(year=self.current_year + 1)
                if not self.is_date_far_future(dt):
                    return dt
            except ValueError:
                pass

        # Try month + day + time format
        match = re.search(self.DATE_PATTERN, channel_name, re.IGNORECASE)
        if match:
            month_str, day, hour, minute, ampm = match.groups()
            month = self._month_to_num(month_str)

            # Handle AM/PM
            hour = int(hour)
            if ampm:
                ampm = ampm.upper()
                if ampm == "PM" and hour != 12:
                    hour += 12
                elif ampm == "AM" and hour == 12:
                    hour = 0

            try:
                # Create datetime for this year
                dt = datetime(self.current_year, month, int(day), hour, int(minute))

                # If the calendar date is before today, assume next year.
                # Compare dates only — same-day games stay on today's date even if
                # the listed time has already passed (common for MILB/MLB PPV listings).
                today = self.current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                event_day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                if event_day < today:
                    dt = dt.replace(year=self.current_year + 1)

                return dt
            except ValueError:
                # Invalid date
                pass

        return None

    def extract_weekday(self, channel_name: str) -> Optional[str]:
        """Extract day of week if present (e.g., 'Sat', 'Sun')."""
        match = re.search(self.WEEKDAY_PATTERN, channel_name, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def extract_time_only(self, channel_name: str) -> Optional[Tuple[int, int, Optional[str]]]:
        """
        Extract time without date (e.g., '9:00am', '14:30').

        Returns (hour, minute, ampm) where ampm is 'am' or 'pm' or None.
        Cost: 0 API calls (regex only).
        """
        # Try to find time pattern
        match = re.search(self.TIME_ONLY_PATTERN, channel_name, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            ampm = match.group(3).lower() if match.group(3) else None
            return (hour, minute, ampm)
        return None

    @staticmethod
    def extract_stop_time(channel_name: str) -> Optional[datetime]:
        """
        Extract provider-supplied stop time from channel name.

        Parses 'stop:YYYY-MM-DD HH:MM[:SS]' tokens present on live broadcast feeds.

        Examples:
        - "MLB 10 | Royals x Rangers start:2026-05-31 19:35:00 stop:2026-06-01 02:48:20"
          -> datetime(2026, 6, 1, 2, 48, 20)

        Returns: naive datetime (UTC), or None if token absent or unparseable.
        """
        match = re.search(PPVEventExtractor.STOP_TIME_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        try:
            ts = match.group(1).strip()
            if ts.count(":") == 2:
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return datetime.strptime(ts, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def infer_date_from_time(self, hour: int, minute: int, ampm: Optional[str] = None) -> datetime:
        """
        Infer a date from time-only information.

        Strategy: Use today's date if time is >= current time, otherwise tomorrow.
        This assumes the channel name is listing an upcoming event.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            ampm: 'am' or 'pm' if 12-hour format

        Returns: datetime with inferred date and time.
        """
        # Ensure inputs are integers
        hour = int(hour)
        minute = int(minute)

        # Normalize to 24-hour format
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour != 12:
                hour = hour + 12
            elif ampm == "am" and hour == 12:
                hour = 0

        # Safety check: hour should be 0-23
        hour = hour % 24
        minute = minute % 60

        # Create datetime for today
        candidate = self.current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If time is in the past, use tomorrow
        if candidate < self.current_date:
            from datetime import timedelta

            candidate = candidate + timedelta(days=1)

        return candidate

    def infer_date_from_weekday(self, weekday: str) -> Optional[datetime]:
        """
        Infer a date from weekday name.

        Strategy: Find the next occurrence of the given weekday from today.

        Args:
            weekday: Day abbreviation ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')

        Returns: datetime for next occurrence of that weekday, or None if invalid weekday.
        """
        weekday = weekday.lower()
        weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        if weekday not in weekday_names:
            return None

        target_weekday = weekday_names.index(weekday)
        current_weekday = self.current_date.weekday()

        # Calculate days until target weekday
        # Python weekday(): Mon=0, Sun=6
        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7

        from datetime import timedelta

        target_date = self.current_date + timedelta(days=days_ahead)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def combine_date_and_time(self, date: datetime, hour: int, minute: int, ampm: Optional[str] = None) -> datetime:
        """
        Combine a date with time information.

        Args:
            date: Date to use (day/month/year)
            hour: Hour (0-23)
            minute: Minute (0-59)
            ampm: 'am' or 'pm' if 12-hour format

        Returns: Combined datetime.
        """
        # Normalize to 24-hour format
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0

        return date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def extract_all(self, channel_name: str) -> Dict:
        """
        Extract all available information from channel name using smart inference.

        Extraction strategies (in order):
        1. Full date (Month DD HH:MM format)
        2. Time + Day of week → Calculate date for next occurrence of weekday + time
        3. Time only → Assume today's date (or tomorrow if time has passed)
        4. Day of week only → Assume midnight on next occurrence
        5. Competitors always extracted if available

        Returns dict with keys: competitors, date, weekday, sport, is_placeholder, inferred_how, is_inactive
        """
        inline_sport, _ = self.extract_sport(channel_name)
        result: Dict = {
            "is_placeholder": self.is_placeholder(channel_name),
            "is_inactive": self.is_inactive_channel(channel_name),
            "competitors": self.extract_competitors(channel_name),
            "sport": inline_sport,
            "date": None,
            "weekday": None,
            "time_only": None,
            "raw_name": channel_name,
            "inferred_how": None,  # How date was inferred
        }

        # Skip placeholders and inactive channels early
        if result["is_placeholder"] or result["is_inactive"]:
            return result

        # Check for far-future placeholder dates (2098-12-31, 2099-01-01) BEFORE date extraction
        # These are common provider placeholders that need special handling
        iso_match = re.search(self.ISO_DATE_PATTERN, channel_name, re.IGNORECASE)
        if iso_match:
            year = iso_match.group(1)
            if int(year) >= 2098:
                result["inferred_how"] = "date_too_far_future"
                return result

        # Strategy 1: Try full date (Month DD HH:MM)
        full_date = self.extract_date(channel_name)
        if full_date:
            # Check if date is too far in the future
            if self.is_date_far_future(full_date):
                result["inferred_how"] = "date_too_far_future"
                return result

            result["date"] = full_date
            result["inferred_how"] = "full_date"
            return result

        # Extract components we might need
        weekday = self.extract_weekday(channel_name)
        time_only = self.extract_time_only(channel_name)

        # Strategy 2: Weekday + Time → Calculate next weekday with time
        if weekday and time_only:
            hour, minute, ampm = time_only
            weekday_date = self.infer_date_from_weekday(weekday)
            if weekday_date:
                result["date"] = self.combine_date_and_time(weekday_date, hour, minute, ampm)
                result["weekday"] = weekday
                result["time_only"] = time_only
                result["inferred_how"] = "weekday_plus_time"
                return result

        # Strategy 3: Time only → Assume today (or tomorrow if time passed)
        if time_only:
            hour, minute, ampm = time_only
            result["date"] = self.infer_date_from_time(hour, minute, ampm)
            result["time_only"] = time_only
            result["inferred_how"] = "time_only_inferred_date"
            return result

        # Strategy 4: Weekday only → Next occurrence at midnight
        if weekday:
            weekday_date = self.infer_date_from_weekday(weekday)
            if weekday_date:
                result["date"] = weekday_date
                result["weekday"] = weekday
                result["inferred_how"] = "weekday_only"
                return result

        return result

    # ========================================================================
    # Helper methods
    # ========================================================================

    def _clean_team_name(self, name: str) -> str:
        """Clean team name by removing common cruft."""
        # Remove trailing time patterns like "16:00pm", "11:55am"
        name = re.sub(self.TRAILING_TIME_PATTERN, "", name, flags=re.IGNORECASE)
        # Remove provider/region codes like ":Viaplay SE", ":Sportsnet+"
        name = re.sub(r":\w+.*$", "", name)
        # Remove leading ranking numbers like "#25" or just "25"
        name = re.sub(r"^#?\s*\d+\s+", "", name)
        # Remove trailing numbers (channel numbers, PPV numbers)
        name = re.sub(r"\s+\d+$", "", name)
        # Normalize whitespace
        name = " ".join(name.split())
        return name.strip()

    def _is_valid_team_name(self, name: str) -> bool:
        """Check if name looks like a valid team/competitor name."""
        # Too short (but allow 2-3 char abbreviations like BYU, MH, SPO)
        if len(name) < 2:
            return False

        # Contains only numbers
        if re.match(r"^[\d\s]+$", name):
            return False

        # Looks like metadata (PPV, HD, etc.)
        if re.match(
            r"^(PPV|HD|ᴴᴰ|ᴿᴬᵂ|RAW|4K|60FPS|Day|Round|Game|Match|Studio|Championship|Bowl|Cup)", name, re.IGNORECASE
        ):
            return False

        # Looks like a number sequence
        if re.match(r"^(Day|Round|Game|Match|Studio)\s*\d+", name, re.IGNORECASE):
            return False

        # All-caps abbreviations that are too short (like SD, HD) - but allow 2-3 char sports codes
        # Only filter out 2-char abbreviations that are tech specs
        if re.match(r"^(SD|HD|FHD)$", name) and len(name) <= 3:
            return False

        # Looks like provider/technology tags
        if re.match(r"(HD|SD|FHD|4K|RAW|PPV)$", name, re.IGNORECASE):
            return False

        return True

    def _month_to_num(self, month_str: str) -> int:
        """Convert month abbreviation to number (1-12)."""
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        return months.get(month_str.lower(), 1)
