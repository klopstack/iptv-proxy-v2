"""Tests for centralized PPV sport key registry."""

import pytest

from services.ppv.sport_registry import (
    espn_paths,
    normalize_sport_key,
    normalize_sport_key_exact,
    primary_sport_key,
    sport_key_from_league_name,
    sportsipy_sport_key,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("MLB", "mlb"),
        ("baseball", "mlb"),
        ("MiLB", "milb"),
        ("minor league baseball", "milb"),
        ("NBA", "nba"),
        ("basketball", "nba"),
        ("WNBA", "wnba"),
        ("NHL", "nhl"),
        ("ice hockey", "nhl"),
        ("hockey", "nhl"),
        ("NFL", "nfl"),
        ("american football", "nfl"),
        ("NCAA Football", "ncaaf"),
        ("college football", "ncaaf"),
        ("soccer", "fb"),
        ("football", "fb"),
        ("Premier League Soccer", "fb"),
        (None, None),
        ("", None),
        ("tennis", None),
    ],
)
def test_normalize_sport_key(raw, expected):
    assert normalize_sport_key(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("basketball", "nba"),
        ("wnba", "wnba"),
        ("soccer", "soccer"),
        ("football", "fb"),
        ("ufc", "ufc"),
    ],
)
def test_normalize_sport_key_exact(raw, expected):
    assert normalize_sport_key_exact(raw) == expected


def test_primary_sport_key_prefers_specific_league():
    assert primary_sport_key(frozenset({"mlb", "nba"})) == "mlb"
    assert primary_sport_key(frozenset({"nba", "wnba"})) == "nba"
    assert primary_sport_key(frozenset({"milb", "mlb"})) == "milb"


def test_sport_key_from_league_name():
    assert sport_key_from_league_name("English Premier League") == "soccer"
    assert sport_key_from_league_name("MLB") == "mlb"
    assert sport_key_from_league_name("WNBA") == "wnba"


def test_sportsipy_sport_key_supported_only():
    assert sportsipy_sport_key("NBA") == "nba"
    assert sportsipy_sport_key("WNBA") is None


def test_espn_paths_major_leagues():
    assert espn_paths("NBA", "") == ("basketball", "nba")
    assert espn_paths("WNBA", "") == ("basketball", "wnba")
    assert espn_paths("soccer", "Premier League") == ("soccer", "eng.1")
