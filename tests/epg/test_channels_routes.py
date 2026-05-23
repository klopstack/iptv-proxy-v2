"""Tests for EPG channel list endpoints and account EPG source creation."""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


class TestEpgChannels:
    """Tests for EPG channel endpoints"""

    def test_get_epg_channels_empty(self, app, client):
        """Test getting EPG channels when none exist"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 0

    def test_get_epg_channels(self, app, client, test_epg_channel):
        """Test getting EPG channels"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["channels"][0]["display_name"] == "Test EPG Channel"

    def test_get_epg_channels_with_source_filter(self, app, client, test_epg_source, test_epg_channel):
        """Test getting EPG channels filtered by source"""
        response = client.get(f"/api/epg/channels?source_id={test_epg_source}")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_get_epg_channels_with_search(self, app, client, test_epg_channel):
        """Test getting EPG channels with search"""
        response = client.get("/api/epg/channels?search=Test")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_get_epg_channels_search_no_match(self, app, client, test_epg_channel):
        """Test search with no matching channels"""
        response = client.get("/api/epg/channels?search=NonExistent")
        assert response.status_code == 200
        assert response.json["total"] == 0

    def test_get_epg_channels_filter_by_source(self, app, client, test_epg_source):
        """Test filtering EPG channels by source when multiple sources exist"""
        with app.app_context():
            source2 = EpgSource(
                name="Source 2",
                source_type="xmltv_url",
                url="http://example.com",
            )
            db.session.add(source2)
            db.session.flush()

            db.session.add_all(
                [
                    EpgChannel(source_id=test_epg_source, channel_id="ch1", display_name="Channel 1"),
                    EpgChannel(source_id=source2.id, channel_id="ch2", display_name="Channel 2"),
                ]
            )
            db.session.commit()

        response = client.get(f"/api/epg/channels?source_id={test_epg_source}")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_epg_channels_pagination(self, app, client, test_epg_source):
        """Test EPG channel pagination"""
        with app.app_context():
            # Create multiple channels
            for i in range(5):
                epg_channel = EpgChannel(
                    source_id=test_epg_source,
                    channel_id=f"ch_{i}",
                    display_name=f"Channel {i}",
                )
                db.session.add(epg_channel)
            db.session.commit()

        response = client.get("/api/epg/channels?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 5
        assert len(data["channels"]) == 2

class TestAccountEpgSource:
    """Tests for account EPG source endpoints"""

    def test_create_account_epg_source_not_found(self, app, client):
        """Test creating EPG source for non-existent account"""
        response = client.post("/api/accounts/999/epg-source")
        assert response.status_code == 404

    @patch("routes.epg.channels.create_provider_epg_source")
    def test_create_account_epg_source_success(self, mock_create, app, client, test_account):
        """Test successful account EPG source creation"""
        mock_source = MagicMock()
        mock_source.id = 1
        mock_create.return_value = mock_source

        response = client.post(f"/api/accounts/{test_account}/epg-source")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["source_id"] == 1

    @patch("routes.epg.channels.IPTVService")
    @patch("routes.epg.channels.sync_epg_source")
    @patch("routes.epg.channels.create_provider_epg_source")
    def test_create_account_epg_source_with_sync(
        self, mock_create, mock_sync, MockIPTVService, app, client, test_account
    ):
        """Test creating account EPG source with immediate sync"""
        # Create a mock source with a mock account that has proper attributes
        mock_account = MagicMock()
        mock_account.server = "example.com"
        mock_account.user_agent = "test"
        mock_account.get_primary_credential.return_value = None
        mock_account.username = "test"
        mock_account.password = "test"

        mock_source = MagicMock()
        mock_source.id = 1
        mock_source.account = mock_account
        mock_create.return_value = mock_source

        mock_service = MagicMock()
        mock_service.get_xmltv.return_value = b"<tv></tv>"
        MockIPTVService.return_value = mock_service

        mock_sync.return_value = {"channels_added": 10, "channels_updated": 5}

        response = client.post(f"/api/accounts/{test_account}/epg-source?sync=true")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert "synced" in response.json["message"].lower()
