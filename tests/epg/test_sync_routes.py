"""Tests for EPG source sync endpoints."""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


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
