"""
Integration tests: EpgSyncOrchestrator + real EpgSyncService (mocked network/disk).

Unit tests in test_epg_sync_orchestrator.py patch sync_source; this module exercises
progress phases, DB state, and scheduler status through the real service stack.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from models import Account, EpgChannel, EpgSource, db
from services.epg_sync_orchestrator import EpgSyncOrchestrator, source_needs_sync
from services.epg_sync_progress import PHASE_COMPLETE, PHASE_ERROR
from services.scheduler import SyncScheduler


def _small_xmltv_bytes(channel_id: str = "integ.ch") -> bytes:
    base = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    start = base.strftime("%Y%m%d%H%M%S +0000")
    stop = (base + timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="{channel_id}">
    <display-name>Integration Channel</display-name>
  </channel>
  <programme start="{start}" stop="{stop}" channel="{channel_id}">
    <title>Integration Show</title>
  </programme>
</tv>
""".encode()


@pytest.fixture
def xmltv_source(db):
    source = EpgSource(
        name="Integration XMLTV",
        source_type="xmltv_url",
        url="http://example.com/guide.xml",
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


@pytest.fixture
def provider_source(db):
    account = Account(
        name="Provider Account",
        server="http://provider.example.com",
        username="user",
        password="pass",
    )
    db.session.add(account)
    db.session.flush()
    source = EpgSource(
        name="Integration Provider",
        source_type="provider",
        account_id=account.id,
        enabled=True,
    )
    db.session.add(source)
    db.session.commit()
    return source


def _mock_http_response(content: bytes) -> MagicMock:
    response = MagicMock()
    response.content = content
    response.raise_for_status = lambda: None
    return response


class TestOrchestratorXmltvIntegration:
    @patch("services.epg_sync_service.save_to_cache")
    @patch("requests.get")
    def test_orchestrator_xmltv_url_sets_progress_phases(
        self, mock_get, mock_cache, app, xmltv_source
    ):
        mock_get.return_value = _mock_http_response(_small_xmltv_bytes())
        mock_cache.return_value = True

        with app.app_context():
            result = EpgSyncOrchestrator(app).sync_sources([xmltv_source], parallel=False)

            assert result["sources_synced"] == 1
            db.session.expire_all()
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_phase == PHASE_COMPLETE
            assert refreshed.last_sync_status == "success"
            progress = json.loads(refreshed.sync_progress)
            assert progress.get("channels_added", 0) >= 0
            assert EpgChannel.query.filter_by(source_id=xmltv_source.id).count() == 1
            mock_get.assert_called_once()
            mock_cache.assert_called_once()

    @patch("services.epg_sync_service.save_to_cache")
    @patch("requests.get")
    def test_orchestrator_xmltv_fetch_error_sets_error_phase(
        self, mock_get, mock_cache, app, xmltv_source
    ):
        mock_get.side_effect = requests.RequestException("network down")

        with app.app_context():
            old_sync = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(tzinfo=None)
            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = old_sync
            db.session.commit()

            result = EpgSyncOrchestrator(app).sync_sources([source], parallel=False)

            assert result["sources_synced"] == 0
            db.session.expire_all()
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.sync_phase == PHASE_ERROR
            assert refreshed.last_sync == old_sync
            assert refreshed.sync_in_progress is False
            mock_cache.assert_not_called()


class TestOrchestratorProviderIntegration:
    @patch("services.epg_sync_service.save_to_cache")
    @patch("services.epg_sync_service.IPTVService")
    def test_orchestrator_provider_source_completes(
        self, mock_iptv_cls, mock_cache, app, provider_source
    ):
        mock_service = MagicMock()
        mock_service.get_xmltv.return_value = _small_xmltv_bytes("prov.ch")
        mock_iptv_cls.return_value = mock_service
        mock_cache.return_value = True

        with app.app_context():
            source = db.session.get(EpgSource, provider_source.id)
            result = EpgSyncOrchestrator(app).sync_sources([source], parallel=False)

            assert result["sources_synced"] == 1
            db.session.expire_all()
            refreshed = db.session.get(EpgSource, provider_source.id)
            assert refreshed.sync_phase == PHASE_COMPLETE
            assert refreshed.last_sync_status == "success"
            mock_service.get_xmltv.assert_called_once()


class TestOrchestratorListStatusAndDue:
    @patch("services.epg_sync_service.save_to_cache")
    @patch("requests.get")
    def test_list_status_after_success_source_not_due(
        self, mock_get, mock_cache, app, xmltv_source
    ):
        mock_get.return_value = _mock_http_response(_small_xmltv_bytes())
        mock_cache.return_value = True

        with app.app_context():
            orch = EpgSyncOrchestrator(app)
            orch.sync_sources([xmltv_source], parallel=False)

            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert source_needs_sync(refreshed, 12) is False

            snaps = orch.list_status()
            row = next(s for s in snaps if s["source_id"] == xmltv_source.id)
            assert row["sync_phase"] == PHASE_COMPLETE
            assert row["last_sync"] is not None

    @patch("requests.get")
    def test_source_still_due_after_failed_sync_never_synced(self, mock_get, app, xmltv_source):
        mock_get.side_effect = requests.RequestException("timeout")

        with app.app_context():
            EpgSyncOrchestrator(app).sync_sources([xmltv_source], parallel=False)
            refreshed = db.session.get(EpgSource, xmltv_source.id)
            assert refreshed.last_sync is None
            assert source_needs_sync(refreshed, 12) is True


class TestSchedulerEpgSourcesIntegration:
    @patch("services.epg_sync_service.save_to_cache")
    @patch("requests.get")
    def test_scheduler_get_status_epg_sources_shape(
        self, mock_get, mock_cache, app, xmltv_source
    ):
        mock_get.return_value = _mock_http_response(_small_xmltv_bytes())
        mock_cache.return_value = True

        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=6)
            status = scheduler.get_status()
            assert "epg_sources" in status
            assert isinstance(status["epg_sources"], list)
            assert len(status["epg_sources"]) == 1
            row = status["epg_sources"][0]
            assert row["source_id"] == xmltv_source.id
            assert row["due"] is True
            assert "sync_phase" in row
            assert "progress" in row

            EpgSyncOrchestrator(app).sync_sources([xmltv_source], parallel=False)

            status_after = scheduler.get_status()
            row_after = next(s for s in status_after["epg_sources"] if s["source_id"] == xmltv_source.id)
            assert row_after["sync_phase"] == PHASE_COMPLETE
            assert row_after["due"] is False

    def test_sync_due_sources_with_real_service_mocked_http(self, app, xmltv_source):
        with app.app_context():
            with patch("requests.get") as mock_get:
                with patch("services.epg_sync_service.save_to_cache", return_value=True):
                    mock_get.return_value = _mock_http_response(_small_xmltv_bytes())
                    result = EpgSyncOrchestrator(app).sync_due_sources(12, parallel=False)

            assert result["sources_synced"] == 1

            source = db.session.get(EpgSource, xmltv_source.id)
            source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            with patch(
                "services.epg_sync_orchestrator.EpgSyncService.sync_source"
            ) as mock_sync:
                result2 = EpgSyncOrchestrator(app).sync_due_sources(12, parallel=False)
                assert result2["message"] == "No EPG sources due for sync"
                mock_sync.assert_not_called()
