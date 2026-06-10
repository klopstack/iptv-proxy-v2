"""SofaScore football calendar merge into TheSportsDBCalendarScraper (World Cup)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED
from services.tennis.sofascore_calendar import (
    EVENT_SOURCE_SOFASCORE,
    clear_sofascore_football_calendar_cache,
    parse_football_scheduled_events,
)
from services.thesportsdb_calendar_scraper import (
    CalendarEvent,
    TheSportsDBCalendarScraper,
    filter_sofascore_football_without_tsdb_duplicates,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sofascore"
FOOTBALL_FIXTURE = FIXTURES / "scheduled_events_football_20260611_wc.json"
CALENDAR_DATE = "2026-06-11"


def _load_sofascore_events():
    payload = json.loads(FOOTBALL_FIXTURE.read_text(encoding="utf-8"))
    return parse_football_scheduled_events(payload, date_str=CALENDAR_DATE)


class TestSofascoreFootballTsdbDedup:
    def test_drops_sofascore_when_tsdb_has_same_matchup(self):
        tsdb_events = [
            CalendarEvent(
                event_id="tsdb-mex-sa",
                event_name="Mexico vs South Africa",
                league_name="FIFA World Cup",
                time_utc="18:00",
                date=CALENDAR_DATE,
                home_team="Mexico",
                away_team="South Africa",
                source="thesportsdb",
                sport="Soccer",
            )
        ]
        sofascore_events = _load_sofascore_events()
        deduped = filter_sofascore_football_without_tsdb_duplicates(tsdb_events, sofascore_events)

        mexico_pairs = [event for event in deduped if {event.home_team, event.away_team} == {"Mexico", "South Africa"}]
        assert mexico_pairs == []
        assert len(deduped) == 1
        assert {deduped[0].home_team, deduped[0].away_team} == {"South Korea", "Czechia"}

    def test_keeps_all_sofascore_when_tsdb_missing_fixture(self):
        deduped = filter_sofascore_football_without_tsdb_duplicates([], _load_sofascore_events())
        assert len(deduped) == 2


@pytest.fixture
def scraper():
    return TheSportsDBCalendarScraper(cache_ttl=60)


class TestCalendarScraperFootballMerge:
    def setup_method(self):
        clear_sofascore_football_calendar_cache()

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_flag_off_excludes_sofascore_football(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        scraper,
        app,
    ):
        Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "false")
        mock_milb_fetch.return_value = []
        mock_fetch.return_value = []
        mock_api_fetch.return_value = []

        events = scraper.get_events_for_date(CALENDAR_DATE, force_refresh=True)

        assert all(event.source != EVENT_SOURCE_SOFASCORE for event in events)

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_flag_on_merges_sofascore_football_with_tsdb_dedup(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        scraper,
        app,
    ):
        Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "true")
        mock_milb_fetch.return_value = []
        mock_fetch.return_value = []
        mock_api_fetch.return_value = [
            CalendarEvent(
                event_id="tsdb-mex-sa",
                event_name="Mexico vs South Africa",
                league_name="FIFA World Cup",
                time_utc="18:00",
                date=CALENDAR_DATE,
                home_team="Mexico",
                away_team="South Africa",
                source="thesportsdb",
                sport="Soccer",
            )
        ]

        sofascore_events = _load_sofascore_events()

        with patch(
            "services.ppv.calendar_providers.sofascore.fetch_events_for_slug",
            side_effect=lambda slug, date_str, **kwargs: sofascore_events if slug == "football" else [],
        ):
            events = scraper.get_events_for_date(CALENDAR_DATE, force_refresh=True)

        sources = {event.source for event in events}
        assert "thesportsdb" in sources
        assert EVENT_SOURCE_SOFASCORE in sources

        mexico_sofascore = [
            event
            for event in events
            if event.source == EVENT_SOURCE_SOFASCORE
            and {event.home_team, event.away_team} == {"Mexico", "South Africa"}
        ]
        assert mexico_sofascore == []

        korea_sofascore = [
            event
            for event in events
            if event.source == EVENT_SOURCE_SOFASCORE
            and {event.home_team, event.away_team} == {"South Korea", "Czechia"}
        ]
        assert len(korea_sofascore) == 1
