"""Generic SofaScore client and registry tests (TODO 133)."""

import json
from pathlib import Path
from unittest.mock import patch

from models.sync import Settings
from services.ppv.calendar_providers.sofascore import (
    clear_sofascore_tennis_calendar_cache,
    fetch_events_for_slug,
    get_sofascore_calendar_stats,
)
from services.ppv.calendar_providers.sofascore.registry import enabled_slugs, slug_enabled
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED

FIXTURES = Path(__file__).parent / "fixtures" / "sofascore"
TENNIS_FIXTURE = FIXTURES / "scheduled_events_20260603.json"


class TestSofaScoreRegistry:
    def test_football_enabled_by_default(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "true")
            Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "false")
            assert slug_enabled("football") is True
            assert slug_enabled("tennis") is False
            assert "football" in enabled_slugs()
            assert "tennis" not in enabled_slugs()

    def test_tennis_flag_gates_slug(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "true")
            assert slug_enabled("tennis") is True


class TestGenericClient:
    def test_fetch_events_for_slug_uses_cache(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "true")
            clear_sofascore_tennis_calendar_cache()
            payload = json.loads(TENNIS_FIXTURE.read_text(encoding="utf-8"))
            with patch(
                "services.ppv.calendar_providers.sofascore.client.fetch_scheduled_events_http",
                return_value=payload,
            ) as mock_fetch:
                first = fetch_events_for_slug("tennis", "2026-06-03")
                second = fetch_events_for_slug("tennis", "2026-06-03")
            assert len(first) > 0
            assert first == second
            assert mock_fetch.call_count == 1

    def test_disabled_slug_returns_empty(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "false")
            assert fetch_events_for_slug("tennis", "2026-06-03") == []

    def test_stats_include_enabled_slugs(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED, "true")
            stats = get_sofascore_calendar_stats()
            assert "enabled_slugs" in stats
            assert stats["football_enabled"] is True
