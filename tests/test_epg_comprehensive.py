"""
Comprehensive tests for EPG routes and helper functions.

This test suite covers:
- EPG source management (CRUD operations)
- EPG source synchronization
- PPV channel visibility updates
- EPG channel management
- Channel-to-EPG mapping
- Schedules Direct integration
- XMLTV grabber integration
- Helper function decomposition and testing
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from routes.epg import _sync_sd_channels_to_epg

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_account(app):
    """Create a test account"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="test_user",
            password="test_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account.id


@pytest.fixture
def test_account_obj(app, test_account):
    """Get the Account object"""
    with app.app_context():
        yield db.session.get(Account, test_account)


@pytest.fixture
def test_category(app, test_account):
    """Create a test category"""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()
        yield category.id


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
def test_xmltv_url_source(app):
    """Create an XMLTV URL type EPG source"""
    with app.app_context():
        source = EpgSource(
            name="XMLTV URL Source",
            source_type="xmltv_url",
            url="http://example.com/epg.xml",
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def test_sd_source(app):
    """Create a Schedules Direct EPG source"""
    with app.app_context():
        source = EpgSource(
            name="Schedules Direct Source",
            source_type="schedules_direct",
            sd_username="test_user",
            sd_password="test_pass",
            sd_lineup="USA-NY12345-X",
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
# Tests for PPV Routes (no database dependencies)
# ============================================================================


class TestPPVVisibility:
    """Tests for PPV channel visibility endpoints"""

    @patch("services.epg_service.update_ppv_channel_visibility")
    def test_update_ppv_visibility_success(self, mock_update, app, client):
        """Test updating PPV channel visibility"""
        mock_update.return_value = {
            "events_detected": 5,
            "channels_shown": 3,
            "channels_hidden": 2,
            "ppv_channels_processed": 10,
        }

        response = client.post("/api/epg/ppv/update-visibility")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "5 active event" in data["message"]
        assert "3 channel(s) shown" in data["message"]

    @patch("services.epg_service.update_ppv_channel_visibility")
    def test_update_ppv_visibility_with_account(self, mock_update, app, client, test_account):
        """Test updating PPV visibility for specific account"""
        mock_update.return_value = {
            "events_detected": 2,
            "channels_shown": 1,
            "channels_hidden": 1,
            "ppv_channels_processed": 3,
        }

        response = client.post(f"/api/epg/ppv/update-visibility?account_id={test_account}")
        assert response.status_code == 200
        mock_update.assert_called_once_with(test_account)

    @patch("services.epg_service.get_ppv_epg_xmltv")
    def test_get_ppv_epg_xmltv(self, mock_get_ppv, app, client):
        """Test getting PPV EPG XMLTV data"""
        mock_xml = b"<?xml version='1.0'?><tv></tv>"
        mock_get_ppv.return_value = mock_xml

        response = client.get("/api/epg/ppv/xmltv")
        assert response.status_code == 200
        assert "application/xml" in response.content_type
        assert response.data == mock_xml

    @patch("services.epg_service.get_ppv_epg_xmltv")
    def test_get_ppv_epg_xmltv_with_params(self, mock_get_ppv, app, client, test_account):
        """Test getting PPV EPG with duration parameter"""
        mock_xml = b"<?xml version='1.0'?><tv></tv>"
        mock_get_ppv.return_value = mock_xml

        response = client.get(f"/api/epg/ppv/xmltv?account_id={test_account}&duration=12")
        assert response.status_code == 200
        mock_get_ppv.assert_called_once_with(test_account, duration_hours=12)


# ============================================================================
# Tests for EPG Sources
# ============================================================================


class TestEpgSourcesCRUD:
    """Tests for EPG source CRUD operations"""

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
        assert response.json[0]["name"] == "Test EPG Source"
        assert response.json[0]["source_type"] == "provider"

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
        assert "Source type is required" in response.json["error"]

    def test_create_epg_source_invalid_type(self, app, client):
        """Test creating EPG source with invalid type"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "invalid"},
        )
        assert response.status_code == 400
        assert "Invalid source type" in response.json["error"]

    def test_create_epg_source_provider_missing_account(self, app, client):
        """Test creating provider source without account"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "provider"},
        )
        assert response.status_code == 400
        assert "Account ID is required" in response.json["error"]

    def test_create_epg_source_provider_invalid_account(self, app, client):
        """Test creating provider source with invalid account"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "provider", "account_id": 99999},
        )
        assert response.status_code == 404

    def test_create_epg_source_provider_success(self, app, client, test_account):
        """Test successfully creating a provider EPG source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "New Provider Source",
                "source_type": "provider",
                "account_id": test_account,
                "priority": 50,
            },
        )
        assert response.status_code == 201
        assert "New Provider Source" in response.json.get("name", "")

    def test_create_epg_source_xmltv_url_success(self, app, client):
        """Test successfully creating an XMLTV URL source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "XMLTV URL",
                "source_type": "xmltv_url",
                "url": "http://example.com/epg.xml",
            },
        )
        assert response.status_code == 201

    def test_create_epg_source_xmltv_grabber_missing_name(self, app, client):
        """Test creating XMLTV grabber source without name"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "Grabber Source",
                "source_type": "xmltv_grabber",
            },
        )
        assert response.status_code == 400
        assert "XMLTV grabber name is required" in response.json["error"]

    def test_create_epg_source_xmltv_grabber_success(self, app, client):
        """Test successfully creating an XMLTV grabber source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "Grabber Source",
                "source_type": "xmltv_grabber",
                "xmltv_grabber": "tv_grab_zz_sdjson",
                "xmltv_days": 14,
                "xmltv_offset": 2,
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
        assert response.json["success"] is True

        # Verify update
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)
            assert source.name == "Updated Name"
            assert source.priority == 200

    def test_delete_epg_source_not_found(self, app, client):
        """Test deleting non-existent EPG source"""
        response = client.delete("/api/epg/sources/99999")
        assert response.status_code == 404

    def test_delete_epg_source_success(self, app, client, test_epg_source):
        """Test successfully deleting an EPG source"""
        response = client.delete(f"/api/epg/sources/{test_epg_source}")
        assert response.status_code == 200
        assert response.json["success"] is True

        # Verify deletion
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)
            assert source is None


# ============================================================================
# Tests for EPG Channels
# ============================================================================


class TestEpgChannels:
    """Tests for EPG channel endpoints"""

    def test_get_epg_channels_empty(self, app, client):
        """Test getting EPG channels when none exist"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        assert response.json["total"] == 0
        assert response.json["channels"] == []

    def test_get_epg_channels_with_data(self, app, client, test_epg_channel):
        """Test getting EPG channels with data"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        assert response.json["total"] == 1
        assert len(response.json["channels"]) == 1
        assert response.json["channels"][0]["id"] == test_epg_channel

    def test_get_epg_channels_with_search(self, app, client, test_epg_channel):
        """Test searching for EPG channels"""
        response = client.get("/api/epg/channels?search=Test")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_epg_channels_search_no_match(self, app, client, test_epg_channel):
        """Test searching with no matches"""
        response = client.get("/api/epg/channels?search=NonExistent")
        assert response.status_code == 200
        assert response.json["total"] == 0

    def test_get_epg_channels_with_pagination(self, app, client, test_epg_source):
        """Test EPG channels with pagination"""
        with app.app_context():
            # Create multiple channels
            for i in range(5):
                ch = EpgChannel(
                    source_id=test_epg_source,
                    channel_id=f"ch_{i}",
                    display_name=f"Channel {i}",
                )
                db.session.add(ch)
            db.session.commit()

        response = client.get("/api/epg/channels?limit=2&offset=0")
        assert response.status_code == 200
        assert response.json["total"] == 5
        assert len(response.json["channels"]) == 2

        # Get next page
        response = client.get("/api/epg/channels?limit=2&offset=2")
        assert response.status_code == 200
        assert len(response.json["channels"]) == 2

    def test_get_epg_channels_filter_by_source(self, app, client, test_epg_source):
        """Test filtering EPG channels by source"""
        with app.app_context():
            # Create another source
            source2 = EpgSource(
                name="Source 2",
                source_type="xmltv_url",
                url="http://example.com",
            )
            db.session.add(source2)
            db.session.flush()

            ch1 = EpgChannel(source_id=test_epg_source, channel_id="ch1", display_name="Channel 1")
            ch2 = EpgChannel(source_id=source2.id, channel_id="ch2", display_name="Channel 2")
            db.session.add_all([ch1, ch2])
            db.session.commit()

        response = client.get(f"/api/epg/channels?source_id={test_epg_source}")
        assert response.status_code == 200
        assert response.json["total"] == 1


# ============================================================================
# Tests for EPG Mappings
# ============================================================================


class TestEpgMappings:
    """Tests for EPG mapping endpoints"""

    def test_get_epg_mappings_unmapped_view(self, app, client, test_account):
        """Test getting unmapped channels"""
        with app.app_context():
            # Create a channel without mapping
            cat = Category.query.filter_by(account_id=test_account).first()
            if not cat:
                cat = Category(account_id=test_account, category_id="cat1", category_name="Cat")
                db.session.add(cat)
                db.session.flush()

            ch = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="Unmapped Channel",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(ch)
            db.session.commit()

        response = client.get(f"/api/epg/mappings?view_mode=unmapped&account_id={test_account}")
        assert response.status_code == 200
        assert response.json["view_mode"] == "unmapped"
        assert response.json["total"] >= 1

    def test_get_epg_mappings_mapped_view(self, app, client, test_epg_mapping):
        """Test getting mapped channels"""
        response = client.get("/api/epg/mappings?view_mode=mapped")
        assert response.status_code == 200
        assert response.json["view_mode"] == "mapped"
        assert response.json["total"] >= 1

    def test_get_epg_mappings_all_view(self, app, client, test_channel, test_account):
        """Test getting all channels with mapping info"""
        response = client.get(f"/api/epg/mappings?view_mode=all&account_id={test_account}")
        assert response.status_code == 200
        assert response.json["view_mode"] == "all"

    def test_create_epg_mapping_missing_channel_id(self, app, client):
        """Test creating mapping without channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"epg_channel_id": 1},
        )
        assert response.status_code == 400
        assert "channel_id is required" in response.json["error"]

    def test_create_epg_mapping_missing_epg_channel_id(self, app, client):
        """Test creating mapping without epg_channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 1},
        )
        assert response.status_code == 400
        assert "epg_channel_id is required" in response.json["error"]

    def test_create_epg_mapping_invalid_channel(self, app, client, test_epg_channel):
        """Test creating mapping with invalid channel"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 99999, "epg_channel_id": test_epg_channel},
        )
        assert response.status_code == 404

    def test_create_epg_mapping_invalid_epg_channel(self, app, client, test_channel):
        """Test creating mapping with invalid EPG channel"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": 99999},
        )
        assert response.status_code == 404

    def test_create_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successfully creating an EPG mapping"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
        )
        assert response.status_code == 201
        assert response.json["success"] is True
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
        assert "already exists" in response.json["error"]

    def test_create_epg_mapping_with_time_offset(self, app, client, test_channel, test_epg_channel):
        """Test creating mapping with time offset"""
        response = client.post(
            "/api/epg/mappings",
            json={
                "channel_id": test_channel,
                "epg_channel_id": test_epg_channel,
                "time_offset_hours": -5,
            },
        )
        assert response.status_code == 201
        with app.app_context():
            mapping = db.session.get(ChannelEpgMapping, response.json["mapping_id"])
            assert mapping.time_offset_hours == -5

    def test_delete_epg_mapping_not_found(self, app, client):
        """Test deleting non-existent mapping"""
        response = client.delete("/api/epg/mappings/99999")
        assert response.status_code == 404

    def test_delete_epg_mapping_success(self, app, client, test_epg_mapping):
        """Test successfully deleting a mapping"""
        response = client.delete(f"/api/epg/mappings/{test_epg_mapping}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_bulk_delete_epg_mappings_missing_account(self, app, client):
        """Test bulk delete without account_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"category_id": 1},
        )
        assert response.status_code == 400

    def test_bulk_delete_epg_mappings_missing_category(self, app, client, test_account):
        """Test bulk delete without category_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account},
        )
        assert response.status_code == 400

    def test_bulk_delete_epg_mappings_empty_category(self, app, client, test_account):
        """Test bulk delete with no channels in category"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": 99999},
        )
        assert response.status_code == 200
        assert response.json["deleted_count"] == 0

    def test_bulk_delete_epg_mappings_success(self, app, client, test_account, test_category, test_epg_mapping):
        """Test successfully bulk deleting mappings"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": test_category},
        )
        assert response.status_code == 200
        assert response.json["deleted_count"] >= 1


# ============================================================================
# Tests for EPG Coverage
# ============================================================================


class TestEpgCoverage:
    """Tests for EPG coverage statistics"""

    @patch("services.epg_service.EpgService.get_epg_coverage_stats")
    def test_get_epg_coverage(self, mock_stats, app, client):
        """Test getting EPG coverage statistics"""
        mock_stats.return_value = {
            "total_channels": 100,
            "channels_with_epg": 75,
            "coverage_percent": 75.0,
            "by_source": [{"source": "Test", "mapped": 75}],
        }

        response = client.get("/api/epg/coverage")
        assert response.status_code == 200
        assert response.json["total_channels"] == 100

    @patch("services.epg_service.EpgService.get_epg_coverage_stats")
    def test_get_epg_coverage_filtered(self, mock_stats, app, client, test_account):
        """Test getting EPG coverage for specific account"""
        mock_stats.return_value = {
            "total_channels": 50,
            "channels_with_epg": 40,
            "coverage_percent": 80.0,
        }

        response = client.get(f"/api/epg/coverage?account_id={test_account}")
        assert response.status_code == 200
        mock_stats.assert_called_once_with(test_account)

    @patch("services.epg_service.EpgService.get_category_epg_coverage")
    def test_get_category_epg_coverage(self, mock_coverage, app, client, test_account):
        """Test getting EPG coverage by category"""
        mock_coverage.return_value = [
            {"category": "Movies", "mapped": 50, "total": 100},
            {"category": "Sports", "mapped": 30, "total": 40},
        ]

        response = client.get(f"/api/epg/coverage/categories/{test_account}")
        assert response.status_code == 200
        assert response.json["account_id"] == test_account
        assert len(response.json["categories"]) == 2

    def test_get_category_epg_coverage_invalid_account(self, app, client):
        """Test getting coverage for non-existent account"""
        response = client.get("/api/epg/coverage/categories/99999")
        assert response.status_code == 404


# ============================================================================
# Tests for Source Mappings Endpoint
# ============================================================================


class TestSourceMappings:
    """Tests for getting source-specific mappings"""

    def test_get_source_mappings_not_found(self, app, client):
        """Test getting mappings for non-existent source"""
        response = client.get("/api/epg/sources/99999/mappings")
        assert response.status_code == 404

    def test_get_source_mappings_empty(self, app, client, test_epg_source):
        """Test getting mappings when none exist"""
        response = client.get(f"/api/epg/sources/{test_epg_source}/mappings")
        assert response.status_code == 200
        assert response.json["total"] == 0
        assert response.json["mappings"] == []

    def test_get_source_mappings_with_data(self, app, client, test_account, test_epg_source):
        """Test getting source mappings with data"""
        with app.app_context():
            # Create EPG channel for this source
            epg_ch = EpgChannel(
                source_id=test_epg_source,
                channel_id="epg_1",
                display_name="EPG Channel 1",
            )
            db.session.add(epg_ch)
            db.session.flush()

            # Create channel and mapping
            cat = Category.query.filter_by(account_id=test_account).first()
            if not cat:
                cat = Category(account_id=test_account, category_id="cat", category_name="Cat")
                db.session.add(cat)
                db.session.flush()

            ch = Channel(
                account_id=test_account,
                stream_id="st1",
                name="Channel 1",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(ch)
            db.session.flush()

            mapping = ChannelEpgMapping(
                channel_id=ch.id,
                epg_channel_id=epg_ch.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

        response = client.get(f"/api/epg/sources/{test_epg_source}/mappings")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_source_mappings_with_search(self, app, client, test_account, test_epg_source):
        """Test searching source mappings"""
        with app.app_context():
            epg_ch = EpgChannel(
                source_id=test_epg_source,
                channel_id="epg_search",
                display_name="SearchableChannel",
            )
            db.session.add(epg_ch)
            db.session.flush()

            cat = Category(account_id=test_account, category_id="cat", category_name="Cat")
            db.session.add(cat)
            db.session.flush()

            ch = Channel(
                account_id=test_account,
                stream_id="st1",
                name="TestSearchable",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(ch)
            db.session.flush()

            mapping = ChannelEpgMapping(
                channel_id=ch.id,
                epg_channel_id=epg_ch.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

        response = client.get(f"/api/epg/sources/{test_epg_source}/mappings?search=SearchableChannel")
        assert response.status_code == 200
        assert response.json["total"] == 1


# ============================================================================
# Tests for Helper Functions (Core Business Logic)
# ============================================================================


class TestSyncSdChannelsHelper:
    """Tests for _sync_sd_channels_to_epg helper function"""

    def test_sync_sd_channels_empty_list(self, app, test_epg_source):
        """Test syncing with empty channel list"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)
            stats = _sync_sd_channels_to_epg(source, [])

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 0
            assert stats["channels_removed"] == 0

    def test_sync_sd_channels_new_channels(self, app, test_epg_source):
        """Test syncing with new channels"""
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
            assert stats["channels_removed"] == 0

            # Verify channels were created
            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()
            assert len(epg_channels) == 2

    def test_sync_sd_channels_update_existing(self, app, test_epg_source):
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
            assert epg_ch.icon_url == "http://new-logo.com/logo.png"

    def test_sync_sd_channels_mixed_operations(self, app, test_epg_source):
        """Test mixed add/update operations"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            # Create one existing channel
            existing = EpgChannel(
                source_id=test_epg_source,
                channel_id="I12345.json.schedulesdirect.org",
                display_name="ESPN",
            )
            db.session.add(existing)
            db.session.commit()

            # Sync with one update and one new
            channels = [
                {
                    "stationID": "12345",
                    "callsign": "ESPN",
                    "name": "ESPN HD",
                    "logo": None,
                },
                {
                    "stationID": "99999",
                    "callsign": "HBOMAX",
                    "name": "HBO Max",
                    "logo": {"url": "http://example.com/max.png"},
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 1
            assert stats["channels_updated"] == 1

    def test_sync_sd_channels_handles_missing_fields(self, app, test_epg_source):
        """Test handling channels with missing optional fields"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source)

            # Channel with minimal fields
            channels = [
                {
                    "stationID": "12345",
                    # Missing callsign and name
                    "logo": None,
                },
                {
                    "stationID": "67890",
                    "callsign": "TEST",
                    # Missing name
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)
            assert stats["channels_added"] == 2

            # Verify channels were created with fallback names
            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()
            assert len(epg_channels) == 2
            for ch in epg_channels:
                assert ch.display_name is not None  # Should have fallback name

    def test_sync_sd_channels_display_names_json(self, app, test_epg_source):
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
            assert "ESPN" in display_names or "ESPN East" in display_names


# ============================================================================
# Tests for Schedules Direct Routes
# ============================================================================


class TestSchedulesDirectAuth:
    """Tests for Schedules Direct authentication"""

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_missing_username(self, mock_validate, app, client):
        """Test SD credentials check without username"""
        response = client.post(
            "/api/epg/sd/test",
            json={"password": "pass"},
        )
        assert response.status_code == 400

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_missing_password(self, mock_validate, app, client):
        """Test SD credentials check without password"""
        response = client.post(
            "/api/epg/sd/test",
            json={"username": "user"},
        )
        assert response.status_code == 400

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_success(self, mock_validate, app, client):
        """Test successful SD credentials validation"""
        mock_validate.return_value = {"success": True, "subscription_expired": False}

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "test", "password": "pass"},
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_failure(self, mock_validate, app, client):
        """Test failed SD credentials validation"""
        mock_validate.return_value = {"success": False, "error": "Invalid credentials"}

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "wrong", "password": "wrong"},
        )
        assert response.status_code == 401
        assert response.json["success"] is False


# ============================================================================
# Tests for XMLTV Grabber Routes
# ============================================================================


class TestXmltvGrabber:
    """Tests for XMLTV grabber endpoints"""

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_installed_grabbers")
    def test_get_xmltv_grabbers(self, mock_grabbers, app, client):
        """Test getting list of installed grabbers"""
        mock_grabber = MagicMock()
        mock_grabber.name = "tv_grab_zz_sdjson"
        mock_grabber.description = "Schedules Direct JSON grabber"
        mock_grabber.path = "/usr/bin/tv_grab_zz_sdjson"
        mock_grabber.capabilities = ["baseline"]

        mock_grabbers.return_value = [mock_grabber]

        response = client.get("/api/xmltv/grabbers")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["name"] == "tv_grab_zz_sdjson"

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_grabber_by_name")
    def test_get_xmltv_grabber_success(self, mock_get, app, client):
        """Test getting info about a specific grabber"""
        mock_grabber = MagicMock()
        mock_grabber.name = "tv_grab_zz_sdjson"
        mock_grabber.description = "SD JSON"
        mock_grabber.path = "/usr/bin/tv_grab_zz_sdjson"
        mock_grabber.capabilities = ["baseline"]
        mock_get.return_value = mock_grabber

        response = client.get("/api/xmltv/grabbers/tv_grab_zz_sdjson")
        assert response.status_code == 200
        assert response.json["name"] == "tv_grab_zz_sdjson"

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_grabber_by_name")
    def test_get_xmltv_grabber_not_found(self, mock_get, app, client):
        """Test getting non-existent grabber"""
        mock_get.return_value = None

        response = client.get("/api/xmltv/grabbers/nonexistent")
        assert response.status_code == 404


# ============================================================================
# Integration Tests
# ============================================================================


class TestEpgIntegration:
    """Integration tests for EPG workflow"""

    def test_full_mapping_workflow(self, app, client, test_account, test_epg_source):
        """Test complete workflow: create channels, EPG, and mappings"""
        with app.app_context():
            # 1. Create channels
            cat = Category(account_id=test_account, category_id="movies", category_name="Movies")
            db.session.add(cat)
            db.session.flush()

            for i in range(3):
                ch = Channel(
                    account_id=test_account,
                    stream_id=f"ch{i}",
                    name=f"Channel {i}",
                    category_id=cat.id,
                    is_active=True,
                )
                db.session.add(ch)
            db.session.commit()

            channels = Channel.query.filter_by(account_id=test_account).all()

        # 2. Create EPG channels
        with app.app_context():
            for i in range(3):
                epg_ch = EpgChannel(
                    source_id=test_epg_source,
                    channel_id=f"epg_{i}",
                    display_name=f"EPG {i}",
                )
                db.session.add(epg_ch)
            db.session.commit()

            epg_channels = EpgChannel.query.filter_by(source_id=test_epg_source).all()

        # 3. Create mappings
        mappings_created = 0
        for i, (ch, epg_ch) in enumerate(zip(channels, epg_channels)):
            response = client.post(
                "/api/epg/mappings",
                json={"channel_id": ch.id, "epg_channel_id": epg_ch.id},
            )
            if response.status_code == 201:
                mappings_created += 1

        assert mappings_created == 3

        # 4. Verify all mappings
        response = client.get(f"/api/epg/mappings?view_mode=mapped&account_id={test_account}")
        assert response.status_code == 200
        assert response.json["total"] == 3
