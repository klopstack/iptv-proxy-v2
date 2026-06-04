"""Tests for EventIndex component."""

from datetime import datetime, timezone

import pytest

from services.reverse_event_matcher.event_index import EventIndex
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
            event_name="UFC 300",
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
            home_team=None,
            away_team=None,
        ),
        make_event(
            event_id="5",
            event_name="Boxing Match",
            league_name="Boxing",
            home_team="Jake Paul Jr",
            away_team="Tommy Fury",
        ),
    ]


class TestEventIndexBasics:
    """Test basic EventIndex functionality."""

    def test_initialization(self, event_index):
        """Test EventIndex initializes with empty indexes."""
        assert len(event_index.team_index) == 0
        assert len(event_index.event_name_index) == 0
        assert len(event_index.league_index) == 0
        assert len(event_index.word_index) == 0
        assert len(event_index.last_name_index) == 0
        assert len(event_index.first_name_index) == 0

    def test_build_indexes(self, event_index, sample_events):
        """Test building indexes from events."""
        event_index.build_indexes(sample_events)

        # Should have indexed teams, events, leagues
        assert len(event_index.team_index) > 0
        assert len(event_index.event_name_index) > 0
        assert len(event_index.league_index) > 0
        assert len(event_index.word_index) > 0

    def test_clear_indexes(self, event_index, sample_events):
        """Test clearing all indexes."""
        event_index.build_indexes(sample_events)
        assert len(event_index.team_index) > 0

        event_index.clear()
        assert len(event_index.team_index) == 0
        assert len(event_index.event_name_index) == 0
        assert len(event_index.league_index) == 0
        assert len(event_index.word_index) == 0

    def test_get_stats(self, event_index, sample_events):
        """Test getting index statistics."""
        event_index.build_indexes(sample_events)

        stats = event_index.get_stats()
        assert "teams" in stats
        assert "event_names" in stats
        assert "leagues" in stats
        assert "words" in stats
        assert "last_names" in stats
        assert "first_names" in stats

        # Should have some teams indexed
        assert stats["teams"] > 0


class TestTeamIndexing:
    """Test team name indexing."""

    def test_team_index_basic(self, event_index, sample_events):
        """Test teams are indexed correctly."""
        event_index.build_indexes(sample_events)

        # Check normalized team names are in index
        assert "manchester united" in event_index.team_index
        assert "liverpool fc" in event_index.team_index
        assert "los angeles lakers" in event_index.team_index

    def test_team_index_multiple_events(self, event_index):
        """Test same team in multiple events."""
        events = [
            make_event(
                event_id="1",
                event_name="Match 1",
                league_name="NBA",
                home_team="Lakers",
                away_team="Celtics",
            ),
            make_event(
                event_id="2",
                event_name="Match 2",
                league_name="NBA",
                home_team="Lakers",
                away_team="Warriors",
            ),
        ]

        event_index.build_indexes(events)

        # Lakers should appear in index for both events
        lakers_events = event_index.team_index["lakers"]
        assert len(lakers_events) == 2

    def test_normalized_teams_map(self, event_index, sample_events):
        """Test normalized teams map stores original names."""
        event_index.build_indexes(sample_events)

        # Check we can get original team name from normalized
        assert event_index.normalized_teams["manchester united"] == "Manchester United"
        assert event_index.normalized_teams["liverpool fc"] == "Liverpool FC"


class TestNamePartIndexing:
    """Test first/last name indexing for individual sports."""

    def test_last_name_indexing(self, event_index, sample_events):
        """Test last names are indexed for individual athletes."""
        event_index.build_indexes(sample_events)

        # Should index last names from "Amanda Serrano"
        assert "serrano" in event_index.last_name_index
        assert "tellez" in event_index.last_name_index

        # Check events are associated
        serrano_events = event_index.last_name_index["serrano"]
        assert len(serrano_events) > 0
        assert serrano_events[0].home_team == "Amanda Serrano"

    def test_first_name_indexing(self, event_index, sample_events):
        """Test first names are indexed for individual athletes."""
        event_index.build_indexes(sample_events)

        # Should index first names from "Amanda Serrano"
        assert "amanda" in event_index.first_name_index
        assert "reina" in event_index.first_name_index

    def test_three_part_names(self, event_index, sample_events):
        """Test three-part names like 'Jake Paul Jr'."""
        event_index.build_indexes(sample_events)

        # For "Jake Paul Jr": first_name="jake", last_name="jr" (but "jr" is too short to index)
        assert "jake" in event_index.first_name_index
        # "jr" is only 2 chars, so it won't be in last_name_index (MIN_WORD_LENGTH=4)
        assert "jr" not in event_index.last_name_index

    def test_team_names_not_indexed_as_people(self, event_index, sample_events):
        """Test team names are not indexed as individual names."""
        event_index.build_indexes(sample_events)

        # "Manchester United" has team suffix, shouldn't be in name indexes
        assert "manchester" not in event_index.last_name_index
        assert "united" not in event_index.last_name_index

    def test_name_parts_map(self, event_index, sample_events):
        """Test name parts map stores first and last names."""
        event_index.build_indexes(sample_events)

        # Should have name parts for "amanda serrano"
        assert "amanda serrano" in event_index.name_parts
        first, last = event_index.name_parts["amanda serrano"]
        assert first == "amanda"
        assert last == "serrano"

    def test_doubles_side_indexes_each_partner_last_name(self, event_index):
        """Tennis doubles calendar sides (Player A / Player B) index all surnames."""
        events = [
            make_event(
                event_id="d1",
                event_name="Doubles",
                league_name="WTA",
                home_team="Alize Cornet / Daniela Hantuchova",
                away_team="Martina Hingis / Angelique Kerber",
            ),
        ]
        event_index.build_indexes(events)

        for surname in ("cornet", "hantuchova", "hingis", "kerber"):
            assert surname in event_index.last_name_index

    def test_single_word_name(self, event_index):
        """Test single-word names are treated as last name."""
        events = [
            make_event(
                event_id="1",
                event_name="Fight",
                league_name="Boxing",
                home_team="Madonna",
                away_team="Cher",
            ),
        ]

        event_index.build_indexes(events)

        # Single names should be in last_name_index
        assert "madonna" in event_index.last_name_index
        assert "cher" in event_index.last_name_index

        # Should have name parts with empty first name
        assert event_index.name_parts["madonna"] == ("", "madonna")


class TestEventNameIndexing:
    """Test event name indexing."""

    def test_event_name_index(self, event_index, sample_events):
        """Test event names are indexed."""
        event_index.build_indexes(sample_events)

        # Check normalized event names
        assert "ufc 300" in event_index.event_name_index
        assert "premier league match" in event_index.event_name_index
        assert "nba finals game 7" in event_index.event_name_index

    def test_event_name_words_indexed(self, event_index, sample_events):
        """Test significant words from event names are indexed."""
        event_index.build_indexes(sample_events)

        # Words from "Formula 1 Monaco Grand Prix" that meet MIN_WORD_LENGTH=4
        assert "monaco" in event_index.word_index
        assert "grand" in event_index.word_index
        assert "prix" in event_index.word_index  # Exactly 4 chars, should be indexed
        assert "formula" in event_index.word_index


class TestLeagueIndexing:
    """Test league name indexing."""

    def test_league_index(self, event_index, sample_events):
        """Test leagues are indexed."""
        event_index.build_indexes(sample_events)

        # Check normalized league names
        assert "ufc" in event_index.league_index
        assert "premier league" in event_index.league_index
        assert "nba" in event_index.league_index
        assert "formula 1" in event_index.league_index

    def test_league_words_indexed(self, event_index, sample_events):
        """Test significant words from league names are indexed."""
        event_index.build_indexes(sample_events)

        # "Premier" and "League" and "Boxing" are all stop words, so they won't be indexed
        # "Formula" from "Formula 1" should be indexed (7 chars, not a stop word)
        assert "formula" in event_index.word_index

        # Verify stop words are NOT indexed
        assert "premier" not in event_index.word_index
        assert "league" not in event_index.word_index
        assert "boxing" not in event_index.word_index


class TestWordIndexing:
    """Test word-based indexing."""

    def test_word_index_filters_stop_words(self, event_index):
        """Test that stop words are not indexed."""
        events = [
            make_event(
                event_id="1",
                event_name="The Big Match of the Year",
                league_name="Sports",
            ),
        ]

        event_index.build_indexes(events)

        # Stop words like "the", "of" should not be indexed
        assert "the" not in event_index.word_index
        assert "of" not in event_index.word_index

        # Significant words should be indexed
        assert "year" in event_index.word_index

    def test_word_index_minimum_length(self, event_index):
        """Test that short words are not indexed."""
        events = [
            make_event(
                event_id="1",
                event_name="UFC vs NBA",
                league_name="Sports",
            ),
        ]

        event_index.build_indexes(events)

        # Short words (less than 4 chars) should not be indexed
        assert "ufc" not in event_index.word_index
        assert "nba" not in event_index.word_index

    def test_word_index_from_multiple_sources(self, event_index, sample_events):
        """Test words are indexed from both event and league names."""
        event_index.build_indexes(sample_events)

        # "formula" appears in league name "Formula 1" (7 chars, not a stop word)
        assert "formula" in event_index.word_index
        formula_events = event_index.word_index["formula"]

        # Should have the Formula 1 event
        assert len(formula_events) >= 1


class TestRealWorldScenarios:
    """Test with real-world-like scenarios."""

    def test_boxing_match_indexing(self, event_index):
        """Test indexing a boxing match with individual athletes."""
        events = [
            make_event(
                event_id="1",
                event_name="UFC 300 - Serrano vs Tellez",
                league_name="UFC",
                home_team="Amanda Serrano",
                away_team="Reina Tellez",
            ),
        ]

        event_index.build_indexes(events)

        # Should index last names
        assert "serrano" in event_index.last_name_index
        assert "tellez" in event_index.last_name_index

        # Should index event name (normalization keeps "vs" since it's not removed)
        assert "ufc 300 serrano vs tellez" in event_index.event_name_index

        # Should index league
        assert "ufc" in event_index.league_index

        # Should index team names
        assert "amanda serrano" in event_index.team_index
        assert "reina tellez" in event_index.team_index

    def test_soccer_match_indexing(self, event_index):
        """Test indexing a soccer match with team names."""
        events = [
            make_event(
                event_id="1",
                event_name="Premier League",
                league_name="Premier League",
                home_team="Manchester United FC",
                away_team="Liverpool FC",
            ),
        ]

        event_index.build_indexes(events)

        # Teams should be indexed
        assert "manchester united fc" in event_index.team_index
        assert "liverpool fc" in event_index.team_index

        # Team names should NOT be in last_name_index (they have "FC" suffix)
        assert "manchester" not in event_index.last_name_index
        assert "liverpool" not in event_index.last_name_index

    def test_rebuild_indexes(self, event_index, sample_events):
        """Test rebuilding indexes with new events."""
        # Build with initial events
        event_index.build_indexes(sample_events)
        initial_team_count = len(event_index.team_index)

        # Add more events and rebuild
        more_events = sample_events + [
            make_event(
                event_id="99",
                event_name="New Match",
                league_name="New League",
                home_team="New Team A",
                away_team="New Team B",
            ),
        ]

        event_index.build_indexes(more_events)

        # Should have more teams now
        assert len(event_index.team_index) > initial_team_count
        assert "new team a" in event_index.team_index
