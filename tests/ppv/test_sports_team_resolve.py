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
