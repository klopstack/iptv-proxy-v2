"""Tests for FB team refresh from bundled location registry."""

import json

import pytest


@pytest.fixture
def fb_registry_path(tmp_path):
    data = {
        "version": "2026-06-02-test",
        "entries": [
            {
                "sport": "fb",
                "key": "133604",
                "name": "Arsenal",
                "city": "London",
                "country": "England",
                "venue_name": "Emirates Stadium",
                "iana_timezone": "Europe/London",
                "thesportsdb_id": "133604",
                "aliases": ["arsenal", "gunners", "afc"],
                "league": "English Premier League",
                "source": "thesportsdb:133604",
            },
            {
                "sport": "fb",
                "key": "133602",
                "name": "Liverpool",
                "city": "Liverpool",
                "country": "England",
                "iana_timezone": "Europe/London",
                "thesportsdb_id": "133602",
                "aliases": ["liverpool", "reds"],
                "source": "thesportsdb:133602",
            },
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    from services.team_location_registry import clear_registry_cache

    clear_registry_cache()
    yield str(path)
    clear_registry_cache()


class TestRefreshFbTeamsFromRegistry:
    def test_upserts_fb_teams_by_idteam(self, app, fb_registry_path, monkeypatch):
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            fb_registry_path,
        )
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()

        with app.app_context():
            from models import SportsTeam, db
            from services.sportsipy_service import refresh_fb_teams_from_registry

            db.session.query(SportsTeam).filter_by(sport="fb").delete()
            db.session.commit()

            result = refresh_fb_teams_from_registry()
            assert result["success"] is True
            assert result["teams_added"] == 2

            arsenal = SportsTeam.query.filter_by(sport="fb", abbreviation="133604").one()
            assert arsenal.name == "Arsenal"
            assert arsenal.city == "London"
            assert arsenal.iana_timezone == "Europe/London"
            assert arsenal.source == "thesportsdb+location_registry"
            assert "gunners" in arsenal.get_aliases()

    def test_removes_legacy_seed_abbreviations(self, app, fb_registry_path, monkeypatch):
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            fb_registry_path,
        )
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()

        with app.app_context():
            from models import SportsTeam, db
            from services.sportsipy_service import refresh_fb_teams_from_registry

            legacy = SportsTeam(sport="fb", abbreviation="MUN", name="Manchester United", source="seed")
            legacy.set_aliases(["man united"])
            db.session.add(legacy)
            db.session.commit()

            result = refresh_fb_teams_from_registry()
            assert result["teams_removed"] == 1
            assert SportsTeam.query.filter_by(sport="fb", abbreviation="MUN").first() is None


class TestFbTimezoneResolution:
    def test_home_team_id_lookup(self, fb_registry_path, monkeypatch):
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            fb_registry_path,
        )
        from services.ppv.timezone_resolution import _home_team_timezone
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()
        tz = _home_team_timezone("Arsenal", "soccer", home_team_id="133604")
        assert tz == "Europe/London"

    def test_fb_no_heuristic_fallback(self, fb_registry_path, monkeypatch):
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            fb_registry_path,
        )
        from services.ppv.timezone_resolution import _home_team_timezone
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()
        assert _home_team_timezone("Unknown FC", "soccer") is None

    def test_resolve_channel_timezone_with_home_team_id(self, fb_registry_path, monkeypatch):
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            fb_registry_path,
        )
        from services.ppv.extraction import MatchupInfo
        from services.ppv.timezone_resolution import resolve_channel_timezone
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()
        matchup = MatchupInfo(
            home_team="Arsenal",
            away_team="Chelsea",
            separator="@",
            ordering_rule="eu_home_away",
            ordering_confidence=0.9,
        )
        resolution = resolve_channel_timezone(
            "Sky Sports - Chelsea @ Arsenal",
            sport="soccer",
            matchup=matchup,
            home_team_id="133604",
        )
        assert resolution.timezone == "Europe/London"
        assert resolution.source == "home_venue_sports_team"


class TestRefreshWnbaTeamsFromRegistry:
    def test_upserts_wnba_teams(self, app, tmp_path, monkeypatch):
        data = {
            "version": "2026-06-02-test",
            "entries": [
                {
                    "sport": "wnba",
                    "key": "136010",
                    "name": "Las Vegas Aces",
                    "city": "Paradise",
                    "country": "United States",
                    "iana_timezone": "America/Los_Angeles",
                    "thesportsdb_id": "136010",
                    "aliases": ["las vegas aces", "aces"],
                    "league": "WNBA",
                    "source": "thesportsdb:136010",
                },
            ],
        }
        registry_path = tmp_path / "registry.json"
        registry_path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(
            "services.team_location_registry.DEFAULT_REGISTRY_PATH",
            str(registry_path),
        )
        from services.team_location_registry import clear_registry_cache

        clear_registry_cache()

        with app.app_context():
            from models import SportsTeam, db
            from services.sportsipy_service import refresh_tsdb_registry_teams

            db.session.query(SportsTeam).filter_by(sport="wnba").delete()
            db.session.commit()

            result = refresh_tsdb_registry_teams(sports=("wnba",))
            assert result["success"] is True
            assert result["teams_added"] == 1

            aces = SportsTeam.query.filter_by(sport="wnba", abbreviation="136010").one()
            assert aces.iana_timezone == "America/Los_Angeles"
