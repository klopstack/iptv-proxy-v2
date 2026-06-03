"""Tests for PPV enrichment orchestrator."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import or_

from models import Account, Channel, Settings, db
from services.ppv.constants import (
    ENRICHMENT_BACKLOG_BATCH_SIZE,
    ENRICHMENT_BATCH_SIZE,
    PPV_ENRICHMENT_BACKLOG_THRESHOLD,
    PPV_ENRICHMENT_MAX_SCAN_MULTIPLIER,
)
from services.ppv.orchestrator import PPVEnrichmentOrchestrator


class TestOrchestratorSettings:
    def test_is_enabled_default_true(self, app):
        with app.app_context():
            assert PPVEnrichmentOrchestrator.is_enabled() is True

    def test_is_enabled_respects_setting(self, app):
        with app.app_context():
            Settings.set("ppv_enrichment_enabled", "false")
            assert PPVEnrichmentOrchestrator.is_enabled() is False
            Settings.set("ppv_enrichment_enabled", "true")

    def test_enrich_pending_skips_when_disabled(self, app):
        with app.app_context():
            Settings.set("ppv_enrichment_enabled", "false")
            orch = PPVEnrichmentOrchestrator(app)
            result = orch.enrich_pending_channels()
            assert result.get("skipped") is True
            Settings.set("ppv_enrichment_enabled", "true")


class TestQueueStats:
    def test_get_queue_stats_counts_pending(self, app):
        with app.app_context():
            account = Account(name="Orch", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            hot = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)

            db.session.add_all(
                [
                    Channel(
                        account_id=account.id,
                        stream_id="q1",
                        name="UFC 301: A vs B",
                        is_ppv=True,
                        ppv_enrichment_status="queued",
                        last_seen=hot,
                    ),
                    Channel(
                        account_id=account.id,
                        stream_id="q2",
                        name="PPV 1",
                        is_ppv=True,
                        ppv_enrichment_status=None,
                        last_seen=old,
                    ),
                    Channel(
                        account_id=account.id,
                        stream_id="m1",
                        name="UFC 302: C vs D",
                        is_ppv=True,
                        ppv_enrichment_status="matched",
                        last_seen=hot,
                    ),
                ]
            )
            db.session.commit()

            stats = PPVEnrichmentOrchestrator.get_queue_stats()
            assert stats["queued_count"] == 2
            assert stats["hot_queued_count"] == 1


class TestSelectEnrichableBatch:
    def test_skips_placeholders_and_selects_real_events(self, app):
        with app.app_context():
            account = Account(name="Batch", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            recent = datetime.now(timezone.utc).replace(tzinfo=None)
            channels = [
                Channel(
                    account_id=account.id,
                    stream_id="s1",
                    name="PPV 1",
                    is_ppv=True,
                    ppv_enrichment_status="queued",
                    last_seen=recent,
                ),
                Channel(
                    account_id=account.id,
                    stream_id="s2",
                    name="NBA: Lakers vs Celtics | 2026-06-15 19:00",
                    is_ppv=True,
                    ppv_enrichment_status="queued",
                    last_seen=recent,
                ),
            ]
            db.session.add_all(channels)
            db.session.commit()

            pending = or_(
                Channel.ppv_enrichment_status.is_(None),
                Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
            )
            selected, skipped = PPVEnrichmentOrchestrator._select_enrichable_batch(
                account.id, batch_size=5, pending_status_filter=pending
            )
            assert len(selected) == 1
            assert selected[0].stream_id == "s2"
            assert skipped >= 1
            assert channels[0].ppv_enrichment_status == "skipped"

    def test_respects_max_scan_multiplier(self, app):
        with app.app_context():
            account = Account(name="ScanCap", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            recent = datetime.now(timezone.utc).replace(tzinfo=None)
            for i in range(30):
                db.session.add(
                    Channel(
                        account_id=account.id,
                        stream_id=f"cap-{i}",
                        name=f"PPV {i}",
                        is_ppv=True,
                        ppv_enrichment_status="queued",
                        last_seen=recent,
                    )
                )
            db.session.commit()

            batch_size = 2
            pending = or_(
                Channel.ppv_enrichment_status.is_(None),
                Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
            )
            selected, _skipped = PPVEnrichmentOrchestrator._select_enrichable_batch(
                account.id, batch_size=batch_size, pending_status_filter=pending
            )
            assert len(selected) == 0
            max_scan = batch_size * PPV_ENRICHMENT_MAX_SCAN_MULTIPLIER
            scanned = Channel.query.filter_by(account_id=account.id, ppv_enrichment_status="skipped").count()
            assert scanned <= max_scan

    def test_skip_marks_deferred_until_after_cursor_consumed(self, app):
        """Regression: 'database is locked' from autoflush during yield_per loop.

        Previously, marking channels skipped and committing mid-loop expired
        other in-session ORM objects.  The next channel.name access triggered
        an autoflush (write) that raced with concurrent writers (e.g. the
        channel health scan) and raised sqlite3.OperationalError: database is
        locked.

        The fix defers all writes (no_autoflush + post-loop commits) until
        after the yield_per cursor is fully consumed.  Verify that all channels
        are correctly marked skipped and persisted to the DB, and that no
        unexpected dirty state is left in the session.
        """
        with app.app_context():
            account = Account(name="DeferredWrites", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            recent = datetime.now(timezone.utc).replace(tzinfo=None)
            for i in range(12):
                db.session.add(
                    Channel(
                        account_id=account.id,
                        stream_id=f"dw-{i}",
                        name=f"PPV {i}",  # placeholder names → all classified as skip
                        is_ppv=True,
                        ppv_enrichment_status="queued",
                        last_seen=recent,
                    )
                )
            db.session.commit()

            pending = or_(
                Channel.ppv_enrichment_status.is_(None),
                Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
            )
            selected, skipped = PPVEnrichmentOrchestrator._select_enrichable_batch(
                account.id, batch_size=5, pending_status_filter=pending
            )

            assert selected == []
            assert skipped == 12
            # No dirty objects left — all writes were committed.
            assert not db.session.dirty

            # Expire all in-memory state and re-query to confirm persistence.
            db.session.expire_all()
            persisted = Channel.query.filter_by(account_id=account.id, ppv_enrichment_status="skipped").count()
            assert persisted == 12


class TestAdaptiveBatchSize:
    def test_backlog_threshold_selects_larger_batch(self, app):
        with app.app_context():
            account = Account(name="BatchSize", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            orch = PPVEnrichmentOrchestrator(app)
            captured_batch = []

            def capture_batch(account_id, batch_size, pending_filter):
                captured_batch.append(batch_size)
                return [], 0

            with patch.object(orch, "is_enabled", return_value=True), patch.object(
                orch,
                "get_queue_stats",
                return_value={"queued_count": PPV_ENRICHMENT_BACKLOG_THRESHOLD + 50},
            ), patch.object(orch, "_select_enrichable_batch", side_effect=capture_batch), patch.object(
                orch, "_get_enrichment_service"
            ):
                orch.enrich_pending_channels()

            assert captured_batch == [ENRICHMENT_BACKLOG_BATCH_SIZE]

    def test_normal_queue_uses_default_batch(self, app):
        with app.app_context():
            account = Account(name="BatchNorm", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            orch = PPVEnrichmentOrchestrator(app)
            captured_batch = []

            def capture_batch(account_id, batch_size, pending_filter):
                captured_batch.append(batch_size)
                return [], 0

            with patch.object(orch, "is_enabled", return_value=True), patch.object(
                orch, "get_queue_stats", return_value={"queued_count": 10}
            ), patch.object(orch, "_select_enrichable_batch", side_effect=capture_batch), patch.object(
                orch, "_get_enrichment_service"
            ):
                orch.enrich_pending_channels()

            assert captured_batch == [ENRICHMENT_BATCH_SIZE]


class TestRunEnhancedFallback:
    def test_skips_when_disabled(self, app):
        with app.app_context():
            Settings.set("ppv_enrichment_enabled", "false")
            orch = PPVEnrichmentOrchestrator(app)
            assert orch.run_enhanced_fallback().get("skipped") is True
            Settings.set("ppv_enrichment_enabled", "true")
