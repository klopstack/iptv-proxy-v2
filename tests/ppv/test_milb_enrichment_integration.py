"""
MiLB PPV end-to-end integration test (TODO 62).

Verifies the full pipeline with recorded MLB Stats fixtures (no live network):

    MiLB channel name → calendar scrape → reverse match → Event persisted → correct source

Expected IPTV channel name format::

    US (MiLB NNN) | <Away Team> @ <Home Team> (YYYY-MM-DD HH:MM:SS)

Example aligned with ``tests/fixtures/mlb_stats/schedule_aaa_2025-05-31.json``::

    US (MiLB 009) | Columbus Clippers @ Rochester Red Wings (2025-05-31 18:45:10)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, Event, EventChannelLink, db
from services.mlb_stats_calendar import clear_milb_calendar_cache
from services.ppv.enrichment import PPVCalendarEnrichmentService

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "mlb_stats"

# Matches gamePk 780676 in schedule_aaa_2025-05-31.json (22:45 UTC → 18:45 America/New_York).
MILB_CHANNEL_NAME = "US (MiLB 009) | Columbus Clippers @ Rochester Red Wings (2025-05-31 18:45:10)"
MILB_GAME_PK = "780676"
CALENDAR_DATE = "2025-05-31"


@pytest.fixture
def milb_schedule_games():
    data = json.loads((FIXTURES / "schedule_aaa_2025-05-31.json").read_text(encoding="utf-8"))
    games = data["dates"][0]["games"]
    for game in games:
        game["_level"] = "Triple-A"
        game["_sport_id"] = 11
    return games


@pytest.fixture
def enrichment_fixed_now(monkeypatch):
    """Pin persistence and matcher age checks to the day after the fixture schedule date."""
    now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return now
            return now.replace(tzinfo=None)

    import services.ppv.persistence as persistence_mod
    import services.reverse_event_matcher.match_filter as match_filter_mod

    monkeypatch.setattr(persistence_mod, "datetime", FixedDateTime)
    monkeypatch.setattr(match_filter_mod, "datetime", FixedDateTime)
    return now


@pytest.fixture
def milb_channel_id(app, db):
    with app.app_context():
        account = Account(name="MiLB E2E", server="test.local", enabled=True)
        db.session.add(account)
        db.session.flush()
        category = Category(
            account_id=account.id,
            category_id="milb-ppv",
            category_name="US| MILB PPV",
            is_ppv=True,
        )
        db.session.add(category)
        db.session.flush()
        channel = Channel(
            account_id=account.id,
            stream_id="milb-009",
            name=MILB_CHANNEL_NAME,
            category_id=category.id,
            is_ppv=True,
            ppv_enrichment_status="queued",
        )
        db.session.add(channel)
        db.session.commit()
        yield channel.id


class TestMilbEnrichmentIntegration:
    def test_milb_channel_to_event_e2e(
        self,
        app,
        db,
        milb_channel_id,
        milb_schedule_games,
        enrichment_fixed_now,
    ):
        clear_milb_calendar_cache()

        with app.app_context():
            channel = db.session.get(Channel, milb_channel_id)
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
                patch("services.mlb_stats_calendar._is_date_in_milb_window", return_value=True),
                patch("services.mlb_stats_calendar.get_mlb_stats_client") as mock_client,
                patch("services.ppv.cleanup.sync_ppv_epg_after_enrichment", return_value={}),
            ):
                mock_client.return_value.get_milb_schedule_for_date.return_value = milb_schedule_games
                stats = service.enrich_channels([channel], fetch_details=True)

            db.session.refresh(channel)
            event = Event.query.filter_by(
                external_id=MILB_GAME_PK,
                source=Event.SOURCE_MLB_STATS,
            ).first()
            link = EventChannelLink.query.filter_by(channel_id=channel.id).first()

            assert stats["matched"] == 1, stats
            assert stats["events_created"] == 1, stats
            assert stats["detail_queue_size"] == 0, "MiLB events must not queue TheSportsDB detail fetch"
            assert event is not None
            assert event.source == Event.SOURCE_MLB_STATS
            assert event.home_team_name == "Rochester Red Wings"
            assert event.away_team_name == "Columbus Clippers"
            assert event.external_id == MILB_GAME_PK
            assert link is not None
            assert link.event_id == event.id
            assert link.match_confidence >= 0.35
            assert channel.ppv_enrichment_status == "matched"
