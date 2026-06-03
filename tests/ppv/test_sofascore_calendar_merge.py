"""SofaScore tennis calendar merge into TheSportsDBCalendarScraper (TODO 126)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED
from services.tennis.espn_calendar import EVENT_SOURCE_ESPN, parse_scoreboard_payload
from services.tennis.sofascore_calendar import (
    EVENT_SOURCE_SOFASCORE,
    clear_sofascore_tennis_calendar_cache,
    parse_tennis_scheduled_events,
)
from services.thesportsdb_calendar_scraper import (
    CalendarEvent,
    TheSportsDBCalendarScraper,
    filter_sofascore_tennis_without_espn_duplicates,
)

FIXTURES = Path(__file__).parent / "fixtures"
ESPN_WTA = FIXTURES / "espn_tennis_scoreboard_20260603_wta.json"
SOFASCORE = FIXTURES / "sofascore" / "scheduled_events_20260603.json"
CALENDAR_DATE = "2026-06-03"


def _load_espn_events():
    payload = json.loads(ESPN_WTA.read_text(encoding="utf-8"))
    return parse_scoreboard_payload(payload, tour="wta", fallback_date=CALENDAR_DATE)


def _load_sofascore_events():
    payload = json.loads(SOFASCORE.read_text(encoding="utf-8"))
    return parse_tennis_scheduled_events(payload, date_str=CALENDAR_DATE)


class TestSofascoreEspnDedup:
    def test_drops_sofascore_when_espn_has_same_player_pair(self):
        espn_events = _load_espn_events()
        sofascore_events = _load_sofascore_events()
        deduped = filter_sofascore_tennis_without_espn_duplicates(espn_events, sofascore_events)

        kalinskaya_pairs = [
            event for event in deduped if {event.home_team, event.away_team} == {"Anna Kalinskaya", "Maja Chwalinska"}
        ]
        assert kalinskaya_pairs == []

        espn_pairs = {
            tuple(sorted([event.home_team.lower(), event.away_team.lower()]))
            for event in espn_events
            if event.source == EVENT_SOURCE_ESPN
        }
        deduped_pairs = {
            tuple(sorted([event.home_team.lower(), event.away_team.lower()]))
            for event in deduped
            if event.source == EVENT_SOURCE_SOFASCORE
        }
        assert deduped_pairs.isdisjoint(espn_pairs)

    def test_keeps_sofascore_only_matchups(self):
        espn_events = _load_espn_events()
        unique_sofascore = [
            CalendarEvent(
                event_id="ss-only-1",
                event_name="Wheelchair Player A vs Wheelchair Player B",
                league_name="ITF | Wheelchair",
                time_utc="10:00",
                date=CALENDAR_DATE,
                home_team="Wheelchair Player A",
                away_team="Wheelchair Player B",
                source=EVENT_SOURCE_SOFASCORE,
                sport="Tennis",
            )
        ]
        deduped = filter_sofascore_tennis_without_espn_duplicates(espn_events, unique_sofascore)
        assert len(deduped) == 1
        assert deduped[0].event_id == "ss-only-1"


@pytest.fixture
def scraper():
    return TheSportsDBCalendarScraper(cache_ttl=60)


class TestCalendarScraperSofascoreMerge:
    def setup_method(self):
        clear_sofascore_tennis_calendar_cache()

    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_flag_off_excludes_sofascore_events(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        mock_espn_fetch,
        scraper,
        app,
    ):
        Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "false")
        mock_milb_fetch.return_value = []
        mock_fetch.return_value = []
        mock_api_fetch.return_value = []

        events = scraper.get_events_for_date(CALENDAR_DATE, force_refresh=True)

        assert all(event.source != EVENT_SOURCE_SOFASCORE for event in events)

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    def test_flag_on_merges_sofascore_after_espn_with_dedup(
        self,
        mock_fetch,
        mock_api_fetch,
        mock_milb_fetch,
        scraper,
        app,
    ):
        Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "true")
        mock_milb_fetch.return_value = []
        mock_fetch.return_value = []
        mock_api_fetch.return_value = []

        espn_events = _load_espn_events()
        sofascore_events = _load_sofascore_events() + [
            CalendarEvent(
                event_id="ss-wheelchair-1",
                event_name="Wheelchair Player A vs Wheelchair Player B",
                league_name="ITF | Wheelchair",
                time_utc="10:00",
                date=CALENDAR_DATE,
                home_team="Wheelchair Player A",
                away_team="Wheelchair Player B",
                source=EVENT_SOURCE_SOFASCORE,
                sport="Tennis",
            )
        ]

        with (
            patch.object(
                scraper,
                "_fetch_espn_tennis_events_for_date",
                return_value=espn_events,
            ),
            patch.object(
                scraper,
                "_fetch_sofascore_tennis_events_for_date",
                return_value=sofascore_events,
            ),
        ):
            events = scraper.get_events_for_date(CALENDAR_DATE, force_refresh=True)

        sources = {event.source for event in events}
        assert EVENT_SOURCE_ESPN in sources
        assert EVENT_SOURCE_SOFASCORE in sources

        kalinskaya_sofascore = [
            event
            for event in events
            if event.source == EVENT_SOURCE_SOFASCORE
            and {event.home_team, event.away_team} == {"Anna Kalinskaya", "Maja Chwalinska"}
        ]
        assert kalinskaya_sofascore == []

        kalinskaya_espn = [
            event
            for event in events
            if event.source == EVENT_SOURCE_ESPN
            and {event.home_team, event.away_team} == {"Anna Kalinskaya", "Maja Chwalinska"}
        ]
        assert len(kalinskaya_espn) == 1

        wheelchair = [
            event for event in events if event.source == EVENT_SOURCE_SOFASCORE and event.event_id == "ss-wheelchair-1"
        ]
        assert len(wheelchair) == 1
