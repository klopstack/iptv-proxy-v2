"""
Tests for Match Filter Component

Tests date filtering, confidence boosting, and result post-processing.
"""

from datetime import datetime, timedelta, timezone

import pytest

from services.reverse_event_matcher.match_filter import DateFilter, MatchFilter
from services.reverse_event_matcher.match_strategy import MatchResult
from services.thesportsdb_calendar_scraper import CalendarEvent


def make_event(**kwargs):
    """Helper to create CalendarEvent with simplified API for tests."""
    now = datetime.now(timezone.utc)
    defaults = {
        "time_utc": now.strftime("%H:%M") + " UTC",
        "date": now.strftime("%Y-%m-%d"),
    }
    defaults.update(kwargs)
    return CalendarEvent(**defaults)


def make_match_result(event_id: str, confidence: float, **event_kwargs) -> MatchResult:
    """Helper to create MatchResult for testing."""
    event = make_event(event_id=event_id, event_name=f"Event {event_id}", league_name="Test League", **event_kwargs)
    return MatchResult(
        event=event,
        confidence=confidence,
        match_type="test",
        matched_terms=["test"],
        details={},
    )


@pytest.fixture
def match_filter():
    """Create a MatchFilter instance for tests."""
    return MatchFilter()


@pytest.fixture
def now():
    """Fixed 'now' time for consistent testing."""
    return datetime(2026, 1, 4, 12, 0, 0, tzinfo=timezone.utc)


class TestDateBoundaries:
    """Test date boundary calculations for different filter types."""

    def test_all_filter_no_boundaries(self, match_filter, now):
        """DateFilter.ALL should have no date restrictions."""
        min_date, max_date = match_filter._get_date_boundaries(DateFilter.ALL, now)
        assert min_date is None
        assert max_date is None

    def test_upcoming_only_filter(self, match_filter, now):
        """DateFilter.UPCOMING_ONLY should start 3 hours before now."""
        min_date, max_date = match_filter._get_date_boundaries(DateFilter.UPCOMING_ONLY, now)
        assert min_date == now - timedelta(hours=3)
        assert max_date is None

    def test_recent_and_upcoming_filter(self, match_filter, now):
        """DateFilter.RECENT_AND_UPCOMING should start 7 days before now."""
        min_date, max_date = match_filter._get_date_boundaries(DateFilter.RECENT_AND_UPCOMING, now)
        assert min_date == now - timedelta(days=7)
        assert max_date is None

    def test_current_week_filter(self, match_filter, now):
        """DateFilter.CURRENT_WEEK should be -3 days to +7 days."""
        min_date, max_date = match_filter._get_date_boundaries(DateFilter.CURRENT_WEEK, now)
        assert min_date == now - timedelta(days=3)
        assert max_date == now + timedelta(days=7)


class TestDateMatching:
    """Test channel date matching against event dates."""

    def test_exact_date_match(self, match_filter):
        """Test exact date match gets strong boost."""
        channel_date = datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc)
        event_date = datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc)

        matches, boost = match_filter._check_date_match(channel_date, event_date)

        assert matches is True
        assert boost == 0.15  # close_match_boost

    def test_close_date_match(self, match_filter):
        """Test close date match (within 6 hours) gets strong boost."""
        channel_date = datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc)
        event_date = datetime(2026, 1, 4, 18, 0, tzinfo=timezone.utc)  # 4 hours later

        matches, boost = match_filter._check_date_match(channel_date, event_date)

        assert matches is True
        assert boost == 0.15  # close_match_boost

    def test_tolerance_date_match(self, match_filter):
        """Test date match within tolerance (48 hours) gets moderate boost."""
        channel_date = datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc)
        event_date = datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc)  # ~44 hours later

        matches, boost = match_filter._check_date_match(channel_date, event_date)

        assert matches is True
        assert boost == 0.05  # tolerance_match_boost

    def test_date_mismatch(self, match_filter):
        """Test date outside tolerance doesn't match."""
        channel_date = datetime(2026, 1, 4, 14, 0, tzinfo=timezone.utc)
        event_date = datetime(2026, 1, 10, 14, 0, tzinfo=timezone.utc)  # 6 days later

        matches, boost = match_filter._check_date_match(channel_date, event_date)

        assert matches is False
        assert boost == 0.0

    def test_timezone_naive_dates(self, match_filter):
        """Test that timezone-naive dates are handled correctly."""
        # Both dates naive - should be treated as UTC
        channel_date = datetime(2026, 1, 4, 14, 0)  # No timezone
        event_date = datetime(2026, 1, 4, 16, 0)  # No timezone, 2 hours later

        matches, boost = match_filter._check_date_match(channel_date, event_date)

        assert matches is True
        assert boost == 0.15  # Within close match threshold


class TestConfidenceFiltering:
    """Test minimum confidence threshold filtering."""

    def test_filter_by_min_confidence(self, match_filter, now):
        """Test that low confidence matches are filtered out."""
        matches = [
            make_match_result("1", confidence=0.9),
            make_match_result("2", confidence=0.5),
            make_match_result("3", confidence=0.3),  # Below threshold
        ]

        filtered = match_filter.filter_matches(
            matches,
            min_confidence=0.45,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 2
        assert filtered[0].event.event_id == "1"
        assert filtered[1].event.event_id == "2"

    def test_custom_min_confidence(self, match_filter, now):
        """Test with custom minimum confidence threshold."""
        matches = [
            make_match_result("1", confidence=0.9),
            make_match_result("2", confidence=0.7),
            make_match_result("3", confidence=0.5),
        ]

        filtered = match_filter.filter_matches(
            matches,
            min_confidence=0.65,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 2
        assert filtered[0].event.event_id == "1"
        assert filtered[1].event.event_id == "2"


class TestDeduplication:
    """Test deduplication of matches by event ID."""

    def test_duplicate_event_ids_removed(self, match_filter, now):
        """Test that duplicate event IDs are removed, keeping first occurrence."""
        matches = [
            make_match_result("1", confidence=0.9),
            make_match_result("1", confidence=0.8),  # Duplicate
            make_match_result("2", confidence=0.7),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 2
        assert filtered[0].event.event_id == "1"
        assert filtered[0].confidence == 0.9  # First occurrence kept
        assert filtered[1].event.event_id == "2"


class TestSortingAndLimiting:
    """Test result sorting and max_results limiting."""

    def test_sorted_by_confidence_descending(self, match_filter, now):
        """Test that results are sorted by confidence (highest first)."""
        matches = [
            make_match_result("1", confidence=0.5),
            make_match_result("2", confidence=0.9),
            make_match_result("3", confidence=0.7),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 3
        assert filtered[0].event.event_id == "2"  # 0.9
        assert filtered[1].event.event_id == "3"  # 0.7
        assert filtered[2].event.event_id == "1"  # 0.5

    def test_max_results_limit(self, match_filter, now):
        """Test that max_results limits the number of returned matches."""
        matches = [make_match_result(str(i), confidence=0.5 + i * 0.05) for i in range(10)]

        filtered = match_filter.filter_matches(
            matches,
            max_results=3,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 3
        # Should be top 3 by confidence
        assert filtered[0].confidence >= filtered[1].confidence
        assert filtered[1].confidence >= filtered[2].confidence


class TestDateRangeFiltering:
    """Test date range filtering with different DateFilter types."""

    def test_upcoming_only_filters_past_events(self, match_filter, now):
        """Test that UPCOMING_ONLY filters out old events."""
        past_time = now - timedelta(days=5)
        past_date_str = past_time.strftime("%Y-%m-%d")
        past_time_str = past_time.strftime("%H:%M") + " UTC"

        future_time = now + timedelta(days=2)
        future_date_str = future_time.strftime("%Y-%m-%d")
        future_time_str = future_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("1", confidence=0.9, date=past_date_str, time_utc=past_time_str),
            make_match_result("2", confidence=0.8, date=future_date_str, time_utc=future_time_str),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.UPCOMING_ONLY,
            current_time=now,
        )

        # Only future event should remain
        assert len(filtered) == 1
        assert filtered[0].event.event_id == "2"

    def test_recent_and_upcoming_includes_recent(self, match_filter, now):
        """Test that RECENT_AND_UPCOMING includes events from last 7 days."""
        recent_time = now - timedelta(days=5)
        recent_date_str = recent_time.strftime("%Y-%m-%d")
        recent_time_str = recent_time.strftime("%H:%M") + " UTC"

        old_time = now - timedelta(days=10)
        old_date_str = old_time.strftime("%Y-%m-%d")
        old_time_str = old_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("1", confidence=0.9, date=recent_date_str, time_utc=recent_time_str),
            make_match_result("2", confidence=0.8, date=old_date_str, time_utc=old_time_str),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.RECENT_AND_UPCOMING,
            current_time=now,
        )

        # Only recent event should remain
        assert len(filtered) == 1
        assert filtered[0].event.event_id == "1"

    def test_current_week_window(self, match_filter, now):
        """Test that CURRENT_WEEK includes -3 days to +7 days."""
        within_time = now + timedelta(days=5)
        within_date_str = within_time.strftime("%Y-%m-%d")
        within_time_str = within_time.strftime("%H:%M") + " UTC"

        outside_time = now + timedelta(days=10)
        outside_date_str = outside_time.strftime("%Y-%m-%d")
        outside_time_str = outside_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("1", confidence=0.9, date=within_date_str, time_utc=within_time_str),
            make_match_result("2", confidence=0.8, date=outside_date_str, time_utc=outside_time_str),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.CURRENT_WEEK,
            current_time=now,
        )

        # Only event within window should remain
        assert len(filtered) == 1
        assert filtered[0].event.event_id == "1"

    def test_all_filter_includes_everything(self, match_filter, now):
        """Test that DateFilter.ALL doesn't filter by date."""
        past_time = now - timedelta(days=30)
        past_date_str = past_time.strftime("%Y-%m-%d")
        past_time_str = past_time.strftime("%H:%M") + " UTC"

        future_time = now + timedelta(days=30)
        future_date_str = future_time.strftime("%Y-%m-%d")
        future_time_str = future_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("1", confidence=0.9, date=past_date_str, time_utc=past_time_str),
            make_match_result("2", confidence=0.8, date=future_date_str, time_utc=future_time_str),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        # Both should remain
        assert len(filtered) == 2


class TestChannelDateBoosting:
    """Test confidence boosting when channel date matches event date."""

    def test_channel_date_boosts_confidence(self, match_filter, now):
        """Test that matching channel date boosts confidence."""
        event_time = now + timedelta(hours=2)
        event_date_str = event_time.strftime("%Y-%m-%d")
        event_time_str = event_time.strftime("%H:%M") + " UTC"

        match = make_match_result("1", confidence=0.7, date=event_date_str, time_utc=event_time_str)
        channel_date = now + timedelta(hours=1)  # 1 hour before event (close match)

        filtered = match_filter.filter_matches(
            [match],
            channel_date=channel_date,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 1
        # Confidence should be boosted: 0.7 + 0.15 = 0.85
        assert filtered[0].confidence == 0.85
        assert filtered[0].details["date_match"] is True
        assert filtered[0].details["date_boost"] == 0.15

    def test_channel_date_filters_non_matching_events(self, match_filter, now):
        """Test that channel date filters out events with non-matching dates."""
        event_time = now + timedelta(days=10)  # Way in future
        event_date_str = event_time.strftime("%Y-%m-%d")
        event_time_str = event_time.strftime("%H:%M") + " UTC"

        match = make_match_result("1", confidence=0.9, date=event_date_str, time_utc=event_time_str)
        channel_date = now  # Today - doesn't match event 10 days away

        filtered = match_filter.filter_matches(
            [match],
            channel_date=channel_date,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        # Event should be filtered out due to date mismatch
        assert len(filtered) == 0

    def test_confidence_capped_at_one(self, match_filter, now):
        """Test that confidence boost doesn't exceed 1.0."""
        event_time = now
        event_date_str = event_time.strftime("%Y-%m-%d")
        event_time_str = event_time.strftime("%H:%M") + " UTC"

        match = make_match_result("1", confidence=0.95, date=event_date_str, time_utc=event_time_str)
        channel_date = now  # Exact match - would give +0.15 boost

        filtered = match_filter.filter_matches(
            [match],
            channel_date=channel_date,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert len(filtered) == 1
        # Confidence should be capped at 1.0 (not 0.95 + 0.15 = 1.10)
        assert filtered[0].confidence == 1.0


class TestEventAgeValidation:
    """Test event age validation to reject historical events."""

    def test_recent_event_valid(self, match_filter, now):
        """Test that recent events (within 30 days ago) are valid."""
        # Event 7 days ago
        event_date = now - timedelta(days=7)
        assert match_filter.is_event_valid_age(event_date, now) is True

    def test_old_event_invalid(self, match_filter, now):
        """Test that old events (more than 30 days ago) are invalid."""
        # Event 45 days ago (beyond MAX_EVENT_AGE_DAYS)
        event_date = now - timedelta(days=45)
        assert match_filter.is_event_valid_age(event_date, now) is False

    def test_very_old_event_invalid(self, match_filter, now):
        """Test that very old events (like 2014) are definitely invalid."""
        # Event from 2014 (like the Liverpool vs Swansea bug)
        event_date = datetime(2014, 12, 29, 20, 0, 0, tzinfo=timezone.utc)
        assert match_filter.is_event_valid_age(event_date, now) is False

    def test_future_event_valid(self, match_filter, now):
        """Test that near-future events are valid."""
        # Event 30 days from now
        event_date = now + timedelta(days=30)
        assert match_filter.is_event_valid_age(event_date, now) is True

    def test_far_future_event_invalid(self, match_filter, now):
        """Test that far-future events are invalid."""
        # Event 400 days from now (beyond MAX_EVENT_FUTURE_DAYS)
        event_date = now + timedelta(days=400)
        assert match_filter.is_event_valid_age(event_date, now) is False

    def test_none_event_date_valid(self, match_filter, now):
        """Test that None event date is treated as valid (can't validate)."""
        assert match_filter.is_event_valid_age(None, now) is True

    def test_custom_max_age(self, now):
        """Test custom max event age parameter."""
        # Use very short max age (7 days)
        filter_strict = MatchFilter(max_event_age_days=7)

        event_10_days_ago = now - timedelta(days=10)
        event_5_days_ago = now - timedelta(days=5)

        assert filter_strict.is_event_valid_age(event_10_days_ago, now) is False
        assert filter_strict.is_event_valid_age(event_5_days_ago, now) is True

    def test_strict_validation_filters_old_events(self, match_filter, now):
        """Test that strict date validation filters out old events in filter_matches."""
        # Create event from 45 days ago
        old_time = now - timedelta(days=45)
        old_date_str = old_time.strftime("%Y-%m-%d")
        old_time_str = old_time.strftime("%H:%M") + " UTC"

        # Create event from 3 days ago
        recent_time = now - timedelta(days=3)
        recent_date_str = recent_time.strftime("%Y-%m-%d")
        recent_time_str = recent_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("old_event", confidence=0.95, date=old_date_str, time_utc=old_time_str),
            make_match_result("recent_event", confidence=0.85, date=recent_date_str, time_utc=recent_time_str),
        ]

        filtered = match_filter.filter_matches(
            matches,
            date_filter=DateFilter.ALL,  # No date range filter
            min_confidence=0.45,
            current_time=now,
        )

        # Only the recent event should pass
        assert len(filtered) == 1
        assert filtered[0].event.event_id == "recent_event"

    def test_disable_strict_validation(self, now):
        """Test that strict validation can be disabled."""
        filter_non_strict = MatchFilter(strict_date_validation=False)

        # Create very old event
        old_time = now - timedelta(days=365 * 10)  # 10 years ago
        old_date_str = old_time.strftime("%Y-%m-%d")
        old_time_str = old_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("ancient_event", confidence=0.90, date=old_date_str, time_utc=old_time_str),
        ]

        # With strict validation disabled, old events should pass through
        # (assuming the date range filter allows it)
        filtered = filter_non_strict.filter_matches(
            matches,
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        # Ancient event should pass since strict validation is disabled
        assert len(filtered) == 1
        assert filtered[0].event.event_id == "ancient_event"


class TestEmptyInput:
    """Test handling of empty input."""

    def test_empty_matches_list(self, match_filter, now):
        """Test that empty matches list returns empty result."""
        filtered = match_filter.filter_matches(
            [],
            date_filter=DateFilter.ALL,
            current_time=now,
        )

        assert filtered == []


class TestIntegration:
    """Integration tests combining multiple filtering operations."""

    def test_full_filtering_pipeline(self, match_filter, now):
        """Test complete filtering: date, confidence, dedup, sort, limit."""
        event_time = now + timedelta(hours=2)
        event_date_str = event_time.strftime("%Y-%m-%d")
        event_time_str = event_time.strftime("%H:%M") + " UTC"

        old_time = now - timedelta(days=10)
        old_date_str = old_time.strftime("%Y-%m-%d")
        old_time_str = old_time.strftime("%H:%M") + " UTC"

        matches = [
            make_match_result("1", confidence=0.6, date=event_date_str, time_utc=event_time_str),
            make_match_result("2", confidence=0.9, date=event_date_str, time_utc=event_time_str),
            make_match_result("3", confidence=0.3, date=event_date_str, time_utc=event_time_str),  # Too low
            make_match_result("2", confidence=0.8, date=event_date_str, time_utc=event_time_str),  # Duplicate
            make_match_result("4", confidence=0.7, date=old_date_str, time_utc=old_time_str),  # Too old
        ]

        channel_date = now + timedelta(hours=1)

        filtered = match_filter.filter_matches(
            matches,
            channel_date=channel_date,
            date_filter=DateFilter.UPCOMING_ONLY,
            min_confidence=0.45,
            max_results=2,
            current_time=now,
        )

        # Should have: event 2 (boosted to 1.0), event 1 (boosted to 0.75)
        # Event 3 filtered (too low), event 4 filtered (too old), duplicate removed
        assert len(filtered) == 2
        assert filtered[0].event.event_id == "2"  # Highest confidence
        assert filtered[0].confidence == 1.0  # 0.9 + 0.15 capped at 1.0
        assert filtered[1].event.event_id == "1"  # Second highest
        assert filtered[1].confidence == 0.75  # 0.6 + 0.15
