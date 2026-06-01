"""Tests for PPV enrichment matching validation."""

from unittest.mock import MagicMock, patch

import pytest

from services.ppv.enrichment import PPVCalendarEnrichmentService


class TestEnrichmentCompetitorValidation:
    @pytest.fixture
    def service(self, app):
        with app.app_context():
            yield PPVCalendarEnrichmentService(app)

    def test_rejects_league_only_match_when_competitors_known(self, service):
        channel = MagicMock()
        channel.name = "US (WNBA 43) | Los Angeles Sparks at Golden State Valkyries (2026-06-16 02:00:00)"
        channel.category = None

        extraction = {
            "competitors": ("Los Angeles Sparks", "Golden State Valkyries"),
            "date": None,
        }

        wrong_event = MagicMock()
        wrong_event.event_name = "Dallas Wings vs Las Vegas Aces"
        wrong_event.home_team = "Dallas Wings"
        wrong_event.away_team = "Las Vegas Aces"
        wrong_event.event_id = "999"
        wrong_event.league_name = "WNBA"

        calendar_events = [wrong_event]

        match_result = MagicMock()
        match_result.event = wrong_event
        match_result.confidence = 0.7
        match_result.match_type = "league_plus_word"

        with patch.object(service.reverse_matcher, "load_events_for_date_range"):
            with patch.object(service.reverse_matcher, "find_matches", return_value=[match_result]):
                result = service._match_channel_to_calendar(
                    channel,
                    extraction,
                    calendar_events=calendar_events,
                    date_str="2026-06-16",
                )

        assert not result.matched
        assert result.match_method == "competitor_mismatch"

    def test_accepts_mlb_mascot_match_with_context(self, service):
        from services.thesportsdb_calendar_scraper import CalendarEvent

        channel = MagicMock()
        channel.name = "MLB 10 | Royals x Rangers start:2026-05-31 19:35:00 stop:2026-06-01 02:48:20"
        channel.category = MagicMock()
        channel.category.category_name = "US| MLB PPV"

        extraction = {
            "competitors": ("Royals", "Rangers"),
            "date": None,
        }

        calendar_event = CalendarEvent(
            event_id="2387740",
            event_name="Texas Rangers vs Kansas City Royals",
            league_name="MLB",
            time_utc="18:35",
            date="2026-05-31",
            home_team="Texas Rangers",
            away_team="Kansas City Royals",
        )

        match_result = MagicMock()
        match_result.event = calendar_event
        match_result.confidence = 0.70
        match_result.match_type = "word_overlap"

        with patch.object(service.reverse_matcher, "load_events_for_date_range"):
            with patch.object(service.reverse_matcher, "find_matches", return_value=[match_result]):
                result = service._match_channel_to_calendar(
                    channel,
                    extraction,
                    calendar_events=[calendar_event],
                    date_str="2026-05-31",
                )

        assert result.matched is True
        assert result.calendar_event == calendar_event
