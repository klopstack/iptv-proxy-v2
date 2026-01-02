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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PPVEventExtractor:
    """Extracts event information from PPV channel names using regex patterns."""

    # Competitor pattern: team names separated by vs/at/@ with optional periods
    # Special handling for 'vs' to allow comma-separated player names (tennis, etc.)
    # Allows commas in team names for multi-player events, non-greedy second group for 'vs'
    # For other separators (at/@/-), uses greedy matching with different lookahead
    # Two-branch pattern:
    # Branch 1 (groups 1,2): "vs" with optional commas (for tennis: "Federer, Roger vs Nadal, Rafael @ time")
    # Branch 2 (groups 3,4): "at/@/versus/-" without commas (other sports)
    COMPETITOR_PATTERN = r"([#A-Za-z0-9\s&\'\-,]+?)\s+(?:vs\.?)\s+([#A-Za-z0-9\s&\'\-,\.]+?)(?=\s*[@|(\[]|$)|([#A-Za-z0-9\s&\'-]+?)\s+(?:at\.?|versus|@|-)\s+([#A-Za-z0-9\s&\'-\-\.]+?)(?=\s*[-|(\[]|$)"

    # Placeholder pattern: channels marked as "NO EVENT STREAMING"
    NO_EVENT_PATTERN = r"NO EVENT STREAMING"

    # Date pattern: "Month DD HH:MM" or "Month DD HH:MM AM/PM" or "Month DDth HH:MM AM/PM"
    # Handles ordinal suffixes (st, nd, rd, th) optionally
    DATE_PATTERN = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{1,2}):(\d{2})(?:\s+(AM|PM))?"

    # ISO date pattern: "YYYY-MM-DD HH:MM"
    ISO_DATE_PATTERN = r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})"

    # Day of week pattern: "Mon", "Tue", "Wed", etc.
    WEEKDAY_PATTERN = r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b"

    # Time-only pattern: "HH:MM", "HH:MMam", "9:00am"
    TIME_ONLY_PATTERN = r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm))?\b"

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
        Check if event date is too far in the future (>1 year).

        Events more than a year away are likely placeholders or
        not actually being broadcast.

        Args:
            event_date: Event datetime to check

        Returns: True if date is more than 1 year in the future
        """
        from datetime import timedelta

        max_future = self.current_date + timedelta(days=365)
        return event_date > max_future

    def extract_competitors(self, channel_name: str) -> Optional[Tuple[str, str]]:
        """
        Extract competitor/team names from channel name.

        Returns (competitor1, competitor2) or None if no match found.

        Examples:
        - "Arsenal vs Brighton @ Dec 27" -> ("Arsenal", "Brighton")
        - "Vegas Golden Knights @ Colorado Avalanche" -> ("Vegas Golden Knights", "Colorado Avalanche")
        - "Federer, Roger vs Nadal, Rafael" -> ("Federer, Roger", "Nadal, Rafael")
        """
        # Skip placeholders
        if self.is_placeholder(channel_name):
            return None

        # Try to find competitor match
        match = re.search(self.COMPETITOR_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None

        # Handle alternate patterns: (vs with comma) vs (other separators without comma)
        # vs pattern has groups 1,2; other separators have groups 3,4
        if match.group(1) is not None:
            # 'vs' pattern matched (groups 1, 2)
            comp1 = match.group(1).strip()
            comp2 = match.group(2).strip()
        else:
            # Other separator pattern matched (groups 3, 4)
            comp1 = match.group(3).strip()
            comp2 = match.group(4).strip()

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

                # If date is in the past, try next year
                if dt < datetime.now():
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

        Returns dict with keys: competitors, date, weekday, is_placeholder, inferred_how, is_inactive
        """
        result: Dict = {
            "is_placeholder": self.is_placeholder(channel_name),
            "is_inactive": self.is_inactive_channel(channel_name),
            "competitors": self.extract_competitors(channel_name),
            "date": None,
            "weekday": None,
            "time_only": None,
            "raw_name": channel_name,
            "inferred_how": None,  # How date was inferred
        }

        # Skip placeholders and inactive channels early
        if result["is_placeholder"] or result["is_inactive"]:
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


class EventMatchingStrategy:
    """Base class for event matching strategies."""

    def match(self, extractor: PPVEventExtractor, channel_name: str, thesportsdb_service) -> Optional[Dict]:
        """
        Attempt to match channel to event.

        Returns dict with: event_id, confidence, method, or None if no match.
        """
        raise NotImplementedError


class DirectSearchStrategy(EventMatchingStrategy):
    """Tier 1: Direct search using parsed team names."""

    def match(self, extractor: PPVEventExtractor, channel_name: str, thesportsdb_service) -> Optional[Dict]:
        """
        Extract competitor names and search TheSportsDB directly.

        Cost: 1 API call if attempted.
        """
        competitors = extractor.extract_competitors(channel_name)
        if not competitors:
            return None

        home_team, away_team = competitors

        try:
            # Search TheSportsDB for this matchup
            event = thesportsdb_service.match_channel_to_event(home_team, away_team)
            if event:
                return {
                    "event_id": event.get("idEvent"),
                    "confidence": 0.95,  # High confidence for direct match
                    "method": "direct_search",
                    "home_team": home_team,
                    "away_team": away_team,
                }
        except Exception as e:
            logger.debug(f"Direct search failed for '{channel_name}': {e}")

        return None


class CalendarBrowseStrategy(EventMatchingStrategy):
    """Tier 2: Calendar browse using extracted date."""

    def match(self, extractor: PPVEventExtractor, channel_name: str, thesportsdb_service) -> Optional[Dict]:
        """
        Extract date and browse TheSportsDB calendar for events on that date.

        Cost: 1 HTTP call per unique date (browse_calendar endpoint).
        Then 1 API call per event fetched for details.
        """
        # Extract date and competitors
        date = extractor.extract_date(channel_name)
        competitors = extractor.extract_competitors(channel_name)

        if not date or not competitors:
            return None

        home_team, away_team = competitors

        try:
            # Browse calendar for events on this date
            events = thesportsdb_service.browse_calendar_for_date(date.strftime("%Y-%m-%d"))

            if not events:
                return None

            # Try to find matching event by team names
            for event in events:
                event_home = event.get("strHomeTeam", "").lower()
                event_away = event.get("strAwayTeam", "").lower()

                if self._teams_match(home_team.lower(), away_team.lower(), event_home, event_away):
                    return {
                        "event_id": event.get("idEvent"),
                        "confidence": 0.85,  # Slightly lower confidence (date-based match)
                        "method": "calendar_browse",
                        "date": date.isoformat(),
                        "home_team": event_home,
                        "away_team": event_away,
                    }
        except Exception as e:
            logger.debug(f"Calendar browse failed for '{channel_name}': {e}")

        return None

    def _teams_match(self, home1: str, away1: str, home2: str, away2: str) -> bool:
        """Check if team pairs match (either order)."""
        # Exact match
        if (home1 == home2 and away1 == away2) or (home1 == away2 and away1 == home2):
            return True

        # Partial match (team names can be shortened)
        # e.g., "vegas" matches "vegas golden knights"
        home1_words = home1.split()
        away1_words = away1.split()
        home2_words = home2.split()
        away2_words = away2.split()

        # Check if home1 is a prefix of home2 (or vice versa)
        if (all(w in home2_words for w in home1_words) or all(w in home1_words for w in home2_words)) and (
            all(w in away2_words for w in away1_words) or all(w in away1_words for w in away2_words)
        ):
            return True

        return False


class EventMatcher:
    """
    Matches PPV channels to TheSportsDB events using tiered strategies.

    Strategy order:
    1. Filter placeholders (cost: 0)
    2. Try Direct Search (cost: 1 API call)
    3. Try Calendar Browse (cost: 1 HTTP call + API calls for details)
    4. Skip if no match (cost: 0)
    """

    def __init__(self, thesportsdb_service):
        """Initialize matcher with TheSportsDB service."""
        self.extractor = PPVEventExtractor()
        self.thesportsdb_service = thesportsdb_service
        self.direct_search = DirectSearchStrategy()
        self.calendar_browse = CalendarBrowseStrategy()

    def match(self, channel_name: str) -> Optional[Dict]:
        """
        Attempt to match channel name to TheSportsDB event.

        Returns dict with: event_id, confidence, method, or None if no match.

        Cost: Depends on channel content:
        - Placeholder: 0 API calls
        - Extractable with full data: ~1 API call (direct search)
        - Extractable with partial data: ~1 HTTP call + variable API calls
        - Not extractable: 0 API calls
        """
        # Skip placeholders
        if self.extractor.is_placeholder(channel_name):
            return None

        # Try strategies in order of cost/efficiency
        # Tier 1: Direct search (1 API call)
        result = self.direct_search.match(self.extractor, channel_name, self.thesportsdb_service)
        if result:
            return result

        # Tier 2: Calendar browse (1 HTTP call + API calls)
        result = self.calendar_browse.match(self.extractor, channel_name, self.thesportsdb_service)
        if result:
            return result

        # No match found
        return None

    def analyze_batch(self, channel_names: List[str]) -> Dict:
        """
        Analyze a batch of channel names and generate statistics.

        Returns dict with: total, placeholders, successfully_matched, etc.
        """
        stats: Dict[str, Any] = {
            "total": 0,
            "placeholders": 0,
            "matched_direct": 0,
            "matched_calendar": 0,
            "failed_extraction": 0,
            "matches": [],
            "failures": [],
        }

        for channel_name in channel_names:
            stats["total"] += 1

            # Check for placeholder
            if self.extractor.is_placeholder(channel_name):
                stats["placeholders"] += 1
                continue

            # Try extraction
            match = self.match(channel_name)
            if match:
                stats["matches"].append(
                    {
                        "channel": channel_name,
                        "match": match,
                    }
                )
                if match["method"] == "direct_search":
                    stats["matched_direct"] += 1
                else:
                    stats["matched_calendar"] += 1
            else:
                stats["failures"].append(channel_name)
                stats["failed_extraction"] += 1

        return stats
