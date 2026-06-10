"""Tests for SofaScore tennis calendar provider (slice 1 — not wired to enrichment)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import Event
from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED
from services.ppv.enrichment.types import calendar_event_source
from services.tennis.sofascore_calendar import (
    EVENT_SOURCE_SOFASCORE,
    MIN_REQUEST_INTERVAL_SECONDS,
    clear_sofascore_tennis_calendar_cache,
    fetch_scheduled_events,
    fetch_tennis_events_for_date,
    parse_tennis_scheduled_events,
    scheduled_event_to_calendar_event,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sofascore"
TENNIS_FIXTURE = FIXTURES / "scheduled_events_20260603.json"


def _load_fixture() -> dict:
    return json.loads(TENNIS_FIXTURE.read_text(encoding="utf-8"))


class TestParseTennisFixture:
    def test_parses_kalinskaya_match(self):
        payload = _load_fixture()
        events = parse_tennis_scheduled_events(payload, date_str="2026-06-03")
        match = next(e for e in events if {e.home_team, e.away_team} == {"Anna Kalinskaya", "Maja Chwalinska"})
        assert match.event_id == "16198594"
        assert match.source == EVENT_SOURCE_SOFASCORE
        assert match.sport == "Tennis"
        assert "Roland Garros" in match.league_name
        assert match.time_utc

    def test_calendar_event_source_maps_to_model_constant(self):
        payload = _load_fixture()
        events = parse_tennis_scheduled_events(payload, date_str="2026-06-03")
        assert events
        assert calendar_event_source(events[0]) == Event.SOURCE_SOFASCORE


class TestScheduledEventToCalendarEvent:
    def test_skips_cancelled_status(self):
        payload = _load_fixture()
        raw = dict(payload["events"][0])
        raw["status"] = {"type": "cancelled"}
        assert scheduled_event_to_calendar_event(raw, fallback_date="2026-06-03") is None


class TestHttpGet:
    def test_prefers_curl_cffi_with_chrome_impersonation(self):
        mock_response = MagicMock()
        mock_curl = MagicMock()
        mock_curl.get.return_value = mock_response

        with patch.dict("sys.modules", {"curl_cffi": MagicMock(requests=mock_curl)}):
            from services.tennis.sofascore_calendar import _http_get

            result = _http_get("https://api.sofascore.com/test", timeout=30, headers={"User-Agent": "test"})
            assert result is mock_response
            mock_curl.get.assert_called_once_with(
                "https://api.sofascore.com/test",
                timeout=30,
                headers={"User-Agent": "test"},
                impersonate="chrome",
            )

    def test_falls_back_to_requests_when_curl_cffi_missing(self):
        mock_response = MagicMock()
        with patch("services.tennis.sofascore_calendar.requests.get", return_value=mock_response) as mock_requests:
            import builtins

            real_import = builtins.__import__

            def _import_without_curl(name, *args, **kwargs):
                if name == "curl_cffi":
                    raise ImportError("no curl_cffi")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_import_without_curl):
                from services.tennis.sofascore_calendar import _http_get

                result = _http_get("https://api.sofascore.com/test", timeout=30)
                assert result is mock_response
                mock_requests.assert_called_once()


class TestFetchTennisEventsForDate:
    def setup_method(self):
        clear_sofascore_tennis_calendar_cache()

    def test_flag_off_returns_empty_without_http(self, app):
        Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "false")
        with patch("services.tennis.sofascore_calendar._http_get") as mock_get:
            assert fetch_tennis_events_for_date("2026-06-03") == []
            mock_get.assert_not_called()

    def test_cache_hit_skips_second_http(self, app):
        Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "true")
        payload = _load_fixture()
        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_response.raise_for_status = MagicMock()

        with patch("services.tennis.sofascore_calendar._http_get", return_value=mock_response) as mock_get:
            first = fetch_tennis_events_for_date("2026-06-03", force_refresh=True)
            second = fetch_tennis_events_for_date("2026-06-03")
            assert len(first) >= 1
            assert len(second) == len(first)
            assert mock_get.call_count == 1

    def test_rate_limit_spaces_requests(self, app):
        """Verify _rate_limit sleeps when the minimum interval has not elapsed."""
        import services.tennis.sofascore_calendar as sc

        sc._last_request_time = 100.0
        time_values = iter([100.5, 100.5])

        with patch.object(sc.time, "time", side_effect=lambda: next(time_values)):
            with patch.object(sc.random, "uniform", return_value=0.0):
                with patch.object(sc.time, "sleep") as mock_sleep:
                    sc._rate_limit()
        mock_sleep.assert_called_once_with(MIN_REQUEST_INTERVAL_SECONDS - 0.5)
