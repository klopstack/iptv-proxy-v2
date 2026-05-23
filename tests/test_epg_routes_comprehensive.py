"""
Comprehensive tests for EPG routes and helper functions - Part 2.
This file focuses on the most critical testable routes and helper functions.
"""
import json
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from routes.epg.sources import _sync_sd_channels_to_epg

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_channel(app, test_account, test_category):
    """Create a test channel"""
    with app.app_context():
        channel = Channel(
            account_id=test_account,
            stream_id="ch1",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=test_category,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()
        yield channel.id


@pytest.fixture
def test_epg_source(app, test_account):
    """Create a provider-type EPG source"""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="provider",
            account_id=test_account,
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def test_epg_channel(app, test_epg_source):
    """Create a test EPG channel"""
    with app.app_context():
        epg_channel = EpgChannel(
            source_id=test_epg_source,
            channel_id="epg_ch1",
            display_name="Test EPG Channel",
        )
        db.session.add(epg_channel)
        db.session.commit()
        yield epg_channel.id


@pytest.fixture
def test_epg_mapping(app, test_channel, test_epg_channel):
    """Create a test EPG mapping"""
    with app.app_context():
        mapping = ChannelEpgMapping(
            channel_id=test_channel,
            epg_channel_id=test_epg_channel,
            mapping_type="automatic",
            confidence=0.95,
        )
        db.session.add(mapping)
        db.session.commit()
        yield mapping.id


# ============================================================================
# Tests for EPG Sources CRUD
# ============================================================================


class TestEpgSourcesBasic:
    """Basic tests for EPG source management"""

    def test_get_epg_sources_empty(self, app, client):
        """Test getting EPG sources when none exist"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        assert response.json == []

    def test_get_epg_sources_with_data(self, app, client, test_epg_source):
        """Test getting EPG sources with data"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["id"] == test_epg_source

    def test_create_epg_source_missing_name(self, app, client):
        """Test creating EPG source without name"""
        response = client.post(
            "/api/epg/sources",
            json={"source_type": "provider"},
        )
        assert response.status_code == 400
        assert "Name is required" in response.json["error"]

    def test_create_epg_source_missing_type(self, app, client):
        """Test creating EPG source without type"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test Source"},
        )
        assert response.status_code == 400

    def test_create_epg_source_invalid_type(self, app, client):
        """Test creating EPG source with invalid type"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "invalid"},
        )
        assert response.status_code == 400

    def test_create_epg_source_xmltv_url(self, app, client):
        """Test creating an XMLTV URL source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "XMLTV URL",
                "source_type": "xmltv_url",
                "url": "http://example.com/epg.xml",
            },
        )
        assert response.status_code == 201

    def test_update_epg_source_not_found(self, app, client):
        """Test updating non-existent EPG source"""
        response = client.put(
            "/api/epg/sources/99999",
            json={"name": "Updated"},
        )
        assert response.status_code == 404

    def test_update_epg_source_success(self, app, client, test_epg_source):
        """Test successfully updating an EPG source"""
        response = client.put(
            f"/api/epg/sources/{test_epg_source}",
            json={"name": "Updated Name", "priority": 200},
        )
        assert response.status_code == 200

    def test_delete_epg_source_not_found(self, app, client):
        """Test deleting non-existent EPG source"""
        response = client.delete("/api/epg/sources/99999")
        assert response.status_code == 404

    def test_delete_epg_source_success(self, app, client, test_epg_source):
        """Test successfully deleting an EPG source"""
        response = client.delete(f"/api/epg/sources/{test_epg_source}")
        assert response.status_code == 200


# ============================================================================
# Tests for EPG Channels
# ============================================================================


class TestEpgChannelsBasic:
    """Basic tests for EPG channels"""

    def test_get_epg_channels_empty(self, app, client):
        """Test getting EPG channels when none exist"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        assert response.json["total"] == 0

    def test_get_epg_channels_with_data(self, app, client, test_epg_channel):
        """Test getting EPG channels with data"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_epg_channels_search(self, app, client, test_epg_channel):
        """Test searching EPG channels"""
        response = client.get("/api/epg/channels?search=Test")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_epg_channels_no_search_results(self, app, client, test_epg_channel):
        """Test search with no results"""
        response = client.get("/api/epg/channels?search=NonExistent")
        assert response.status_code == 200
        assert response.json["total"] == 0


# ============================================================================
# Tests for EPG Mappings
# ============================================================================


class TestEpgMappingsBasic:
    """Basic tests for EPG mappings"""

    def test_create_epg_mapping_missing_channel_id(self, app, client):
        """Test creating mapping without channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"epg_channel_id": 1},
        )
        assert response.status_code == 400

    def test_create_epg_mapping_missing_epg_channel_id(self, app, client):
        """Test creating mapping without epg_channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 1},
        )
        assert response.status_code == 400

    def test_create_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successfully creating an EPG mapping"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
        )
        assert response.status_code == 201
        assert "mapping_id" in response.json

    def test_create_epg_mapping_duplicate(self, app, client, test_epg_mapping):
        """Test creating duplicate mapping"""
        with app.app_context():
            mapping = db.session.get(ChannelEpgMapping, test_epg_mapping)
            channel_id = mapping.channel_id
            epg_channel_id = mapping.epg_channel_id

        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": channel_id, "epg_channel_id": epg_channel_id},
        )
        assert response.status_code == 409

    def test_delete_epg_mapping_not_found(self, app, client):
        """Test deleting non-existent mapping"""
        response = client.delete("/api/epg/mappings/99999")
        assert response.status_code == 404

    def test_delete_epg_mapping_success(self, app, client, test_epg_mapping):
        """Test successfully deleting a mapping"""
        response = client.delete(f"/api/epg/mappings/{test_epg_mapping}")
        assert response.status_code == 200

    def test_bulk_delete_mappings_invalid(self, app, client):
        """Test bulk delete with invalid params"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": 1},  # Missing category_id
        )
        assert response.status_code == 400


# ============================================================================
# Tests for Helper Functions - _sync_sd_channels_to_epg
# ============================================================================


class TestSyncSdChannelsHelper:
    """Tests for the _sync_sd_channels_to_epg helper function"""

    def test_sync_empty_channels(self, app, test_epg_source):
        """Test syncing empty channel list"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)
            stats = _sync_sd_channels_to_epg(source, [])

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 0
            assert stats["channels_removed"] == 0

    def test_sync_new_channels(self, app, test_epg_source):
        """Test syncing new channels"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN",
                    "logo": {"url": "http://example.com/logo.png"},
                },
                {
                    "stationID": "67890",
                    "callsign": "HBO",
                    "name": "HBO",
                    "logo": None,
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            # Verify channels were created
            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()
            assert len(epg_channels) == 2

    def test_sync_update_existing(self, app, test_epg_source):
        """Test updating existing channels"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            # Create existing channel
            existing = EpgChannel(
                source_id=test_epg_source,
                channel_id="I12345.json.schedulesdirect.org",
                display_name="Old Name",
            )
            db.session.add(existing)
            db.session.commit()

            # Sync with updated data
            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN HD",
                    "logo": {"url": "http://new-logo.com/logo.png"},
                }
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 1

            # Verify update
            epg_ch = EpgChannel.query.filter_by(source_id=test_epg_source).first()
            assert epg_ch.display_name == "ESPN"

    def test_sync_missing_optional_fields(self, app, test_epg_source):
        """Test handling channels with missing optional fields"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            # Channel with minimal fields
            channels = [
                {
                    "stationID": "12345",
                    "logo": None,
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)
            assert stats["channels_added"] == 1

            # Verify channel was created with fallback name
            epg_ch = EpgChannel.query.filter_by(source_id=test_epg_source).first()
            assert epg_ch.display_name is not None

    def test_sync_display_names_json(self, app, test_epg_source):
        """Test that display_names are properly stored as JSON"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN East",
                },
            ]

            _sync_sd_channels_to_epg(source, channels)

            epg_ch = EpgChannel.query.filter_by(source_id=test_epg_source).first()
            assert epg_ch.display_names_json is not None

            # Verify it's valid JSON
            display_names = json.loads(epg_ch.display_names_json)
            assert isinstance(display_names, list)


# ============================================================================
# Tests for SD Authentication
# ============================================================================


class TestSchedulesDirectAuth:
    """Tests for Schedules Direct authentication"""

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_missing_username(self, mock_validate, app, client):
        """Test SD credentials check without username"""
        response = client.post(
            "/api/epg/sd/test",
            json={"password": "pass"},
        )
        assert response.status_code == 400

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_missing_password(self, mock_validate, app, client):
        """Test SD credentials check without password"""
        response = client.post(
            "/api/epg/sd/test",
            json={"username": "user"},
        )
        assert response.status_code == 400

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_success(self, mock_validate, app, client):
        """Test successful SD credentials validation"""
        mock_validate.return_value = {"success": True, "subscription_expired": False}

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "test", "password": "pass"},
        )
        assert response.status_code == 200

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_failure(self, mock_validate, app, client):
        """Test failed SD credentials validation"""
        mock_validate.return_value = {"success": False, "error": "Invalid credentials"}

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "wrong", "password": "wrong"},
        )
        assert response.status_code == 401


# ============================================================================
# Coverage Tests
# ============================================================================


class TestEpgCoverage:
    """Tests for EPG coverage statistics"""

    @patch("routes.epg.sources.EpgService.get_epg_coverage_stats")
    def test_get_epg_coverage(self, mock_stats, app, client):
        """Test getting EPG coverage"""
        mock_stats.return_value = {
            "total_channels": 100,
            "channels_with_epg": 75,
            "coverage_percent": 75.0,
        }

        response = client.get("/api/epg/coverage")
        assert response.status_code == 200

    def test_get_category_coverage_invalid_account(self, app, client):
        """Test getting coverage for invalid account"""
        response = client.get("/api/epg/coverage/categories/99999")
        assert response.status_code == 404
