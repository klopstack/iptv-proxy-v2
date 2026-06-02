"""Tests for bundled team location registry."""

import json
import tempfile
from pathlib import Path

import pytest

from services.team_location_registry import (
    LocationEntry,
    apply_location_to_sports_team,
    clear_registry_cache,
    lookup,
    lookup_by_alias,
    lookup_by_name,
)


@pytest.fixture
def registry_path(tmp_path):
    data = {
        "version": "2026-06-02-test",
        "entries": [
            {
                "sport": "nba",
                "key": "UTA",
                "name": "Utah Jazz",
                "city": "Salt Lake City",
                "state": "UT",
                "country": "US",
                "iana_timezone": "America/Denver",
                "source": "override",
            },
            {
                "sport": "nba",
                "key": "GSW",
                "name": "Golden State Warriors",
                "city": "San Francisco",
                "state": "CA",
                "country": "US",
                "iana_timezone": "America/Los_Angeles",
                "source": "override",
            },
            {
                "sport": "nfl",
                "key": "LAR",
                "name": "Los Angeles Rams",
                "city": "Inglewood",
                "state": "CA",
                "country": "US",
                "venue_name": "SoFi Stadium",
                "iana_timezone": "America/Los_Angeles",
                "source": "override",
            },
            {
                "sport": "ncaab",
                "key": "PURDUE",
                "name": "Purdue University",
                "city": "West Lafayette",
                "state": "IN",
                "country": "US",
                "iana_timezone": "America/Indiana/Indianapolis",
                "source": "test",
            },
            {
                "sport": "milb",
                "key": "534",
                "name": "Rochester Red Wings",
                "city": "Rochester",
                "state": "NY",
                "country": "US",
                "iana_timezone": "America/New_York",
                "aliases": ["rochester red wings"],
                "source": "mlb_stats_api",
            },
            {
                "sport": "fb",
                "key": "133604",
                "name": "Arsenal",
                "city": "London",
                "country": "England",
                "iana_timezone": "Europe/London",
                "thesportsdb_id": "133604",
                "aliases": ["arsenal", "gunners"],
                "source": "thesportsdb:133604",
            },
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    clear_registry_cache()
    yield str(path)
    clear_registry_cache()


class TestTeamLocationRegistry:
    def test_lookup_hit(self, registry_path):
        entry = lookup("nba", "UTA", registry_path=registry_path)
        assert entry is not None
        assert entry.city == "Salt Lake City"
        assert entry.iana_timezone == "America/Denver"

    def test_lookup_miss(self, registry_path):
        assert lookup("nba", "ZZZ", registry_path=registry_path) is None

    def test_lookup_by_name_exact(self, registry_path):
        entry = lookup_by_name("nba", "Golden State Warriors", registry_path=registry_path)
        assert entry is not None
        assert entry.key == "GSW"

    def test_lookup_by_name_no_prefix_heuristic(self, registry_path):
        assert lookup_by_name("nba", "Golden State", registry_path=registry_path) is None

    def test_milb_lookup_by_team_id_and_alias(self, registry_path):
        entry = lookup("milb", "534", registry_path=registry_path)
        assert entry is not None
        assert entry.iana_timezone == "America/New_York"
        assert lookup_by_alias("milb", "Rochester Red Wings", registry_path=registry_path) is not None

    def test_apply_location_to_sports_team(self, registry_path):
        class _Row:
            city = None
            state = None
            country = None
            venue_name = None
            latitude = None
            longitude = None
            iana_timezone = None
            location_source = None

        entry = lookup("nfl", "LAR", registry_path=registry_path)
        row = _Row()
        apply_location_to_sports_team(row, entry)
        assert row.city == "Inglewood"
        assert row.venue_name == "SoFi Stadium"
        assert row.iana_timezone == "America/Los_Angeles"
        assert row.location_source == "override"

    def test_college_slug_lookup(self, registry_path):
        entry = lookup("ncaab", "PURDUE", registry_path=registry_path)
        assert entry is not None
        assert entry.state == "IN"

    def test_fb_lookup_by_idteam(self, registry_path):
        entry = lookup("fb", "133604", registry_path=registry_path)
        assert entry is not None
        assert entry.iana_timezone == "Europe/London"
        assert entry.thesportsdb_id == "133604"

    def test_fb_lookup_by_alias(self, registry_path):
        from services.team_location_registry import lookup_by_alias

        entry = lookup_by_alias("fb", "gunners", registry_path=registry_path)
        assert entry is not None
        assert entry.key == "133604"

    def test_fb_key_not_uppercased(self, registry_path):
        entry = lookup("fb", "133604", registry_path=registry_path)
        assert entry.key == "133604"

    def test_override_precedence_in_fixture(self, registry_path):
        """Fixture uses override sources; lookup returns authoritative bundled values."""
        entry = LocationEntry.from_dict(
            {
                "sport": "nba",
                "key": "UTA",
                "name": "Utah Jazz",
                "city": "Salt Lake City",
                "iana_timezone": "America/Denver",
                "source": "override",
            }
        )
        assert entry.source == "override"
