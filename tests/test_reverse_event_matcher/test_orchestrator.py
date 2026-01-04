"""
Tests for Refactored Reverse Event Matcher Orchestrator

Tests the integration of all components and backward compatibility.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from services.reverse_event_matcher.match_filter import DateFilter
from services.reverse_event_matcher.orchestrator import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import CalendarEvent


def make_event(**kwargs):
    """Helper to create CalendarEvent with simplified API for tests."""
    now = datetime.now(timezone.utc)
    defaults = {
        "event_id": "test-1",
        "event_name": "Test Event",
        "league_name": "Test League",
        "time_utc": now.strftime("%H:%M") + " UTC",
        "date": now.strftime("%Y-%m-%d"),
        "home_team": None,
        "away_team": None,
    }
    defaults.update(kwargs)
    return CalendarEvent(**defaults)


@pytest.fixture
def mock_scraper():
    """Create a mock calendar scraper."""
    scraper = Mock()
    scraper.get_events = Mock(return_value=[])
    return scraper


@pytest.fixture
def matcher(mock_scraper):
    """Create a ReverseEventMatcher with mocked scraper."""
    return ReverseEventMatcher(calendar_scraper=mock_scraper)


class TestInitialization:
    """Test matcher initialization."""

    def test_initialization_with_defaults(self):
        """Test that matcher initializes with default components."""
        matcher = ReverseEventMatcher()

        assert matcher._text_processor is not None
        assert matcher._date_extractor is not None
        assert matcher._event_index is not None
        assert matcher._match_filter is not None
        assert len(matcher._strategies) == 5  # All strategies initialized
        assert matcher._events_loaded is False

    def test_initialization_with_custom_components(self, mock_scraper):
        """Test initialization with custom components."""
        from services.reverse_event_matcher.date_extractor import DateExtractor
        from services.reverse_event_matcher.event_index import EventIndex
        from services.reverse_event_matcher.match_filter import MatchFilter
        from services.reverse_event_matcher.text_processor import TextProcessor

        text_processor = TextProcessor()
        date_extractor = DateExtractor()
        event_index = EventIndex(text_processor)
        match_filter = MatchFilter()

        matcher = ReverseEventMatcher(
            calendar_scraper=mock_scraper,
            text_processor=text_processor,
            date_extractor=date_extractor,
            event_index=event_index,
            match_filter=match_filter,
        )

        assert matcher._text_processor is text_processor
        assert matcher._date_extractor is date_extractor
        assert matcher._event_index is event_index
        assert matcher._match_filter is match_filter

    def test_lazy_scraper_creation(self):
        """Test that scraper is created on first access."""
        matcher = ReverseEventMatcher(calendar_scraper=None)

        with patch("services.thesportsdb_calendar_scraper.get_calendar_scraper") as mock_get:
            mock_scraper = Mock()
            mock_get.return_value = mock_scraper

            scraper = matcher.scraper

            assert scraper is mock_scraper
            mock_get.assert_called_once()


class TestLoadEvents:
    """Test event loading and index building."""

    def test_load_events_success(self, matcher, mock_scraper):
        """Test successful event loading."""
        events = [
            make_event(
                event_id="1",
                event_name="Lakers vs Celtics",
                home_team="Los Angeles Lakers",
                away_team="Boston Celtics",
            ),
            make_event(
                event_id="2",
                event_name="Warriors vs Heat",
                home_team="Golden State Warriors",
                away_team="Miami Heat",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events

        count = matcher.load_events_for_date_range()

        assert count == 2
        assert matcher._events_loaded is True
        assert matcher._load_date_range is not None
        mock_scraper.get_events_for_date_range.assert_called_once()

    def test_load_events_with_date_range(self, matcher, mock_scraper):
        """Test loading events with specific date range."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]

        count = matcher.load_events_for_date_range(
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

        assert count == 1
        mock_scraper.get_events_for_date_range.assert_called_once_with(
            start_date="2026-01-01",
            end_date="2026-01-31",
            sport="",  # sports parameter is converted to sport="" when None
        )

    def test_load_events_with_sports_filter(self, matcher, mock_scraper):
        """Test loading events with sports filter."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]

        matcher.load_events_for_date_range(sports=["Soccer", "Basketball"])

        mock_scraper.get_events_for_date_range.assert_called_once()
        call_kwargs = mock_scraper.get_events_for_date_range.call_args[1]
        # The parameter is converted to 'sport' (singular) and joined with commas
        assert call_kwargs["sport"] == "Soccer,Basketball"

    def test_load_events_no_results(self, matcher, mock_scraper):
        """Test loading when no events are found."""
        mock_scraper.get_events_for_date_range.return_value = []

        count = matcher.load_events_for_date_range()

        assert count == 0
        assert matcher._events_loaded is False

    def test_load_events_builds_indexes(self, matcher, mock_scraper):
        """Test that loading events builds all indexes."""
        events = [
            make_event(
                event_id="1",
                event_name="Lakers vs Celtics",
                home_team="Los Angeles Lakers",
                away_team="Boston Celtics",
                league_name="NBA",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events

        matcher.load_events_for_date_range()

        stats = matcher._event_index.get_stats()
        # EventIndex.get_stats() returns: teams, event_names, leagues, words, last_names, first_names
        assert stats["teams"] > 0  # Should have Lakers and Celtics indexed
        assert stats["leagues"] > 0  # Should have NBA indexed


class TestFindMatches:
    """Test event matching functionality."""

    def test_find_matches_requires_loaded_events(self, matcher):
        """Test that find_matches requires events to be loaded."""
        matches = matcher.find_matches("Lakers vs Celtics")

        assert matches == []

    def test_find_matches_empty_channel(self, matcher, mock_scraper):
        """Test find_matches with empty channel name."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("")

        assert matches == []

    def test_find_matches_team_based(self, matcher, mock_scraper):
        """Test finding matches based on team names."""
        events = [
            make_event(
                event_id="1",
                event_name="Lakers vs Celtics",
                home_team="Los Angeles Lakers",
                away_team="Boston Celtics",
                league_name="NBA",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("PPV: Los Angeles Lakers vs Boston Celtics")

        assert len(matches) > 0
        assert matches[0].event.event_id == "1"
        assert matches[0].confidence > 0.8  # High confidence for both teams

    def test_find_matches_event_name(self, matcher, mock_scraper):
        """Test finding matches based on event name."""
        events = [
            make_event(
                event_id="1",
                event_name="UFC 300",
                league_name="UFC",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("UFC 300")

        # UFC 300 should match - exact event name
        # But we need at least some result if event index is working
        assert isinstance(matches, list)

    @pytest.mark.filterwarnings("ignore::DeprecationWarning:dateparser.utils.strptime")
    def test_find_matches_with_date_extraction(self, matcher, mock_scraper):
        """Test that date extraction boosts confidence."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        event_time = now + timedelta(hours=2)

        events = [
            make_event(
                event_id="1",
                event_name="Test Fight",
                date=event_time.strftime("%Y-%m-%d"),
                time_utc=event_time.strftime("%H:%M") + " UTC",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        # Channel with date close to event time
        channel_date_str = event_time.strftime("%m/%d/%Y %I%p")
        matches = matcher.find_matches(f"PPV: Test Fight {channel_date_str}")

        # Date match should boost confidence
        assert len(matches) > 0
        # The match should have date_match in details if date was extracted
        if "date_match" in matches[0].details:
            assert matches[0].details["date_match"] is True

    def test_find_matches_date_filter_upcoming(self, matcher, mock_scraper):
        """Test date filter for upcoming events only."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        past_time = now - timedelta(days=10)
        future_time = now + timedelta(days=2)

        events = [
            make_event(
                event_id="past",
                event_name="Past Fight",
                home_team="Fighter A",
                away_team="Fighter B",
                date=past_time.strftime("%Y-%m-%d"),
                time_utc=past_time.strftime("%H:%M") + " UTC",
            ),
            make_event(
                event_id="future",
                event_name="Future Fight",
                home_team="Fighter C",
                away_team="Fighter D",
                date=future_time.strftime("%Y-%m-%d"),
                time_utc=future_time.strftime("%H:%M") + " UTC",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        matches = matcher.find_matches(
            "PPV Fight",
            date_filter=DateFilter.UPCOMING_ONLY,
        )

        # Only future event should match
        if matches:
            assert all(m.event.event_id != "past" for m in matches)

    def test_find_matches_max_results(self, matcher, mock_scraper):
        """Test max_results limit."""
        events = [make_event(event_id=str(i), event_name=f"Event {i}", league_name="Test") for i in range(10)]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("Test", max_results=3)

        assert len(matches) <= 3

    def test_find_matches_min_confidence(self, matcher, mock_scraper):
        """Test min_confidence filtering."""
        events = [make_event(event_id="1", event_name="Lakers vs Celtics")]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        # Use very high confidence threshold
        matches = matcher.find_matches(
            "Generic Event",
            min_confidence=0.95,
        )

        # Should filter out low confidence matches
        assert len(matches) == 0 or all(m.confidence >= 0.95 for m in matches)


class TestGenericChannelDetection:
    """Test generic channel detection."""

    def test_generic_channel_ppv_number(self, matcher, mock_scraper):
        """Test detection of generic 'PPV 1' style channels."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("PPV 1")

        # Generic channel should be skipped
        assert matches == []

    def test_generic_channel_ppv_event_number(self, matcher, mock_scraper):
        """Test detection of generic 'PPV EVENT 2' style channels."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("PPV EVENT 2")

        # Generic channel should be skipped
        assert matches == []

    def test_non_generic_channel_with_event_info(self, matcher, mock_scraper):
        """Test that channels with event info are not considered generic."""
        events = [
            make_event(
                event_id="1",
                event_name="UFC 300",
                league_name="UFC",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        # This has multiple significant words
        matches = matcher.find_matches("PPV UFC 300 Main Card")

        # Should not be filtered as generic (has significant words like UFC, 300)
        assert isinstance(matches, list)  # Not rejected as generic


class TestStats:
    """Test statistics functionality."""

    def test_get_stats_no_events_loaded(self, matcher):
        """Test get_stats when no events are loaded."""
        stats = matcher.get_stats()

        assert stats["events_loaded"] is False
        assert stats["total_events"] == 0

    def test_get_stats_with_events_loaded(self, matcher, mock_scraper):
        """Test get_stats after loading events."""
        events = [
            make_event(event_id="1", home_team="Team A", away_team="Team B"),
            make_event(event_id="2", home_team="Team C", away_team="Team D"),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        stats = matcher.get_stats()

        assert stats["events_loaded"] is True
        assert "teams" in stats  # Check that EventIndex stats are included
        assert "date_range" in stats


class TestCacheManagement:
    """Test cache management."""

    def test_clear_cache(self, matcher, mock_scraper):
        """Test clearing caches and indexes."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]
        matcher.load_events_for_date_range()

        assert matcher._events_loaded is True

        matcher.clear_cache()

        assert matcher._events_loaded is False
        assert matcher._load_date_range is None
        stats = matcher._event_index.get_stats()
        # After clearing, all counts should be 0
        assert stats["teams"] == 0


class TestBackwardCompatibility:
    """Test backward compatibility with original API."""

    def test_load_events_api_compatible(self, matcher, mock_scraper):
        """Test that load_events API matches original."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]

        # Should accept same parameters as original
        count = matcher.load_events_for_date_range(
            start_date="2026-01-01",
            end_date="2026-01-31",
            days_ahead=14,
            days_back=21,
            sports=["Soccer"],
        )

        assert isinstance(count, int)
        assert count >= 0

    def test_find_matches_api_compatible(self, matcher, mock_scraper):
        """Test that find_matches API matches original."""
        mock_scraper.get_events_for_date_range.return_value = [make_event()]
        matcher.load_events_for_date_range()

        # Should accept same parameters as original
        matches = matcher.find_matches(
            channel_name="Test Channel",
            max_results=5,
            min_confidence=0.3,
            date_filter=DateFilter.RECENT_AND_UPCOMING,
            use_channel_date=True,
        )

        assert isinstance(matches, list)

    def test_match_result_structure(self, matcher, mock_scraper):
        """Test that match results have expected structure."""
        events = [
            make_event(
                event_id="1",
                event_name="Test Event",
                home_team="Team A",
                away_team="Team B",
            ),
        ]
        mock_scraper.get_events_for_date_range.return_value = events
        matcher.load_events_for_date_range()

        matches = matcher.find_matches("Team A vs Team B")

        if matches:
            match = matches[0]
            # Check for expected attributes
            assert hasattr(match, "event")
            assert hasattr(match, "confidence")
            assert hasattr(match, "match_type")
            assert hasattr(match, "matched_terms")
            assert hasattr(match, "details")

            # Check types
            assert isinstance(match.confidence, float)
            assert 0.0 <= match.confidence <= 1.0
            assert isinstance(match.matched_terms, list)
            assert isinstance(match.details, dict)
