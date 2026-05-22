"""
Enhanced PPV Matching Service

Provides improved PPV channel matching by:
1. Extracting dates from channels and fetching event data for those specific dates
2. Falling back to direct TheSportsDB API lookup when reverse matching fails
3. Categorizing channels using patterns from analyze_non_vs_events.py
4. Supporting extended date ranges (up to 1 month ahead)

This service integrates with existing ReverseEventMatcher and TheSportsDBService
to provide a more comprehensive matching experience.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from services.ppv.extraction import PPVEventExtractor
from services.reverse_event_matcher import ReverseEventMatcher, get_reverse_matcher
from services.thesportsdb_calendar_scraper import CalendarEvent, get_calendar_scraper
from services.thesportsdb_service import TheSportsDBService, get_thesportsdb_service

logger = logging.getLogger(__name__)


# Channel categorization patterns (from analyze_non_vs_events.py)
NON_VS_PATTERNS = {
    "tournament": [
        r"\b(world\s+cup|cup\s+\d+|championship|tournament|league|playoff|finals?|semi[- ]?finals?|round\s+\d+)\b",
        r"\b(open|masters|invitational|qualif(ier|ying)?|knockout|bracket)\b",
        r"\b(season\s+\d+|series\s+\d+|week\s+\d+|day\s+\d+)\b",
    ],
    "highlight": [
        r"\b(highlight|recap|review|roundup|summary|replay|rerun|best\s+of|goals?|moments?)\b",
        r"\b(extended\s+highlights?|full\s+match|match\s+highlights?)\b",
    ],
    "documentary": [
        r"\b(documentary|special|feature|biography|profile|story|behind[- ]?the[- ]?scenes)\b",
        r"\b(30\s+for\s+30|history\s+of|untold|legends?|icons?|heroes?)\b",
    ],
    "training": [
        r"\b(training|practice|practice\s+session|friendly|friendly\s+match|preseason|warm[- ]?up)\b",
        r"\b(open\s+practice|media\s+day|press\s+conference)\b",
    ],
    "show": [
        r"\b(talk\s+show|news|magazine|interview|analysis|podcast|radio|show|program|live\s+coverage)\b",
        r"\b(pre[- ]?game|post[- ]?game|game\s+day|preview|kickoff|spotlight)\b",
    ],
    "series": [
        r"\b(episode|ep\.\s+\d+|season\s+\d+\s+episode|series|chapter|part\s+\d+)\b",
    ],
    "player": [
        r"\b(player\s+profile|athlete\s+profile|focus\s+on|featuring|starring|interview\s+with)\b",
        r"\b(all\s+access|locker\s+room|exclusive|behind[- ]?the[- ]?scenes)\b",
    ],
}


class ChannelCategory:
    """Classification of a PPV channel."""

    PLACEHOLDER = "placeholder"
    TOURNAMENT = "tournament"
    HIGHLIGHT = "highlight"
    DOCUMENTARY = "documentary"
    TRAINING = "training"
    SHOW = "show"
    SERIES = "series"
    PLAYER = "player"
    VS_EVENT = "vs_event"  # Likely a vs event that should be matchable
    OTHER = "other"  # Unknown category


class EnhancedMatchResult:
    """Result from enhanced matching."""

    def __init__(
        self,
        event: Optional[CalendarEvent] = None,
        confidence: float = 0.0,
        match_method: str = "none",
        category: str = ChannelCategory.OTHER,
        extracted_data: Optional[Dict[str, Any]] = None,
    ):
        self.event = event
        self.confidence = confidence
        self.match_method = match_method  # reverse, direct_api, calendar_search
        self.category = category
        self.extracted_data = extracted_data or {}

    def __repr__(self):
        if self.event:
            return f"<EnhancedMatchResult {self.event.event_name} ({self.match_method}, {self.confidence:.2f})>"
        return f"<EnhancedMatchResult no_match ({self.category})>"


class EnhancedPPVMatcher:
    """
    Enhanced PPV matching service that combines multiple strategies.

    Matching Pipeline:
    1. Categorize channel (filter out non-matchable content)
    2. Extract date/time and competitors from channel name
    3. Try reverse matching with loaded events
    4. If no match and has date: fetch events for that specific date
    5. If no match and has competitors: try direct TheSportsDB team search
    6. Return best match with confidence and method used
    """

    def __init__(
        self,
        reverse_matcher: Optional[ReverseEventMatcher] = None,
        thesportsdb_service: Optional[TheSportsDBService] = None,
        event_extractor: Optional[PPVEventExtractor] = None,
        default_timezone: str = "America/New_York",
    ):
        self._reverse_matcher = reverse_matcher
        self._thesportsdb_service = thesportsdb_service
        self._extractor = event_extractor or PPVEventExtractor()
        self._default_timezone = default_timezone

        # Cache for fetched dates
        self._date_cache: Set[str] = set()

        # Statistics
        self._stats = {
            "total_attempts": 0,
            "reverse_matches": 0,
            "direct_api_matches": 0,
            "calendar_matches": 0,
            "no_matches": 0,
            "filtered_non_vs": 0,
            "filtered_placeholder": 0,
        }

    @property
    def reverse_matcher(self) -> ReverseEventMatcher:
        """Get or create reverse matcher."""
        if self._reverse_matcher is None:
            self._reverse_matcher = get_reverse_matcher()
        return self._reverse_matcher

    @property
    def thesportsdb_service(self) -> TheSportsDBService:
        """Get or create TheSportsDB service."""
        if self._thesportsdb_service is None:
            self._thesportsdb_service = get_thesportsdb_service()
        return self._thesportsdb_service

    def categorize_channel(self, channel_name: str) -> Tuple[str, str]:
        """
        Categorize a channel by content type.

        Returns: (category, matched_pattern)
        """
        # Check for placeholder patterns first
        if self._is_placeholder(channel_name):
            return ChannelCategory.PLACEHOLDER, "placeholder"

        name_lower = channel_name.lower()

        # Check non-vs patterns
        for category, patterns in NON_VS_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, name_lower, re.IGNORECASE)
                if match:
                    return category, match.group(0)

        # Check if it has vs/at indicators (likely a matchable event)
        if self._extractor.extract_competitors(channel_name):
            return ChannelCategory.VS_EVENT, "competitors_found"

        return ChannelCategory.OTHER, ""

    def _is_placeholder(self, channel_name: str) -> bool:
        """Check if channel is a placeholder/generic channel."""
        name = channel_name.strip()

        # Section headers
        if name.startswith("#"):
            return True

        # No event markers
        if re.search(r"\bNO\s+EVENT\s+STREAMING\b", name, re.IGNORECASE):
            return True

        # Generic numbered channels like "PPV Event 42"
        if re.match(r"^[A-Za-z0-9\s\-]*(?:PPV|Event|Game|Channel|Match)\s+\d+\s*$", name, re.IGNORECASE):
            return True

        # Generic patterns with just numbers at end
        if re.match(r"^[A-Z]{2}:\s*\w+\s+(?:PPV|EVENT)\s+\d+\s*-?\s*$", name, re.IGNORECASE):
            return True

        return False

    def extract_channel_info(self, channel_name: str) -> Dict[str, Any]:
        """
        Extract all useful information from a channel name.

        Returns dict with:
        - competitors: Tuple of team names or None
        - date: datetime or None
        - sport: string or None
        - time_only: (hour, minute, ampm) or None
        - weekday: string or None
        """
        info: Dict[str, Any] = {
            "competitors": None,
            "date": None,
            "sport": None,
            "time_only": None,
            "weekday": None,
        }

        # Extract sport first (cleans the name)
        sport, _ = self._extractor.extract_sport(channel_name)
        info["sport"] = sport

        # Extract competitors
        info["competitors"] = self._extractor.extract_competitors(channel_name)

        # Extract date
        info["date"] = self._extractor.extract_date(channel_name)

        # If no full date, try time-only
        if not info["date"]:
            info["time_only"] = self._extractor.extract_time_only(channel_name)
            info["weekday"] = self._extractor.extract_weekday(channel_name)

        return info

    def ensure_events_loaded(
        self,
        days_ahead: int = 30,
        days_back: int = 21,
        specific_dates: Optional[List[str]] = None,
    ) -> int:
        """
        Ensure events are loaded for the required date range.

        Args:
            days_ahead: Days into future to load
            days_back: Days into past to load
            specific_dates: Additional specific dates to load (YYYY-MM-DD format)

        Returns:
            Number of events loaded
        """
        # Check if base range is already loaded
        if not self.reverse_matcher._events_loaded:
            count = self.reverse_matcher.load_events_for_date_range(
                days_ahead=days_ahead,
                days_back=days_back,
            )
            logger.info(f"Loaded {count} events for base date range")
        else:
            count = self.reverse_matcher._event_index.get_stats().get("events", 0)

        # Load any specific dates that aren't in the cache
        if specific_dates:
            scraper = get_calendar_scraper()
            new_events = []

            for date_str in specific_dates:
                if date_str not in self._date_cache:
                    events = scraper.get_events_for_date(date_str)
                    new_events.extend(events)
                    self._date_cache.add(date_str)
                    logger.debug(f"Fetched {len(events)} events for {date_str}")

            # If we have new events, rebuild indexes
            if new_events:
                # Add to existing index
                # Note: This would need EventIndex to support incremental updates
                # For now, we just log and include them in calendar search
                logger.info(f"Fetched {len(new_events)} events for specific dates")

        return count

    def collect_channel_dates(self, channel_names: List[str]) -> List[str]:
        """
        Extract all unique dates from a list of channel names.

        Useful for pre-loading event data for all dates mentioned in channels.

        Returns list of dates in YYYY-MM-DD format.
        """
        dates = set()

        for channel_name in channel_names:
            date = self._extractor.extract_date(channel_name)
            if date and not self._extractor.is_date_far_future(date):
                dates.add(date.strftime("%Y-%m-%d"))

        return sorted(dates)

    def find_match(
        self,
        channel_name: str,
        min_confidence: float = 0.3,
        skip_non_vs: bool = True,
    ) -> EnhancedMatchResult:
        """
        Find the best match for a channel using all available strategies.

        Args:
            channel_name: PPV channel name to match
            min_confidence: Minimum confidence threshold
            skip_non_vs: Whether to skip channels categorized as non-vs content

        Returns:
            EnhancedMatchResult with best match or categorization
        """
        self._stats["total_attempts"] += 1

        # Step 1: Categorize channel
        category, pattern = self.categorize_channel(channel_name)

        # Filter out placeholders
        if category == ChannelCategory.PLACEHOLDER:
            self._stats["filtered_placeholder"] += 1
            return EnhancedMatchResult(category=category)

        # Optionally filter non-vs content
        if skip_non_vs and category in (
            ChannelCategory.HIGHLIGHT,
            ChannelCategory.DOCUMENTARY,
            ChannelCategory.TRAINING,
            ChannelCategory.SHOW,
            ChannelCategory.PLAYER,
        ):
            self._stats["filtered_non_vs"] += 1
            return EnhancedMatchResult(category=category)

        # Step 2: Extract channel info
        info = self.extract_channel_info(channel_name)

        # Step 3: Try reverse matching first
        result = self._try_reverse_match(channel_name, min_confidence)
        if result and result.confidence >= min_confidence:
            self._stats["reverse_matches"] += 1
            return EnhancedMatchResult(
                event=result.event,
                confidence=result.confidence,
                match_method="reverse",
                category=category,
                extracted_data=info,
            )

        # Step 4: If we have a date, try calendar search for that specific date
        if info["date"]:
            date_str = info["date"].strftime("%Y-%m-%d")
            result = self._try_calendar_search(
                channel_name=channel_name,
                date_str=date_str,
                competitors=info["competitors"],
                min_confidence=min_confidence,
            )
            if result:
                self._stats["calendar_matches"] += 1
                return EnhancedMatchResult(
                    event=result[0],
                    confidence=result[1],
                    match_method="calendar_search",
                    category=category,
                    extracted_data=info,
                )

        # Step 5: If we have competitors, try direct API search
        if info["competitors"]:
            result = self._try_direct_api_search(
                competitors=info["competitors"],
                sport=info["sport"],
                min_confidence=min_confidence,
            )
            if result:
                self._stats["direct_api_matches"] += 1
                return EnhancedMatchResult(
                    event=result[0],
                    confidence=result[1],
                    match_method="direct_api",
                    category=category,
                    extracted_data=info,
                )

        # No match found
        self._stats["no_matches"] += 1
        return EnhancedMatchResult(
            category=category,
            extracted_data=info,
        )

    def _try_reverse_match(self, channel_name: str, min_confidence: float):
        """Try to match using the reverse event matcher."""
        try:
            matches = self.reverse_matcher.find_matches(
                channel_name=channel_name,
                max_results=1,
                min_confidence=min_confidence,
            )
            if matches:
                return matches[0]
        except Exception as e:
            logger.warning(f"Reverse match error: {e}")
        return None

    def _try_calendar_search(
        self,
        channel_name: str,
        date_str: str,
        competitors: Optional[Tuple[str, str]],
        min_confidence: float,
    ) -> Optional[Tuple[CalendarEvent, float]]:
        """Try to find a match by searching calendar for specific date."""
        try:
            scraper = get_calendar_scraper()

            # Get events for the date
            matches = scraper.find_matching_events(
                date=date_str,
                competitors=competitors,
            )

            if matches and matches[0][1] >= min_confidence:
                return matches[0]

        except Exception as e:
            logger.warning(f"Calendar search error: {e}")
        return None

    def _try_direct_api_search(
        self,
        competitors: Tuple[str, str],
        sport: Optional[str],
        min_confidence: float,
    ) -> Optional[Tuple[CalendarEvent, float]]:
        """
        Try to find a match using direct TheSportsDB API search.

        This searches for events by team name when reverse matching fails.
        """
        try:
            # Search for events matching both teams
            result = self.thesportsdb_service.match_channel_to_event(
                channel_name=f"{competitors[0]} vs {competitors[1]}",
            )

            if result:
                # Convert API result to CalendarEvent
                event = self._api_result_to_calendar_event(result)
                if event:
                    return (event, 0.6)  # Medium-high confidence for direct API match

        except Exception as e:
            logger.warning(f"Direct API search error: {e}")
        return None

    def _api_result_to_calendar_event(self, api_result: Dict[str, Any]) -> Optional[CalendarEvent]:
        """Convert TheSportsDB API result to CalendarEvent format."""
        try:
            event_id = api_result.get("idEvent", "")
            if not event_id:
                return None

            return CalendarEvent(
                event_id=str(event_id),
                event_name=api_result.get("strEvent", ""),
                league_name=api_result.get("strLeague", ""),
                time_utc=api_result.get("strTime", ""),
                date=api_result.get("dateEvent", ""),
                home_team=api_result.get("strHomeTeam"),
                away_team=api_result.get("strAwayTeam"),
            )
        except Exception as e:
            logger.warning(f"Error converting API result: {e}")
            return None

    def batch_find_matches(
        self,
        channel_names: List[str],
        min_confidence: float = 0.3,
        skip_non_vs: bool = True,
        preload_dates: bool = True,
    ) -> List[EnhancedMatchResult]:
        """
        Find matches for multiple channels efficiently.

        Pre-loads event data for all dates found in channels before matching.

        Args:
            channel_names: List of channel names to match
            min_confidence: Minimum confidence threshold
            skip_non_vs: Whether to skip non-vs content
            preload_dates: Whether to preload events for extracted dates

        Returns:
            List of EnhancedMatchResult for each channel
        """
        # Preload events for dates found in channels
        if preload_dates:
            dates = self.collect_channel_dates(channel_names)
            if dates:
                logger.info(f"Preloading events for {len(dates)} dates extracted from channels")
                self.ensure_events_loaded(specific_dates=dates)

        # Match each channel
        results = []
        for channel_name in channel_names:
            result = self.find_match(
                channel_name=channel_name,
                min_confidence=min_confidence,
                skip_non_vs=skip_non_vs,
            )
            results.append(result)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get matching statistics."""
        total = self._stats["total_attempts"] or 1
        return {
            **self._stats,
            "match_rate": (
                self._stats["reverse_matches"] + self._stats["direct_api_matches"] + self._stats["calendar_matches"]
            )
            / total,
            "filter_rate": (self._stats["filtered_non_vs"] + self._stats["filtered_placeholder"]) / total,
        }

    def reset_stats(self):
        """Reset statistics counters."""
        for key in self._stats:
            self._stats[key] = 0

    def prefetch_events_for_channels(
        self,
        channel_names: List[str],
        days_ahead: int = 30,
        days_back: int = 7,
    ) -> Dict[str, Any]:
        """
        Pre-fetch event data for dates found in channels and a standard date range.

        This is intended to be called from the scheduler to ensure event data
        is available before matching is needed.

        Args:
            channel_names: List of channel names to extract dates from
            days_ahead: Days into the future to fetch
            days_back: Days into the past to fetch

        Returns:
            Dict with fetch statistics
        """
        stats = {
            "range_dates": 0,
            "channel_dates": 0,
            "total_dates": 0,
            "already_cached": 0,
            "newly_fetched": 0,
            "total_events": 0,
        }

        # Generate standard date range
        now = datetime.now(timezone.utc)
        range_dates = set()
        for i in range(-days_back, days_ahead + 1):
            date = now + timedelta(days=i)
            range_dates.add(date.strftime("%Y-%m-%d"))
        stats["range_dates"] = len(range_dates)

        # Extract dates from channels
        channel_dates = set(self.collect_channel_dates(channel_names))
        stats["channel_dates"] = len(channel_dates)

        # Combine all dates
        all_dates = range_dates | channel_dates
        stats["total_dates"] = len(all_dates)

        # Fetch events for each date
        scraper = get_calendar_scraper()
        for date_str in sorted(all_dates):
            # Check if already cached
            cache_key = scraper._get_cache_key(date_str, "")
            if scraper._is_cache_valid(cache_key):
                stats["already_cached"] += 1
                events, _ = scraper._cache[cache_key]
                stats["total_events"] += len(events)
                self._date_cache.add(date_str)
            else:
                try:
                    events = scraper.get_events_for_date(date_str)
                    stats["newly_fetched"] += 1
                    stats["total_events"] += len(events)
                    self._date_cache.add(date_str)
                    logger.debug(f"Fetched {len(events)} events for {date_str}")
                except Exception as e:
                    logger.warning(f"Failed to fetch events for {date_str}: {e}")

        # Also ensure events are loaded in reverse matcher
        if not self.reverse_matcher._events_loaded:
            self.reverse_matcher.load_events_for_date_range(
                days_ahead=days_ahead,
                days_back=days_back,
            )

        logger.info(
            f"Prefetch complete: {stats['total_dates']} dates, "
            f"{stats['newly_fetched']} newly fetched, "
            f"{stats['total_events']} total events"
        )

        return stats

    @classmethod
    def prefetch_for_account(cls, account_id: int, days_ahead: int = 30, days_back: int = 7) -> Dict[str, Any]:
        """
        Pre-fetch event data for a specific account's PPV channels.

        This is a convenience method for the scheduler.

        Args:
            account_id: Account ID to fetch channels for
            days_ahead: Days into the future to fetch
            days_back: Days into the past to fetch

        Returns:
            Dict with fetch statistics
        """
        from models import Channel

        # Get PPV channel names for this account (non-placeholder only)
        channels = Channel.query.filter(
            Channel.account_id == account_id,
            Channel.is_ppv == True,  # noqa: E712
            ~Channel.name.like("%NO EVENT STREAMING%"),
        ).all()

        channel_names = [c.name for c in channels]

        matcher = get_enhanced_ppv_matcher()
        return matcher.prefetch_events_for_channels(
            channel_names=channel_names,
            days_ahead=days_ahead,
            days_back=days_back,
        )

    @classmethod
    def prefetch_all_accounts(cls, days_ahead: int = 30, days_back: int = 7) -> Dict[str, Any]:
        """
        Pre-fetch event data for all enabled accounts' PPV channels.

        This is intended to be called from the scheduler.

        Args:
            days_ahead: Days into the future to fetch
            days_back: Days into the past to fetch

        Returns:
            Dict with aggregate fetch statistics
        """
        from models import Account, Channel

        # Get all enabled accounts
        accounts = Account.query.filter_by(enabled=True).all()
        account_ids = [a.id for a in accounts]

        # Get all PPV channel names across all accounts
        channels = Channel.query.filter(
            Channel.account_id.in_(account_ids),
            Channel.is_ppv == True,  # noqa: E712
            ~Channel.name.like("%NO EVENT STREAMING%"),
        ).all()

        channel_names = [c.name for c in channels]

        logger.info(f"Prefetching events for {len(channel_names)} PPV channels from {len(accounts)} accounts")

        matcher = get_enhanced_ppv_matcher()
        return matcher.prefetch_events_for_channels(
            channel_names=channel_names,
            days_ahead=days_ahead,
            days_back=days_back,
        )


# Global instance
_enhanced_matcher: Optional[EnhancedPPVMatcher] = None


def get_enhanced_ppv_matcher() -> EnhancedPPVMatcher:
    """Get or create the global enhanced PPV matcher instance."""
    global _enhanced_matcher
    if _enhanced_matcher is None:
        _enhanced_matcher = EnhancedPPVMatcher()
    return _enhanced_matcher
