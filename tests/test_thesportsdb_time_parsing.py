"""Tests for TheSportsDB event time parsing and UTC normalization."""

from datetime import datetime, timezone

from services.datetime_utils import (
    infer_thesportsdb_event_timezone,
    parse_thesportsdb_scheduled_at,
    parse_title_timezone,
    to_naive_utc,
)


class TestToNaiveUtc:
    def test_naive_passthrough(self):
        dt = datetime(2026, 1, 6, 1, 20)
        assert to_naive_utc(dt) == dt

    def test_aware_converts_to_utc(self):
        dt = datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc)
        assert to_naive_utc(dt) == datetime(2026, 1, 6, 1, 20)

    def test_eastern_converts_to_utc(self):
        from zoneinfo import ZoneInfo

        dt = datetime(2026, 1, 5, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        assert to_naive_utc(dt) == datetime(2026, 1, 6, 1, 0)


class TestParseTitleTimezone:
    def test_est(self):
        assert parse_title_timezone("Team A vs B 7:00 PM EST") == "America/New_York"

    def test_pt(self):
        assert parse_title_timezone("Team A vs B 4:00 PM PT") == "America/Los_Angeles"

    def test_utc(self):
        assert parse_title_timezone("Team A vs B 00:00 UTC") == "UTC"

    def test_missing(self):
        assert parse_title_timezone("Team A vs B 7:00 PM") is None


class TestParseThesportsdbScheduledAt:
    def test_timestamp_with_z(self):
        scheduled, tz = parse_thesportsdb_scheduled_at(
            {
                "idEvent": "1",
                "strTimestamp": "2026-01-05T22:00:00Z",
                "dateEvent": "2026-01-05",
                "strTime": "22:00:00",
            }
        )
        assert scheduled == datetime(2026, 1, 5, 22, 0)
        assert tz is None

    def test_naive_timestamp_uses_str_time_utc(self):
        """Naive strTimestamp must not be treated as UTC when strTime is available."""
        scheduled, _ = parse_thesportsdb_scheduled_at(
            {
                "idEvent": "441613",
                "strTimestamp": "2014-12-29T20:00:00",
                "dateEvent": "2014-12-29",
                "strTime": "20:00:00",
                "strTimeLocal": "20:00:00",
            }
        )
        assert scheduled == datetime(2014, 12, 29, 20, 0)

    def test_us_evening_game_utc_from_str_time(self):
        """US 7 PM Eastern kickoff stored as 00:00 UTC next day in strTime."""
        scheduled, tz = parse_thesportsdb_scheduled_at(
            {
                "idEvent": "99",
                "strTimestamp": "2026-01-06T00:00:00",
                "dateEvent": "2026-01-06",
                "strTime": "00:00:00",
                "strTimeLocal": "19:00:00",
                "strCountry": "USA",
            }
        )
        assert scheduled == datetime(2026, 1, 6, 0, 0)
        assert tz == "America/New_York"

    def test_date_only_returns_none(self):
        scheduled, _ = parse_thesportsdb_scheduled_at(
            {
                "idEvent": "2",
                "dateEvent": "2026-01-05",
            }
        )
        assert scheduled is None

    def test_timestamp_with_numeric_offset(self):
        scheduled, _ = parse_thesportsdb_scheduled_at(
            {
                "idEvent": "3",
                "strTimestamp": "2026-01-05T17:00:00-05:00",
                "dateEvent": "2026-01-05",
                "strTime": "22:00:00",
            }
        )
        assert scheduled == datetime(2026, 1, 5, 22, 0)


class TestInferThesportsdbEventTimezone:
    def test_from_country_when_local_differs(self):
        tz = infer_thesportsdb_event_timezone(
            {
                "strTime": "00:00:00",
                "strTimeLocal": "19:00:00",
                "strCountry": "USA",
            }
        )
        assert tz == "America/New_York"

    def test_from_country_when_times_match(self):
        tz = infer_thesportsdb_event_timezone(
            {
                "strTime": "20:00:00",
                "strTimeLocal": "20:00:00",
                "strCountry": "England",
            }
        )
        assert tz == "Europe/London"
