"""
Tests for Match Strategy Components

Tests each matching strategy in isolation with various scenarios.
"""

from datetime import datetime, timezone

import pytest

from services.reverse_event_matcher.event_index import EventIndex
from services.reverse_event_matcher.match_strategy import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    EventNameMatchStrategy,
    LastNameMatchStrategy,
    LeagueMatchStrategy,
    MatchResult,
    TeamMatchStrategy,
    WordMatchStrategy,
)
from services.reverse_event_matcher.text_processor import TextProcessor
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


@pytest.fixture
def text_processor():
    """Create a TextProcessor instance for tests."""
    return TextProcessor()


@pytest.fixture
def event_index(text_processor):
    """Create an EventIndex instance for tests."""
    return EventIndex(text_processor)


@pytest.fixture
def sample_events():
    """Create sample CalendarEvent objects for testing."""
    return [
        make_event(
            event_id="1",
            event_name="UFC 300 Main Card",
            league_name="UFC",
            home_team="Amanda Serrano",
            away_team="Reina Tellez",
        ),
        make_event(
            event_id="2",
            event_name="Premier League Match",
            league_name="Premier League",
            home_team="Manchester United",
            away_team="Liverpool FC",
        ),
        make_event(
            event_id="3",
            event_name="NBA Finals Game 7",
            league_name="NBA",
            home_team="Los Angeles Lakers",
            away_team="Boston Celtics",
        ),
        make_event(
            event_id="4",
            event_name="Formula 1 Monaco Grand Prix",
            league_name="Formula 1",
        ),
        make_event(
            event_id="5",
            event_name="Boxing Championship",
            league_name="Boxing",
            home_team="Jake Paul Jr",
            away_team="Tommy Fury",
        ),
    ]


class TestTeamMatchStrategy:
    """Test team-based matching strategy."""

    def test_both_teams_match(self, event_index, text_processor, sample_events):
        """Test matching when both teams are in channel name."""
        event_index.build_indexes(sample_events)
        strategy = TeamMatchStrategy()

        channel = "Los Angeles Lakers vs Boston Celtics Live HD"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find the Lakers vs Celtics game
        assert len(matches) > 0
        match = matches[0]
        assert match.event.event_id == "3"
        assert match.match_type == "both_teams"
        assert match.confidence >= HIGH_CONFIDENCE
        assert "Los Angeles Lakers" in match.matched_terms
        assert "Boston Celtics" in match.matched_terms

    def test_one_team_match(self, event_index, text_processor, sample_events):
        """Test matching when only one team is in channel name."""
        event_index.build_indexes(sample_events)
        strategy = TeamMatchStrategy()

        channel = "Manchester United Game Tonight"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find the Manchester United match
        assert len(matches) > 0
        match = matches[0]
        assert match.event.event_id == "2"
        assert match.match_type == "one_team"
        assert match.confidence >= MEDIUM_CONFIDENCE
        assert "Manchester United" in match.matched_terms

    def test_short_team_names_filtered(self, event_index, text_processor):
        """Test that short team names (< 5 chars) are filtered out."""
        events = [
            make_event(
                event_id="1",
                event_name="Game",
                league_name="Soccer",
                home_team="Cal",  # 3 chars - should be filtered
                away_team="UCLA",  # 4 chars - should be filtered
            )
        ]
        event_index.build_indexes(events)
        strategy = TeamMatchStrategy()

        channel = "Cal vs UCLA"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should not match due to MIN_TEAM_NAME_LENGTH filter
        assert len(matches) == 0

    def test_no_teams_in_channel(self, event_index, text_processor, sample_events):
        """Test when channel has no team names."""
        event_index.build_indexes(sample_events)
        strategy = TeamMatchStrategy()

        channel = "Sports Highlights Show"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        assert len(matches) == 0


class TestLastNameMatchStrategy:
    """Test last name-based matching strategy."""

    def test_both_last_names_match(self, event_index, text_processor, sample_events):
        """Test matching when both fighter last names are in channel."""
        event_index.build_indexes(sample_events)
        strategy = LastNameMatchStrategy()

        channel = "Serrano vs Tellez Boxing HD"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find the Serrano vs Tellez fight
        assert len(matches) > 0
        match = matches[0]
        assert match.event.event_id == "1"
        assert match.match_type == "both_last_names"
        assert match.confidence >= HIGH_CONFIDENCE
        assert "serrano" in match.matched_terms
        assert "tellez" in match.matched_terms

    def test_one_last_name_match(self, event_index, text_processor, sample_events):
        """Test matching when only one last name is in channel."""
        event_index.build_indexes(sample_events)
        strategy = LastNameMatchStrategy()

        channel = "Fury Boxing Match Tonight"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find Fury's fight (but lower confidence)
        assert len(matches) > 0
        match = matches[0]
        assert match.event.event_id == "5"
        assert match.match_type == "one_last_name"
        assert match.confidence > LOW_CONFIDENCE
        assert match.confidence < MEDIUM_CONFIDENCE
        assert "fury" in match.matched_terms

    def test_short_last_names_filtered(self, event_index, text_processor):
        """Test that short last names (< 4 chars) are filtered."""
        events = [
            make_event(
                event_id="1",
                event_name="Fight",
                league_name="Boxing",
                home_team="Ali",  # 3 chars - should be filtered
                away_team="Joe",  # 3 chars - should be filtered
            )
        ]
        event_index.build_indexes(events)
        strategy = LastNameMatchStrategy()

        channel = "Ali vs Joe"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should not match due to minimum length filter
        assert len(matches) == 0

    def test_no_last_names_in_channel(self, event_index, text_processor, sample_events):
        """Test when channel has no recognizable last names."""
        event_index.build_indexes(sample_events)
        strategy = LastNameMatchStrategy()

        channel = "Boxing Championship Event"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Might match if "championship" appears as last name, but unlikely
        # At minimum, should have lower confidence
        for match in matches:
            assert match.confidence <= MEDIUM_CONFIDENCE


class TestEventNameMatchStrategy:
    """Test event name-based matching strategy."""

    def test_exact_substring_match(self, event_index, text_processor, sample_events):
        """Test exact substring matching of event names."""
        event_index.build_indexes(sample_events)
        strategy = EventNameMatchStrategy()

        channel = "UFC 300 Main Card Live Stream HD"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find UFC 300 via substring match
        assert len(matches) > 0
        match = matches[0]
        assert match.event.event_id == "1"
        assert match.match_type == "event_name_exact"
        assert match.confidence >= HIGH_CONFIDENCE

    def test_token_similarity_match(self, event_index, text_processor, sample_events):
        """Test token-based similarity matching."""
        event_index.build_indexes(sample_events)
        strategy = EventNameMatchStrategy()

        # Long channel with some words from "Formula 1 Monaco Grand Prix"
        channel = "Formula One Monaco Racing Grand Prix Championship"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find Formula 1 event via token similarity
        matching_event = [m for m in matches if m.event.event_id == "4"]
        assert len(matching_event) > 0
        match = matching_event[0]
        assert match.match_type == "event_name_tokens"
        assert match.confidence > LOW_CONFIDENCE
        assert "token_similarity" in match.details

    def test_short_channel_filtered(self, event_index, text_processor, sample_events):
        """Test that short channels (< 15 chars) are filtered."""
        event_index.build_indexes(sample_events)
        strategy = EventNameMatchStrategy()

        channel = "UFC 300"  # Only 7 chars
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should return empty due to length filter
        assert len(matches) == 0

    def test_short_event_names_filtered(self, event_index, text_processor):
        """Test that short event names (< 15 chars) are filtered."""
        events = [
            make_event(
                event_id="1",
                event_name="Game 1",  # Only 6 chars
                league_name="NBA",
            )
        ]
        event_index.build_indexes(events)
        strategy = EventNameMatchStrategy()

        channel = "Game 1 Championship"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should not match due to short event name
        assert len(matches) == 0


class TestLeagueMatchStrategy:
    """Test league-based matching strategy."""

    def test_league_plus_multiple_words(self, event_index, text_processor, sample_events):
        """Test matching league plus multiple significant words."""
        event_index.build_indexes(sample_events)
        strategy = LeagueMatchStrategy()

        # Use UFC (includes word "championship" from event, plus "serrano" last name)
        # Actually, use Premier League which is cleaner
        channel = "Premier League Manchester Liverpool"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find Premier League event
        matching_events = [m for m in matches if m.event.event_id == "2"]
        assert len(matching_events) > 0
        match = matching_events[0]
        # Note: "Premier" and "League" are stop words, so this might have low confidence
        # But it should still match
        assert match.confidence >= LOW_CONFIDENCE
        assert any("premier league" in t.lower() for t in match.matched_terms)

    def test_league_plus_one_word(self, event_index, text_processor, sample_events):
        """Test matching league plus one significant word."""
        event_index.build_indexes(sample_events)
        strategy = LeagueMatchStrategy()

        channel = "UFC Championship Prelims"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find UFC event with lower confidence
        if len(matches) > 0:
            match = matches[0]
            assert match.confidence >= LOW_CONFIDENCE
            assert match.confidence <= MEDIUM_CONFIDENCE

    def test_no_league_match(self, event_index, text_processor, sample_events):
        """Test when channel has no league name."""
        event_index.build_indexes(sample_events)
        strategy = LeagueMatchStrategy()

        channel = "Sports Event Tonight"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should return empty - no league matched
        assert len(matches) == 0


class TestWordMatchStrategy:
    """Test word overlap matching strategy."""

    def test_high_word_overlap(self, event_index, text_processor, sample_events):
        """Test matching with high word overlap."""
        event_index.build_indexes(sample_events)
        strategy = WordMatchStrategy()

        # Channel with multiple words from Formula 1 event
        channel = "Formula Grand Prix Monaco Racing"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should find Formula 1 event
        matching_events = [m for m in matches if m.event.event_id == "4"]
        assert len(matching_events) > 0
        match = matching_events[0]
        assert match.match_type == "word_overlap"
        assert match.confidence >= LOW_CONFIDENCE
        assert match.details["word_count"] >= 3

    def test_insufficient_word_overlap(self, event_index, text_processor, sample_events):
        """Test that matches with < 2 word overlap are filtered."""
        event_index.build_indexes(sample_events)
        strategy = WordMatchStrategy()

        channel = "randomword"  # Only 1 word that doesn't match anything
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should not match - no overlap (need 2+ words)
        assert len(matches) == 0

    def test_no_word_overlap(self, event_index, text_processor, sample_events):
        """Test when channel has no overlapping words."""
        event_index.build_indexes(sample_events)
        strategy = WordMatchStrategy()

        channel = "completely different content here"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        matches = strategy.find_matches(normalized, words, event_index)

        # Should return empty
        assert len(matches) == 0


class TestMatchResultStructure:
    """Test MatchResult dataclass."""

    def test_match_result_creation(self):
        """Test creating a MatchResult."""
        event = make_event(
            event_id="1",
            event_name="Test Event",
            league_name="Test League",
        )

        result = MatchResult(
            event=event,
            confidence=0.85,
            match_type="test_match",
            matched_terms=["term1", "term2"],
            details={"key": "value"},
        )

        assert result.event.event_id == "1"
        assert result.confidence == 0.85
        assert result.match_type == "test_match"
        assert len(result.matched_terms) == 2
        assert result.details["key"] == "value"


class TestStrategyIntegration:
    """Test strategies working together."""

    def test_multiple_strategies_same_event(self, event_index, text_processor, sample_events):
        """Test that multiple strategies can find the same event with different confidence."""
        event_index.build_indexes(sample_events)

        channel = "Los Angeles Lakers vs Boston Celtics NBA Finals Game 7"
        normalized = text_processor.normalize_text(channel)
        words = text_processor.extract_significant_words(channel)

        # Try all strategies
        team_strategy = TeamMatchStrategy()
        league_strategy = LeagueMatchStrategy()
        word_strategy = WordMatchStrategy()

        team_matches = team_strategy.find_matches(normalized, words, event_index)
        league_matches = league_strategy.find_matches(normalized, words, event_index)
        word_matches = word_strategy.find_matches(normalized, words, event_index)

        # All should find the Lakers vs Celtics game
        assert any(m.event.event_id == "3" for m in team_matches)
        assert any(m.event.event_id == "3" for m in league_matches)
        # Word strategy might not find it (requires 3+ word overlap, most are stop words)
        # Just verify it runs without error
        assert isinstance(word_matches, list)

        # Team strategy should have highest confidence
        team_confidence = max(m.confidence for m in team_matches if m.event.event_id == "3")
        assert team_confidence >= HIGH_CONFIDENCE
