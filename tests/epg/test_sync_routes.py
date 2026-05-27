"""Tests for EPG source sync endpoints."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from services.epg_sync_progress import PHASE_COMPLETE, PHASE_FETCHING


class TestEpgSourceSync:
    """Tests for EPG source sync endpoints"""

    def test_sync_source_not_found(self, app, client):
        """Test syncing non-existent source"""
        response = client.post("/api/epg/sources/999/sync")
        assert response.status_code == 404

    def test_sync_provider_source_no_account(self, app, client):
        """Test syncing provider source without account"""
        with app.app_context():
            source = EpgSource(
                name="Provider Source",
                source_type="provider",
                account_id=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "account" in response.json["error"].lower()

    def test_sync_xmltv_url_no_url(self, app, client):
        """Test syncing XMLTV URL source without URL"""
        with app.app_context():
            source = EpgSource(
                name="XMLTV Source",
                source_type="xmltv_url",
                url=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "url" in response.json["error"].lower()

    @patch("services.iptv_service.IPTVService.get_xmltv")
    @patch("services.epg.parsing.sync_epg_source")
    def test_sync_provider_source_success(self, mock_sync, mock_get_xmltv, app, client, test_epg_source, test_account):
        """Test successful provider source sync"""
        mock_get_xmltv.return_value = b"<tv></tv>"
        mock_sync.return_value = {"channels_added": 10, "channels_updated": 5}

        response = client.post(f"/api/epg/sources/{test_epg_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("requests.get")
    @patch("services.epg.parsing.sync_epg_source")
    def test_sync_xmltv_url_success(self, mock_sync, mock_requests, app, client):
        """Test successful XMLTV URL source sync"""
        # Create XMLTV URL source
        with app.app_context():
            source = EpgSource(
                name="XMLTV Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        # Mock the requests response
        mock_response = MagicMock()
        mock_response.content = b"<tv></tv>"
        mock_requests.return_value = mock_response

        mock_sync.return_value = {"channels_added": 5, "channels_updated": 2}

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_sync_schedules_direct_missing_credentials(self, app, client):
        """Test syncing Schedules Direct source without credentials returns 400"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "credentials" in response.json["error"].lower()

    def test_sync_schedules_direct_missing_lineup(self, app, client):
        """Test syncing Schedules Direct source without lineup returns 400"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="testuser",
                sd_password="testpass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "lineup" in response.json["error"].lower()

    @patch("services.epg_sync_service.SchedulesDirectClient")
    @patch("services.epg.sources.sync_sd_channels_to_epg")
    def test_sync_schedules_direct_success(self, mock_sync, mock_sd_client_class, app, client):
        """Test successful Schedules Direct sync"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="testuser",
                sd_password="testpass",
                sd_lineup="USA-NY12345-X",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        # Mock the SD client
        mock_client = MagicMock()
        mock_sd_client_class.return_value = mock_client
        mock_client.get_lineup_channels.return_value = [
            {
                "stationID": "12345",
                "callsign": "ESPN",
                "name": "ESPN HD",
                "logo": {"url": "http://example.com/espn.png"},
            },
            {
                "stationID": "67890",
                "callsign": "CNN",
                "name": "CNN",
                "logo": None,
            },
        ]
        mock_sync.return_value = {"channels_added": 2, "channels_updated": 0}

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["stats"]["channels_added"] == 2

    @patch("services.epg_sync_service.SchedulesDirectClient")
    def test_sync_schedules_direct_error(self, mock_sd_client_class, app, client):
        """Test Schedules Direct sync with API error"""
        from services.schedules_direct import SchedulesDirectError

        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="testuser",
                sd_password="testpass",
                sd_lineup="USA-NY12345-X",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        # Mock the SD client to raise an error
        mock_client = MagicMock()
        mock_sd_client_class.return_value = mock_client
        mock_client.authenticate.side_effect = SchedulesDirectError("Invalid credentials")

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "Invalid credentials" in response.json["error"]

    @patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
    def test_per_source_sync_sets_progress(self, mock_sync, app, client):
        """Per-source sync drives sync_phase via orchestrator progress callback."""
        with app.app_context():
            source = EpgSource(
                name="Progress Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

            def sync_with_progress(source, progress=None):
                if progress:
                    progress(PHASE_FETCHING, message="test")
                return True, "ok", {"channels_added": 1}

            mock_sync.side_effect = sync_with_progress

            response = client.post(f"/api/epg/sources/{source_id}/sync")
            assert response.status_code == 200
            assert response.json["success"] is True

            db.session.expire_all()
            refreshed = db.session.get(EpgSource, source_id)
            assert refreshed.sync_phase == PHASE_COMPLETE
            assert refreshed.sync_in_progress is False
            progress = json.loads(refreshed.sync_progress)
            assert progress.get("message") == "ok"

    def test_sync_returns_409_when_already_in_progress(self, app, client):
        with app.app_context():
            source = EpgSource(
                name="Busy Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                sync_in_progress=True,
                sync_started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        with patch("services.epg_sync_orchestrator.EpgSyncService.sync_source") as mock_sync:
            response = client.post(f"/api/epg/sources/{source_id}/sync")
            assert response.status_code == 409
            assert "in progress" in response.json["error"].lower()
            mock_sync.assert_not_called()

    def test_sync_unknown_source_type(self, app, client):
        """Test syncing source with unknown type returns 400"""
        with app.app_context():
            source = EpgSource(
                name="Unknown Source",
                source_type="unknown",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "unknown" in response.json["error"].lower()
