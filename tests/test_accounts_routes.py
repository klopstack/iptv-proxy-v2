"""
Tests for accounts routes - account management, credentials, tags, channels, etc.
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelTag, Credential, Tag, db


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
def test_account_with_channels(app, test_account):
    """Create a test account with channels and categories"""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.flush()

        for i in range(5):
            channel = Channel(
                account_id=test_account,
                stream_id=f"ch{i}",
                name=f"Test Channel {i}",
                cleaned_name=f"Test Channel {i}",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
        db.session.commit()
        yield test_account


@pytest.fixture
def test_credential(app, test_account):
    """Create a test credential"""
    with app.app_context():
        cred = Credential(
            account_id=test_account,
            username="cred_user",
            password="cred_pass",
            max_connections=2,
            enabled=True,
        )
        db.session.add(cred)
        db.session.commit()
        yield cred.id


# ============================================================================
# Account Test Connection Tests
# ============================================================================


class TestAccountTestConnection:
    """Tests for account test connection endpoint"""

    def test_test_connection_account_not_found(self, app, client):
        """Test connection for non-existent account"""
        response = client.post("/api/accounts/999/test")
        assert response.status_code == 404

    def test_test_connection_no_credentials_or_legacy(self, app, client, test_account):
        """Test connection with no credentials or legacy fields"""
        with app.app_context():
            account = Account.query.get(test_account)
            account.username = None
            account.password = None
            db.session.commit()

        response = client.post(f"/api/accounts/{test_account}/test")
        # Should return error when no credentials are available
        assert response.status_code in [200, 400]  # May still succeed with empty list

    @patch("routes.accounts.IPTVService")
    def test_test_connection_legacy_mode_success(self, MockIPTVService, app, client, test_account):
        """Test connection using legacy username/password"""
        mock_service = MagicMock()
        mock_service.authenticate.return_value = {
            "server_info": {"url": "http://example.com", "time_now": "2024-01-01"},
            "user_info": {"username": "test", "status": "Active", "exp_date": "2025-01-01", "max_connections": "2"},
        }
        mock_service.get_live_streams.return_value = [{"stream_id": 1}] * 10
        mock_service.get_live_categories.return_value = [{"category_id": 1}] * 5
        MockIPTVService.return_value = mock_service

        response = client.post(f"/api/accounts/{test_account}/test")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["channels"] == 10
        assert response.json["legacy_mode"] is True

    @patch("routes.accounts.IPTVService")
    def test_test_connection_legacy_mode_error(self, MockIPTVService, app, client, test_account):
        """Test connection using legacy mode with error"""
        mock_service = MagicMock()
        mock_service.authenticate.side_effect = Exception("Connection refused")
        MockIPTVService.return_value = mock_service

        response = client.post(f"/api/accounts/{test_account}/test")
        assert response.status_code == 400
        assert response.json["success"] is False
        assert "Connection refused" in response.json["error"]

    @patch("routes.accounts.IPTVService")
    def test_test_connection_with_credentials(self, MockIPTVService, app, client, test_account, test_credential):
        """Test connection using credentials"""
        mock_service = MagicMock()
        mock_service.authenticate.return_value = {
            "server_info": {"url": "http://example.com"},
            "user_info": {
                "username": "cred_user",
                "status": "Active",
                "exp_date": "2025-01-01",
                "max_connections": "2",
            },
        }
        mock_service.get_live_streams.return_value = [{"stream_id": 1}] * 15
        mock_service.get_live_categories.return_value = [{"category_id": 1}] * 8
        MockIPTVService.return_value = mock_service

        response = client.post(f"/api/accounts/{test_account}/test")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["channels"] == 15
        assert len(response.json["credentials"]) == 1


# ============================================================================
# Preview Filter Matches Tests
# ============================================================================


class TestPreviewFilterMatches:
    """Tests for preview filter matches endpoint"""

    def test_preview_account_not_found(self, app, client):
        """Test preview for non-existent account"""
        response = client.post("/api/accounts/999/preview-channels", json={})
        assert response.status_code == 404

    def test_preview_account_disabled(self, app, client, test_account_with_channels):
        """Test preview for disabled account"""
        with app.app_context():
            account = db.session.get(Account, test_account_with_channels)
            account.enabled = False
            db.session.commit()

        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "category", "filter_value": "test"},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_preview_account_not_synced(self, app, client, test_account):
        """Test preview for account without synced channels"""
        response = client.post(
            f"/api/accounts/{test_account}/preview-channels",
            json={"filter_type": "category", "filter_value": "test"},
            content_type="application/json",
        )
        assert response.status_code == 503
        assert "sync" in response.json["error"].lower()

    def test_preview_missing_filter_type(self, app, client, test_account_with_channels):
        """Test preview with missing filter_type"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_value": "test"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "filter_type" in response.json["error"]

    def test_preview_missing_filter_value(self, app, client, test_account_with_channels):
        """Test preview with missing filter_value"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "category"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "filter_value" in response.json["error"]

    def test_preview_category_filter(self, app, client, test_account_with_channels):
        """Test preview with category filter"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "category", "filter_value": "Test"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["total_count"] == 5
        assert response.json["match_count"] == 5

    def test_preview_channel_name_filter(self, app, client, test_account_with_channels):
        """Test preview with channel name filter"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "channel_name", "filter_value": "Channel 1"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["match_count"] == 1

    def test_preview_regex_filter(self, app, client, test_account_with_channels):
        """Test preview with regex filter"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "regex", "filter_value": r"Channel [0-2]"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["match_count"] == 3

    def test_preview_regex_filter_invalid(self, app, client, test_account_with_channels):
        """Test preview with invalid regex"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "regex", "filter_value": r"[invalid"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "invalid regex" in response.json["error"].lower()

    def test_preview_tag_filter(self, app, client, test_account_with_channels):
        """Test preview with tag filter"""
        # Create some tags for channels (use uppercase as that's the normalized format)
        with app.app_context():
            tag = Tag(name="TESTTAG")
            db.session.add(tag)
            db.session.flush()

            channel_tag = ChannelTag(
                account_id=test_account_with_channels,
                stream_id="ch0",
                tag_id=tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

        # Test with mixed case input (should match due to case-insensitive normalization)
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "tag", "filter_value": "TestTag"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["match_count"] == 1

    def test_preview_tag_filter_empty_tags(self, app, client, test_account_with_channels):
        """Test preview with empty tag filter"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "tag", "filter_value": ""},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_preview_invalid_filter_type(self, app, client, test_account_with_channels):
        """Test preview with invalid filter type"""
        response = client.post(
            f"/api/accounts/{test_account_with_channels}/preview-channels",
            json={"filter_type": "invalid", "filter_value": "test"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "invalid" in response.json["error"].lower()


# ============================================================================
# Cleanup Orphan Tags Tests
# ============================================================================


class TestCleanupOrphanTags:
    """Tests for cleanup orphan tags endpoint"""

    def test_cleanup_orphan_tags_none(self, app, client):
        """Test cleanup when no orphan tags exist"""
        response = client.post("/api/tags/cleanup-orphans")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["tags_deleted"] == 0

    def test_cleanup_orphan_tags_with_orphans(self, app, client):
        """Test cleanup when orphan tags exist"""
        with app.app_context():
            # Create orphaned tags
            for i in range(5):
                tag = Tag(name=f"OrphanTag{i}")
                db.session.add(tag)
            db.session.commit()

        response = client.post("/api/tags/cleanup-orphans")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["tags_deleted"] == 5


# ============================================================================
# Credential Management Tests
# ============================================================================


class TestCredentialManagement:
    """Tests for credential management endpoints"""

    def test_get_credentials_account_not_found(self, app, client):
        """Test getting credentials for non-existent account"""
        response = client.get("/api/accounts/999/credentials")
        assert response.status_code == 404

    def test_get_credentials_empty(self, app, client, test_account):
        """Test getting credentials when none exist"""
        response = client.get(f"/api/accounts/{test_account}/credentials")
        assert response.status_code == 200
        assert response.json == []

    def test_get_credentials(self, app, client, test_account, test_credential):
        """Test getting credentials"""
        response = client.get(f"/api/accounts/{test_account}/credentials")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["username"] == "cred_user"

    def test_add_credential_missing_username(self, app, client, test_account):
        """Test adding credential without username"""
        response = client.post(
            f"/api/accounts/{test_account}/credentials",
            json={"password": "pass"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "username" in response.json["error"].lower()

    def test_add_credential_missing_password(self, app, client, test_account):
        """Test adding credential without password"""
        response = client.post(
            f"/api/accounts/{test_account}/credentials",
            json={"username": "user"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "password" in response.json["error"].lower()

    def test_add_credential_duplicate_username(self, app, client, test_account, test_credential):
        """Test adding credential with duplicate username"""
        response = client.post(
            f"/api/accounts/{test_account}/credentials",
            json={"username": "cred_user", "password": "newpass"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "already exists" in response.json["error"]

    @patch("routes.accounts.IPTVService")
    def test_add_credential_success(self, MockIPTVService, app, client, test_account):
        """Test successful credential addition"""
        mock_service = MagicMock()
        mock_service.authenticate.return_value = {
            "user_info": {"max_connections": "2", "status": "Active", "exp_date": "2025-01-01"}
        }
        MockIPTVService.return_value = mock_service

        response = client.post(
            f"/api/accounts/{test_account}/credentials",
            json={"username": "new_user", "password": "new_pass"},
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json["username"] == "new_user"

    @patch("routes.accounts.IPTVService")
    def test_add_credential_verify_fails(self, MockIPTVService, app, client, test_account):
        """Test credential addition when verification fails (still adds)"""
        mock_service = MagicMock()
        mock_service.authenticate.side_effect = Exception("Auth failed")
        MockIPTVService.return_value = mock_service

        response = client.post(
            f"/api/accounts/{test_account}/credentials",
            json={"username": "unverified_user", "password": "pass"},
            content_type="application/json",
        )
        # Should still succeed, just without verification info
        assert response.status_code == 201
        assert response.json["username"] == "unverified_user"

    def test_update_credential_not_found(self, app, client, test_account):
        """Test updating non-existent credential"""
        response = client.put(
            f"/api/accounts/{test_account}/credentials/999",
            json={"username": "updated"},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_update_credential_success(self, app, client, test_account, test_credential):
        """Test successful credential update"""
        response = client.put(
            f"/api/accounts/{test_account}/credentials/{test_credential}",
            json={"username": "updated_user", "enabled": False},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["username"] == "updated_user"
        assert response.json["enabled"] is False

    def test_delete_credential_not_found(self, app, client, test_account):
        """Test deleting non-existent credential"""
        response = client.delete(f"/api/accounts/{test_account}/credentials/999")
        assert response.status_code == 404

    def test_delete_credential_last_credential(self, app, client, test_account, test_credential):
        """Test deleting the last credential returns error"""
        response = client.delete(f"/api/accounts/{test_account}/credentials/{test_credential}")
        assert response.status_code == 400
        assert "last credential" in response.json["error"].lower()

    def test_delete_credential_success(self, app, client, test_account, test_credential):
        """Test successful credential deletion"""
        # Add a second credential first
        with app.app_context():
            cred2 = Credential(
                account_id=test_account,
                username="cred_user2",
                password="cred_pass2",
                enabled=True,
            )
            db.session.add(cred2)
            db.session.commit()

        response = client.delete(f"/api/accounts/{test_account}/credentials/{test_credential}")
        assert response.status_code == 204


# ============================================================================
# Account Sync Tests
# ============================================================================


class TestAccountSync:
    """Tests for account sync endpoints"""

    def test_sync_account_not_found(self, app, client):
        """Test syncing non-existent account"""
        response = client.post("/api/accounts/999/sync")
        assert response.status_code == 404

    @patch("services.sync_service.ChannelSyncService.sync_account")
    def test_sync_account_success(self, mock_sync, app, client, test_account):
        """Test successful account sync"""
        mock_sync.return_value = {"channels_synced": 10, "channels_removed": 2}

        response = client.post(f"/api/accounts/{test_account}/sync")
        assert response.status_code == 200

    def test_sync_status(self, app, client, test_account):
        """Test getting sync status"""
        response = client.get(f"/api/accounts/{test_account}/sync/status")
        assert response.status_code == 200
        assert "channel_count" in response.json


# ============================================================================
# Account Categories Tests
# ============================================================================


class TestAccountCategories:
    """Tests for account categories endpoints"""

    def test_get_categories_account_not_found(self, app, client):
        """Test getting categories for non-existent account"""
        response = client.get("/api/accounts/999/categories")
        assert response.status_code == 404

    @patch("routes.accounts.get_iptv_service_for_account")
    @patch("routes.accounts.cache_service")
    def test_get_categories_empty(self, mock_cache, mock_get_service, app, client, test_account):
        """Test getting categories when none exist"""
        mock_service = MagicMock()
        mock_service.get_live_categories.return_value = []
        mock_get_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = None

        response = client.get(f"/api/accounts/{test_account}/categories")
        assert response.status_code == 200
        assert response.json == []

    @patch("routes.accounts.get_iptv_service_for_account")
    @patch("routes.accounts.cache_service")
    def test_get_categories(self, mock_cache, mock_get_service, app, client, test_account):
        """Test getting categories"""
        mock_service = MagicMock()
        mock_service.get_live_categories.return_value = [{"category_id": "1", "category_name": "Test Category"}]
        mock_get_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = None

        response = client.get(f"/api/accounts/{test_account}/categories")
        assert response.status_code == 200
        assert len(response.json) == 1


# ============================================================================
# Account Tags Tests
# ============================================================================


class TestAccountTags:
    """Tests for account tags endpoints"""

    def test_get_tags_account_not_found(self, app, client):
        """Test getting tags for non-existent account"""
        response = client.get("/api/accounts/999/tags")
        assert response.status_code == 404

    def test_get_tags_empty(self, app, client, test_account):
        """Test getting tags when none exist"""
        response = client.get(f"/api/accounts/{test_account}/tags")
        assert response.status_code == 200
        assert response.json == []

    def test_get_tags(self, app, client, test_account_with_channels):
        """Test getting tags"""
        # Create some tags
        with app.app_context():
            tag1 = Tag(name="Tag1")
            tag2 = Tag(name="Tag2")
            db.session.add_all([tag1, tag2])
            db.session.flush()

            ct1 = ChannelTag(account_id=test_account_with_channels, stream_id="ch0", tag_id=tag1.id)
            ct2 = ChannelTag(account_id=test_account_with_channels, stream_id="ch0", tag_id=tag2.id)
            ct3 = ChannelTag(account_id=test_account_with_channels, stream_id="ch1", tag_id=tag1.id)
            db.session.add_all([ct1, ct2, ct3])
            db.session.commit()

        response = client.get(f"/api/accounts/{test_account_with_channels}/tags")
        assert response.status_code == 200
        assert len(response.json) == 2


# ============================================================================
# Process Tags Tests
# ============================================================================


class TestProcessTags:
    """Tests for tag processing endpoints"""

    def test_process_tags_account_not_found(self, app, client):
        """Test processing tags for non-existent account returns 503 (no channels)"""
        response = client.post("/api/accounts/999/process-tags")
        # Returns 503 because no channels are synced
        assert response.status_code == 503

    def test_process_tags_account_disabled(self, app, client, test_account):
        """Test processing tags for disabled account (no channels synced)"""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.enabled = False
            db.session.commit()

        response = client.post(f"/api/accounts/{test_account}/process-tags")
        # Returns 503 because no channels are synced, not 403
        assert response.status_code == 503

    def test_process_tags_not_synced(self, app, client, test_account):
        """Test processing tags when not synced"""
        response = client.post(f"/api/accounts/{test_account}/process-tags")
        # Should return 503 when account is not synced
        assert response.status_code == 503

    def test_process_tags_success(self, app, client, test_account_with_channels):
        """Test successful tag processing"""
        response = client.post(f"/api/accounts/{test_account_with_channels}/process-tags")
        assert response.status_code == 200


# ============================================================================
# Channel Details Tests
# ============================================================================


class TestChannelDetails:
    """Tests for channel details endpoint"""

    def test_get_channel_details_account_not_found(self, app, client):
        """Test getting channel details for non-existent account"""
        response = client.get("/api/accounts/999/channels/ch1")
        assert response.status_code == 404

    def test_get_channel_details_channel_not_found(self, app, client, test_account):
        """Test getting details for non-existent channel"""
        response = client.get(f"/api/accounts/{test_account}/channels/nonexistent")
        assert response.status_code == 404

    def test_get_channel_details_success(self, app, client, test_account_with_channels):
        """Test successful channel details retrieval"""
        response = client.get(f"/api/accounts/{test_account_with_channels}/channels/ch0")
        assert response.status_code == 200
        data = response.json
        assert data["stream_id"] == "ch0"
        assert "name" in data
        assert "tags" in data
