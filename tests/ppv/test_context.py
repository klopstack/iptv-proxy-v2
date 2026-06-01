"""
Tests for the PPV context provider architecture.

Covers:
- DataType enum
- ContextDataProvider.covers() helpers
- ProviderRegistry discovery and coverage_report
- ContextCache TTL and threading
- build_prompt() fact injection
- validate_description() hallucination detection
- build_mechanical_description() fallback
- build_event_context() with mock providers
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from services.ppv.context.base import (
    ContextDataProvider,
    DataType,
    EventContext,
    TeamContext,
)
from services.ppv.context.cache import ContextCache
from services.ppv.context.prompt_builder import (
    build_mechanical_description,
    build_prompt,
    validate_description,
)
from services.ppv.context.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_team(name="Team A", record="10-5", standing="1st in Division"):
    return TeamContext(name=name, record=record, standing=standing, recent_form=["W 3-1", "L 0-2"])


def _make_context(**kwargs):
    defaults = dict(
        sport="Soccer",
        league="Premier League",
        home_team=_make_team("Arsenal", "18-5-3", "2nd in Premier League"),
        away_team=_make_team("Chelsea", "14-8-4", "5th in Premier League"),
        head_to_head=["2024-03-01: Arsenal 2-1 Chelsea", "2023-12-10: Chelsea 1-1 Arsenal"],
        event_notes="Top of the table clash with European spots at stake.",
        data_sources=["espn"],
        missing_data=[],
    )
    defaults.update(kwargs)
    return EventContext(**defaults)


# ---------------------------------------------------------------------------
# DataType enum
# ---------------------------------------------------------------------------

class TestDataType:
    def test_values(self):
        assert DataType.STANDINGS.value == "standings"
        assert DataType.HEAD_TO_HEAD.value == "head_to_head"
        assert DataType.TEAM_FORM.value == "team_form"
        assert DataType.EVENT_NOTES.value == "event_notes"
        assert DataType.FIGHTER_RECORD.value == "fighter_record"


# ---------------------------------------------------------------------------
# ContextDataProvider.covers() helpers
# ---------------------------------------------------------------------------

class _DummyProvider(ContextDataProvider):
    name = "dummy"
    supported_sports = {"Soccer", "NFL"}
    supported_leagues = {"Premier League", "La Liga"}
    provided_data_types = {DataType.STANDINGS, DataType.HEAD_TO_HEAD}
    priority = 50

    def get_standings(self, *a, **kw): return None
    def get_head_to_head(self, *a, **kw): return None
    def get_team_form(self, *a, **kw): return None
    def get_event_notes(self, *a, **kw): return None


class _BroadProvider(ContextDataProvider):
    """Covers all sports, all leagues (empty sets)."""
    name = "broad"
    supported_sports = set()
    supported_leagues = set()
    provided_data_types = {DataType.STANDINGS}
    priority = 90

    def get_standings(self, *a, **kw): return None
    def get_head_to_head(self, *a, **kw): return None
    def get_team_form(self, *a, **kw): return None
    def get_event_notes(self, *a, **kw): return None


class TestContextDataProviderCovers:
    def test_covers_matching_sport_and_league(self):
        p = _DummyProvider()
        assert p.covers("Soccer", "Premier League", DataType.STANDINGS)

    def test_covers_rejects_unsupported_sport(self):
        p = _DummyProvider()
        assert not p.covers("Basketball", "Premier League", DataType.STANDINGS)

    def test_covers_rejects_unsupported_league(self):
        p = _DummyProvider()
        assert not p.covers("Soccer", "Bundesliga", DataType.STANDINGS)

    def test_covers_rejects_unsupported_data_type(self):
        p = _DummyProvider()
        assert not p.covers("Soccer", "Premier League", DataType.TEAM_FORM)

    def test_broad_provider_covers_everything(self):
        p = _BroadProvider()
        assert p.covers("MiLB", "Double-A East", DataType.STANDINGS)

    def test_covers_sport_helper(self):
        p = _DummyProvider()
        assert p.covers_sport("NFL")
        assert not p.covers_sport("Hockey")

    def test_covers_league_helper(self):
        p = _DummyProvider()
        assert p.covers_league("La Liga")
        assert not p.covers_league("Bundesliga")

    def test_broad_provider_covers_any_league(self):
        p = _BroadProvider()
        assert p.covers_league("Anything")


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    def _make_registry(self):
        reg = ProviderRegistry()
        reg.register(_DummyProvider())
        reg.register(_BroadProvider())
        return reg

    def test_get_providers_for_returns_matching(self):
        reg = self._make_registry()
        providers = reg.get_providers_for("Soccer", "Premier League", DataType.STANDINGS)
        names = [p.name for p in providers]
        assert "dummy" in names

    def test_get_providers_for_returns_broad_fallback(self):
        reg = self._make_registry()
        providers = reg.get_providers_for("MiLB", "Triple-A East", DataType.STANDINGS)
        names = [p.name for p in providers]
        assert "broad" in names

    def test_get_providers_for_excludes_unsupported_type(self):
        reg = self._make_registry()
        # broad only has STANDINGS, dummy only has STANDINGS + HEAD_TO_HEAD
        providers = reg.get_providers_for("Soccer", "Premier League", DataType.TEAM_FORM)
        assert providers == []

    def test_providers_ordered_by_priority(self):
        reg = self._make_registry()
        providers = reg.get_providers_for("Soccer", "Premier League", DataType.STANDINGS)
        priorities = [p.priority for p in providers]
        assert priorities == sorted(priorities)

    def test_coverage_report_structure(self):
        reg = self._make_registry()
        report = reg.coverage_report()
        assert isinstance(report, dict)
        assert "providers" in report
        assert "by_sport" in report

    def test_coverage_report_lists_providers(self):
        reg = self._make_registry()
        report = reg.coverage_report()
        provider_names = {p["name"] for p in report["providers"]}
        assert "dummy" in provider_names
        assert "broad" in provider_names


# ---------------------------------------------------------------------------
# ContextCache
# ---------------------------------------------------------------------------

class TestContextCache:
    def test_set_and_get(self):
        cache = ContextCache()
        cache.set("key1", {"data": "value"}, DataType.STANDINGS)
        assert cache.get("key1") == {"data": "value"}

    def test_miss_returns_none(self):
        cache = ContextCache()
        assert cache.get("missing_key") is None

    def test_expired_entry_returns_none(self):
        cache = ContextCache()
        # Override TTL to 0 seconds for STANDINGS data type
        from services.ppv.context.cache import CACHE_TTL
        original = CACHE_TTL.get(DataType.STANDINGS)
        CACHE_TTL[DataType.STANDINGS] = 0
        try:
            cache.set("key_exp", {"x": 1}, DataType.STANDINGS)
            time.sleep(0.01)
            assert cache.get("key_exp") is None
        finally:
            if original is not None:
                CACHE_TTL[DataType.STANDINGS] = original

    def test_thread_safety(self):
        """Multiple threads can write to and read from the cache without error."""
        cache = ContextCache()
        errors = []

        def worker(i):
            try:
                cache.set(f"k{i}", i, DataType.TEAM_FORM)
                val = cache.get(f"k{i}")
                assert val == i or val is None  # May be evicted if TTL is tiny
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ---------------------------------------------------------------------------
# build_prompt()
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_contains_team_names(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        assert "Arsenal" in prompt
        assert "Chelsea" in prompt

    def test_contains_record(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        assert "18-5-3" in prompt

    def test_contains_head_to_head(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        assert "Arsenal 2-1 Chelsea" in prompt

    def test_contains_event_notes(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        assert "European spots" in prompt

    def test_unknown_section_when_missing(self):
        ctx = _make_context(head_to_head=[], event_notes=None)
        prompt = build_prompt(ctx)
        assert "UNKNOWN" in prompt

    def test_missing_data_listed_in_prompt(self):
        # When both teams have no record/standing, prompt should use UNKNOWN markers
        ctx = _make_context(
            missing_data=[DataType.STANDINGS.value],
            home_team=TeamContext(name="Arsenal", record=None, standing=None, recent_form=[]),
            away_team=TeamContext(name="Chelsea", record=None, standing=None, recent_form=[]),
        )
        prompt = build_prompt(ctx)
        assert "UNKNOWN" in prompt


# ---------------------------------------------------------------------------
# validate_description()
# ---------------------------------------------------------------------------

class TestValidateDescription:
    def test_valid_description_passes(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        desc = "Arsenal take on Chelsea in a top-of-the-table clash with 18-5-3 form."
        assert validate_description(desc, prompt) is True

    def test_hallucinated_number_fails(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        # "99" does not appear in the prompt context
        desc = "Arsenal's last 99 games were all wins."
        result = validate_description(desc, prompt)
        # Should fail because 99 is not in the prompt
        assert result is False

    def test_no_numbers_passes(self):
        ctx = _make_context()
        prompt = build_prompt(ctx)
        desc = "A major Premier League fixture."
        assert validate_description(desc, prompt) is True


# ---------------------------------------------------------------------------
# build_mechanical_description()
# ---------------------------------------------------------------------------

class TestBuildMechanicalDescription:
    def test_contains_both_teams(self):
        ctx = _make_context()
        desc = build_mechanical_description(ctx)
        assert "Arsenal" in desc
        assert "Chelsea" in desc

    def test_contains_sport_and_league(self):
        ctx = _make_context()
        desc = build_mechanical_description(ctx)
        assert "Soccer" in desc or "Premier League" in desc

    def test_returns_string(self):
        ctx = _make_context()
        assert isinstance(build_mechanical_description(ctx), str)


# ---------------------------------------------------------------------------
# build_event_context() with mock providers
# ---------------------------------------------------------------------------

class TestBuildEventContext:
    def test_uses_registered_provider(self, app):
        """build_event_context calls providers and returns an EventContext."""
        from services.ppv.context.assembler import build_event_context
        from services.ppv.context.registry import ProviderRegistry

        mock_provider = MagicMock(spec=_DummyProvider)
        mock_provider.name = "mock"
        mock_provider.supported_sports = set()  # covers all
        mock_provider.supported_leagues = set()
        mock_provider.provided_data_types = {
            DataType.STANDINGS,
            DataType.HEAD_TO_HEAD,
            DataType.TEAM_FORM,
            DataType.EVENT_NOTES,
        }
        mock_provider.priority = 1
        mock_provider.covers.return_value = True
        mock_provider.covers_sport.return_value = True
        mock_provider.covers_league.return_value = True
        mock_provider.get_standings.return_value = {
            "_all_teams": {
                "team a": {"record": "10-5", "standing": "1st"},
                "team b": {"record": "8-7", "standing": "3rd"},
            }
        }
        mock_provider.get_head_to_head.return_value = ["2024-01-01: Team A 2-1 Team B"]
        mock_provider.get_team_form.return_value = ["W 2-0", "L 1-3"]
        mock_provider.get_event_notes.return_value = "Key fixture at the top."

        # Build a minimal mock event
        event = MagicMock()
        event.home_team_name = "Team A"
        event.away_team_name = "Team B"
        event.sport = "Soccer"
        event.league_name = "Test League"
        event.home_team_id = None
        event.away_team_id = None
        event.start_time = None
        event.external_id = None

        mock_registry = ProviderRegistry()
        mock_registry.register(mock_provider)

        with app.app_context():
            with patch("services.ppv.context.assembler.get_registry", return_value=mock_registry):
                ctx = build_event_context(event)

        assert isinstance(ctx, EventContext)
        assert ctx.sport == "Soccer"
        assert ctx.home_team.name == "Team A"
        assert ctx.away_team.name == "Team B"
        assert isinstance(ctx.data_sources, list)
