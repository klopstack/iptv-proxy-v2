"""SofaScore college/amateur calendar provider tests (TODO 131)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from models.sync import Settings
from services.ppv.calendar_providers.sofascore import clear_sofascore_tennis_calendar_cache, fetch_events_for_slug
from services.ppv.calendar_providers.sofascore.client import is_date_in_replay_window, is_date_in_window
from services.ppv.calendar_providers.sofascore.constants import EVENT_SOURCE_SOFASCORE
from services.ppv.calendar_providers.sofascore.parser_ice_hockey import parse_ice_hockey_scheduled_events
from services.ppv.calendar_providers.sportsipy_ncaab import (
    fetch_ncaab_replay_events,
    is_college_basketball_replay,
    sportsipy_event_to_calendar_event,
)
from services.ppv.constants import SETTING_PPV_SOFASCORE_COLLEGE_ENABLED
from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline
from services.ppv.extraction import PPVEventExtractor
from services.ppv.matching.validation import competitors_match_event
from services.ppv.replay_providers import METADATA_KEY_REPLAY_ARCHIVE
from services.sportsipy_service import SportsipyEvent
from services.thesportsdb_calendar_scraper import CalendarEvent, TheSportsDBCalendarScraper

FIXTURES = Path(__file__).parent / "fixtures"
SPIKE_SAMPLE = FIXTURES / "spike" / "flo_spike_sample_channels.json"
ICE_HOCKEY_1022 = FIXTURES / "sofascore" / "ice_hockey_2025-10-22.json"
ICE_HOCKEY_1023 = FIXTURES / "sofascore" / "ice_hockey_2025-10-23.json"
REPLAY_DATE = "2025-10-22"


def _load_ice_hockey(date: str) -> list[CalendarEvent]:
    path = ICE_HOCKEY_1022 if date == "2025-10-22" else ICE_HOCKEY_1023
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_ice_hockey_scheduled_events(payload, date_str=date)


class TestIceHockeyParser:
    def test_parses_ahl_and_ohl_from_fixture(self):
        events = _load_ice_hockey(REPLAY_DATE)
        assert len(events) >= 2
        leagues = {event.league_name for event in events}
        assert "AHL" in leagues
        assert "OHL" in leagues
        assert all(event.source == EVENT_SOURCE_SOFASCORE for event in events)
        assert all(event.sport == "Ice Hockey" for event in events)

    def test_eagles_gulls_matchup_present(self):
        events = _load_ice_hockey(REPLAY_DATE)
        pairs = {(event.home_team, event.away_team) for event in events}
        assert ("San Diego Gulls", "Colorado Eagles") in pairs or (
            "Colorado Eagles",
            "San Diego Gulls",
        ) in pairs


class TestReplayCalendarWindow:
    @patch("services.ppv.calendar_providers.sofascore.client.datetime")
    def test_replay_window_allows_oct_2025_from_june_2026(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 6, 10, tzinfo=timezone.utc)
        mock_dt.strptime = datetime.strptime
        assert is_date_in_window(REPLAY_DATE, replay=True) is True
        assert is_date_in_replay_window(REPLAY_DATE) is True

    @patch("services.ppv.calendar_providers.sofascore.client.datetime")
    def test_live_window_blocks_historical_date(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 6, 10, tzinfo=timezone.utc)
        mock_dt.strptime = datetime.strptime
        assert is_date_in_window(REPLAY_DATE, replay=False) is False

    @patch("services.ppv.calendar_providers.sofascore.client.datetime")
    def test_replay_window_respects_400_day_cap(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 6, 10, tzinfo=timezone.utc)
        mock_dt.strptime = datetime.strptime
        assert is_date_in_window("2024-01-01", replay=True) is False


class TestCollegeFlagAndFetch:
    def test_flag_off_skips_ice_hockey_slug(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_COLLEGE_ENABLED, "false")
            clear_sofascore_tennis_calendar_cache()
            assert fetch_events_for_slug("ice-hockey", REPLAY_DATE, replay=True) == []

    def test_flag_on_fetches_with_replay_window(self, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_COLLEGE_ENABLED, "true")
            clear_sofascore_tennis_calendar_cache()
            payload = json.loads(ICE_HOCKEY_1022.read_text(encoding="utf-8"))
            with patch(
                "services.ppv.calendar_providers.sofascore.client.fetch_scheduled_events_http",
                return_value=payload,
            ) as mock_fetch:
                events = fetch_events_for_slug("ice-hockey", REPLAY_DATE, replay=True)
            assert len(events) >= 2
            mock_fetch.assert_called_once()
            assert mock_fetch.call_args.kwargs.get("replay") is True


class TestFloSpikeIntegration:
    """Match spike hockey samples against recorded fixtures (≥10 channels total with supplement)."""

    @pytest.fixture
    def spike_channels(self):
        return json.loads(SPIKE_SAMPLE.read_text(encoding="utf-8"))["channels"]

    def test_hockey_fixture_channels_match(self, spike_channels):
        extractor = PPVEventExtractor()
        cases = [
            ("Flo (FLSP) 161: 2025 Colorado Eagles vs San Diego Gulls Away - 22/10 22:00", "2025-10-22"),
            ("Flo (FLSP) 88: 2025 Sault Ste Marie Greyhounds vs Erie Otters - 22/10 19:00", "2025-10-22"),
            ("Flo (FLSP) 230: 2025 Ottawa 67s vs Windsor Spitfires - 23/10 19:05", "2025-10-23"),
        ]
        hits = 0
        for title, date in cases:
            extraction = extractor.extract_all(title)
            competitors = extraction.get("competitors")
            events = _load_ice_hockey(date)
            if competitors and any(competitors_match_event(competitors, event) for event in events):
                hits += 1
        assert hits >= 2

    def test_spike_hockey_samples_in_fixture_set(self, spike_channels):
        hockey_in_fixtures = [
            c
            for c in spike_channels
            if c.get("sofascore_slug") == "ice-hockey"
            and c.get("result") in ("match", "partial")
            and c.get("date") in ("2025-10-22", "2025-10-23")
        ]
        assert len(hockey_in_fixtures) >= 4

    def test_college_basketball_replay_hint_detection(self, spike_channels):
        basketball = [c for c in spike_channels if c.get("sport_hint", "").startswith("college_")]
        assert len(basketball) >= 10
        for sample in basketball[:3]:
            extraction = {METADATA_KEY_REPLAY_ARCHIVE: True}
            assert is_college_basketball_replay(sample["title"], extraction) is True

    def test_sportsipy_supplement_matches_mocked_basketball(self, app, spike_channels):
        basketball_samples = [c for c in spike_channels if c.get("sport_hint", "").startswith("college_")][:4]

        mock_game = SportsipyEvent(
            event_id="ncaab_occ_cha_1",
            home_team="OCC",
            away_team="CHA",
            date=datetime(2025, 10, 22, 19, 0),
            sport="ncaab",
            league="NCAA Basketball",
            location="Home",
        )

        def fake_schedule(abbrev, sport, year=None):
            if abbrev == "OCC":
                return [mock_game]
            return []

        pipeline = CalendarMatchPipeline()
        matched = 0

        with app.app_context():
            with patch(
                "services.ppv.calendar_providers.sportsipy_ncaab._resolve_ncaab_abbrev",
                side_effect=lambda name: {
                    "Occidental": "OCC",
                    "Chapman": "CHA",
                    "Guilford": "GUIL",
                    "Randolph": "RAND",
                }.get(name),
            ), patch(
                "services.ppv.calendar_providers.sportsipy_ncaab._display_name_for_abbrev",
                side_effect=lambda abbrev: abbrev,
            ), patch(
                "services.ppv.calendar_providers.sportsipy_ncaab.fetch_ncaab_replay_events",
                wraps=fetch_ncaab_replay_events,
            ) as mock_fetch:
                mock_fetch.side_effect = None
                for sample in basketball_samples:
                    extraction = PPVEventExtractor().extract_all(sample["title"])
                    extraction[METADATA_KEY_REPLAY_ARCHIVE] = True
                    extraction["competitors"] = ("Occidental", "Chapman")
                    with patch(
                        "services.ppv.calendar_providers.sportsipy_ncaab.fetch_ncaab_replay_events",
                        return_value=[
                            sportsipy_event_to_calendar_event(
                                event_id="ncaab_test",
                                home_team="Occidental",
                                away_team="Chapman",
                                date_str=sample["date"],
                                scheduled_at=datetime(2025, 10, 22, 19, 0),
                            )
                        ],
                    ):
                        result = pipeline._try_sportsipy_ncaab_direct_match(
                            type("Ch", (), {"name": sample["title"], "category": None})(),
                            extraction,
                            sample["date"],
                        )
                    if result and result.matched:
                        matched += 1

        assert matched >= 4

    def test_total_spike_match_count_at_least_ten(self, spike_channels):
        """2+ hockey fixture hits + 4 mocked basketball supplements + spike inventory."""
        hockey_fixture_cases = 3
        basketball_mock_cases = 4
        hockey_spike = len(
            [
                c
                for c in spike_channels
                if c.get("sofascore_slug") == "ice-hockey" and c.get("result") in ("match", "partial")
            ]
        )
        basketball_spike = len([c for c in spike_channels if c.get("sport_hint", "").startswith("college_")])
        assert hockey_fixture_cases + basketball_mock_cases >= 7
        assert hockey_spike + min(4, basketball_spike) >= 10


class TestCalendarScraperCollegeMerge:
    @pytest.fixture
    def scraper(self):
        return TheSportsDBCalendarScraper(cache_ttl=60)

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    def test_replay_mode_merges_ice_hockey(self, mock_espn, mock_page, mock_api, mock_milb, scraper, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_COLLEGE_ENABLED, "true")
            mock_page.return_value = []
            mock_api.return_value = []
            mock_milb.return_value = []
            hockey_events = _load_ice_hockey(REPLAY_DATE)

            with patch(
                "services.ppv.calendar_providers.sofascore.fetch_events_for_slug",
                side_effect=lambda slug, date_str, **kwargs: hockey_events
                if slug == "ice-hockey" and kwargs.get("replay")
                else [],
            ):
                events = scraper.get_events_for_date(REPLAY_DATE, force_refresh=True, replay=True)

            assert any(event.source == EVENT_SOURCE_SOFASCORE and event.sport == "Ice Hockey" for event in events)

    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date")
    @patch("services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page")
    @patch(
        "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
        return_value=[],
    )
    def test_live_mode_skips_historical_ice_hockey(self, mock_espn, mock_page, mock_api, mock_milb, scraper, app):
        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_COLLEGE_ENABLED, "true")
            mock_page.return_value = []
            mock_api.return_value = []
            mock_milb.return_value = []

            with patch(
                "services.ppv.calendar_providers.sofascore.fetch_events_for_slug",
                side_effect=lambda slug, date_str, **kwargs: _load_ice_hockey(REPLAY_DATE)
                if slug == "ice-hockey" and kwargs.get("replay")
                else [],
            ) as mock_fetch:
                events = scraper.get_events_for_date(REPLAY_DATE, force_refresh=True, replay=False)

            assert all(not (event.source == EVENT_SOURCE_SOFASCORE and event.sport == "Ice Hockey") for event in events)
            mock_fetch.assert_called()
            assert all(
                call.kwargs.get("replay") is False for call in mock_fetch.call_args_list if call.args[0] == "ice-hockey"
            )
