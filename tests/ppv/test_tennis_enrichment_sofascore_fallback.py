"""Tennis PPV enrichment via SofaScore when ESPN calendar is empty (TODO 126)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, Event, EventChannelLink
from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED
from services.ppv.enrichment import PPVCalendarEnrichmentService
from services.tennis.sofascore_calendar import clear_sofascore_tennis_calendar_cache

FIXTURES = Path(__file__).parent / "fixtures" / "sofascore"
SOFASCORE_FIXTURE = FIXTURES / "scheduled_events_20260603.json"
CALENDAR_DATE = "2026-06-03"
TENNIS_CHANNEL_NAME = "Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM"


@pytest.fixture
def enrichment_fixed_now(monkeypatch):
    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return now
            return now.replace(tzinfo=None)

    import services.ppv.calendar_providers.sofascore.client as sofascore_client_mod
    import services.ppv.enrichability as enrichability_mod
    import services.ppv.extraction.extractor as extractor_mod
    import services.ppv.persistence as persistence_mod
    import services.reverse_event_matcher.match_filter as match_filter_mod

    monkeypatch.setattr(sofascore_client_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(enrichability_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(extractor_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(persistence_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(match_filter_mod, "datetime", FixedDateTime)
    return now


@pytest.fixture
def tennis_channel_id(app, db):
    with app.app_context():
        account = Account(name="Tennis SofaScore E2E", server="test.local", enabled=True)
        db.session.add(account)
        db.session.flush()
        category = Category(
            account_id=account.id,
            category_id="tennis-ppv",
            category_name="US| TENNIS PPV",
            is_ppv=True,
        )
        db.session.add(category)
        db.session.flush()
        channel = Channel(
            account_id=account.id,
            stream_id="tennis-ss-1",
            name=TENNIS_CHANNEL_NAME,
            category_id=category.id,
            is_ppv=True,
            ppv_enrichment_status="queued",
        )
        db.session.add(channel)
        db.session.commit()
        yield channel.id


class TestTennisEnrichmentSofascoreFallback:
    def test_matches_via_sofascore_when_espn_empty(
        self,
        app,
        db,
        tennis_channel_id,
        enrichment_fixed_now,
    ):
        clear_sofascore_tennis_calendar_cache()
        payload = json.loads(SOFASCORE_FIXTURE.read_text(encoding="utf-8"))

        with app.app_context():
            Settings.set(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "true")
            channel = db.session.get(Channel, tennis_channel_id)
            service = PPVCalendarEnrichmentService(app)
            service.calendar_scraper._cache.clear()

            with (
                patch(
                    "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_calendar_page",
                    return_value=[],
                ),
                patch(
                    "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_api_events_for_date",
                    return_value=[],
                ),
                patch(
                    "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_milb_events_for_date",
                    return_value=[],
                ),
                patch(
                    "services.thesportsdb_calendar_scraper.TheSportsDBCalendarScraper._fetch_espn_tennis_events_for_date",
                    return_value=[],
                ),
                patch(
                    "services.ppv.calendar_providers.sofascore.client.fetch_scheduled_events_http",
                    return_value=payload,
                ),
                patch("services.ppv.cleanup.sync_ppv_epg_after_enrichment", return_value={}),
            ):
                stats = service.enrich_channels([channel], fetch_details=False)

            db.session.refresh(channel)
            event = Event.query.filter_by(source=Event.SOURCE_SOFASCORE).first()
            link = EventChannelLink.query.filter_by(channel_id=channel.id).first()

            assert stats["matched"] == 1, stats
            assert event is not None
            assert {event.home_team_name, event.away_team_name} == {"Anna Kalinskaya", "Maja Chwalinska"}
            assert link is not None
            assert channel.ppv_enrichment_status == "matched"
