"""Tests for MiLB calendar mapping."""

import json
from pathlib import Path
from unittest.mock import patch

from services.mlb_stats_calendar import fetch_milb_events_for_date, game_to_calendar_event

FIXTURES = Path(__file__).parent / "fixtures" / "mlb_stats"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestGameToCalendarEvent:
    def test_maps_game_pk_and_teams(self):
        game = _load("schedule_aaa_2025-05-31.json")["dates"][0]["games"][0]
        game["_level"] = "Triple-A"
        ev = game_to_calendar_event(game)
        assert ev is not None
        assert ev.event_id == "780676"
        assert ev.home_team == "Rochester Red Wings"
        assert ev.away_team == "Columbus Clippers"
        assert ev.home_team_id == "534"
        assert "MiLB" in ev.league_name
        assert ev.source == "mlb_stats_api"
        assert ev.scheduled_at is not None


class TestFetchMilbEvents:
    def test_fetches_and_caches(self):
        from services.mlb_stats_calendar import clear_milb_calendar_cache

        clear_milb_calendar_cache()
        games = _load("schedule_aaa_2025-05-31.json")["dates"][0]["games"]
        for g in games:
            g["_level"] = "Triple-A"
            g["_sport_id"] = 11

        with patch("services.mlb_stats_calendar._is_date_in_milb_window", return_value=True):
            with patch("services.mlb_stats_calendar.get_mlb_stats_client") as mock_client:
                mock_client.return_value.get_milb_schedule_for_date.return_value = games
                events = fetch_milb_events_for_date("2025-05-31", force_refresh=True)

        assert len(events) == 2
        names = {e.home_team for e in events} | {e.away_team for e in events}
        assert "Rochester Red Wings" in names
        assert "Syracuse Mets" in names
