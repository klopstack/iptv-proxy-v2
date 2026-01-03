"""
Tests for TheSportsDB Calendar Scraper Service

Tests the calendar scraping functionality without making actual HTTP requests.
"""

from datetime import timezone
from unittest.mock import patch

import pytest

from services.thesportsdb_calendar_scraper import CalendarEvent, TheSportsDBCalendarScraper


class TestCalendarEvent:
    """Tests for CalendarEvent class."""

    def test_calendar_event_creation(self):
        """Test basic CalendarEvent creation."""
        event = CalendarEvent(
            event_id="2376181",
            event_name="Team A vs Team B",
            league_name="Test League",
            time_utc="14:30",
            date="2024-01-15",
        )

        assert event.event_id == "2376181"
        assert event.event_name == "Team A vs Team B"
        assert event.league_name == "Test League"
        assert event.time_utc == "14:30"
        assert event.date == "2024-01-15"

    def test_calendar_event_with_teams(self):
        """Test CalendarEvent with parsed team names."""
        event = CalendarEvent(
            event_id="123",
            event_name="Arsenal vs Chelsea",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Arsenal",
            away_team="Chelsea",
        )

        assert event.home_team == "Arsenal"
        assert event.away_team == "Chelsea"

    def test_scheduled_at_property(self):
        """Test scheduled_at datetime parsing."""
        event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test League",
            time_utc="14:30",
            date="2024-06-15",
        )

        scheduled = event.scheduled_at
        assert scheduled is not None
        assert scheduled.year == 2024
        assert scheduled.month == 6
        assert scheduled.day == 15
        assert scheduled.hour == 14
        assert scheduled.minute == 30
        assert scheduled.tzinfo == timezone.utc

    def test_scheduled_at_handles_invalid_time(self):
        """Test scheduled_at returns None for invalid time."""
        event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test League",
            time_utc="invalid",
            date="2024-06-15",
        )

        assert event.scheduled_at is None

    def test_to_dict(self):
        """Test dictionary conversion."""
        event = CalendarEvent(
            event_id="123",
            event_name="Team A vs Team B",
            league_name="Test League",
            time_utc="14:30",
            date="2024-06-15",
            home_team="Team A",
            away_team="Team B",
            event_url="https://thesportsdb.com/event/123",
        )

        data = event.to_dict()

        assert data["event_id"] == "123"
        assert data["event_name"] == "Team A vs Team B"
        assert data["league_name"] == "Test League"
        assert data["home_team"] == "Team A"
        assert data["away_team"] == "Team B"
        assert data["scheduled_at"] is not None


class TestTheSportsDBCalendarScraper:
    """Tests for TheSportsDBCalendarScraper class."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance for testing."""
        return TheSportsDBCalendarScraper(cache_ttl=60)

    def test_cache_key_generation(self, scraper):
        """Test cache key format."""
        key = scraper._get_cache_key("2024-06-15", "")
        assert key == "2024-06-15:"

        key_with_sport = scraper._get_cache_key("2024-06-15", "Boxing")
        assert key_with_sport == "2024-06-15:Boxing"

    def test_cache_validation(self, scraper):
        """Test cache validity checking."""
        # Empty cache should be invalid
        assert not scraper._is_cache_valid("2024-06-15:")

        # Add something to cache
        import time

        scraper._cache["2024-06-15:"] = ([], time.time())
        assert scraper._is_cache_valid("2024-06-15:")

    def test_parse_teams_from_event_name_vs(self, scraper):
        """Test team extraction with 'vs' separator."""
        home, away = scraper._parse_teams_from_event_name("Arsenal vs Chelsea")
        assert home == "Arsenal"
        assert away == "Chelsea"

    def test_parse_teams_from_event_name_vs_dot(self, scraper):
        """Test team extraction with 'vs.' separator."""
        home, away = scraper._parse_teams_from_event_name("Team A vs. Team B")
        assert home == "Team A"
        assert away == "Team B"

    def test_parse_teams_from_event_name_at(self, scraper):
        """Test team extraction with 'at' separator."""
        home, away = scraper._parse_teams_from_event_name("Lakers at Celtics")
        assert home == "Lakers"
        assert away == "Celtics"

    def test_parse_teams_from_event_name_no_separator(self, scraper):
        """Test team extraction with no recognized separator."""
        home, away = scraper._parse_teams_from_event_name("Single Team Event")
        assert home is None
        assert away is None

    def test_time_difference_minutes(self, scraper):
        """Test time difference calculation."""
        diff = scraper._time_difference_minutes("14:30", "15:00")
        assert diff == 30

        diff = scraper._time_difference_minutes("00:00", "23:59")
        assert diff == 1439  # 23 hours 59 minutes

    def test_time_difference_invalid(self, scraper):
        """Test time difference with invalid input."""
        diff = scraper._time_difference_minutes("invalid", "15:00")
        assert diff is None

    def test_fuzzy_team_match_exact(self, scraper):
        """Test fuzzy team matching with exact match."""
        event = CalendarEvent(
            event_id="123",
            event_name="Arsenal vs Chelsea",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Arsenal",
            away_team="Chelsea",
        )

        assert scraper._fuzzy_team_match("arsenal", event)
        assert scraper._fuzzy_team_match("chelsea", event)
        assert not scraper._fuzzy_team_match("liverpool", event)

    def test_fuzzy_team_match_partial(self, scraper):
        """Test fuzzy team matching with partial match."""
        event = CalendarEvent(
            event_id="123",
            event_name="Manchester United vs Manchester City",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Manchester United",
            away_team="Manchester City",
        )

        # Should match partial names
        assert scraper._fuzzy_team_match("manchester", event)
        assert scraper._fuzzy_team_match("united", event)
        assert scraper._fuzzy_team_match("city", event)

    def test_calculate_match_confidence_both_competitors(self, scraper):
        """Test confidence calculation with both competitors matching."""
        event = CalendarEvent(
            event_id="123",
            event_name="Arsenal vs Chelsea",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Arsenal",
            away_team="Chelsea",
        )

        confidence = scraper._calculate_match_confidence(
            event,
            competitors=("Arsenal", "Chelsea"),
        )

        assert confidence >= 0.6  # Both teams should give high confidence

    def test_calculate_match_confidence_one_competitor(self, scraper):
        """Test confidence calculation with one competitor matching."""
        event = CalendarEvent(
            event_id="123",
            event_name="Arsenal vs Chelsea",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Arsenal",
            away_team="Chelsea",
        )

        confidence = scraper._calculate_match_confidence(
            event,
            competitors=("Arsenal", "Liverpool"),
        )

        assert confidence >= 0.3
        assert confidence < 0.6  # Only one team matches

    def test_calculate_match_confidence_with_time(self, scraper):
        """Test confidence calculation including time match."""
        event = CalendarEvent(
            event_id="123",
            event_name="Arsenal vs Chelsea",
            league_name="Premier League",
            time_utc="15:00",
            date="2024-03-01",
            home_team="Arsenal",
            away_team="Chelsea",
        )

        confidence = scraper._calculate_match_confidence(
            event,
            competitors=("Arsenal", "Chelsea"),
            time_utc="15:00",  # Exact time match
        )

        # Should be higher than without time match
        confidence_no_time = scraper._calculate_match_confidence(
            event,
            competitors=("Arsenal", "Chelsea"),
        )

        assert confidence > confidence_no_time

    def test_clear_cache(self, scraper):
        """Test cache clearing."""
        import time

        scraper._cache["test"] = ([], time.time())
        assert len(scraper._cache) == 1

        scraper.clear_cache()
        assert len(scraper._cache) == 0

    def test_get_cache_stats(self, scraper):
        """Test cache statistics."""
        import time

        scraper._cache["test1"] = ([], time.time())
        scraper._cache["test2"] = ([], time.time() - 10000)  # Old entry

        stats = scraper.get_cache_stats()

        assert "total_entries" in stats
        assert "valid_entries" in stats
        assert stats["total_entries"] == 2


class TestCalendarHTMLParsing:
    """Tests for HTML parsing functionality."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance."""
        return TheSportsDBCalendarScraper()

    @pytest.fixture
    def sample_html(self):
        """Sample calendar HTML for testing."""
        return """
        <table>
            <tr>
                <td>14:30 UTC </td>
                <td width='20'> </td>
                <td><img src='https://example.com/league.png'/> Premier League</td>
                <td width='20'> </td>
                <td><img src='https://example.com/flag.png'/> <a href='/event/2376181-arsenal-vs-chelsea' title='Arsenal vs Chelsea'>Arsenal vs Chelsea</a></td>
            </tr>
            <tr>
                <td>18:00 UTC </td>
                <td width='20'> </td>
                <td><img src='https://example.com/nba.png'/> NBA</td>
                <td width='20'> </td>
                <td><img src='https://example.com/usa.png'/> <a href='/event/9876543-lakers-vs-celtics'>Lakers vs Celtics</a></td>
            </tr>
            <tr>
                <td>Not a valid row</td>
            </tr>
        </table>
        """

    def test_parse_calendar_html(self, scraper, sample_html):
        """Test parsing of calendar HTML."""
        events = scraper._parse_calendar_html(sample_html, "2024-03-01")

        assert len(events) == 2

        # First event
        assert events[0].event_id == "2376181"
        assert events[0].event_name == "Arsenal vs Chelsea"
        assert events[0].league_name == "Premier League"
        assert "14:30" in events[0].time_utc or events[0].time_utc == "14:30"

        # Second event
        assert events[1].event_id == "9876543"
        assert events[1].event_name == "Lakers vs Celtics"
        assert events[1].league_name == "NBA"

    def test_parse_event_row_valid(self, scraper):
        """Test parsing a valid event row."""
        from bs4 import BeautifulSoup

        row_html = """
        <tr>
            <td>20:00 UTC </td>
            <td width='20'> </td>
            <td><img src='icon.png'/> UFC</td>
            <td width='20'> </td>
            <td><img src='flag.png'/> <a href='/event/1234567-fighter-a-vs-fighter-b'>Fighter A vs Fighter B</a></td>
        </tr>
        """
        soup = BeautifulSoup(row_html, "html.parser")
        row = soup.find("tr")

        event = scraper._parse_event_row(row, "2024-06-15")

        assert event is not None
        assert event.event_id == "1234567"
        assert event.event_name == "Fighter A vs Fighter B"
        assert event.league_name == "UFC"
        assert event.home_team == "Fighter A"
        assert event.away_team == "Fighter B"

    def test_parse_event_row_no_link(self, scraper):
        """Test parsing a row without an event link."""
        from bs4 import BeautifulSoup

        row_html = """
        <tr>
            <td>20:00 UTC </td>
            <td width='20'> </td>
            <td>League</td>
            <td width='20'> </td>
            <td>No link here</td>
        </tr>
        """
        soup = BeautifulSoup(row_html, "html.parser")
        row = soup.find("tr")

        event = scraper._parse_event_row(row, "2024-06-15")
        assert event is None

    def test_parse_event_row_insufficient_cells(self, scraper):
        """Test parsing a row with not enough cells."""
        from bs4 import BeautifulSoup

        row_html = """
        <tr>
            <td>Just one cell</td>
        </tr>
        """
        soup = BeautifulSoup(row_html, "html.parser")
        row = soup.find("tr")

        event = scraper._parse_event_row(row, "2024-06-15")
        assert event is None


class TestFindMatchingEvents:
    """Tests for the find_matching_events method."""

    @pytest.fixture
    def scraper_with_events(self):
        """Create a scraper with pre-cached events."""
        scraper = TheSportsDBCalendarScraper()

        # Create mock events
        events = [
            CalendarEvent(
                event_id="1",
                event_name="Arsenal vs Chelsea",
                league_name="Premier League",
                time_utc="15:00",
                date="2024-03-01",
                home_team="Arsenal",
                away_team="Chelsea",
            ),
            CalendarEvent(
                event_id="2",
                event_name="Manchester United vs Liverpool",
                league_name="Premier League",
                time_utc="17:30",
                date="2024-03-01",
                home_team="Manchester United",
                away_team="Liverpool",
            ),
            CalendarEvent(
                event_id="3",
                event_name="Canelo vs Plant",
                league_name="Boxing",
                time_utc="04:00",
                date="2024-03-01",
                home_team="Canelo",
                away_team="Plant",
            ),
        ]

        # Pre-populate cache
        import time

        scraper._cache["2024-03-01:"] = (events, time.time())

        return scraper

    def test_find_by_competitors(self, scraper_with_events):
        """Test finding events by competitor names."""
        matches = scraper_with_events.find_matching_events(
            date="2024-03-01",
            competitors=("Arsenal", "Chelsea"),
        )

        assert len(matches) > 0
        best_event, confidence = matches[0]
        assert best_event.event_id == "1"
        assert confidence >= 0.6

    def test_find_by_partial_competitors(self, scraper_with_events):
        """Test finding events by partial competitor names."""
        matches = scraper_with_events.find_matching_events(
            date="2024-03-01",
            competitors=("Canelo", "Plant"),
        )

        assert len(matches) > 0
        best_event, confidence = matches[0]
        assert best_event.event_id == "3"

    def test_find_with_time_filter(self, scraper_with_events):
        """Test finding events with time constraint."""
        # Should prefer the event closer to specified time
        matches = scraper_with_events.find_matching_events(
            date="2024-03-01",
            competitors=("Arsenal", "Chelsea"),
            time_utc="15:00",
        )

        assert len(matches) > 0
        best_event, _ = matches[0]
        assert best_event.event_id == "1"

    def test_find_no_matches(self, scraper_with_events):
        """Test when no events match."""
        matches = scraper_with_events.find_matching_events(
            date="2024-03-01",
            competitors=("Real Madrid", "Barcelona"),
        )

        # Should return empty or low-confidence matches
        if matches:
            _, confidence = matches[0]
            assert confidence < 0.3  # Very low confidence


class TestIntegration:
    """Integration tests (with mocked HTTP)."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance."""
        return TheSportsDBCalendarScraper()

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_get_events_for_date_uses_cache(self, mock_fetch, scraper):
        """Test that subsequent calls use cache."""
        mock_events = [
            CalendarEvent(
                event_id="1",
                event_name="Test Event",
                league_name="Test League",
                time_utc="15:00",
                date="2024-03-01",
            )
        ]
        mock_fetch.return_value = mock_events

        # First call should fetch
        events1 = scraper.get_events_for_date("2024-03-01")
        assert mock_fetch.call_count == 1
        assert len(events1) == 1

        # Second call should use cache
        events2 = scraper.get_events_for_date("2024-03-01")
        assert mock_fetch.call_count == 1  # No additional fetch
        assert len(events2) == 1

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_force_refresh_bypasses_cache(self, mock_fetch, scraper):
        """Test that force_refresh bypasses cache."""
        mock_events = [
            CalendarEvent(
                event_id="1",
                event_name="Test Event",
                league_name="Test League",
                time_utc="15:00",
                date="2024-03-01",
            )
        ]
        mock_fetch.return_value = mock_events

        # First call
        scraper.get_events_for_date("2024-03-01")
        assert mock_fetch.call_count == 1

        # Force refresh should fetch again
        scraper.get_events_for_date("2024-03-01", force_refresh=True)
        assert mock_fetch.call_count == 2
