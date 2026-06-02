"""Tests for MiLB team refresh."""

from unittest.mock import MagicMock, patch


class TestRefreshMilbTeams:
    def test_upserts_teams(self, app):
        from models import SportsTeam, db
        from services.milb_team_service import refresh_milb_teams_from_mlb_api

        api_teams = [
            {
                "id": 534,
                "name": "Rochester Red Wings",
                "locationName": "Rochester",
                "teamName": "Red Wings",
                "clubName": "Red Wings",
                "league": {"name": "International League"},
                "_level": "Triple-A",
            }
        ]

        with patch("services.milb_team_service.get_mlb_stats_client") as mock_client:
            mock_client.return_value.get_milb_teams.return_value = api_teams
            with patch("services.milb_team_service.lookup", return_value=None):
                with patch("services.milb_team_service.lookup_by_name", return_value=None):
                    result = refresh_milb_teams_from_mlb_api(season=2025)

        assert result["success"] is True
        assert result["teams_added"] == 1
        team = SportsTeam.query.filter_by(sport="milb", abbreviation="534").first()
        assert team is not None
        assert team.name == "Rochester Red Wings"
        db.session.delete(team)
        db.session.commit()
