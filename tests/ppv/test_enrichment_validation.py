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

        extraction = {
            "competitors": ("Los Angeles Sparks", "Golden State Valkyries"),
            "date": None,
        }

        wrong_event = MagicMock()
        wrong_event.event_name = "Dallas Wings vs Las Vegas Aces"
        wrong_event.home_team = "Dallas Wings"
        wrong_event.away_team = "Las Vegas Aces"
        wrong_event.event_id = "999"

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
