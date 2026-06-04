"""Tests for tennis doubles competitor validation (TODO 127)."""

import json
from pathlib import Path

import pytest

from services.ppv.extraction.competitors import extract_competitors_detail
from services.ppv.matching.validation import competitors_match_event, competitors_match_event_doubles
from services.thesportsdb_calendar_scraper import CalendarEvent

FIXTURES = Path(__file__).parent / "fixtures" / "tennis_doubles_channels.json"


def _event(row: dict) -> CalendarEvent:
    return CalendarEvent(
        event_id=row["id"],
        event_name=row.get("event_name", ""),
        league_name=row["league_name"],
        time_utc="12:00",
        date="2026-06-03",
        home_team=row["home_team"],
        away_team=row["away_team"],
        sport=row.get("sport", "Tennis"),
    )


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURES.open(encoding="utf-8") as f:
        return json.load(f)


class TestCompetitorsMatchEventDoubles:
    def test_four_surnames_match_calendar(self, fixture_data):
        players = ("Cornet", "Hantuchova", "Hingis", "Kerber")
        event = _event(fixture_data["calendar_events"][0])
        assert competitors_match_event_doubles(players, event)

    def test_order_independent(self, fixture_data):
        event = _event(fixture_data["calendar_events"][0])
        shuffled = ("Kerber", "Hingis", "Hantuchova", "Cornet")
        assert competitors_match_event_doubles(shuffled, event)

    def test_extracted_channel_matches_calendar(self, fixture_data):
        channel = fixture_data["doubles"][0]["channel"]
        detail = extract_competitors_detail(channel)
        event = _event(fixture_data["calendar_events"][0])
        assert detail and detail.players
        assert competitors_match_event(
            (detail.side1, detail.side2),
            event,
            players=detail.players,
        )

    def test_golovin_forget_parmentier_simon(self, fixture_data):
        channel = fixture_data["doubles"][1]["channel"]
        detail = extract_competitors_detail(channel)
        event = _event(fixture_data["calendar_events"][1])
        assert detail and detail.players
        assert competitors_match_event(
            (detail.side1, detail.side2),
            event,
            players=detail.players,
        )

    def test_wheelchair_doubles_kamiji(self, fixture_data):
        channel = fixture_data["wheelchair_doubles"][0]["channel"]
        detail = extract_competitors_detail(channel)
        event = _event(fixture_data["calendar_events"][2])
        assert detail and detail.players
        assert competitors_match_event(
            (detail.side1, detail.side2),
            event,
            players=detail.players,
        )

    def test_singles_still_validates_two_players(self, fixture_data):
        event = CalendarEvent(
            event_id="s1",
            event_name="",
            league_name="WTA",
            time_utc="12:00",
            date="2026-06-03",
            home_team="Anna Kalinskaya",
            away_team="Maja Chwalinska",
            sport="Tennis",
        )
        assert competitors_match_event(("Anna Kalinskaya", "Maja Chwalinska"), event)

    def test_doubles_calendar_required(self, fixture_data):
        singles_event = CalendarEvent(
            event_id="s2",
            event_name="",
            league_name="WTA",
            time_utc="12:00",
            date="2026-06-03",
            home_team="Iga Swiatek",
            away_team="Coco Gauff",
            sport="Tennis",
        )
        assert not competitors_match_event_doubles(
            ("Cornet", "Hantuchova", "Hingis", "Kerber"),
            singles_event,
        )
