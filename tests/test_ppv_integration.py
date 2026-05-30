"""End-to-end PPV enrichment pipeline integration test."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Account, Category, Channel, Event, db
from services.ppv.detection import is_ppv_category
from services.ppv.persistence import create_or_update_event, link_channel_to_event
from services.ppv.visibility import PPVVisibilityService
from services.thesportsdb_calendar_scraper import CalendarEvent


@pytest.fixture
def ppv_account(app):
    with app.app_context():
        account = Account(name="PPV Test", server="test.local", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()
        cat = Category(
            account_id=account.id,
            category_id="1",
            category_name="US| ESPN+ PPV",
            is_ppv=True,
        )
        db.session.add(cat)
        db.session.commit()
        yield account
        db.session.delete(account)
        db.session.commit()


def test_ppv_category_detection_and_visibility(app, ppv_account):
    """PPV channel with linked active event is visible under hide_inactive."""
    with app.app_context():
        account = ppv_account
        cat = Category.query.filter_by(account_id=account.id).first()
        assert is_ppv_category(cat.category_name)

        channel = Channel(
            account_id=account.id,
            stream_id=9001,
            name="UFC 300: Jones vs Miocic",
            category_id=cat.id,
            is_ppv=True,
            is_active=True,
            ppv_enrichment_status="matched",
        )
        db.session.add(channel)
        db.session.commit()

        cal = CalendarEvent(
            event_id="evt-9001",
            event_name="UFC 300: Jones vs Miocic",
            league_name="UFC",
            time_utc="20:00:00",
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            home_team="Jones",
            away_team="Miocic",
        )
        event = create_or_update_event(cal)
        assert event is not None
        event.scheduled_at = datetime.now(timezone.utc) + timedelta(hours=2)
        event.status = Event.STATUS_SCHEDULED
        db.session.flush()
        link_channel_to_event(channel, event, 0.9, "test")
        db.session.commit()

        vis = PPVVisibilityService(account)
        assert vis.should_show_channel(channel) is True

        xml = __import__("services.ppv.epg", fromlist=["PPVEpgService"]).PPVEpgService.generate_ppv_epg_xmltv(
            account_id=account.id
        )
        assert b"UFC 300" in xml or b"Jones" in xml


def test_ppv_orchestrator_respects_enabled_setting(app, ppv_account):
    with app.app_context():
        from models import Settings
        from services.ppv.orchestrator import PPVEnrichmentOrchestrator

        Settings.set("ppv_enrichment_enabled", "false")
        orch = PPVEnrichmentOrchestrator(app)
        assert orch.is_enabled() is False
        result = orch.enrich_pending_channels()
        assert result.get("skipped") is True
        Settings.set("ppv_enrichment_enabled", "true")
