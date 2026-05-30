"""Tests for parallel EPG sync orchestration (unit tests).

Patches EpgSyncService.sync_source throughout. See test_epg_sync_integration.py
for orchestrator + real service integration with mocked HTTP/disk.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import EpgSource, db
from services.epg_sync_orchestrator import EpgSyncOrchestrator, source_needs_sync
from services.epg_sync_progress import PHASE_COMPLETE, PHASE_FETCHING


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


class TestSourceNeedsSync:
    def test_never_synced_is_due(self, app, xmltv_source):
        with app.app_context():
            assert source_needs_sync(xmltv_source, 12) is True

    def test_in_progress_not_due(self, app, xmltv_source):
        with app.app_context():
            xmltv_source.sync_in_progress = True
            db.session.commit()
            assert source_needs_sync(xmltv_source, 12) is False

    def test_recent_sync_not_due(self, app, xmltv_source):
        with app.app_context():
            xmltv_source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            assert source_needs_sync(xmltv_source, 12) is False

    def test_stale_sync_is_due(self, app, xmltv_source):
        with app.app_context():
            xmltv_source.last_sync = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(tzinfo=None)
            db.session.commit()
            assert source_needs_sync(xmltv_source, 24) is True


class TestEpgSyncOrchestratorEmpty:
    def test_sync_sources_empty(self, app):
        with app.app_context():
            result = EpgSyncOrchestrator(app).sync_sources([])
            assert result["message"] == "No sources to sync"
            assert result["results"] == []
            assert result["sources_skipped"] == 0

    def test_sync_due_sources_none_due(self, app, xmltv_source):
        with app.app_context():
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            result = EpgSyncOrchestrator(app).sync_due_sources(12)
            assert result["message"] == "No EPG sources due for sync"
            assert result["results"] == []


class TestEpgSyncOrchestratorSync:
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_sources_parallel_success(self, mock_update, mock_sync, app, xmltv_source, second_source):
        with app.app_context():
            mock_sync.return_value = (True, "ok", {"channels_added": 1, "programs_added": 10})

            result = EpgSyncOrchestrator(app).sync_sources(
                [xmltv_source, second_source],
                parallel=True,
                max_workers=2,
            )

            assert result["total_sources"] == 2
            assert result["sources_synced"] == 2
            assert result["success"] is True
            assert mock_sync.call_count == 2

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_sources_sequential(self, mock_update, mock_sync, app, xmltv_source, second_source):
        with app.app_context():
            mock_sync.return_value = (True, "ok", {})

            result = EpgSyncOrchestrator(app).sync_sources(
                [xmltv_source, second_source],
                parallel=False,
            )

            assert result["total_sources"] == 2
            assert mock_sync.call_count == 2

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_sources_partial_failure(self, mock_update, mock_sync, app, xmltv_source, second_source):
        with app.app_context():

            def side_effect(source, progress=None):
                if source.id == xmltv_source.id:
                    return True, "ok", {"channels_added": 1}
                return False, "failed", {}

            mock_sync.side_effect = side_effect

            result = EpgSyncOrchestrator(app).sync_sources([xmltv_source, second_source], parallel=False)

            assert result["total_sources"] == 2
            assert result["sources_synced"] == 1
            assert result["success"] is False

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_source_invokes_progress_callback(self, mock_update, mock_sync, app, xmltv_source):
        with app.app_context():
            captured = []

            def sync_with_progress(source, progress=None):
                if progress:
                    progress(PHASE_FETCHING, message="downloading")
                    progress(PHASE_COMPLETE, message="done", programmes_parsed=99)
                return True, "done", {"programs_added": 3}

            mock_sync.side_effect = sync_with_progress

            EpgSyncOrchestrator(app).sync_sources([xmltv_source], parallel=False)

            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_phase == PHASE_COMPLETE
            progress = json.loads(refreshed.sync_progress)
            assert progress.get("programmes_parsed") == 99

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_missing_source_id(self, mock_update, mock_sync, app):
        with app.app_context():
            result = EpgSyncOrchestrator(app).sync_sources([], parallel=False)
            assert result["results"] == []

            # Call thread helper directly for missing row
            out = EpgSyncOrchestrator(app)._sync_source_in_thread(99999)
            assert out["success"] is False
            assert "not found" in out["message"].lower()

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_due_sources_only_enabled_and_due(self, mock_update, mock_sync, app, xmltv_source, second_source):
        with app.app_context():
            due = db.session.get(EpgSource, xmltv_source.id)
            due.last_sync = None
            fresh = db.session.get(EpgSource, second_source.id)
            fresh.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            disabled = EpgSource(
                name="Disabled",
                source_type="xmltv_url",
                url="http://example.com/x.xml",
                enabled=False,
            )
            db.session.add(disabled)
            db.session.commit()

            mock_sync.return_value = (True, "ok", {})

            result = EpgSyncOrchestrator(app).sync_due_sources(12, parallel=False)

            assert result["total_sources"] == 1
            assert result["sources_synced"] == 1
            mock_sync.assert_called_once()

    @patch("services.epg_sync_orchestrator.ThreadPoolExecutor")
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_parallel_uses_max_workers_cap(
        self, mock_update, mock_sync, mock_executor_cls, app, xmltv_source, second_source
    ):
        with app.app_context():
            mock_sync.return_value = (True, "ok", {})
            executor = MagicMock()
            executor.__enter__.return_value = executor
            future = MagicMock()
            future.result.return_value = {"source_id": xmltv_source.id, "success": True}
            executor.submit.return_value = future
            mock_executor_cls.return_value = executor

            import services.epg_sync_orchestrator as orch_mod

            with patch.object(orch_mod, "as_completed", return_value=[future]):
                EpgSyncOrchestrator(app).sync_sources(
                    [xmltv_source, second_source],
                    parallel=True,
                    max_workers=2,
                )

            mock_executor_cls.assert_called_once_with(max_workers=2)

    @patch("services.epg_sync_orchestrator.ThreadPoolExecutor")
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_parallel_future_exception_captured(
        self, mock_update, mock_sync, mock_executor_cls, app, xmltv_source, second_source
    ):
        with app.app_context():
            mock_sync.return_value = (True, "ok", {})

            executor = MagicMock()
            executor.__enter__.return_value = executor
            submitted = {}

            def make_future(source_id):
                future = MagicMock()

                def boom():
                    raise RuntimeError("worker exploded")

                future.result = boom
                submitted[future] = source_id
                return future

            executor.submit.side_effect = lambda fn, sid: make_future(sid)
            mock_executor_cls.return_value = executor

            import services.epg_sync_orchestrator as orch_mod

            with patch.object(orch_mod, "as_completed", lambda futures: list(futures.keys())):
                result = EpgSyncOrchestrator(app).sync_sources(
                    [xmltv_source, second_source],
                    parallel=True,
                    max_workers=2,
                )

            assert result["total_sources"] == 2
            assert all(r["success"] is False for r in result["results"])
            assert all("worker exploded" in r["message"] for r in result["results"])


class TestSyncSourceById:
    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    @patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status")
    def test_sync_source_by_id_delegates_to_sync_sources(self, mock_update, mock_sync, app, xmltv_source):
        with app.app_context():
            mock_sync.return_value = (True, "done", {"channels_added": 2})

            result = EpgSyncOrchestrator(app).sync_source_by_id(xmltv_source.id)

            assert result["success"] is True
            assert result["source_id"] == xmltv_source.id
            mock_sync.assert_called_once()

    def test_sync_source_by_id_not_found(self, app):
        with app.app_context():
            result = EpgSyncOrchestrator(app).sync_source_by_id(99999)
            assert result["not_found"] is True
            assert result["success"] is False


class TestEpgSyncOrchestratorStatus:
    def test_list_status_includes_all_sources(self, app, xmltv_source, second_source):
        with app.app_context():
            statuses = EpgSyncOrchestrator(app).list_status()
            ids = {s["source_id"] for s in statuses}
            assert xmltv_source.id in ids
            assert second_source.id in ids

    def test_queued_phase_persisted_before_sync(self, app, xmltv_source):
        with app.app_context():
            with patch("services.epg_sync_orchestrator.EpgSyncService.sync_source") as mock_sync:
                with patch("services.epg_sync_orchestrator.EpgSyncService.update_source_sync_status"):
                    mock_sync.return_value = (True, "ok", {})

                    EpgSyncOrchestrator(app)._sync_source_in_thread(xmltv_source.id)

            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_phase == PHASE_COMPLETE
