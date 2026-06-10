"""Tests for SofaScore football calendar provider (World Cup coverage)."""

import json
from pathlib import Path
from unittest.mock import patch

from models import Event
from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED
from services.ppv.enrichment.types import calendar_event_source
from services.tennis.sofascore_calendar import (
    EVENT_SOURCE_SOFASCORE,
    clear_sofascore_football_calendar_cache,
    fetch_football_events_for_date,
    parse_football_scheduled_events,
    scheduled_event_to_calendar_event,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sofascore"
FOOTBALL_FIXTURE = FIXTURES / "scheduled_events_football_20260611_wc.json"
CALENDAR_DATE = "2026-06-11"


def _load_fixture() -> dict:
    return json.loads(FOOTBALL_FIXTURE.read_text(encoding="utf-8"))


class TestParseFootballFixture:
    def test_parses_world_cup_fixtures(self):
        payload = _load_fixture()
        events = parse_football_scheduled_events(payload, date_str=CALENDAR_DATE)
        matchups = {tuple(sorted([e.home_team, e.away_team])) for e in events}
        assert ("Mexico", "South Africa") in matchups
        assert ("Czechia", "South Korea") in matchups
        assert all(event.source == EVENT_SOURCE_SOFASCORE for event in events)
        assert all(event.sport == "Soccer" for event in events)
        assert all("World Cup" in event.league_name for event in events)

    def test_calendar_event_source_maps_to_model_constant(self):
        payload = _load_fixture()
        events = parse_football_scheduled_events(payload, date_str=CALENDAR_DATE)
        assert events
        assert calendar_event_source(events[0]) == Event.SOURCE_SOFASCORE


class TestScheduledEventToCalendarEvent:
    def test_skips_cancelled_status(self):
        payload = _load_fixture()
        raw = dict(payload["events"][0])
        raw["status"] = {"type": "cancelled"}
        assert scheduled_event_to_calendar_event(raw, fallback_date=CALENDAR_DATE, sport="Soccer") is None


class TestFetchFootballEventsForDate:
    def setup_method(self):
        clear_sofascore_football_calendar_cache()

    def test_flag_off_returns_empty_without_http(self, app):
        Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "false")
        with patch("services.ppv.calendar_providers.sofascore.client.fetch_scheduled_events_http") as mock_fetch:
            assert fetch_football_events_for_date(CALENDAR_DATE) == []
            mock_fetch.assert_not_called()

    def test_flag_on_fetches_and_caches(self, app):
        Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "true")
        payload = _load_fixture()

        with patch(
            "services.ppv.calendar_providers.sofascore.client.fetch_scheduled_events_http",
            return_value=payload,
        ) as mock_fetch:
            first = fetch_football_events_for_date(CALENDAR_DATE, force_refresh=True)
            second = fetch_football_events_for_date(CALENDAR_DATE)
            assert len(first) == 2
            assert len(second) == len(first)
            assert mock_fetch.call_count == 1
