"""Tests for MLB Stats API client."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.mlb_stats_api import MILB_SPORT_IDS, MlbStatsApiClient, MlbStatsApiError, get_mlb_stats_client

FIXTURES = Path(__file__).parent / "fixtures" / "mlb_stats"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestMlbStatsApiClient:
    def test_get_teams_parses_response(self):
        client = MlbStatsApiClient(request_delay=0)
        with patch.object(client, "_get", return_value=_load("teams_aaa.json")):
            teams = client.get_teams(11, season=2025)
        assert len(teams) == 2
        assert teams[0]["name"] == "Syracuse Mets"

    def test_get_venue_with_location(self):
        client = MlbStatsApiClient(request_delay=0)
        with patch.object(client, "_get", return_value=_load("venue_2773.json")):
            venue = client.get_venue(2773)
        assert venue is not None
        assert venue["location"]["city"] == "Rochester"

    def test_get_schedule_for_date(self):
        client = MlbStatsApiClient(request_delay=0)
        with patch.object(client, "_get", return_value=_load("schedule_aaa_2025-05-31.json")):
            data = client.get_schedule(11, date="2025-05-31")
        games = data["dates"][0]["games"]
        assert len(games) == 2
        assert games[0]["gamePk"] == 780676

    def test_get_milb_schedule_for_date(self):
        client = MlbStatsApiClient(request_delay=0)

        def fake_get(path, params=None):
            if path == "schedule" and params and params.get("sportId") == 11:
                return _load("schedule_aaa_2025-05-31.json")
            return {"dates": []}

        with patch.object(client, "_get", side_effect=fake_get):
            games = client.get_milb_schedule_for_date("2025-05-31", sport_ids=(11,))
        assert len(games) == 2
        assert games[0]["_level"] == "Triple-A"

    @patch("services.mlb_stats_api.time.sleep")
    def test_retries_on_server_error(self, _mock_sleep):
        client = MlbStatsApiClient(request_delay=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = None
        with patch.object(client._session, "get", return_value=mock_resp):
            with pytest.raises(MlbStatsApiError):
                client.get_sports()

    def test_milb_sport_ids_cover_aaa_through_a(self):
        assert MILB_SPORT_IDS == (11, 12, 13, 14)

    def test_singleton_client(self):
        a = get_mlb_stats_client()
        b = get_mlb_stats_client()
        assert a is b
