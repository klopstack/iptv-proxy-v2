"""Tests for PPV competitor validation."""

from services.ppv.matching.context import resolve_sport_league_context
from services.ppv.matching.validation import (
    competitors_match_event,
    is_weak_match_type,
    team_names_match,
    team_names_match_for_event_validation,
)
from services.thesportsdb_calendar_scraper import CalendarEvent


def _event(home, away, event_id="1"):
    return CalendarEvent(
        event_id=event_id,
        event_name=f"{home} vs {away}",
        league_name="Test League",
        time_utc="20:00",
        date="2026-06-16",
        home_team=home,
        away_team=away,
    )


class TestCompetitorValidation:
    def test_team_names_match_partial(self):
        assert team_names_match("Los Angeles Sparks", "Sparks")
        assert team_names_match("Golden State Valkyries", "Valkyries")

    def test_team_names_match_mlb_nicknames(self):
        assert team_names_match("Giants", "San Francisco Giants")
        assert team_names_match("Rockies", "Colorado Rockies")
        assert team_names_match("Blue Jays", "Toronto Blue Jays")

    def test_team_names_reject_ambiguous_only(self):
        assert not team_names_match("United", "Manchester United")
        assert not team_names_match("City", "Kansas City")

    def test_competitors_match_mlb_event(self):
        event = _event("Colorado Rockies", "San Francisco Giants")
        assert competitors_match_event(("Giants", "Rockies"), event)
        assert competitors_match_event(("Rockies", "Giants"), event)

    def test_team_names_match_mlb_abbreviations(self):
        assert team_names_match("D-backs", "Arizona Diamondbacks")
        assert team_names_match("Dbacks", "Arizona Diamondbacks")

    def test_competitors_match_mlb_dbacks_mariners(self):
        event = _event("Seattle Mariners", "Arizona Diamondbacks")
        assert competitors_match_event(("D-backs", "Mariners"), event)

    def test_mlb_royals_rangers_mascots_with_context(self):
        event = CalendarEvent(
            event_id="2387740",
            event_name="Texas Rangers vs Kansas City Royals",
            league_name="MLB",
            time_utc="18:35",
            date="2026-05-31",
            home_team="Texas Rangers",
            away_team="Kansas City Royals",
        )
        ctx = resolve_sport_league_context(
            "MLB 10 | Royals x Rangers start:2026-05-31 19:35:00",
            "US| MLB PPV",
        )
        assert competitors_match_event(("Royals", "Rangers"), event, context=ctx)

    def test_strict_vs_event_validation_rangers(self):
        assert not team_names_match("Rangers", "Texas Rangers")
        assert team_names_match_for_event_validation("Rangers", "Texas Rangers", sport_key="mlb")

    def test_competitors_reject_mlb_for_soccer_context(self):
        event = CalendarEvent(
            event_id="2387740",
            event_name="Texas Rangers vs Kansas City Royals",
            league_name="MLB",
            time_utc="18:35",
            date="2026-05-31",
            home_team="Texas Rangers",
            away_team="Kansas City Royals",
        )
        ctx = resolve_sport_league_context(
            "End | Royals at Rangers | NL: SOCCER PPV 94",
            "NL| SOCCER PPV",
        )
        assert not competitors_match_event(("Royals", "Rangers"), event, context=ctx)

    def test_competitors_match_event_both_teams(self):
        event = _event("Dallas Wings", "Las Vegas Aces")
        assert competitors_match_event(("Dallas Wings", "Las Vegas Aces"), event)
        assert not competitors_match_event(("Los Angeles Sparks", "Golden State Valkyries"), event)

    def test_competitors_reject_unknown_teams(self):
        event = _event("Unknown", "Unknown")
        assert not competitors_match_event(("Team A", "Team B"), event)

    def test_weak_match_types(self):
        assert is_weak_match_type("league_plus_word")
        assert not is_weak_match_type("both_teams")
