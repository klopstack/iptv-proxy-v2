"""Tests for football-data.org context provider."""

from unittest.mock import patch

from services.ppv.context.providers.football_data import FootballDataProvider, _league_code


class TestLeagueCode:
    def test_maps_premier_league(self):
        assert _league_code("Premier League") == "PL"
        assert _league_code("english premier league") == "PL"

    def test_unknown_league_returns_none(self):
        assert _league_code("MLS") is None


class TestFootballDataStandings:
    @patch("services.ppv.context.providers.football_data.requests.get")
    def test_get_standings_parses_table(self, mock_get):
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {
            "standings": [
                {
                    "type": "TOTAL",
                    "table": [
                        {
                            "position": 1,
                            "playedGames": 10,
                            "points": 25,
                            "won": 8,
                            "draw": 1,
                            "lost": 1,
                            "team": {"name": "Arsenal"},
                        }
                    ],
                }
            ]
        }

        provider = FootballDataProvider()
        with patch.object(provider, "get_setting", return_value="test-key"):
            result = provider.get_standings("Soccer", "Premier League")

        assert result is not None
        assert "arsenal" in result["_all_teams"]
        assert result["_all_teams"]["arsenal"]["record"] == "8W-1D-1L"
        assert "#1" in result["_all_teams"]["arsenal"]["standing"]

    def test_get_standings_without_api_key_returns_none(self):
        provider = FootballDataProvider()
        with patch.object(provider, "get_setting", return_value=None):
            assert provider.get_standings("Soccer", "Premier League") is None
