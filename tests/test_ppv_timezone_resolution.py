"""Tests for PPV channel timezone resolution."""

from datetime import datetime, timezone

import pytest

from services.ppv.constants import COUNTRY_PREFIX_TZ
from services.ppv.extraction import PPVEventExtractor
from services.ppv.timezone_resolution import (
    local_channel_datetime_to_utc,
    metadata_only_date_tolerance_hours,
    resolve_channel_timezone,
)
from services.ppv.venue_inference import detect_venue_inference_mode
from services.reverse_event_matcher.match_filter import MatchFilter


class TestCountryPrefixExtraction:
    def test_us_prefix(self):
        assert PPVEventExtractor.extract_country_prefix("US: DAZN PPV 3 - Teams") == "US"

    def test_uk_prefix(self):
        assert PPVEventExtractor.extract_country_prefix("UK: ESPN+ 1 - Game") == "UK"


class TestMatchupOrdering:
    def test_us_away_home(self):
        ext = PPVEventExtractor()
        m = ext.extract_matchup("US: ROYALS x RANGERS | Sat 31 May 19:05")
        assert m is not None
        assert m.ordering_rule in ("us_away_home", "metadata_only")
        if m.ordering_rule == "us_away_home":
            assert m.home_team == "RANGERS"
            assert m.away_team == "ROYALS"

    def test_uk_home_first(self):
        ext = PPVEventExtractor()
        m = ext.extract_matchup("UK: SAINTS - HARLEQUINS | Sat 03 Jan 17:15")
        assert m is not None
        assert m.home_team == "SAINTS"


class TestTimezoneResolution:
    def test_nl_prefix(self):
        res = resolve_channel_timezone("NL: DAZN PPV 7 - Ajax vs PSV")
        assert res.timezone == COUNTRY_PREFIX_TZ["NL"]
        assert res.confidence >= 0.8

    def test_es_prefix(self):
        res = resolve_channel_timezone("ES: LALIGA+ PPV 3 - Real vs Barca")
        assert res.timezone == "Europe/Madrid"

    def test_world_cup_metadata_only(self):
        res = resolve_channel_timezone("US: World Cup: Brazil vs Germany")
        assert res.source.startswith("metadata_only")
        mode = detect_venue_inference_mode("World Cup: Brazil vs Germany")
        assert mode.mode == "metadata_only"

    def test_central_via_team_city(self):
        res = resolve_channel_timezone(
            "US: ROYALS x RANGERS | Sat 31 May 19:05",
            competitors=("ROYALS", "RANGERS"),
        )
        assert res.timezone in ("America/Chicago", "America/New_York")
        if res.source == "home_venue_sports_team":
            assert res.timezone == "America/Chicago"


class TestUtcConversion:
    def test_uk_to_utc(self):
        res = resolve_channel_timezone("UK: Game | Tue 23 Dec 01:50")
        naive = datetime(2025, 12, 23, 1, 50)
        utc = local_channel_datetime_to_utc(naive, res)
        assert res.timezone == "Europe/London"
        assert utc.hour == 1


class TestMatchFilterUtc:
    def test_us_central_title_vs_utc_event(self):
        mf = MatchFilter(date_tolerance_hours=48, strict_date_validation=False)
        from services.reverse_event_matcher.match_strategy import MatchResult
        from services.thesportsdb_calendar_scraper import CalendarEvent

        event = CalendarEvent(
            event_id="1",
            event_name="Royals vs Rangers",
            league_name="MLB",
            time_utc="00:05",
            date="2025-05-31",
        )
        event._scheduled_at_cached = datetime(2025, 5, 31, 0, 5)
        event._scheduled_at_computed = True

        match = MatchResult(
            event=event,
            confidence=0.7,
            match_type="both_teams",
            matched_terms=[],
            details={},
        )

        from services.reverse_event_matcher.match_filter import DateFilter

        channel_utc = datetime(2025, 5, 31, 0, 5, tzinfo=timezone.utc)
        results = mf.filter_matches(
            [match],
            channel_date=channel_utc,
            channel_timezone="UTC",
            min_confidence=0.4,
            date_filter=DateFilter.ALL,
        )
        assert len(results) == 1

    def test_metadata_only_wider_tolerance(self):
        mode = detect_venue_inference_mode("US: Super Bowl: Chiefs vs Eagles")
        assert metadata_only_date_tolerance_hours(mode) == 72


class TestVenueInference:
    def test_super_bowl(self):
        mode = detect_venue_inference_mode("Super Bowl LVIII")
        assert mode.mode == "metadata_only"

    def test_conference_final_not_neutral(self):
        mode = detect_venue_inference_mode("NBA Conference Final Game 1")
        assert mode.mode == "team_home"

    def test_fa_cup_final(self):
        mode = detect_venue_inference_mode("FA Cup Final: Team A vs Team B")
        assert mode.mode == "metadata_only"
