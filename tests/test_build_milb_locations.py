"""Tests for MiLB registry build helpers."""

from unittest.mock import MagicMock, patch

from scripts.build_team_locations import _build_milb_entries


class TestBuildMilbEntries:
    def test_builds_entries_from_api(self):
        teams = [
            {
                "id": 534,
                "name": "Rochester Red Wings",
                "locationName": "Rochester",
                "teamName": "Red Wings",
                "clubName": "Red Wings",
                "venue": {"id": 2773, "name": "Innovative Field"},
                "league": {"name": "International League"},
            }
        ]
        venue = {
            "name": "Innovative Field",
            "location": {
                "city": "Rochester",
                "stateAbbrev": "NY",
                "country": "USA",
                "defaultCoordinates": {"latitude": 43.15, "longitude": -77.62},
            },
        }

        mock_client = MagicMock()
        mock_client.get_teams.return_value = teams
        mock_client.get_venue.return_value = venue

        with patch("services.mlb_stats_api.get_mlb_stats_client", return_value=mock_client):
            entries = _build_milb_entries(refresh=False, tf=None, season=2025)

        milb = [e for e in entries if e.get("key") == "534"]
        assert len(milb) == 1
        assert milb[0]["sport"] == "milb"
        assert milb[0]["name"] == "Rochester Red Wings"
        assert "rochester red wings" in milb[0].get("aliases", [])
