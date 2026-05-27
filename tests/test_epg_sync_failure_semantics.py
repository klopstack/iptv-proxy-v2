"""
Contract tests for EPG sync failure semantics (TODOs 40–41).

These encode production requirements: failed syncs must not advance per-source
last_sync or global last_epg_sync metadata, and due-source logic must remain
correct after failures.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from models import EpgSource, SyncMetadata, db
from services.epg_sync_orchestrator import (
    SYNC_KEY_LAST_EPG_SYNC,
    EpgSyncOrchestrator,
    source_needs_sync,
)
from services.epg_sync_progress import PHASE_ERROR
from services.epg_sync_service import EpgSyncService


@pytest.fixture
def xmltv_source(db):
    source = EpgSource(
        name="XMLTV Source",
        source_type="xmltv_url",
        url="http://example.com/guide.xml",
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


@pytest.fixture
def second_source(db):
    source = EpgSource(
        name="Second Source",
        source_type="xmltv_url",
        url="http://example.com/guide2.xml",
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


@pytest.fixture(autouse=True)
def _clear_global_epg_sync_metadata(app):
    with app.app_context():
        SyncMetadata.delete(SYNC_KEY_LAST_EPG_SYNC)
    yield


class TestUpdateSourceSyncStatusOnFailure:
    @patch("services.epg_sync_service.db.session.commit")
    def test_failure_does_not_update_last_sync(self, mock_commit):
        source = Mock()
        old_sync = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(tzinfo=None)
        source.last_sync = old_sync

        EpgSyncService.update_source_sync_status(source, False, "Sync failed", {})

        assert source.last_sync == old_sync
        mock_commit.assert_called_once()

    @patch("services.epg_sync_service.db.session.commit")
    def test_failure_sets_error_status_and_message(self, mock_commit):
        source = Mock()

        EpgSyncService.update_source_sync_status(source, False, "network timeout", {})

        assert source.last_sync_status == "error"
        assert source.last_sync_message == "network timeout"
        mock_commit.assert_called_once()

    @patch("services.epg_sync_service.db.session.commit")
    def test_failure_clears_sync_in_progress(self, mock_commit):
        source = Mock()
        source.sync_in_progress = True

        EpgSyncService.update_source_sync_status(source, False, "failed", {})

        assert source.sync_in_progress is False
        mock_commit.assert_called_once()

    @patch("services.epg_sync_service.db.session.commit")
    def test_success_updates_last_sync(self, mock_commit):
        source = Mock()
        before = datetime.now(timezone.utc).replace(tzinfo=None)

        EpgSyncService.update_source_sync_status(source, True, "OK", {})

        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert source.last_sync_status == "success"
        assert before <= source.last_sync <= after
        mock_commit.assert_called_once()

    def test_failure_preserves_last_sync_in_database(self, app, db):
        with app.app_context():
            source = EpgSource(
                name="DB Source",
                source_type="xmltv_url",
                url="http://example.com/guide.xml",
                enabled=True,
            )
            db.session.add(source)
            old_sync = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(tzinfo=None)
            source.last_sync = old_sync
            source.last_sync_status = "success"
            source.sync_in_progress = True
            db.session.commit()

            EpgSyncService.update_source_sync_status(source, False, "Sync failed", {})

            refreshed = db.session.get(EpgSource, source.id)
            assert refreshed.last_sync == old_sync
            assert refreshed.last_sync_status == "error"
            assert refreshed.last_sync_message == "Sync failed"
            assert refreshed.sync_in_progress is False


class TestOrchestratorGlobalMetadata:
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_all_failed_does_not_set_last_epg_sync_metadata(
        self, mock_sync, app, xmltv_source, second_source
    ):
        with app.app_context():
            previous = "2020-01-01T00:00:00+00:00"
            SyncMetadata.set(SYNC_KEY_LAST_EPG_SYNC, previous)
            mock_sync.return_value = (False, "failed", {})

            result = EpgSyncOrchestrator(app).sync_sources(
                [xmltv_source, second_source],
                parallel=False,
            )

            assert result["sources_synced"] == 0
            assert SyncMetadata.get(SYNC_KEY_LAST_EPG_SYNC) == previous

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_partial_success_updates_metadata_when_policy_allows(
        self, mock_sync, app, xmltv_source, second_source
    ):
        with app.app_context():
            previous = "2020-01-01T00:00:00+00:00"
            SyncMetadata.set(SYNC_KEY_LAST_EPG_SYNC, previous)

            def side_effect(source, progress=None):
                if source.id == xmltv_source.id:
                    return True, "ok", {}
                return False, "failed", {}

            mock_sync.side_effect = side_effect

            EpgSyncOrchestrator(app).sync_sources([xmltv_source, second_source], parallel=False)

            assert SyncMetadata.get(SYNC_KEY_LAST_EPG_SYNC) != previous

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_all_success_updates_last_epg_sync_metadata(
        self, mock_sync, app, xmltv_source, second_source
    ):
        with app.app_context():
            mock_sync.return_value = (True, "ok", {})

            EpgSyncOrchestrator(app).sync_sources([xmltv_source, second_source], parallel=False)

            assert SyncMetadata.get(SYNC_KEY_LAST_EPG_SYNC) is not None


class TestOrchestratorPreservesLastSyncOnFailure:
    @patch.object(EpgSyncService, "sync_source")
    def test_failed_sync_preserves_last_sync_and_marks_error(self, mock_sync, app, xmltv_source):
        with app.app_context():
            old_sync = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(tzinfo=None)
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = old_sync
            source.last_sync_status = "success"
            source.sync_in_progress = True
            db.session.commit()

            mock_sync.return_value = (False, "fetch failed", {})

            EpgSyncOrchestrator(app).sync_sources([source], parallel=False)

            db.session.expire_all()
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.last_sync == old_sync
            assert refreshed.last_sync_status == "error"
            assert refreshed.last_sync_message == "fetch failed"
            assert refreshed.sync_in_progress is False

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_exception_clears_sync_in_progress_without_advancing_last_sync(
        self, mock_sync, app, xmltv_source
    ):
        with app.app_context():
            old_sync = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = old_sync
            source.last_sync_status = "success"
            db.session.commit()

            mock_sync.side_effect = RuntimeError("disk full")

            result = EpgSyncOrchestrator(app).sync_sources([xmltv_source], parallel=False)

            assert result["results"][0]["success"] is False
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_phase == PHASE_ERROR
            assert refreshed.sync_in_progress is False
            assert refreshed.last_sync_status == "error"
            assert refreshed.last_sync == old_sync


class TestSourceNeedsSyncAfterFailure:
    def test_failed_source_still_due_when_never_synced(self, app, xmltv_source):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            assert source.last_sync is None
            assert source_needs_sync(source, 12) is True

            source.last_sync_status = "error"
            source.last_sync_message = "fetch failed"
            db.session.commit()

            assert source_needs_sync(source, 12) is True

    def test_failed_source_not_due_if_interval_not_elapsed_and_last_sync_unchanged(
        self, app, xmltv_source
    ):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            source.last_sync_status = "success"
            db.session.commit()

            source.last_sync_status = "error"
            source.last_sync_message = "fetch failed"
            db.session.commit()

            assert source_needs_sync(source, 12) is False

    def test_failed_source_due_when_interval_passed_and_last_sync_unchanged(
        self, app, xmltv_source
    ):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(
                tzinfo=None
            )
            source.last_sync_status = "success"
            db.session.commit()

            source.last_sync_status = "error"
            source.last_sync_message = "fetch failed"
            db.session.commit()

            assert source_needs_sync(source, 24) is True

    @patch.object(EpgSyncService, "sync_source")
    def test_orchestrator_failure_leaves_source_due(self, mock_sync, app, xmltv_source):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(
                tzinfo=None
            )
            source.last_sync_status = "success"
            db.session.commit()

            mock_sync.return_value = (False, "fetch failed", {})

            EpgSyncOrchestrator(app).sync_sources([source], parallel=False)

            db.session.expire_all()
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert source_needs_sync(refreshed, 12) is True
