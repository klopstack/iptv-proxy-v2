"""Tests for shared context team lookup helper."""

from services.ppv.context.team_lookup import lookup_team_entry


def test_lookup_exact_name():
    teams = {"arsenal": {"record": "18-5-3", "standing": "2nd"}}
    assert lookup_team_entry(teams, "Arsenal") == teams["arsenal"]


def test_lookup_by_team_id():
    teams = {"12345": {"record": "10-5", "standing": "1st"}}
    assert lookup_team_entry(teams, "Unknown FC", team_id="12345") == teams["12345"]


def test_lookup_partial_name():
    teams = {"manchester united": {"record": "12-8-4"}}
    assert lookup_team_entry(teams, "United") == teams["manchester united"]
