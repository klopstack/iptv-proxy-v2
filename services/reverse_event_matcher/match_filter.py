"""
Match Filter Component

Handles filtering and post-processing of match results:
- Date-based filtering (range filters and channel date matching)
- Confidence threshold filtering
- Date-based confidence boosting
- Result deduplication and sorting
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional, Set
from zoneinfo import ZoneInfo

from services.reverse_event_matcher.match_strategy import MatchResult
from services.thesportsdb_calendar_scraper import CalendarEvent


class DateFilter(Enum):
    """Filter options for event dates when matching."""

    ALL = "all"  # Match all events regardless of date
    UPCOMING_ONLY = "upcoming_only"  # Only future events
    RECENT_AND_UPCOMING = "recent_and_upcoming"  # Last 7 days + future
    CURRENT_WEEK = "current_week"  # -3 days to +7 days


class MatchFilter:
    """
    Filters and post-processes match results.

    Responsibilities:
    1. Date range filtering (upcoming only, recent+upcoming, etc.)
    2. Channel date matching with tolerance
    3. Confidence boosting based on date proximity
    4. Minimum confidence threshold filtering
    5. Deduplication by event ID
    6. Sorting by confidence
    """

    def __init__(
        self,
        date_tolerance_hours: int = 48,
        close_match_hours: int = 6,
        close_match_boost: float = 0.15,
        tolerance_match_boost: float = 0.05,
        default_timezone: str = "America/New_York",
    ):
        """
        Initialize the match filter.

        Args:
            date_tolerance_hours: Hours of difference to tolerate for date matching
            close_match_hours: Hours difference for "close" match (higher boost)
            close_match_boost: Confidence boost for very close date matches
            tolerance_match_boost: Confidence boost for date matches within tolerance
            default_timezone: IANA timezone name for naive datetimes (default: America/New_York)
        """
        self.date_tolerance_hours = date_tolerance_hours
        self.close_match_hours = close_match_hours
        self.close_match_boost = close_match_boost
        self.tolerance_match_boost = tolerance_match_boost
        self.default_timezone = ZoneInfo(default_timezone)

    def filter_matches(
        self,
        matches: List[MatchResult],
        channel_date: Optional[datetime] = None,
        date_filter: DateFilter = DateFilter.RECENT_AND_UPCOMING,
        min_confidence: float = 0.45,
        max_results: int = 5,
        current_time: Optional[datetime] = None,
    ) -> List[MatchResult]:
        """
        Filter and post-process match results.

        Args:
            matches: List of match results to filter
            channel_date: Optional date extracted from channel name
            date_filter: Date range filter to apply
            min_confidence: Minimum confidence threshold
            max_results: Maximum number of results to return
            current_time: Current time for date comparisons (defaults to now)

        Returns:
            Filtered, deduplicated, and sorted list of matches
        """
        if not matches:
            return []

        now = current_time or datetime.now(timezone.utc)

        # Calculate date filter boundaries
        min_event_date, max_event_date = self._get_date_boundaries(date_filter, now)

        # Filter and boost matches
        filtered_matches: List[MatchResult] = []
        seen_event_ids: Set[str] = set()

        for match in matches:
            # Skip duplicates
            if match.event.event_id in seen_event_ids:
                continue

            # Apply filters
            filtered_match = self._apply_filters(
                match,
                channel_date,
                min_event_date,
                max_event_date,
                now,
            )

            if filtered_match is not None:
                filtered_matches.append(filtered_match)
                seen_event_ids.add(filtered_match.event.event_id)

        # Filter by minimum confidence
        filtered_matches = [m for m in filtered_matches if m.confidence >= min_confidence]

        # Sort by confidence (highest first)
        filtered_matches.sort(key=lambda m: m.confidence, reverse=True)

        return filtered_matches[:max_results]

    def _get_date_boundaries(
        self,
        date_filter: DateFilter,
        now: datetime,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """
        Calculate min and max event dates based on filter type.

        Args:
            date_filter: Type of date filter to apply
            now: Current time

        Returns:
            Tuple of (min_event_date, max_event_date), either can be None
        """
        min_date: Optional[datetime] = None
        max_date: Optional[datetime] = None

        if date_filter == DateFilter.UPCOMING_ONLY:
            # Allow slightly past events (in progress)
            min_date = now - timedelta(hours=3)
        elif date_filter == DateFilter.RECENT_AND_UPCOMING:
            # Last 7 days + all future
            min_date = now - timedelta(days=7)
        elif date_filter == DateFilter.CURRENT_WEEK:
            # -3 days to +7 days
            min_date = now - timedelta(days=3)
            max_date = now + timedelta(days=7)
        # DateFilter.ALL has no restrictions

        return min_date, max_date

    def _apply_filters(
        self,
        match: MatchResult,
        channel_date: Optional[datetime],
        min_event_date: Optional[datetime],
        max_event_date: Optional[datetime],
        now: datetime,
    ) -> Optional[MatchResult]:
        """
        Apply date filtering and boosting to a single match.

        Returns None if the match should be filtered out.
        """
        event_date = match.event.scheduled_at

        # First, check channel date match if present
        if channel_date is not None and event_date is not None:
            date_matches, date_boost = self._check_date_match(channel_date, event_date)
            if not date_matches:
                # Channel has a date that doesn't match this event
                return None
            if date_boost > 0:
                # Apply confidence boost
                match.confidence = min(match.confidence + date_boost, 1.0)
                match.details["date_match"] = True
                match.details["date_boost"] = date_boost
                match.details["channel_date"] = channel_date.isoformat()

        # Second, apply date range filter
        if event_date is not None:
            # Normalize timezone for comparison
            event_date_utc = event_date
            if event_date.tzinfo is None:
                event_date_utc = event_date.replace(tzinfo=self.default_timezone)

            if min_event_date is not None and event_date_utc < min_event_date:
                return None  # Event too old
            if max_event_date is not None and event_date_utc > max_event_date:
                return None  # Event too far in future

        return match

    def _check_date_match(
        self,
        channel_date: datetime,
        event_date: datetime,
    ) -> tuple[bool, float]:
        """
        Check if a channel date matches an event date.

        Args:
            channel_date: Date extracted from channel name
            event_date: Event's scheduled date

        Returns:
            Tuple of (matches, confidence_boost)
        """
        # Ensure both dates are timezone-aware for comparison
        if channel_date.tzinfo is None:
            channel_date = channel_date.replace(tzinfo=self.default_timezone)
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=self.default_timezone)

        # Calculate time difference in hours
        diff_hours = abs((channel_date - event_date).total_seconds() / 3600)

        if diff_hours <= self.close_match_hours:
            # Very close match - strong boost
            return (True, self.close_match_boost)
        elif diff_hours <= self.date_tolerance_hours:
            # Within tolerance - moderate boost
            return (True, self.tolerance_match_boost)
        else:
            # Outside tolerance - dates don't match
            return (False, 0.0)
