"""Tests for SportsTeam resolution and WNBA sport enumeration."""

from unittest.mock import MagicMock, patch

import pytest

from models.ppv import SportsTeam


class TestSportsTeamConstants:
    def test_wnba_in_sports_list(self):
        assert SportsTeam.SPORT_WNBA == "wnba"
        assert "wnba" in SportsTeam.SPORTS


class TestResolveTeam:
    @pytest.fixture
    def mock_teams(self):
        arsenal = MagicMock()
        arsenal.name = "Arsenal"
        arsenal.sport = "fb"
        arsenal.get_aliases.return_value = ["arsenal fc"]

        man_utd = MagicMock()
        man_utd.name = "Manchester United"
        man_utd.sport = "fb"
        man_utd.get_aliases.return_value = ["man utd", "manchester utd"]

        kc = MagicMock()
        kc.name = "Kansas City"
        kc.sport = "mls"
        kc.get_aliases.return_value = []

        return [arsenal, man_utd, kc]

    def test_exact_name_match(self, app, mock_teams):
        with app.app_context(), patch.object(SportsTeam, "query") as mock_query:
            mock_query.filter_by.return_value.all.return_value = mock_teams
            mock_query.all.return_value = mock_teams
            team = SportsTeam.resolve_team("Arsenal", sport="fb")
            assert team is mock_teams[0]

    def test_alias_match(self, app, mock_teams):
        with app.app_context(), patch.object(SportsTeam, "query") as mock_query:
            mock_query.filter_by.return_value.all.return_value = mock_teams
            team = SportsTeam.resolve_team("man utd", sport="fb")
            assert team is mock_teams[1]

    def test_rejects_ambiguous_substring_without_sport(self, app, mock_teams):
        with app.app_context(), patch.object(SportsTeam, "query") as mock_query:
            mock_query.all.return_value = mock_teams
            assert SportsTeam.resolve_team("United") is None
            assert SportsTeam.resolve_team("City") is None

    def test_rejects_short_substring_even_with_sport(self, app, mock_teams):
        with app.app_context(), patch.object(SportsTeam, "query") as mock_query:
            mock_query.filter_by.return_value.all.return_value = mock_teams
            assert SportsTeam.resolve_team("City", sport="mls") is None

    def test_allows_substring_with_sport_and_min_length(self, app, mock_teams):
        with app.app_context(), patch.object(SportsTeam, "query") as mock_query:
            mock_query.filter_by.return_value.all.return_value = mock_teams
            team = SportsTeam.resolve_team("Manchester", sport="fb")
            assert team is mock_teams[1]


class TestMlbHomeTimezone:
    def test_mascot_alias_via_db(self, app):
        from models import SportsTeam, db
        from services.sportsipy_service import _generate_team_aliases

        with app.app_context():
            team = SportsTeam(
                sport=SportsTeam.SPORT_MLB,
                abbreviation="SFG",
                name="San Francisco Giants",
                city="San Francisco",
            )
            team.set_aliases(_generate_team_aliases(team.name, team.abbreviation))
            db.session.add(team)
            db.session.commit()

            resolved = SportsTeam.resolve_team("giants", sport="mlb")
            assert resolved is not None
            assert resolved.name == "San Francisco Giants"
            assert SportsTeam.home_timezone_for_team("giants", sport="mlb") == "America/Los_Angeles"

    def test_mascot_alias_via_registry(self, app, tmp_path, monkeypatch):
        import json

        from services.team_location_registry import clear_registry_cache

        registry = {
            "version": "test",
            "entries": [
                {
                    "sport": "mlb",
                    "key": "SFG",
                    "name": "San Francisco Giants",
                    "city": "San Francisco",
                    "country": "US",
                    "iana_timezone": "America/Los_Angeles",
                    "aliases": ["giants"],
                }
            ],
        }
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps(registry), encoding="utf-8")
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            reg_path,
        )
        clear_registry_cache()

        with app.app_context():
            assert SportsTeam.home_timezone_for_team("Giants", sport="mlb") == "America/Los_Angeles"
            assert SportsTeam.home_timezone_for_team("giants", sport="mlb") == "America/Los_Angeles"
