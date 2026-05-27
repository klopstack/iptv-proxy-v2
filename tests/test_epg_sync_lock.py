"""Tests for EPG source sync lock acquire, skip, and stale recovery."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import EpgSource, db
from services.epg_sync_orchestrator import EpgSyncOrchestrator, recover_stale_epg_sync_locks, try_acquire_epg_sync_lock


@pytest.fixture
def xmltv_source(db):
    source = EpgSource(
        name="Lock Source",
        source_type="xmltv_url",
        url="http://example.com/guide.xml",
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


class TestEpgSyncLockAcquire:
    def test_acquire_and_second_claim_fails(self, app, xmltv_source):
        with app.app_context():
            sid = xmltv_source.id
            assert try_acquire_epg_sync_lock(sid) is True
            assert try_acquire_epg_sync_lock(sid) is False

            source = db.session.get(EpgSource, sid)
            assert source.sync_in_progress is True
            assert source.sync_started_at is not None

    def test_force_acquire_when_already_locked(self, app, xmltv_source):
        with app.app_context():
            sid = xmltv_source.id
            assert try_acquire_epg_sync_lock(sid) is True
            assert try_acquire_epg_sync_lock(sid, force=True) is True

    def test_concurrent_acquire_only_one_succeeds(self, app, xmltv_source):
        with app.app_context():
            sid = xmltv_source.id
            barrier = threading.Barrier(2)
            outcomes: list[bool] = []

            def claim():
                with app.app_context():
                    barrier.wait()
                    outcomes.append(try_acquire_epg_sync_lock(sid))

            t1 = threading.Thread(target=claim)
            t2 = threading.Thread(target=claim)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            assert sum(outcomes) == 1

    def test_recover_stale_epg_sync_locks(self, app, xmltv_source):
        with app.app_context():
            old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
            source = db.session.get(EpgSource, xmltv_source.id)
            source.sync_in_progress = True
            source.sync_started_at = old
            db.session.commit()

            recovered = recover_stale_epg_sync_locks(max_age_hours=12)
            assert recovered == 1

            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_in_progress is False
            assert refreshed.sync_started_at is None


class TestOrchestratorSkipsInProgress:
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_skip_does_not_clear_lock_when_db_in_progress(self, mock_sync, app, xmltv_source):
        """Stale ORM sync_in_progress=False must not clear DB lock on skip."""
        with app.app_context():
            sid = xmltv_source.id
            assert try_acquire_epg_sync_lock(sid) is True
            # Detached row with stale sync_in_progress=False; DB still holds the lock.
            stale = EpgSource(
                id=sid,
                name="Lock Source",
                source_type="xmltv_url",
                url="http://example.com/guide.xml",
                enabled=True,
                sync_in_progress=False,
            )

            result = EpgSyncOrchestrator(app).sync_sources([stale], parallel=False)

            assert result["sources_skipped"] == 1
            mock_sync.assert_not_called()
            refreshed = db.session.get(EpgSource, sid)
            assert refreshed.sync_in_progress is True

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_sync_sources_skips_in_progress(self, mock_sync, app, xmltv_source):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            source.sync_in_progress = True
            source.sync_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            result = EpgSyncOrchestrator(app).sync_sources([source], parallel=False)

            assert result["sources_skipped"] == 1
            assert result["sources_synced"] == 0
            mock_sync.assert_not_called()
            assert result["results"][0]["skipped"] is True
            assert result["results"][0]["success"] is True

            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_in_progress is True
            assert refreshed.sync_phase != "skipped"

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_sync_sources_one_in_progress_one_syncs(self, mock_sync, app, db):
        with app.app_context():
            busy = EpgSource(
                name="Busy",
                source_type="xmltv_url",
                url="http://example.com/busy.xml",
                enabled=True,
                sync_in_progress=True,
                sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            free = EpgSource(
                name="Free",
                source_type="xmltv_url",
                url="http://example.com/free.xml",
                enabled=True,
            )
            db.session.add_all([busy, free])
            db.session.commit()

            mock_sync.return_value = (True, "ok", {})

            result = EpgSyncOrchestrator(app).sync_sources([busy, free], parallel=False)

            assert result["sources_skipped"] == 1
            assert result["sources_synced"] == 1
            assert mock_sync.call_count == 1
