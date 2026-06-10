"""Integration: doubles channel + ESPN calendar row passes enrichment validation (TODO 127)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.ppv.enrichment import PPVCalendarEnrichmentService
from services.ppv.extraction import PPVEventExtractor
from services.thesportsdb_calendar_scraper import CalendarEvent

FIXTURES = Path(__file__).parent / "fixtures" / "tennis_doubles_channels.json"


@pytest.fixture(scope="module")
def fixture_data():
    with FIXTURES.open(encoding="utf-8") as f:
        return json.load(f)


class TestDoublesEnrichmentIntegration:
    @pytest.fixture
    def service(self, app):
        with app.app_context():
            yield PPVCalendarEnrichmentService(app)

    def test_doubles_channel_passes_competitor_validation(self, service, fixture_data):
        channel_row = fixture_data["doubles"][0]
        cal_row = fixture_data["calendar_events"][0]
        channel = MagicMock()
        channel.name = channel_row["channel"]
        channel.category = None

        extraction = PPVEventExtractor().extract_all(channel.name)
        calendar_event = CalendarEvent(
            event_id=cal_row["id"],
            event_name=cal_row.get("event_name", ""),
            league_name=cal_row["league_name"],
            time_utc="12:00",
            date="2026-06-03",
            home_team=cal_row["home_team"],
            away_team=cal_row["away_team"],
            sport=cal_row.get("sport", "Tennis"),
        )

        match_result = MagicMock()
        match_result.event = calendar_event
        match_result.confidence = 0.75
        match_result.match_type = "both_teams"

        with patch.object(service.reverse_matcher, "load_events_for_date_range"):
            with patch.object(service.reverse_matcher, "find_matches", return_value=[match_result]):
                result = service._match_channel_to_calendar(
                    channel,
                    extraction,
                    calendar_events=[calendar_event],
                    date_str="2026-06-03",
                )

        assert result.matched is True
        assert result.match_method != "competitor_mismatch"
        assert result.calendar_event == calendar_event
