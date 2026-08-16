"""Tests for ESPN tennis calendar provider."""

import json
from pathlib import Path
from unittest.mock import patch

from models import Event
from services.ppv.enrichment.types import calendar_event_source
from services.tennis.espn_calendar import (
    ESPN_TENNIS_TOURS,
    EVENT_SOURCE_ESPN,
    clear_espn_tennis_calendar_cache,
    competition_to_calendar_event,
    fetch_espn_tennis_events_for_date,
    parse_scoreboard_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"
WTA_FIXTURE = FIXTURES / "espn_tennis_scoreboard_20260603_wta.json"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _player_names(events):
    names = set()
    for ev in events:
        if ev.home_team:
            names.add(ev.home_team)
        if ev.away_team:
            names.add(ev.away_team)
    return names


class TestParseScoreboardFixture:
    def test_parses_singles_matches_on_2026_06_03(self):
        payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        events = parse_scoreboard_payload(payload, tour="wta", fallback_date="2026-06-03")
        names = _player_names(events)

        assert "Anna Kalinskaya" in names
        assert "Maja Chwalinska" in names
        assert "Aryna Sabalenka" in names
        assert "Diana Shnaider" in names

        kalinskaya = next(e for e in events if {e.home_team, e.away_team} == {"Anna Kalinskaya", "Maja Chwalinska"})
        assert kalinskaya.event_id == "175549"
        assert kalinskaya.source == EVENT_SOURCE_ESPN
        assert kalinskaya.time_utc == "09:10"
        assert "Roland Garros" in kalinskaya.league_name
        assert kalinskaya.sport == "Tennis"

    def test_parses_doubles_with_roster_display_name(self):
        payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        events = parse_scoreboard_payload(payload, tour="wta", fallback_date="2026-06-03")
        doubles = [e for e in events if (e.home_team and "/" in e.home_team) or (e.away_team and "/" in e.away_team)]
        assert len(doubles) >= 1
        d = doubles[0]
        assert d.event_id == "175912"
        sides = {d.home_team, d.away_team}
        assert "Guo Hanyu / Kristina Mladenovic" in sides
        assert "Shuko Aoyama / En-Shuo Liang" in sides


class TestCompetitionToCalendarEvent:
    def test_maps_home_away_from_competitors(self):
        payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        comp = payload["events"][0]["groupings"][0]["competitions"][0]
        ev = competition_to_calendar_event(
            comp,
            tournament_name="Roland Garros",
            grouping_name="Women's Singles",
            tour="wta",
            fallback_date="2026-06-03",
        )
        assert ev is not None
        assert ev.away_team == "Maja Chwalinska"
        assert ev.home_team == "Anna Kalinskaya"


class TestFetchEspnTennisEvents:
    def test_fetches_wta_and_atp_with_mock_http(self):
        clear_espn_tennis_calendar_cache()
        wta_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        atp_payload = {"events": []}

        def fake_get(url, timeout=30):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    if "/wta/" in url:
                        return wta_payload
                    return atp_payload

            return Resp()

        with patch("services.tennis.espn_calendar._is_date_in_espn_window", return_value=True):
            with patch("services.tennis.espn_calendar.requests.get", side_effect=fake_get):
                events = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)

        names = _player_names(events)
        assert "Anna Kalinskaya" in names
        assert "Aryna Sabalenka" in names

    def test_returns_stale_cache_on_fetch_failure(self):
        clear_espn_tennis_calendar_cache()
        wta_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        responses = [wta_payload, {"events": []}]

        def scoreboard_side_effect(tour, date_str, session=None):
            return responses.pop(0) if responses else {"events": []}

        with patch("services.tennis.espn_calendar._is_date_in_espn_window", return_value=True):
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=scoreboard_side_effect,
            ):
                first = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=RuntimeError("network down"),
            ):
                second = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)

        assert len(first) == len(second) == 3
        assert _player_names(second) == _player_names(first)

    def test_one_tour_failure_keeps_other_tour_events(self):
        clear_espn_tennis_calendar_cache()
        wta_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")

        def scoreboard_side_effect(tour, date_str, session=None):
            if tour == "atp":
                raise RuntimeError("ESPN 503")
            return wta_payload

        with patch("services.tennis.espn_calendar._is_date_in_espn_window", return_value=True):
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=scoreboard_side_effect,
            ):
                events = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)

        assert len(events) == 3
        assert "Anna Kalinskaya" in _player_names(events)

    def test_partial_result_is_not_cached(self):
        clear_espn_tennis_calendar_cache()
        wta_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")
        atp_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")

        def failing_atp(tour, date_str, session=None):
            if tour == "atp":
                raise RuntimeError("ESPN 503")
            return wta_payload

        def both_tours(tour, date_str, session=None):
            return wta_payload if tour == "wta" else atp_payload

        with patch("services.tennis.espn_calendar._is_date_in_espn_window", return_value=True):
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=failing_atp,
            ):
                partial = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=both_tours,
            ) as recovered_fetch:
                recovered = fetch_espn_tennis_events_for_date("2026-06-03")

        assert len(partial) == 3
        # The partial result must not be served from cache: the next call retries both tours.
        assert recovered_fetch.call_count == len(ESPN_TENNIS_TOURS)
        assert len(recovered) == 6

    def test_empty_partial_result_falls_back_to_cache(self):
        clear_espn_tennis_calendar_cache()
        wta_payload = _load_fixture("espn_tennis_scoreboard_20260603_wta.json")

        def both_tours(tour, date_str, session=None):
            return wta_payload if tour == "wta" else {"events": []}

        def empty_wta_failing_atp(tour, date_str, session=None):
            if tour == "atp":
                raise RuntimeError("ESPN 503")
            return {"events": []}

        with patch("services.tennis.espn_calendar._is_date_in_espn_window", return_value=True):
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=both_tours,
            ):
                first = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)
            with patch(
                "services.tennis.espn_calendar._fetch_scoreboard",
                side_effect=empty_wta_failing_atp,
            ):
                second = fetch_espn_tennis_events_for_date("2026-06-03", force_refresh=True)

        # Nothing was actually observed, so the previous result stands rather than an empty one.
        assert len(first) == len(second) == 3


class TestSourceNormalization:
    def test_calendar_event_source_maps_to_model_constant(self):
        from tests.ppv.test_persistence import _calendar_event

        cal = _calendar_event(event_id="175549", source=EVENT_SOURCE_ESPN, sport="Tennis")
        assert calendar_event_source(cal) == Event.SOURCE_ESPN
