"""Smoke tests for FB section of build_team_locations.py using cached fixtures."""

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "thesportsdb"


@pytest.mark.migrations
class TestBuildFbEntries:
    def test_build_fb_from_cached_league_fixture(self, tmp_path, monkeypatch):
        raw_dir = tmp_path / "raw" / "thesportsdb"
        raw_dir.mkdir(parents=True)
        shutil.copy(FIXTURES / "league_4328.json", raw_dir / "league_4328.json")
        shutil.copy(FIXTURES / "team_133604.json", raw_dir / "team_133604.json")

        fb_leagues = tmp_path / "fb_leagues.json"
        fb_leagues.write_text(
            json.dumps({"leagues": [{"id": "4328", "name": "English Premier League"}]}),
            encoding="utf-8",
        )

        import scripts.build_team_locations as build

        monkeypatch.setattr(build, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(build, "TSDB_RAW_DIR", raw_dir)
        monkeypatch.setattr(build, "FB_LEAGUES_PATH", fb_leagues)
        monkeypatch.setattr(build, "ROOT", ROOT)

        entries = build._build_tsdb_league_entries(refresh=False, tf=None)
        assert len(entries) >= 2
        by_key = {e["key"]: e for e in entries}
        assert "133604" in by_key
        assert by_key["133604"]["sport"] == "fb"
        assert by_key["133604"]["iana_timezone"] == "Europe/London"
        assert "gunners" in by_key["133604"].get("aliases", [])

    def test_build_wnba_sport_from_league_config(self, tmp_path, monkeypatch):
        raw_dir = tmp_path / "raw" / "thesportsdb"
        raw_dir.mkdir(parents=True)
        shutil.copy(FIXTURES / "league_4516.json", raw_dir / "league_4516.json")

        fb_leagues = tmp_path / "fb_leagues.json"
        fb_leagues.write_text(
            json.dumps({"leagues": [{"id": "4516", "name": "WNBA", "sport": "wnba"}]}),
            encoding="utf-8",
        )

        import scripts.build_team_locations as build

        monkeypatch.setattr(build, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(build, "TSDB_RAW_DIR", raw_dir)
        monkeypatch.setattr(build, "FB_LEAGUES_PATH", fb_leagues)
        monkeypatch.setattr(build, "ROOT", ROOT)

        entries = build._build_tsdb_league_entries(refresh=False, tf=None)
        assert len(entries) == 1
        assert entries[0]["sport"] == "wnba"
        assert entries[0]["key"] == "136010"
        assert entries[0]["name"] == "Las Vegas Aces"
