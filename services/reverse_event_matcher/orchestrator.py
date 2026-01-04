"""
Refactored Reverse Event Matcher - Orchestrator

Integrates all components to provide a clean, testable architecture:
- TextProcessor: Text normalization and tokenization
- DateExtractor: Date extraction from channel names
- EventIndex: Event indexing for O(1) lookups
- MatchStrategy: Composable matching strategies
- MatchFilter: Result filtering and post-processing

This replaces the original 1148-line monolithic ReverseEventMatcher class.
"""

import logging
from typing import List, Optional

from services.reverse_event_matcher.date_extractor import DateExtractor
from services.reverse_event_matcher.event_index import EventIndex
from services.reverse_event_matcher.match_filter import DateFilter, MatchFilter
from services.reverse_event_matcher.match_strategy import (
    EventNameMatchStrategy,
    LastNameMatchStrategy,
    LeagueMatchStrategy,
    MatchResult,
    TeamMatchStrategy,
    WordMatchStrategy,
)
from services.reverse_event_matcher.text_processor import TextProcessor
from services.thesportsdb_calendar_scraper import CalendarEvent, TheSportsDBCalendarScraper

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE = 0.8
MEDIUM_CONFIDENCE = 0.5
LOW_CONFIDENCE = 0.3


class ReverseEventMatcher:
    """
    Orchestrates event matching using composable components.

    Instead of parsing channel names to find events, this service:
    1. Pre-loads calendar events for a date range (past and future)
    2. Builds search indexes from event data (teams, event names, leagues)
    3. Searches for known event data within channel names
    4. Extracts dates from channel names to improve matching
    5. Returns matches with confidence scores

    This approach works better for:
    - Messy channel name formats
    - Non-standard naming conventions
    - Events without traditional "Team A vs Team B" format
    - Tournament events, races, individual sports
    - Replays of past events
    """

    def __init__(
        self,
        calendar_scraper: Optional[TheSportsDBCalendarScraper] = None,
        text_processor: Optional[TextProcessor] = None,
        date_extractor: Optional[DateExtractor] = None,
        event_index: Optional[EventIndex] = None,
        match_filter: Optional[MatchFilter] = None,
        default_timezone: str = "America/New_York",
    ):
        """
        Initialize the reverse matcher.

        Args:
            calendar_scraper: Optional scraper instance (creates one if None)
            text_processor: Optional text processor (creates default if None)
            date_extractor: Optional date extractor (creates default if None)
            event_index: Optional event index (creates default if None)
            match_filter: Optional match filter (creates default if None)
            default_timezone: IANA timezone for naive datetimes
        """
        self._scraper = calendar_scraper
        self._text_processor = text_processor or TextProcessor()
        self._date_extractor = date_extractor or DateExtractor()
        self._event_index = event_index or EventIndex(self._text_processor)
        self._match_filter = match_filter or MatchFilter(default_timezone=default_timezone)

        # Initialize match strategies (instantiate without arguments)
        self._strategies = [
            TeamMatchStrategy(),
            LastNameMatchStrategy(),
            EventNameMatchStrategy(),
            LeagueMatchStrategy(),
            WordMatchStrategy(),
        ]

        # Track whether events have been loaded
        self._events_loaded = False
        self._load_date_range: Optional[tuple[str, str]] = None

    @property
    def scraper(self) -> TheSportsDBCalendarScraper:
        """Get or create the calendar scraper."""
        if self._scraper is None:
            from services.thesportsdb_calendar_scraper import get_calendar_scraper

            self._scraper = get_calendar_scraper()
        return self._scraper

    def load_events_for_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_ahead: int = 14,
        days_back: int = 21,
        sports: Optional[List[str]] = None,
    ) -> int:
        """
        Load calendar events for a date range and build search indexes.

        Args:
            start_date: Start date in YYYY-MM-DD format (default: today - days_back)
            end_date: End date in YYYY-MM-DD format (default: today + days_ahead)
            days_ahead: Days into future if end_date not specified
            days_back: Days into past if start_date not specified
            sports: Optional list of sports to filter by

        Returns:
            Number of events loaded
        """
        from datetime import datetime, timedelta, timezone

        # Calculate date range
        now = datetime.now(timezone.utc)
        if start_date is None:
            actual_start = now - timedelta(days=days_back)
            start_date = actual_start.strftime("%Y-%m-%d")
        if end_date is None:
            actual_end = now + timedelta(days=days_ahead)
            end_date = actual_end.strftime("%Y-%m-%d")

        logger.info(f"Loading calendar events from {start_date} to {end_date} " f"(sports: {sports or 'all'})")

        # Load events from calendar scraper
        # Scraper returns Dict[str, List[CalendarEvent]], flatten to List[CalendarEvent]
        # Also handle List[CalendarEvent] for backward compatibility with tests
        sport_filter = ",".join(sports) if isinstance(sports, list) else (sports or "")
        events_result = self.scraper.get_events_for_date_range(
            start_date=start_date,
            end_date=end_date,
            sport=sport_filter,
        )

        # Handle both dict and list return types
        if isinstance(events_result, dict):
            events = []
            for date_events in events_result.values():
                events.extend(date_events)
        else:
            # Assume it's already a list (for backward compatibility with tests)
            events = events_result

        if not events:
            logger.warning(f"No events found for date range {start_date} to {end_date}")
            self._events_loaded = False
            return 0

        # Build indexes from loaded events
        self._event_index.build_indexes(events)

        self._events_loaded = True
        self._load_date_range = (start_date, end_date)

        stats = self._event_index.get_stats()
        logger.info(
            f"Loaded {len(events)} events: "
            f"{stats['teams']} teams, "
            f"{stats['last_names']} last names, "
            f"{stats['leagues']} leagues, "
            f"{stats['words']} words"
        )

        return len(events)

    def find_matches(
        self,
        channel_name: str,
        max_results: int = 5,
        min_confidence: float = LOW_CONFIDENCE,
        date_filter: DateFilter = DateFilter.RECENT_AND_UPCOMING,
        use_channel_date: bool = True,
    ) -> List[MatchResult]:
        """
        Find events that match the given channel name.

        Args:
            channel_name: PPV channel name to match
            max_results: Maximum number of matches to return
            min_confidence: Minimum confidence threshold
            date_filter: Filter for event dates
            use_channel_date: Extract and use date from channel name

        Returns:
            List of MatchResult objects, sorted by confidence (highest first)
        """
        if not self._events_loaded:
            logger.warning("No events loaded. Call load_events_for_date_range() first.")
            return []

        if not channel_name:
            return []

        # Skip generic channels with no event information
        if self._is_generic_channel(channel_name):
            logger.debug(f"Skipping generic channel: {channel_name[:50]}")
            return []

        # Extract date from channel name if enabled
        channel_date = None
        if use_channel_date:
            channel_date = self._date_extractor.extract_date(channel_name)
            if channel_date:
                logger.debug(f"Extracted date from channel: {channel_date}")

        # Normalize channel name and extract significant words
        normalized_channel = self._text_processor.normalize_text(channel_name)
        channel_words = self._text_processor.extract_significant_words(normalized_channel)

        # Run all matching strategies
        all_matches: List[MatchResult] = []
        for strategy in self._strategies:
            matches = strategy.find_matches(
                normalized_channel=normalized_channel,
                channel_words=channel_words,
                event_index=self._event_index,
            )
            all_matches.extend(matches)

        if not all_matches:
            logger.debug(f"No matches found for channel: {channel_name[:50]}")
            return []

        # Filter, boost, deduplicate, and sort results
        filtered_matches = self._match_filter.filter_matches(
            matches=all_matches,
            channel_date=channel_date,
            date_filter=date_filter,
            min_confidence=min_confidence,
            max_results=max_results,
        )

        if filtered_matches:
            logger.info(
                f"Found {len(filtered_matches)} matches for '{channel_name[:50]}' "
                f"(best: {filtered_matches[0].event.event_name}, "
                f"confidence: {filtered_matches[0].confidence:.2f})"
            )

        return filtered_matches

    def _is_generic_channel(self, channel_name: str) -> bool:
        """
        Detect generic PPV channels that have no event information.

        Looks for patterns like "PPV 1", "PPV EVENT 2", "PPV CHANNEL 3"
        without any event-specific information.

        Args:
            channel_name: Channel name to check

        Returns:
            True if the channel appears to be generic
        """
        normalized = self._text_processor.normalize_text(channel_name)
        words = self._text_processor.extract_significant_words(normalized)

        # Empty or very short channels are generic
        if len(words) == 0:
            return True

        # Single word channels are too generic (unless they're team names)
        if len(words) == 1:
            word = list(words)[0]
            # Allow single long words that might be team/event names
            if len(word) < 5:
                return True

        # Check for generic patterns: PPV + number, EVENT + number, etc.
        generic_keywords = {"ppv", "event", "channel", "stream", "live", "show", "event", "box", "office"}
        if words <= generic_keywords:
            # All words are generic keywords
            return True

        return False

    def get_stats(self) -> dict:
        """
        Get statistics about loaded events and indexes.

        Returns:
            Dictionary with statistics
        """
        if not self._events_loaded:
            return {
                "events_loaded": False,
                "total_events": 0,
            }

        stats = self._event_index.get_stats()
        stats["events_loaded"] = True
        if self._load_date_range:
            stats["date_range"] = self._load_date_range

        return stats

    def clear_cache(self):
        """Clear all caches and indexes."""
        self._event_index.clear()
        self._text_processor.clear_cache()
        self._events_loaded = False
        self._load_date_range = None
        logger.info("Cleared all caches and indexes")
