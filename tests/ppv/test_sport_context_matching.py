"""Tests for sport/league context resolution and event-bound PPV matching."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from services.ppv.enrichment import PPVCalendarEnrichmentService
from services.ppv.matching.context import event_league_matches_context, resolve_sport_league_context
from services.ppv.matching.validation import (
    competitors_match_event,
    team_names_match,
    team_names_match_for_event_validation,
)
from services.thesportsdb_calendar_scraper import CalendarEvent

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "sport_context_channels.json"


def _load_fixtures():
    with FIXTURES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _calendar_event(data: dict) -> CalendarEvent:
    return CalendarEvent(
        event_id=data["event_id"],
        event_name=data["event_name"],
        league_name=data["league_name"],
        time_utc=data["time_utc"],
        date=data["date"],
        home_team=data["home_team"],
        away_team=data["away_team"],
    )


class TestResolveSportLeagueContext:
    def test_mlb_slot_and_category(self):
        ctx = resolve_sport_league_context(
            "MLB 10 | Royals x Rangers start:2026-05-31 19:35:00",
            "US| MLB PPV",
        )
        assert "mlb" in ctx.sport_keys

    def test_nhl_from_dazn_prefix(self):
        ctx = resolve_sport_league_context(
            "NL: DAZN PPV 7 - SENATORS @ RANGERS | Thu 15 Jan 00:20",
            "NL| NHL PPV",
        )
        assert "nhl" in ctx.sport_keys

    def test_soccer_from_category(self):
        ctx = resolve_sport_league_context(
            "End | Royals at Rangers | NL: SOCCER PPV 94",
            "NL| SOCCER PPV",
        )
        assert "soccer" in ctx.sport_keys
        assert "mlb" not in ctx.sport_keys

    def test_flohockey_maps_to_nhl(self):
        ctx = resolve_sport_league_context(
            "(FLSP 097) | flohockey: 2026 Reading Royals vs Worcester Railers",
            "US| HOCKEY PPV",
        )
        assert "nhl" in ctx.sport_keys

    def test_empty_for_generic_name(self):
        ctx = resolve_sport_league_context("PPV Event 12", None)
        assert ctx.is_empty


class TestEventLeagueMatchesContext:
    def test_mlb_context_accepts_mlb_league(self):
        ctx = resolve_sport_league_context("MLB 10 | Giants x Rockies", "US| MLB PPV")
        assert event_league_matches_context("MLB", ctx)

    def test_mlb_context_rejects_nhl_league(self):
        ctx = resolve_sport_league_context("MLB 10 | Giants x Rockies", "US| MLB PPV")
        assert not event_league_matches_context("NHL", ctx)

    def test_soccer_context_rejects_mlb(self):
        ctx = resolve_sport_league_context("End | Team A at Team B", "NL| SOCCER PPV")
        assert not event_league_matches_context("MLB", ctx)

    def test_hockey_context_accepts_echl(self):
        ctx = resolve_sport_league_context("flohockey: Reading Royals vs Railers", "US| HOCKEY PPV")
        assert event_league_matches_context("American ECHL", ctx)

    def test_empty_context_accepts_any_league(self):
        ctx = resolve_sport_league_context("Generic PPV 1", None)
        assert event_league_matches_context("MLB", ctx)
        assert event_league_matches_context("Unknown League", ctx)


class TestTeamNamesMatchForEventValidation:
    def test_strict_rejects_ambiguous_rangers(self):
        assert not team_names_match("Rangers", "Texas Rangers")

    def test_event_validation_accepts_ambiguous_rangers(self):
        assert team_names_match_for_event_validation("Rangers", "Texas Rangers", sport_key="mlb")

    def test_event_validation_accepts_ambiguous_royals(self):
        assert team_names_match_for_event_validation("Royals", "Kansas City Royals", sport_key="mlb")

    def test_mlb_competitors_match_production_event(self):
        event = _calendar_event(_load_fixtures()[0]["event"])
        ctx = resolve_sport_league_context(
            _load_fixtures()[0]["channel_name"],
            _load_fixtures()[0]["category_name"],
        )
        assert competitors_match_event(("Royals", "Rangers"), event, context=ctx)


@pytest.mark.parametrize("case", _load_fixtures(), ids=lambda c: c["id"])
class TestCompetitorsMatchWithContext:
    def test_fixture_cases(self, case):
        event = _calendar_event(case["event"])
        ctx = resolve_sport_league_context(case["channel_name"], case.get("category_name"))
        for sport_key in case.get("expected_sport_keys", []):
            assert sport_key in ctx.sport_keys

        result = competitors_match_event(tuple(case["competitors"]), event, context=ctx)
        assert result is case["should_match"], case["description"]


class TestMatchChannelToCalendarIntegration:
    @pytest.fixture
    def service(self, app):
        with app.app_context():
            yield PPVCalendarEnrichmentService(app)

    def test_mlb_royals_rangers_succeeds_with_word_overlap_match(self, service):
        """Production case: reverse matcher word_overlap at 0.70 should now validate."""
        fixture = next(c for c in _load_fixtures() if c["id"] == "mlb_royals_rangers")
        calendar_event = _calendar_event(fixture["event"])

        mock_match = Mock()
        mock_match.event = calendar_event
        mock_match.confidence = 0.70
        mock_match.match_type = "word_overlap"

        channel = Mock()
        channel.name = fixture["channel_name"]
        category = Mock()
        category.category_name = fixture["category_name"]
        channel.category = category

        extraction = {
            "competitors": tuple(fixture["competitors"]),
            "date": None,
        }

        service.reverse_matcher = Mock()
        service.reverse_matcher.load_events_for_date_range = Mock()
        service.reverse_matcher.find_matches = Mock(return_value=[mock_match])

        result = service._match_channel_to_calendar(
            channel,
            extraction,
            calendar_events=[calendar_event],
            date_str="2026-05-31",
        )

        assert result.matched is True
        assert result.calendar_event == calendar_event
        assert result.confidence == 0.70

    def test_soccer_ppv_rejects_mlb_event(self, service):
        fixture = next(c for c in _load_fixtures() if c["id"] == "reject_soccer_ppv_mlb_event")
        calendar_event = _calendar_event(fixture["event"])

        mock_match = Mock()
        mock_match.event = calendar_event
        mock_match.confidence = 0.70
        mock_match.match_type = "word_overlap"

        channel = Mock()
        channel.name = fixture["channel_name"]
        category = Mock()
        category.category_name = fixture["category_name"]
        channel.category = category

        extraction = {
            "competitors": tuple(fixture["competitors"]),
            "date": None,
        }

        service.reverse_matcher = Mock()
        service.reverse_matcher.load_events_for_date_range = Mock()
        service.reverse_matcher.find_matches = Mock(return_value=[mock_match])

        result = service._match_channel_to_calendar(
            channel,
            extraction,
            calendar_events=[calendar_event],
            date_str="2026-05-31",
        )

        assert result.matched is False
        assert result.match_method == "league_context_mismatch"


class TestSportsTeamAliasLookup:
    def test_sports_team_aliases_match_when_seeded(self, app, db):
        from models import SportsTeam

        with app.app_context():
            team = SportsTeam(
                sport=SportsTeam.SPORT_MLB,
                abbreviation="TEX",
                name="Texas Rangers",
            )
            team.set_aliases(["rangers", "texas rangers"])
            db.session.add(team)
            db.session.commit()

            from services.ppv.matching import validation as validation_module

            validation_module._sports_team_mapping_cache.clear()

            assert team_names_match_for_event_validation("Rangers", "Texas Rangers", sport_key="mlb")
