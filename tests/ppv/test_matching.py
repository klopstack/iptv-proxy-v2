"""
Tests for Enhanced PPV Matcher service.

Tests the improved matching pipeline including:
- Channel categorization
- Date extraction and pre-fetching
- Multiple matching strategies
- Batch processing
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.ppv.matching.enhanced import (
    ChannelCategory,
    EnhancedMatchResult,
    EnhancedPPVMatcher,
    get_enhanced_ppv_matcher,
)
from services.thesportsdb_calendar_scraper import CalendarEvent


class TestChannelCategorization:
    """Test channel categorization logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.matcher = EnhancedPPVMatcher()

    def test_placeholder_detection(self):
        """Test detection of placeholder channels."""
        placeholders = [
            "###### SKY SPORT+ PPV ######",
            "PPV Event 42",
            "UK: DAZN PPV 1 - NO EVENT STREAMING",
            "Channel 5",
        ]

        for channel in placeholders:
            category, _ = self.matcher.categorize_channel(channel)
            assert category == ChannelCategory.PLACEHOLDER, f"Expected placeholder for '{channel}'"

    def test_tournament_detection(self):
        """Test detection of tournament/league content."""
        tournaments = [
            "Super League Plus | Event 1 Hull KR v St Helens",
            "Scottish Cup 1: St Johnstone vs Celtic",
            "UEFA Champions League Final",
            "World Cup 2026 Qualifier",
        ]

        for channel in tournaments:
            category, pattern = self.matcher.categorize_channel(channel)
            assert category == "tournament", f"Expected tournament for '{channel}', got {category}"

    def test_highlight_detection(self):
        """Test detection of highlight/recap content."""
        highlights = [
            "SC Top World Junior Moments B",
            "Match Highlights: Arsenal vs Chelsea",
            "Best Goals of the Week",
            "Season Recap Show",
        ]

        for channel in highlights:
            category, _ = self.matcher.categorize_channel(channel)
            assert category == "highlight", f"Expected highlight for '{channel}', got {category}"

    def test_training_detection(self):
        """Test detection of training/press conference content."""
        training = [
            "WNBA 6 Pregame Press Conference",
            "NCAA Football Press Conference",
            "Pre-season Friendly: Team A vs Team B",
        ]

        for channel in training:
            category, _ = self.matcher.categorize_channel(channel)
            assert category == "training", f"Expected training for '{channel}', got {category}"

    def test_vs_event_detection(self):
        """Test detection of likely vs events."""
        vs_events = [
            "Live Football 01: Egypt vs Benin 16:00pm",
            "Manchester United vs Liverpool",
            "Vegas Golden Knights @ Colorado Avalanche",
        ]

        for channel in vs_events:
            category, _ = self.matcher.categorize_channel(channel)
            assert category == ChannelCategory.VS_EVENT, f"Expected vs_event for '{channel}', got {category}"

    def test_other_category(self):
        """Test channels that don't fit other categories."""
        other = [
            "Random Channel Name Without Keywords",
            "Some Sports Event",
        ]

        for channel in other:
            category, _ = self.matcher.categorize_channel(channel)
            # These should be either OTHER or VS_EVENT depending on competitor extraction
            assert category in (
                ChannelCategory.OTHER,
                ChannelCategory.VS_EVENT,
            ), f"Expected other/vs_event for '{channel}', got {category}"


class TestChannelInfoExtraction:
    """Test extraction of channel information."""

    def setup_method(self):
        """Set up test fixtures."""
        self.matcher = EnhancedPPVMatcher()

    def test_extract_competitors(self):
        """Test competitor extraction."""
        test_cases = [
            ("Arsenal vs Brighton @ Dec 27", ("Arsenal", "Brighton")),
            ("Vegas Golden Knights @ Colorado Avalanche", ("Vegas Golden Knights", "Colorado Avalanche")),
            ("NORTHAMPTON SAINTS - HARLEQUINS", ("NORTHAMPTON SAINTS", "HARLEQUINS")),
        ]

        for channel, expected in test_cases:
            info = self.matcher.extract_channel_info(channel)
            assert info["competitors"] == expected, f"For '{channel}': expected {expected}, got {info['competitors']}"

    def test_extract_date(self):
        """Test date extraction."""
        current_date = datetime(2026, 1, 5)
        matcher = EnhancedPPVMatcher(
            event_extractor=__import__("services.ppv.extraction", fromlist=["PPVEventExtractor"]).PPVEventExtractor(
                current_date=current_date
            )
        )

        test_cases = [
            ("UFC: Event start:2025-12-28 01:55:00", datetime(2025, 12, 28, 1, 55)),
            ("Game: 24/10 16:00", datetime(2026, 10, 24, 16, 0)),  # DD/MM format
        ]

        for channel, expected_date in test_cases:
            info = matcher.extract_channel_info(channel)
            if info["date"]:
                assert (
                    info["date"].date() == expected_date.date()
                ), f"For '{channel}': expected {expected_date.date()}, got {info['date'].date()}"


class TestEnhancedMatchResult:
    """Test EnhancedMatchResult class."""

    def test_result_with_event(self):
        """Test result when event is matched."""
        event = CalendarEvent(
            event_id="123",
            event_name="Team A vs Team B",
            league_name="Test League",
            time_utc="14:00",
            date="2026-01-05",
        )

        result = EnhancedMatchResult(
            event=event,
            confidence=0.85,
            match_method="reverse",
            category=ChannelCategory.VS_EVENT,
        )

        assert result.event is not None
        assert result.confidence == 0.85
        assert result.match_method == "reverse"
        assert "Team A vs Team B" in repr(result)

    def test_result_without_event(self):
        """Test result when no event matched."""
        result = EnhancedMatchResult(
            category=ChannelCategory.PLACEHOLDER,
        )

        assert result.event is None
        assert result.confidence == 0.0
        assert result.match_method == "none"
        assert "no_match" in repr(result)


class TestMatcherIntegration:
    """Integration tests for the matcher."""

    def setup_method(self):
        """Set up test fixtures with mocked dependencies."""
        self.mock_reverse_matcher = MagicMock()
        self.mock_reverse_matcher._events_loaded = True
        self.mock_reverse_matcher.find_matches.return_value = []

        self.mock_thesportsdb = MagicMock()
        self.mock_thesportsdb.match_channel_to_event.return_value = None

        self.matcher = EnhancedPPVMatcher(
            reverse_matcher=self.mock_reverse_matcher,
            thesportsdb_service=self.mock_thesportsdb,
        )

    def test_placeholder_filtered(self):
        """Test that placeholders are filtered without API calls."""
        result = self.matcher.find_match("PPV Event 1 - NO EVENT STREAMING")

        assert result.category == ChannelCategory.PLACEHOLDER
        assert result.event is None
        self.mock_reverse_matcher.find_matches.assert_not_called()

    def test_non_vs_filtered(self):
        """Test that non-vs content is filtered when skip_non_vs=True."""
        result = self.matcher.find_match(
            "Match Highlights: Arsenal vs Chelsea",
            skip_non_vs=True,
        )

        assert result.category == "highlight"
        assert result.event is None
        self.mock_reverse_matcher.find_matches.assert_not_called()

    def test_non_vs_not_filtered(self):
        """Test that non-vs content is matched when skip_non_vs=False."""
        _ = self.matcher.find_match(
            "Match Highlights: Arsenal vs Chelsea",
            skip_non_vs=False,
        )

        # Should attempt matching
        self.mock_reverse_matcher.find_matches.assert_called()

    def test_reverse_match_used_first(self):
        """Test that reverse matching is tried first."""
        mock_match = MagicMock()
        mock_match.event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test",
            time_utc="14:00",
            date="2026-01-05",
        )
        mock_match.confidence = 0.9

        self.mock_reverse_matcher.find_matches.return_value = [mock_match]

        result = self.matcher.find_match("Manchester United vs Liverpool")

        assert result.match_method == "reverse"
        assert result.confidence == 0.9

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        self.matcher.reset_stats()

        # Match a few channels
        self.matcher.find_match("PPV Event 1")  # Placeholder
        self.matcher.find_match("Match Highlights: Game")  # Non-vs
        self.matcher.find_match("Team A vs Team B")  # Attempted match

        stats = self.matcher.get_stats()

        assert stats["total_attempts"] == 3
        assert stats["filtered_placeholder"] >= 1
        assert stats["filtered_non_vs"] >= 1


class TestDateCollection:
    """Test date collection from channels."""

    def setup_method(self):
        """Set up test fixtures."""
        self.matcher = EnhancedPPVMatcher()

    def test_collect_channel_dates(self):
        """Test extracting dates from channel names."""
        channels = [
            "Game: 2026-01-05 14:00",
            "Event: 2026-01-06 16:00",
            "No date here",
            "Game: 2026-01-05 18:00",  # Duplicate date
        ]

        dates = self.matcher.collect_channel_dates(channels)

        # Should have 2 unique dates
        assert len(dates) == 2
        assert "2026-01-05" in dates
        assert "2026-01-06" in dates


class TestBatchProcessing:
    """Test batch processing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_reverse_matcher = MagicMock()
        self.mock_reverse_matcher._events_loaded = True
        self.mock_reverse_matcher.find_matches.return_value = []

        self.matcher = EnhancedPPVMatcher(
            reverse_matcher=self.mock_reverse_matcher,
        )

    def test_batch_find_matches(self):
        """Test batch matching multiple channels."""
        channels = [
            "PPV Event 1",  # Placeholder
            "Team A vs Team B",  # Matchable
            "Match Highlights",  # Non-vs
        ]

        results = self.matcher.batch_find_matches(
            channel_names=channels,
            skip_non_vs=True,
            preload_dates=False,
        )

        assert len(results) == 3

        # First should be placeholder
        assert results[0].category == ChannelCategory.PLACEHOLDER

        # Third should be filtered as highlight
        assert results[2].category == "highlight"


class TestSingletonInstance:
    """Test the global singleton instance."""

    def test_get_enhanced_ppv_matcher(self):
        """Test getting the singleton instance."""
        matcher1 = get_enhanced_ppv_matcher()
        matcher2 = get_enhanced_ppv_matcher()

        # Should be the same instance
        assert matcher1 is matcher2


# Parametrized tests for pattern matching
@pytest.mark.parametrize(
    "channel,expected_category",
    [
        ("Super League Round 1", "tournament"),
        ("World Cup Final", "tournament"),
        ("Match Recap: Game 1", "highlight"),
        ("Press Conference: Coach Interview", "training"),
        ("Pre-Game Show", "show"),
        ("All Access: Locker Room Tour", "player"),  # Player/exclusive pattern
        ("Behind-the-Scenes Documentary", "documentary"),  # Documentary pattern
    ],
)
def test_pattern_categories(channel, expected_category):
    """Test various channel patterns are categorized correctly."""
    matcher = EnhancedPPVMatcher()
    category, _ = matcher.categorize_channel(channel)
    assert category == expected_category, f"For '{channel}': expected {expected_category}, got {category}"
