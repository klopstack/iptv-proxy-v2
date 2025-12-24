"""
Tests for EPG routes - EPG sources, channels, and mappings
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


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
def test_epg_source(app, test_account):
    """Create a test EPG source"""
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
def test_channel(app, test_account):
    """Create a test channel"""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account,
            stream_id="ch1",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()
        yield channel.id


# ============================================================================
# EPG Sources Tests
# ============================================================================


class TestEpgSources:
    """Tests for EPG source endpoints"""

    def test_get_epg_sources_empty(self, app, client):
        """Test getting EPG sources when none exist"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        assert response.json == []

    def test_get_epg_sources(self, app, client, test_epg_source):
        """Test getting EPG sources"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        sources = response.json
        assert len(sources) == 1
        assert sources[0]["name"] == "Test EPG Source"

    def test_create_epg_source_missing_name(self, app, client):
        """Test creating EPG source without name"""
        response = client.post("/api/epg/sources", json={"source_type": "provider"}, content_type="application/json")
        assert response.status_code == 400
        assert "name" in response.json["error"].lower()

    def test_create_epg_source_missing_type(self, app, client):
        """Test creating EPG source without source_type"""
        response = client.post("/api/epg/sources", json={"name": "Test"}, content_type="application/json")
        assert response.status_code == 400
        assert "source type" in response.json["error"].lower()

    def test_create_epg_source_invalid_type(self, app, client):
        """Test creating EPG source with invalid type"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "invalid_type"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "invalid" in response.json["error"].lower()

    def test_create_epg_source_provider_no_account(self, app, client):
        """Test creating provider source without account_id"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "provider"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "account" in response.json["error"].lower()

    def test_create_epg_source_success(self, app, client, test_account):
        """Test successful EPG source creation"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "New EPG Source",
                "source_type": "provider",
                "account_id": test_account,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert "id" in response.json

    def test_create_epg_source_xmltv_url(self, app, client):
        """Test creating XMLTV URL source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "XMLTV Source",
                "source_type": "xmltv_url",
                "url": "http://example.com/epg.xml",
            },
            content_type="application/json",
        )
        assert response.status_code == 201

    def test_update_epg_source_not_found(self, app, client):
        """Test updating non-existent EPG source"""
        response = client.put("/api/epg/sources/999", json={"name": "Updated"}, content_type="application/json")
        assert response.status_code == 404

    def test_update_epg_source_success(self, app, client, test_epg_source):
        """Test successful EPG source update"""
        response = client.put(
            "/api/epg/sources/" + str(test_epg_source),
            json={"name": "Updated Name", "priority": 50, "enabled": False},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_delete_epg_source_not_found(self, app, client):
        """Test deleting non-existent EPG source"""
        response = client.delete("/api/epg/sources/999")
        assert response.status_code == 404

    def test_delete_epg_source_success(self, app, client, test_epg_source):
        """Test successful EPG source deletion"""
        response = client.delete(f"/api/epg/sources/{test_epg_source}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_get_epg_sources_includes_used_mapping_count(self, app, client, test_account):
        """Test that EPG sources include used_mapping_count"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Test Source With Mappings",
                source_type="provider",
                account_id=test_account,
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create an EPG channel in that source
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_test_ch",
                display_name="Test EPG Ch",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create a category and channel
            category = Category(
                account_id=test_account,
                category_id="test_cat",
                category_name="Test Category",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="test_ch",
                name="Test Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create a mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            source_id = source.id

        # Test the endpoint
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        sources = response.json
        source_data = next((s for s in sources if s["id"] == source_id), None)
        assert source_data is not None
        assert "used_mapping_count" in source_data
        assert source_data["used_mapping_count"] == 1

    def test_get_source_mappings_not_found(self, app, client):
        """Test getting mappings for non-existent source"""
        response = client.get("/api/epg/sources/999/mappings")
        assert response.status_code == 404

    def test_get_source_mappings_empty(self, app, client, test_epg_source):
        """Test getting mappings when source has no mappings"""
        response = client.get(f"/api/epg/sources/{test_epg_source}/mappings")
        assert response.status_code == 200
        data = response.json
        assert data["source_id"] == test_epg_source
        assert data["total"] == 0
        assert data["mappings"] == []

    def test_get_source_mappings_with_data(self, app, client, test_account):
        """Test getting mappings for a source with data"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Test Source",
                source_type="provider",
                account_id=test_account,
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create an EPG channel
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_ch_1",
                display_name="EPG Channel 1",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create category and channel
            category = Category(
                account_id=test_account,
                category_id="cat_1",
                category_name="Category 1",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="ch_1",
                name="Channel 1",
                cleaned_name="Channel 1 Clean",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="auto_fuzzy",
                confidence=0.85,
            )
            db.session.add(mapping)
            db.session.commit()

            source_id = source.id

        # Test the endpoint
        response = client.get(f"/api/epg/sources/{source_id}/mappings")
        assert response.status_code == 200
        data = response.json
        assert data["source_id"] == source_id
        assert data["total"] == 1
        assert len(data["mappings"]) == 1
        mapping_data = data["mappings"][0]
        assert mapping_data["channel_name"] == "Channel 1"
        assert mapping_data["epg_channel_name"] == "EPG Channel 1"
        assert mapping_data["mapping_type"] == "auto_fuzzy"
        assert mapping_data["confidence"] == 0.85
        assert mapping_data["category_name"] == "Category 1"  # category_name from Category model

    def test_get_source_mappings_with_search(self, app, client, test_account):
        """Test searching source mappings"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Search Test Source",
                source_type="provider",
                account_id=test_account,
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create EPG channels
            epg_ch1 = EpgChannel(source_id=source.id, channel_id="epg1", display_name="CNN News")
            epg_ch2 = EpgChannel(source_id=source.id, channel_id="epg2", display_name="ESPN Sports")
            db.session.add_all([epg_ch1, epg_ch2])
            db.session.flush()

            # Create channels and mappings
            category = Category(account_id=test_account, category_id="c1", category_name="Cat")
            db.session.add(category)
            db.session.flush()

            ch1 = Channel(
                account_id=test_account, stream_id="s1", name="CNN HD", category_id=category.id, is_active=True
            )
            ch2 = Channel(
                account_id=test_account, stream_id="s2", name="ESPN HD", category_id=category.id, is_active=True
            )
            db.session.add_all([ch1, ch2])
            db.session.flush()

            m1 = ChannelEpgMapping(channel_id=ch1.id, epg_channel_id=epg_ch1.id, mapping_type="manual", confidence=1.0)
            m2 = ChannelEpgMapping(channel_id=ch2.id, epg_channel_id=epg_ch2.id, mapping_type="manual", confidence=1.0)
            db.session.add_all([m1, m2])
            db.session.commit()

            source_id = source.id

        # Search for CNN
        response = client.get(f"/api/epg/sources/{source_id}/mappings?search=CNN")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["mappings"][0]["channel_name"] == "CNN HD"

    def test_get_source_mappings_pagination(self, app, client, test_account):
        """Test pagination of source mappings"""
        with app.app_context():
            source = EpgSource(name="Pagination Test", source_type="provider", account_id=test_account, enabled=True)
            db.session.add(source)
            db.session.flush()

            category = Category(account_id=test_account, category_id="pag", category_name="Pag Cat")
            db.session.add(category)
            db.session.flush()

            # Create multiple mappings
            for i in range(5):
                epg_ch = EpgChannel(source_id=source.id, channel_id=f"epg{i}", display_name=f"EPG {i}")
                db.session.add(epg_ch)
                db.session.flush()

                ch = Channel(
                    account_id=test_account,
                    stream_id=f"ch{i}",
                    name=f"Channel {i}",
                    category_id=category.id,
                    is_active=True,
                )
                db.session.add(ch)
                db.session.flush()

                mapping = ChannelEpgMapping(
                    channel_id=ch.id, epg_channel_id=epg_ch.id, mapping_type="manual", confidence=1.0
                )
                db.session.add(mapping)

            db.session.commit()
            source_id = source.id

        # Test pagination
        response = client.get(f"/api/epg/sources/{source_id}/mappings?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 5
        assert len(data["mappings"]) == 2
        assert data["offset"] == 0
        assert data["limit"] == 2

        # Get next page
        response = client.get(f"/api/epg/sources/{source_id}/mappings?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json
        assert len(data["mappings"]) == 2
        assert data["offset"] == 2


# ============================================================================
# EPG Channels Tests
# ============================================================================


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


# ============================================================================
# EPG Mappings Tests
# ============================================================================


class TestEpgMappings:
    """Tests for EPG mapping endpoints"""

    def test_get_epg_mappings_empty(self, app, client):
        """Test getting mappings when none exist"""
        response = client.get("/api/epg/mappings")
        assert response.status_code == 200

    def test_get_epg_mappings_unmapped_only(self, app, client, test_channel):
        """Test getting unmapped channels"""
        response = client.get("/api/epg/mappings?unmapped_only=true")
        assert response.status_code == 200
        data = response.json
        assert "unmapped_channels" in data
        assert data["total"] >= 1

    def test_get_epg_mappings_unmapped_with_category_filter(self, app, client, test_account):
        """Test getting unmapped channels filtered by category"""
        with app.app_context():
            # Create two categories
            cat1 = Category(
                account_id=test_account,
                category_id="cat_filter1",
                category_name="Category 1",
            )
            cat2 = Category(
                account_id=test_account,
                category_id="cat_filter2",
                category_name="Category 2",
            )
            db.session.add_all([cat1, cat2])
            db.session.flush()

            # Create channels in different categories
            ch1 = Channel(
                account_id=test_account,
                stream_id="ch_cat1",
                name="Channel in Cat1",
                category_id=cat1.id,
                is_active=True,
                is_visible=True,
            )
            ch2 = Channel(
                account_id=test_account,
                stream_id="ch_cat2",
                name="Channel in Cat2",
                category_id=cat2.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add_all([ch1, ch2])
            db.session.commit()

            # Test filter by category 1
            response = client.get(
                f"/api/epg/mappings?unmapped_only=true&account_id={test_account}&category_id={cat1.id}"
            )
            assert response.status_code == 200
            data = response.json
            assert "unmapped_channels" in data
            # Should only return channels in cat1
            for ch in data["unmapped_channels"]:
                assert ch["category_id"] == cat1.id

            # Test filter by category 2
            response = client.get(
                f"/api/epg/mappings?unmapped_only=true&account_id={test_account}&category_id={cat2.id}"
            )
            assert response.status_code == 200
            data = response.json
            # Should only return channels in cat2
            for ch in data["unmapped_channels"]:
                assert ch["category_id"] == cat2.id

    def test_get_epg_mappings_unmapped_includes_category_info(self, app, client, test_channel, test_account):
        """Test that unmapped channels include category info in response"""
        response = client.get(f"/api/epg/mappings?unmapped_only=true&account_id={test_account}")
        assert response.status_code == 200
        data = response.json
        assert "unmapped_channels" in data
        assert len(data["unmapped_channels"]) > 0
        # Check that category info is included
        ch = data["unmapped_channels"][0]
        assert "category_id" in ch
        assert "category_name" in ch

    def test_create_epg_mapping_missing_channel_id(self, app, client):
        """Test creating mapping without channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"epg_channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "channel_id" in response.json["error"]

    def test_create_epg_mapping_missing_epg_channel_id(self, app, client):
        """Test creating mapping without epg_channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "epg_channel_id" in response.json["error"]

    def test_create_epg_mapping_channel_not_found(self, app, client, test_epg_channel):
        """Test creating mapping with non-existent channel"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 999, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_create_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successful mapping creation"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 201
        assert "mapping_id" in response.json

    def test_create_epg_mapping_duplicate(self, app, client, test_channel, test_epg_channel):
        """Test creating duplicate mapping"""
        # Create first mapping
        client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )

        # Try to create duplicate
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_delete_epg_mapping_not_found(self, app, client):
        """Test deleting non-existent mapping"""
        response = client.delete("/api/epg/mappings/999")
        assert response.status_code == 404

    def test_delete_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successful mapping deletion"""
        # Create mapping first
        create_response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        mapping_id = create_response.json["mapping_id"]

        # Delete it
        response = client.delete(f"/api/epg/mappings/{mapping_id}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_bulk_delete_mappings_missing_account_id(self, app, client):
        """Test bulk delete with missing account_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"category_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "account_id is required" in response.json["error"]

    def test_bulk_delete_mappings_missing_category_id(self, app, client):
        """Test bulk delete with missing category_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "category_id is required" in response.json["error"]

    def test_bulk_delete_mappings_success(self, app, client, test_account, test_epg_source):
        """Test bulk delete of mappings in a category"""
        from models import Category, Channel, ChannelEpgMapping, EpgChannel

        with app.app_context():
            # Create a category
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test Category",
            )
            db.session.add(category)
            db.session.flush()

            # Create EPG channel
            epg_ch = EpgChannel(
                source_id=test_epg_source,
                channel_id="epg1",
                display_name="EPG Channel",
            )
            db.session.add(epg_ch)
            db.session.flush()

            # Create channels with mappings
            channel_ids = []
            for i in range(3):
                ch = Channel(
                    account_id=test_account,
                    stream_id=f"stream{i}",
                    name=f"Channel {i}",
                    category_id=category.id,
                    is_active=True,
                )
                db.session.add(ch)
                db.session.flush()
                channel_ids.append(ch.id)

                mapping = ChannelEpgMapping(
                    channel_id=ch.id,
                    epg_channel_id=epg_ch.id,
                    mapping_type="manual",
                    confidence=1.0,
                )
                db.session.add(mapping)

            db.session.commit()
            category_id = category.id

        # Bulk delete
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": category_id},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["deleted_count"] == 3

    def test_bulk_delete_mappings_empty_category(self, app, client, test_account):
        """Test bulk delete when category has no channels"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": 999},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["deleted_count"] == 0


# ============================================================================
# EPG Coverage Tests
# ============================================================================


class TestEpgCoverage:
    """Tests for EPG coverage endpoints"""

    @patch("services.epg_service.EpgService.get_epg_coverage_stats")
    def test_get_epg_coverage(self, mock_coverage, app, client):
        """Test getting EPG coverage stats"""
        mock_coverage.return_value = {"total_channels": 100, "mapped_channels": 50}

        response = client.get("/api/epg/coverage")
        assert response.status_code == 200
        assert "total_channels" in response.json

    @patch("services.epg_service.EpgService.get_epg_coverage_stats")
    def test_get_epg_coverage_with_account(self, mock_coverage, app, client, test_account):
        """Test getting EPG coverage stats for specific account"""
        mock_coverage.return_value = {"total_channels": 50, "mapped_channels": 25}

        response = client.get(f"/api/epg/coverage?account_id={test_account}")
        assert response.status_code == 200

    @patch("services.epg_service.EpgService.get_category_epg_coverage")
    def test_get_category_coverage(self, mock_coverage, app, client, test_account):
        """Test getting EPG coverage by category"""
        mock_coverage.return_value = [{"category_id": 1, "total": 10, "mapped": 5}]

        response = client.get(f"/api/epg/coverage/categories/{test_account}")
        assert response.status_code == 200

    def test_get_category_coverage_account_not_found(self, app, client):
        """Test category coverage for non-existent account"""
        response = client.get("/api/epg/coverage/categories/999")
        assert response.status_code == 404


# ============================================================================
# EPG Matching Tests
# ============================================================================


class TestEpgMatching:
    """Tests for EPG matching endpoints"""

    def test_match_channels_account_not_found(self, app, client):
        """Test matching channels for non-existent account"""
        response = client.post("/api/epg/match/999")
        assert response.status_code == 404

    @patch("services.epg_match_rules_service.EpgMatchRulesService.match_channels_with_rules")
    def test_match_channels_success(self, mock_match, app, client, test_account):
        """Test successful channel matching (redirects to rule-based matching)"""
        mock_match.return_value = {
            "total_channels": 20,
            "skipped_existing": 2,
            "excluded": 0,
            "matched": 18,
            "unmatched": 0,
        }

        response = client.post(f"/api/epg/match/{test_account}")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert "18 channels" in response.json["message"]
        assert "skipped 2" in response.json["message"]


# ============================================================================
# EPG Source Sync Tests
# ============================================================================


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
    @patch("services.epg_service.EpgService.sync_epg_source")
    def test_sync_provider_source_success(self, mock_sync, mock_get_xmltv, app, client, test_epg_source, test_account):
        """Test successful provider source sync"""
        mock_get_xmltv.return_value = b"<tv></tv>"
        mock_sync.return_value = {"channels_added": 10, "channels_updated": 5}

        response = client.post(f"/api/epg/sources/{test_epg_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("requests.get")
    @patch("services.epg_service.EpgService.sync_epg_source")
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

    @patch("routes.epg.SchedulesDirectClient")
    def test_sync_schedules_direct_success(self, mock_sd_client_class, app, client):
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

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["stats"]["channels_added"] == 2

        # Verify EPG channels were created
        with app.app_context():
            epg_channels = EpgChannel.query.filter_by(source_id=source_id).all()
            assert len(epg_channels) == 2

            # Check channel details
            channel_ids = {c.channel_id for c in epg_channels}
            assert "I12345.json.schedulesdirect.org" in channel_ids
            assert "I67890.json.schedulesdirect.org" in channel_ids

    @patch("routes.epg.SchedulesDirectClient")
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
        assert response.status_code == 500
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


# ============================================================================
# Schedules Direct API Tests
# ============================================================================


class TestSchedulesDirectAPI:
    """Tests for Schedules Direct API endpoints"""

    def test_test_sd_credentials_missing_username(self, app, client):
        """Test testing SD credentials without username"""
        response = client.post(
            "/api/epg/sd/test",
            json={"password": "testpass"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "required" in response.json["error"].lower()

    def test_test_sd_credentials_missing_password(self, app, client):
        """Test testing SD credentials without password"""
        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "required" in response.json["error"].lower()

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_success(self, mock_validate, app, client):
        """Test successful SD credential validation"""
        mock_validate.return_value = {
            "success": True,
            "message": "Authentication successful",
            "account": {"max_lineups": 5},
        }

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser", "password": "testpass"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("routes.epg.validate_credentials")
    def test_test_sd_credentials_failure(self, mock_validate, app, client):
        """Test failed SD credential validation"""
        mock_validate.return_value = {
            "success": False,
            "message": "Invalid credentials",
        }

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser", "password": "wrongpass"},
            content_type="application/json",
        )
        assert response.status_code == 401
        assert response.json["success"] is False

    def test_search_sd_lineups_missing_source_id(self, app, client):
        """Test searching SD lineups without source_id"""
        response = client.get("/api/epg/sd/lineups/search?postalcode=10001")
        assert response.status_code == 400
        assert "source_id" in response.json["error"].lower()

    def test_search_sd_lineups_wrong_source_type(self, app, client, test_epg_source):
        """Test searching SD lineups with non-SD source"""
        response = client.get(f"/api/epg/sd/lineups/search?source_id={test_epg_source}&postalcode=10001")
        assert response.status_code == 400
        assert "schedules direct" in response.json["error"].lower()

    def test_search_sd_lineups_no_credentials(self, app, client):
        """Test searching SD lineups without credentials configured"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 400
        assert "credentials" in response.json["error"].lower()

    @patch("routes.epg.SchedulesDirectClient")
    def test_search_sd_lineups_success(self, MockClient, app, client):
        """Test successful SD lineup search"""
        # Create SD source with credentials
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

        # Mock the client
        mock_client = MagicMock()
        mock_client.search_lineups.return_value = [{"lineup": "USA-NY12345-X", "name": "Test Lineup"}]
        MockClient.return_value = mock_client

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert len(response.json["lineups"]) == 1

    @patch("routes.epg.SchedulesDirectClient")
    def test_search_sd_lineups_error(self, MockClient, app, client):
        """Test SD lineup search with error"""
        from services.schedules_direct import SchedulesDirectError

        # Create SD source with credentials
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

        # Mock the client to raise an error
        mock_client = MagicMock()
        mock_client.authenticate.side_effect = SchedulesDirectError("Test error", code=4003)
        MockClient.return_value = mock_client

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 400
        assert "Test error" in response.json["error"]

    def test_get_sd_lineups_missing_source_id(self, app, client):
        """Test getting SD lineups without source_id"""
        response = client.get("/api/epg/sd/lineups")
        assert response.status_code == 400
        assert "source_id" in response.json["error"].lower()

    def test_get_sd_lineups_success(self, app, client):
        """Test getting SD lineups successfully"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.get(f"/api/epg/sd/lineups?source_id={source_id}")
        assert response.status_code == 200
        # Response is a dict with lineups array and metadata
        assert "lineups" in response.json
        assert isinstance(response.json["lineups"], list)


# ============================================================================
# Account EPG Source Tests
# ============================================================================


class TestAccountEpgSource:
    """Tests for account EPG source endpoints"""

    def test_create_account_epg_source_not_found(self, app, client):
        """Test creating EPG source for non-existent account"""
        response = client.post("/api/accounts/999/epg-source")
        assert response.status_code == 404

    @patch("services.epg_service.EpgService.create_provider_epg_source")
    def test_create_account_epg_source_success(self, mock_create, app, client, test_account):
        """Test successful account EPG source creation"""
        mock_source = MagicMock()
        mock_source.id = 1
        mock_create.return_value = mock_source

        response = client.post(f"/api/accounts/{test_account}/epg-source")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["source_id"] == 1

    @patch("routes.epg.IPTVService")
    @patch("services.epg_service.EpgService.sync_epg_source")
    @patch("services.epg_service.EpgService.create_provider_epg_source")
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
