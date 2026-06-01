"""Canonical HTTP tests for /api/sync/epg and /api/sync/epg/status.

Also covers scheduler status exposure and EPG sync progress migrations.
"""

import importlib.util
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import app as app_module
from models import EpgSource, db


class TestEpgSyncApi:
    @patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_sources")
    def test_post_sync_epg_uses_orchestrator(self, mock_sync, app, client):
        with app.app_context():
            source = EpgSource(
                name="API Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            mock_sync.return_value = {
                "success": True,
                "sources_synced": 1,
                "total_sources": 1,
                "results": [{"source_id": source.id, "success": True}],
            }

            response = client.post("/api/sync/epg")
            assert response.status_code == 200
            data = response.get_json()
            assert data["sources_synced"] == 1
            mock_sync.assert_called_once()
            call_args = mock_sync.call_args
            assert len(call_args[0][0]) == 1
            assert call_args[1]["parallel"] is True

    def test_post_sync_epg_skips_in_progress_source(self, app, client):
        with app.app_context():
            from datetime import datetime, timezone

            source = EpgSource(
                name="Busy API Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                sync_in_progress=True,
                sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(source)
            db.session.commit()

            with patch("services.epg_sync_orchestrator.EpgSyncService.sync_source") as mock_sync:
                response = client.post("/api/sync/epg")
                assert response.status_code == 200
                data = response.get_json()
                assert data["sources_skipped"] == 1
                assert data["sources_synced"] == 0
                mock_sync.assert_not_called()

    @patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_sources")
    def test_post_sync_epg_only_enabled_sources(self, mock_sync, app, client):
        """Bulk sync includes only enabled sources (2 enabled, 1 disabled)."""
        with app.app_context():
            source1 = EpgSource(
                name="Test EPG 1",
                source_type="xmltv_url",
                url="http://test.com/epg1.xml",
                enabled=True,
            )
            source2 = EpgSource(
                name="Test EPG 2",
                source_type="xmltv_url",
                url="http://test.com/epg2.xml",
                enabled=True,
            )
            source3 = EpgSource(
                name="Test EPG 3 (disabled)",
                source_type="xmltv_url",
                url="http://test.com/epg3.xml",
                enabled=False,
            )
            db.session.add_all([source1, source2, source3])
            db.session.commit()

            mock_sync.return_value = {
                "success": True,
                "sources_synced": 2,
                "total_sources": 2,
                "results": [
                    {"source_id": source1.id, "success": True},
                    {"source_id": source2.id, "success": True},
                ],
            }

            response = client.post("/api/sync/epg")
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert data["sources_synced"] == 2
            assert data["total_sources"] == 2
            assert len(data["results"]) == 2
            mock_sync.assert_called_once()
            called_sources = mock_sync.call_args[0][0]
            assert len(called_sources) == 2
            assert all(s.enabled for s in called_sources)
            assert mock_sync.call_args[1]["parallel"] is True

    @patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_sources")
    def test_post_sync_epg_partial_failure(self, mock_sync, app, client):
        """Partial failure returns success false with per-source counts."""
        with app.app_context():
            source1 = EpgSource(
                name="Test EPG Success",
                source_type="xmltv_url",
                url="http://test.com/epg1.xml",
                enabled=True,
            )
            source2 = EpgSource(
                name="Test EPG Fail",
                source_type="xmltv_url",
                url="http://test.com/epg2.xml",
                enabled=True,
            )
            db.session.add_all([source1, source2])
            db.session.commit()

            mock_sync.return_value = {
                "success": False,
                "sources_synced": 1,
                "total_sources": 2,
                "results": [
                    {"source_id": source1.id, "success": True},
                    {"source_id": source2.id, "success": False, "message": "Failed"},
                ],
            }

            response = client.post("/api/sync/epg")
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is False
            assert data["sources_synced"] == 1
            assert data["total_sources"] == 2
            assert mock_sync.call_args[1]["parallel"] is True

    def test_get_epg_sync_status(self, app, client):
        with app.app_context():
            source = EpgSource(
                name="Status Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                sync_phase="programs",
                sync_in_progress=True,
                sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                last_sync=datetime.now(timezone.utc).replace(tzinfo=None),
                sync_progress='{"programmes_parsed": 1000}',
            )
            db.session.add(source)
            db.session.commit()

            response = client.get("/api/sync/epg/status")
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "interval_hours" in data
            assert len(data["sources"]) == 1
            row = data["sources"][0]
            assert row["source_name"] == "Status Source"
            assert row["sync_phase"] == "programs"
            assert row["sync_in_progress"] is True
            assert row["progress"]["programmes_parsed"] == 1000
            assert "due" in row
            assert row["sync_started_at"].endswith("Z")
            assert row["last_sync"].endswith("Z")

    def test_scheduler_status_includes_epg_sources(self, app, client):
        with app.app_context():
            source = EpgSource(
                name="Sched Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                last_sync=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        with patch("routes.api._scheduler", app_module.sync_scheduler):
            response = client.get("/api/scheduler/status")
            assert response.status_code == 200
            data = response.get_json()
            assert "epg_sources" in data
            assert any(s["source_id"] == source_id for s in data["epg_sources"])


class TestEpgSyncMigration:
    def test_migration_adds_progress_columns(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE epg_sources (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1
            )
            """
        )
        conn.commit()
        conn.close()

        spec = importlib.util.spec_from_file_location(
            "mig_epg_progress",
            "migrations/2026_05_27_add_epg_source_sync_progress.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        ok, msg = mod.migrate(str(db_path))
        assert ok is True

        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(epg_sources)")}
        conn.close()

        assert "sync_in_progress" in cols
        assert "sync_phase" in cols
        assert "sync_progress" in cols
        assert "sync_started_at" in cols

    def test_migration_idempotent(self, tmp_path):
        import importlib.util
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE epg_sources (id INTEGER PRIMARY KEY, name TEXT, source_type TEXT)")
        conn.execute("ALTER TABLE epg_sources ADD COLUMN sync_in_progress BOOLEAN DEFAULT 0")
        conn.execute("ALTER TABLE epg_sources ADD COLUMN sync_phase VARCHAR(50)")
        conn.execute("ALTER TABLE epg_sources ADD COLUMN sync_progress TEXT")
        conn.execute("ALTER TABLE epg_sources ADD COLUMN sync_started_at DATETIME")
        conn.commit()
        conn.close()

        spec = importlib.util.spec_from_file_location(
            "mig_epg_progress",
            "migrations/2026_05_27_add_epg_source_sync_progress.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        ok, msg = mod.migrate(str(db_path))
        assert ok is True
        assert "already exist" in msg
