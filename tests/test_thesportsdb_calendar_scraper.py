"""
Tests for TheSportsDB Calendar Scraper Service

Tests the calendar scraping functionality without making actual HTTP requests.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.thesportsdb_calendar_scraper import CACHE_KEY_VERSION, CalendarEvent, TheSportsDBCalendarScraper


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

    def test_scheduled_at_handles_empty_time(self):
        """Test scheduled_at returns None for empty time string."""
        event = CalendarEvent(
            event_id="2385975",
            event_name="Test Event",
            league_name="Test League",
            time_utc="",
            date="2024-06-15",
        )

        assert event.scheduled_at is None

    def test_scheduled_at_handles_empty_date(self):
        """Test scheduled_at returns None for empty date string."""
        event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test League",
            time_utc="14:30",
            date="",
        )

        assert event.scheduled_at is None

    def test_scheduled_at_handles_malformed_time_parts(self):
        """Test scheduled_at returns None when time has empty parts."""
        event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test League",
            time_utc=":30",  # Empty hour part
            date="2024-06-15",
        )

        assert event.scheduled_at is None

    def test_scheduled_at_handles_malformed_date_parts(self):
        """Test scheduled_at returns None when date has missing parts."""
        event = CalendarEvent(
            event_id="123",
            event_name="Test Event",
            league_name="Test League",
            time_utc="14:30",
            date="2024--15",  # Empty month part
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
        assert data["scheduled_at"].endswith("Z")


class TestTheSportsDBCalendarScraper:
    """Tests for TheSportsDBCalendarScraper class."""

    @pytest.fixture
    def scraper(self, tmp_path):
        """Create a scraper instance for testing with isolated cache."""
        return TheSportsDBCalendarScraper(cache_ttl=60, cache_dir=str(tmp_path))

    def test_cache_key_generation(self, scraper):
        """Test cache key format."""
        key = scraper._get_cache_key("2024-06-15", "")
        assert key.startswith(f"{CACHE_KEY_VERSION}:2024-06-15:")
        assert key.endswith(":anon")

        key_with_sport = scraper._get_cache_key("2024-06-15", "Boxing")
        assert key_with_sport == f"{CACHE_KEY_VERSION}:2024-06-15:Boxing:anon"

    def test_is_login_page_with_error(self):
        assert TheSportsDBCalendarScraper._is_login_page_with_error("<h2>Login</h2><div class='form-group has-error'>")
        assert not TheSportsDBCalendarScraper._is_login_page_with_error(
            "<h2>Welcome</h2><a href='/browse.php'>Browse</a>"
        )

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._load_site_credentials")
    def test_cache_key_includes_auth_suffix(self, mock_creds, scraper):
        mock_creds.return_value = ("alice", "secret")
        assert scraper._get_cache_key("2026-05-31").endswith(":auth:alice")

    @patch("services.thesportsdb_calendar_scraper.requests.Session.post")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._load_site_credentials")
    def test_ensure_site_login_success(self, mock_creds, mock_post, scraper):
        mock_creds.return_value = ("alice", "secret")
        mock_post.return_value.text = "<html><a href='/browse.php'>Browse</a></html>"
        mock_post.return_value.raise_for_status = lambda: None

        scraper._ensure_site_login()

        assert scraper._authenticated_user == "alice"
        assert scraper._login_verified is True
        mock_post.assert_called_once()

    @patch("services.thesportsdb_calendar_scraper.requests.Session.post")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._load_site_credentials")
    def test_ensure_site_login_failure(self, mock_creds, mock_post, scraper):
        mock_creds.return_value = ("alice", "wrong")
        mock_post.return_value.text = "<h2>Login</h2><div class='form-group has-error'>"
        mock_post.return_value.raise_for_status = lambda: None

        scraper._ensure_site_login()

        assert scraper._authenticated_user is None
        assert scraper._login_verified is False

    @patch("services.thesportsdb_retry.fetch_url_with_retry")
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._parse_calendar_html",
        return_value=[],
    )
    def test_fetch_calendar_page_uses_retry_fetch(self, mock_parse, mock_fetch_url, scraper):
        mock_response = MagicMock()
        mock_response.text = "<html><table><a href='/event/1'>Game</a></table></html>"
        mock_fetch_url.return_value = mock_response

        scraper._fetch_calendar_page("2026-05-31")

        mock_fetch_url.assert_called_once()
        assert mock_fetch_url.call_args.kwargs["before_attempt"] == scraper._before_calendar_fetch

    def test_api_supplement_sports_includes_combat_and_racket(self):
        from services.thesportsdb_calendar_scraper import API_SUPPLEMENT_SPORTS

        assert "Fighting" in API_SUPPLEMENT_SPORTS
        assert "Tennis" in API_SUPPLEMENT_SPORTS
        assert "Cricket" in API_SUPPLEMENT_SPORTS

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._rate_limit")
    @patch("services.thesportsdb_retry.call_thesportsdb_api")
    def test_fetch_api_events_supplements_multiple_sports(self, mock_call_api, mock_rate_limit, scraper):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_call_api.return_value = {"events": []}

        scraper._fetch_api_events_for_date(today)

        sports_called = {call.kwargs.get("s") for call in mock_call_api.call_args_list}
        assert "Fighting" in sports_called
        assert "Tennis" in sports_called

    def test_is_date_in_api_supplement_window(self, scraper):
        today = datetime.now(timezone.utc).date()
        near = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        far = (today + timedelta(days=120)).strftime("%Y-%m-%d")

        assert scraper._is_date_in_api_supplement_window(near) is True
        assert scraper._is_date_in_api_supplement_window(far) is False

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._rate_limit")
    @patch("services.thesportsdb_retry.call_thesportsdb_api")
    def test_fetch_api_events_skips_non_json_response(self, mock_call_api, mock_rate_limit, scraper):
        mock_call_api.return_value = "<!doctype html><html></html>"

        events = scraper._fetch_api_events_for_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        assert events == []

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._rate_limit")
    @patch("services.thesportsdb_retry.call_thesportsdb_api")
    def test_fetch_api_events_parses_valid_response(self, mock_call_api, mock_rate_limit, scraper):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_call_api.return_value = {
            "events": [
                {
                    "idEvent": "123",
                    "strEvent": "Team A vs Team B",
                    "strLeague": "MLB",
                    "strTime": "19:05:00",
                    "strHomeTeam": "Team A",
                    "strAwayTeam": "Team B",
                }
            ]
        }

        events = scraper._fetch_api_events_for_date(today, sport="Baseball")

        assert len(events) == 1
        assert events[0].event_id == "123"

    def test_cache_validation(self, scraper):
        """Test cache validity checking."""
        cache_key = scraper._get_cache_key("2024-06-15", "")

        # Empty cache should be invalid
        assert not scraper._is_cache_valid(cache_key)

        # Add something to cache
        import time

        from services.thesportsdb_calendar_scraper import CalendarEvent

        sample_event = CalendarEvent(
            event_id="1",
            event_name="A vs B",
            league_name="League",
            time_utc="12:00",
            date="2024-06-15",
        )
        scraper._cache[cache_key] = ([sample_event], time.time())
        assert scraper._is_cache_valid(cache_key)

        # Empty event lists should not be considered valid
        empty_key = scraper._get_cache_key("2024-06-16", "")
        scraper._cache[empty_key] = ([], time.time())
        assert not scraper._is_cache_valid(empty_key)

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

    def test_parse_event_row_new_four_column_layout(self, scraper):
        """Test parsing the current 4-column TheSportsDB calendar layout."""
        from bs4 import BeautifulSoup

        row_html = """
        <tr>
            <td>00:00</td>
            <td>Soccer</td>
            <td>American USL Championship</td>
            <td><a href="/event/2478663-buriram-united-vs-prachuap">
                <img alt="event thumbnail" src="/images/no_thumb.png"/>
                <span>Buriram United vs Prachuap</span>
            </a></td>
        </tr>
        """
        soup = BeautifulSoup(row_html, "html.parser")
        row = soup.find("tr")

        event = scraper._parse_event_row(row, "2026-05-31")

        assert event is not None
        assert event.event_id == "2478663"
        assert event.event_name == "Buriram United vs Prachuap"
        assert event.league_name == "American USL Championship"
        assert event.time_utc == "00:00"
        assert event.home_team == "Buriram United"
        assert event.away_team == "Prachuap"
        assert event.sport == "Soccer"

    def test_parse_event_row_baseball_column_layout(self, scraper):
        """Sport column from browse_calendar (e.g. Baseball | MLB | event)."""
        from bs4 import BeautifulSoup

        row_html = """
        <tr>
            <td>23:10</td>
            <td><img src="/images/icons/svg/sports/baseball.svg"/>
                <a href="/browse_calendar/?d=2026-06-04&amp;s=baseball">Baseball</a></td>
            <td><img src="league.png"/> MLB</td>
            <td><a href="/event/2388001-san-francisco-giants-vs-chicago-cubs">
                San Francisco Giants vs Chicago Cubs</a></td>
        </tr>
        """
        soup = BeautifulSoup(row_html, "html.parser")
        event = scraper._parse_event_row(soup.find("tr"), "2026-06-07")

        assert event is not None
        assert event.sport == "Baseball"
        assert event.league_name == "MLB"

    def test_parse_calendar_html_new_layout(self, scraper):
        """Test parsing calendar HTML with the 4-column layout."""
        html = """
        <table>
            <tr>
                <td></td>
                <td>Soccer</td>
                <td>FA Cup</td>
                <td><a href="/event/1111111-team-a-vs-team-b">Team A vs Team B</a></td>
            </tr>
            <tr>
                <td>14:30</td>
                <td>Basketball</td>
                <td>NBA</td>
                <td><a href="/event/2222222-lakers-vs-celtics">Lakers vs Celtics</a></td>
            </tr>
        </table>
        """
        events = scraper._parse_calendar_html(html, "2026-05-31")

        assert len(events) == 2
        assert events[0].event_id == "1111111"
        assert events[0].time_utc == "00:00"
        assert events[0].sport == "Soccer"
        assert events[1].event_id == "2222222"
        assert events[1].time_utc == "14:30"
        assert events[1].sport == "Basketball"

    def test_from_thesportsdb_api_sets_str_sport(self):
        raw = {
            "idEvent": "2388001",
            "strEvent": "San Francisco Giants vs Chicago Cubs",
            "strLeague": "MLB",
            "strSport": "Baseball",
            "strHomeTeam": "Chicago Cubs",
            "strAwayTeam": "San Francisco Giants",
            "dateEvent": "2026-06-07",
            "strTime": "23:10:00",
        }
        event = CalendarEvent.from_thesportsdb_api(raw, date="2026-06-07")
        assert event is not None
        assert event.sport == "Baseball"
        assert event.league_name == "MLB"

    def test_merge_calendar_events_preserves_html_sport(self, scraper):
        html_event = CalendarEvent(
            event_id="1",
            event_name="Giants vs Cubs",
            league_name="MLB",
            time_utc="23:10",
            date="2026-06-07",
            sport="Baseball",
        )
        api_event = CalendarEvent(
            event_id="1",
            event_name="Giants vs Cubs",
            league_name="MLB",
            time_utc="23:10",
            date="2026-06-07",
            home_team="Chicago Cubs",
            away_team="San Francisco Giants",
        )
        merged = scraper._merge_calendar_events([html_event], [api_event])
        assert len(merged) == 1
        assert merged[0].sport == "Baseball"
        assert merged[0].home_team == "Chicago Cubs"


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

        scraper._cache[scraper._get_cache_key("2024-03-01")] = (events, time.time())

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
    def scraper(self, tmp_path):
        """Create a scraper instance with isolated cache."""
        return TheSportsDBCalendarScraper(cache_dir=str(tmp_path))

    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_sofascore_events_for_date",
        return_value={"tennis": [], "football": []},
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date",
        return_value=[],
    )
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_get_events_for_date_uses_cache(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        mock_espn_fetch,
        mock_sofascore_fetch,
        scraper,
    ):
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

    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_sofascore_events_for_date",
        return_value={"tennis": [], "football": []},
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date",
        return_value=[],
    )
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_force_refresh_bypasses_cache(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        mock_espn_fetch,
        mock_sofascore_fetch,
        scraper,
    ):
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

    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_sofascore_events_for_date",
        return_value={"tennis": [], "football": []},
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_get_events_merges_html_and_api(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        mock_espn_tennis_fetch,
        mock_sofascore_fetch,
        scraper,
    ):
        """API supplement events are merged with HTML calendar events."""
        mock_milb_fetch.return_value = []
        mock_fetch.return_value = [
            CalendarEvent(
                event_id="html-1",
                event_name="HTML Event",
                league_name="Test League",
                time_utc="15:00",
                date="2026-05-31",
            )
        ]
        mock_api_fetch.return_value = [
            CalendarEvent(
                event_id="api-1",
                event_name="Colorado Rockies vs San Francisco Giants",
                league_name="MLB",
                time_utc="19:05",
                date="2026-05-31",
                home_team="Colorado Rockies",
                away_team="San Francisco Giants",
            )
        ]

        events = scraper.get_events_for_date("2026-05-31", force_refresh=True)
        assert len(events) == 2
        assert {e.event_id for e in events} == {"html-1", "api-1"}


class TestPersistentCache:
    """Tests for persistent cache functionality."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """Create a temporary cache directory."""
        return str(tmp_path)

    @pytest.fixture
    def scraper_with_temp_cache(self, temp_cache_dir):
        """Create a scraper with a temporary cache directory."""
        return TheSportsDBCalendarScraper(cache_ttl=60, cache_dir=temp_cache_dir)

    def test_cache_file_path_set(self, scraper_with_temp_cache, temp_cache_dir):
        """Test that cache file path is set correctly."""
        import os

        expected_path = os.path.join(temp_cache_dir, "calendar_cache.json")
        assert scraper_with_temp_cache._cache_file == expected_path

    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_sofascore_events_for_date",
        return_value={"tennis": [], "football": []},
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date",
        return_value=[],
    )
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date",
        return_value=[],
    )
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_save_persistent_cache(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        mock_espn_fetch,
        mock_sofascore_fetch,
        scraper_with_temp_cache,
        temp_cache_dir,
    ):
        """Test that cache is saved to disk."""
        import json
        import os

        mock_events = [
            CalendarEvent(
                event_id="1",
                event_name="Test Event",
                league_name="Test League",
                time_utc="15:00",
                date="2024-03-01",
                home_team="Team A",
                away_team="Team B",
            )
        ]
        mock_fetch.return_value = mock_events

        # Fetch events (should trigger cache save)
        scraper_with_temp_cache.get_events_for_date("2024-03-01")

        # Check cache file exists
        cache_file = os.path.join(temp_cache_dir, "calendar_cache.json")
        assert os.path.exists(cache_file)

        # Check cache content
        with open(cache_file, "r") as f:
            data = json.load(f)

        cache_key = scraper_with_temp_cache._get_cache_key("2024-03-01")
        assert cache_key in data
        assert len(data[cache_key]["events"]) == 1
        assert data[cache_key]["events"][0]["event_id"] == "1"

    def test_load_persistent_cache(self, temp_cache_dir):
        """Test that cache is loaded from disk on startup."""
        import json
        import os
        import time

        # Create a cache file manually
        cache_file = os.path.join(temp_cache_dir, "calendar_cache.json")
        cache_key = f"{CACHE_KEY_VERSION}:2024-03-01::anon"
        cache_data = {
            cache_key: {
                "timestamp": time.time(),
                "events": [
                    {
                        "event_id": "saved1",
                        "event_name": "Saved Event",
                        "league_name": "Saved League",
                        "time_utc": "15:00",
                        "date": "2024-03-01",
                        "home_team": None,
                        "away_team": None,
                        "event_url": None,
                        "league_icon_url": None,
                        "country_flag_url": None,
                        "scheduled_at": "2024-03-01T15:00:00+00:00",
                    }
                ],
            }
        }

        os.makedirs(temp_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        # Create scraper - should load cache
        scraper = TheSportsDBCalendarScraper(cache_ttl=60, cache_dir=temp_cache_dir)

        # Check that cache was loaded
        assert scraper._cache_disk_loads == 1
        assert cache_key in scraper._cache
        events, _ = scraper._cache[cache_key]
        assert len(events) == 1
        assert events[0].event_id == "saved1"

    def test_expired_cache_not_loaded(self, temp_cache_dir):
        """Test that expired cache entries are not loaded."""
        import json
        import os
        import time

        # Create a cache file with old timestamp
        cache_file = os.path.join(temp_cache_dir, "calendar_cache.json")
        cache_key = f"{CACHE_KEY_VERSION}:2024-03-01::anon"
        cache_data = {
            cache_key: {
                "timestamp": time.time() - 100000,  # Very old
                "events": [
                    {
                        "event_id": "old1",
                        "event_name": "Old Event",
                        "league_name": "Old League",
                        "time_utc": "15:00",
                        "date": "2024-03-01",
                        "home_team": None,
                        "away_team": None,
                        "event_url": None,
                        "league_icon_url": None,
                        "country_flag_url": None,
                        "scheduled_at": "2024-03-01T15:00:00+00:00",
                    }
                ],
            }
        }

        os.makedirs(temp_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        # Create scraper with short TTL
        scraper = TheSportsDBCalendarScraper(cache_ttl=60, cache_dir=temp_cache_dir)

        # Expired entry should not be loaded
        assert cache_key not in scraper._cache

    def test_clear_cache_with_persistent(self, scraper_with_temp_cache, temp_cache_dir):
        """Test clearing cache also deletes persistent file."""
        import os

        # Add something to cache
        import time

        scraper_with_temp_cache._cache["test:"] = ([], time.time())

        # Create a cache file
        cache_file = os.path.join(temp_cache_dir, "calendar_cache.json")
        os.makedirs(temp_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write("{}")

        assert os.path.exists(cache_file)

        # Clear cache
        scraper_with_temp_cache.clear_cache(include_persistent=True)

        # Check memory cache is cleared
        assert len(scraper_with_temp_cache._cache) == 0

        # Check file is deleted
        assert not os.path.exists(cache_file)

    def test_get_cache_stats_includes_persistent(self, scraper_with_temp_cache, temp_cache_dir):
        """Test that cache stats include persistent cache info."""
        import os

        # Create a cache file
        cache_file = os.path.join(temp_cache_dir, "calendar_cache.json")
        os.makedirs(temp_cache_dir, exist_ok=True)
        with open(cache_file, "w") as f:
            f.write('{"test": "data"}')

        stats = scraper_with_temp_cache.get_cache_stats()

        assert "persistent_cache_file" in stats
        assert "persistent_cache_size_bytes" in stats
        assert stats["persistent_cache_size_bytes"] > 0
        assert stats["disk_loads"] >= 0
