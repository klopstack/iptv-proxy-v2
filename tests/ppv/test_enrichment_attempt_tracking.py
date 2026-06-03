"""Tests for PPV enrichment attempt tracking."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Channel, db
from services.ppv.enrichment import PPVCalendarEnrichmentService, _record_enrichment_attempt
from services.ppv.enrichment.types import EnrichmentResult
from services.ppv.orchestrator import PPVEnrichmentOrchestrator
from services.ppv.persistence import persist_match


class TestRecordEnrichmentAttempt:
    def test_increments_attempts_and_sets_timestamp(self, app):
        with app.app_context():
            account = Account(name="Attempt", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="a1",
                name="UFC 301: A vs B",
                is_ppv=True,
                ppv_enrichment_status="queued",
                ppv_enrichment_attempts=0,
            )
            db.session.add(channel)
            db.session.commit()

            before = datetime.now(timezone.utc).replace(tzinfo=None)
            _record_enrichment_attempt(channel)
            db.session.commit()
            after = datetime.now(timezone.utc).replace(tzinfo=None)

            db.session.refresh(channel)
            assert channel.ppv_enrichment_attempts == 1
            assert channel.ppv_enrichment_last_attempt is not None
            assert before <= channel.ppv_enrichment_last_attempt <= after

    def test_second_attempt_increments_to_two(self, app):
        with app.app_context():
            account = Account(name="Attempt2", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="a2",
                name="UFC 302: C vs D",
                is_ppv=True,
                ppv_enrichment_status="queued",
                ppv_enrichment_attempts=1,
                ppv_enrichment_last_attempt=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
            )
            db.session.add(channel)
            db.session.commit()

            _record_enrichment_attempt(channel)
            db.session.commit()
            db.session.refresh(channel)
            assert channel.ppv_enrichment_attempts == 2


class TestEnrichmentAttemptTracking:
    def test_no_match_records_attempt(self, app):
        with app.app_context():
            from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline

            account = Account(name="NoMatch", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="nm1",
                name="UFC 303: X vs Y",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()

            pipeline = CalendarMatchPipeline()
            near_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3)
            extraction = {
                "is_placeholder": False,
                "is_inactive": False,
                "competitors": ("X", "Y"),
                "date": near_date,
            }
            coordinator = MagicMock()
            coordinator._extract_all_channels.return_value = [(channel, extraction)]
            coordinator._group_by_date.return_value = {"2026-06-10": [(channel, extraction)]}
            no_match = EnrichmentResult(
                channel=channel,
                matched=False,
                match_method="no_match_found",
                extraction_result={},
            )

            with patch.object(pipeline, "match_channel_to_calendar", return_value=no_match), patch.object(
                pipeline.calendar_scraper, "get_events_for_date", return_value=[]
            ), patch.object(pipeline.reverse_matcher, "load_events_for_date_range"):
                pipeline.run([channel], coordinator=coordinator)

            db.session.refresh(channel)
            assert channel.ppv_enrichment_attempts == 1
            assert channel.ppv_enrichment_last_attempt is not None
            assert channel.ppv_enrichment_status == "no_match"

    def test_process_same_channel_twice_increments_attempts(self, app):
        with app.app_context():
            from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline

            account = Account(name="Twice", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="t1",
                name="UFC 304: M vs N",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()

            pipeline = CalendarMatchPipeline()
            near_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3)
            extraction = {
                "is_placeholder": False,
                "is_inactive": False,
                "competitors": ("M", "N"),
                "date": near_date,
            }
            coordinator = MagicMock()
            coordinator._extract_all_channels.return_value = [(channel, extraction)]
            coordinator._group_by_date.return_value = {"2026-06-10": [(channel, extraction)]}
            no_match = EnrichmentResult(
                channel=channel,
                matched=False,
                match_method="no_match_found",
                extraction_result={},
            )

            with patch.object(pipeline, "match_channel_to_calendar", return_value=no_match), patch.object(
                pipeline.calendar_scraper, "get_events_for_date", return_value=[]
            ), patch.object(pipeline.reverse_matcher, "load_events_for_date_range"):
                pipeline.run([channel], coordinator=coordinator)
                channel.ppv_enrichment_status = "queued"
                db.session.commit()
                pipeline.run([channel], coordinator=coordinator)

            db.session.refresh(channel)
            assert channel.ppv_enrichment_attempts == 2

    def test_skipped_channel_records_attempt(self, app):
        with app.app_context():
            account = Account(name="Skip", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="sk1",
                name="PPV 1",
                is_ppv=True,
                ppv_enrichment_status="queued",
                last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(channel)
            db.session.commit()

            orch = PPVEnrichmentOrchestrator(app)
            from sqlalchemy import or_

            pending = or_(
                Channel.ppv_enrichment_status.is_(None),
                Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
            )
            selected, skipped = PPVEnrichmentOrchestrator._select_enrichable_batch(
                account.id, batch_size=5, pending_status_filter=pending
            )

            assert selected == []
            assert skipped == 1
            db.session.expire_all()
            refreshed = db.session.get(Channel, channel.id)
            assert refreshed.ppv_enrichment_status == "skipped"
            assert refreshed.ppv_enrichment_attempts == 1
            assert refreshed.ppv_enrichment_last_attempt is not None

    def test_persist_match_records_attempt(self, app):
        with app.app_context():
            account = Account(name="Persist", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="pm1",
                name="UFC 305: P vs Q",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()

            cal_event = MagicMock()
            cal_event.event_id = "evt-1"
            cal_event.event_name = "UFC 305"
            cal_event.date = "2026-06-10"
            cal_event.time = "22:00:00"
            cal_event.home_team = "P"
            cal_event.away_team = "Q"
            cal_event.league = "UFC"
            cal_event.sport = "Fighting"
            cal_event.source = "thesportsdb"

            with patch("services.ppv.persistence.create_or_update_event") as mock_create, patch(
                "services.ppv.persistence.link_channel_to_event"
            ) as mock_link:
                mock_event = MagicMock()
                mock_event.id = 99
                mock_event.external_id = "evt-1"
                mock_create.return_value = (mock_event, True)
                mock_link.return_value = MagicMock()
                persist_match(channel, cal_event, 0.9, "calendar_high_confidence")
                db.session.commit()

            db.session.refresh(channel)
            assert channel.ppv_enrichment_attempts == 1
            assert channel.ppv_enrichment_last_attempt is not None
            assert channel.ppv_enrichment_status == "matched"

    def test_status_update_without_attempt_recorder_fails_when_patched(self, app):
        """Regression: enrichment must call _record_enrichment_attempt when setting status."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            account = Account(name="Spy", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="spy1",
                name="UFC 306: R vs S",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()

            from services.ppv.enrichment_post_hooks import (
                EnrichmentPostHooks,
                get_enrichment_post_hooks,
                set_enrichment_post_hooks,
            )

            original_hooks = get_enrichment_post_hooks()
            near_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3)
            try:
                set_enrichment_post_hooks(EnrichmentPostHooks.noop())
                with patch.object(service.match_pipeline, "match_channel_to_calendar") as mock_match, patch.object(
                    service.match_pipeline.calendar_scraper, "get_events_for_date", return_value=[]
                ), patch.object(service, "_extract_all_channels") as mock_extract, patch.object(
                    service, "_group_by_date"
                ) as mock_group, patch.object(service, "_update_stats"), patch(
                    "services.ppv.enrichment.sync_enrichment_status_from_links"
                ), patch(
                    "services.ppv.enrichment.match_pipeline._record_enrichment_attempt"
                ) as mock_record:
                    extraction = {
                        "is_placeholder": False,
                        "competitors": ("R", "S"),
                        "date": near_date,
                    }
                    mock_extract.return_value = [(channel, extraction)]
                    mock_group.return_value = {"2026-06-10": [(channel, extraction)]}
                    mock_match.return_value = EnrichmentResult(
                        channel=channel,
                        matched=False,
                        match_method="no_match_found",
                        extraction_result={},
                    )

                    service.enrich_channels([channel], fetch_details=False)
                    mock_record.assert_called()
            finally:
                set_enrichment_post_hooks(original_hooks)
