"""
Tests for API routes - sync, tags, cache, and channel preview
"""
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, ChannelTag, Tag, db


@pytest.fixture
def test_account(app):
    """Create a test account"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="test_user",
            password="test_pass",
            server="http://example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account


@pytest.fixture
def test_channel_with_tags(app, test_account):
    """Create a test channel with tags"""
    with app.app_context():
        # Create category
        category = Category(account_id=test_account.id, category_id="100", category_name="Test Category")
        db.session.add(category)
        db.session.flush()

        # Create channel
        channel = Channel(
            account_id=test_account.id,
            stream_id="ch1",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.flush()

        # Create tags
        tag1 = Tag(name="HD")
        tag2 = Tag(name="US")
        db.session.add_all([tag1, tag2])
        db.session.flush()

        # Link tags to channel
        channel_tag1 = ChannelTag(account_id=test_account.id, stream_id="ch1", tag_id=tag1.id)
        channel_tag2 = ChannelTag(account_id=test_account.id, stream_id="ch1", tag_id=tag2.id)
        db.session.add_all([channel_tag1, channel_tag2])
        db.session.commit()

        yield channel


# ============================================================================
# Sync All Accounts Tests
# ============================================================================


def test_sync_all_accounts_success(app, client, test_account):
    """Test sync all accounts endpoint"""
    with app.app_context():
        # Mock the sync service
        with patch("services.sync_service.ChannelSyncService.sync_all_accounts") as mock_sync:
            mock_sync.return_value = [{"account_id": test_account.id, "success": True, "channels_synced": 5}]

            response = client.post("/api/sync/all")
            assert response.status_code == 200

            data = response.json
            assert data["success"] is True
            assert data["accounts_synced"] == 1
            assert len(data["results"]) == 1

            # Verify sync was called
            mock_sync.assert_called_once()


def test_sync_all_accounts_handles_errors(app, client):
    """Test sync all accounts handles errors gracefully"""
    with app.app_context():
        # Mock the sync service to raise an exception
        with patch("services.sync_service.ChannelSyncService.sync_all_accounts") as mock_sync:
            mock_sync.side_effect = Exception("Sync failed")

            response = client.post("/api/sync/all")
            assert response.status_code == 500

            data = response.json
            assert data["success"] is False
            assert "error" in data


# ============================================================================
# Tags API Tests
# ============================================================================


def test_get_tags_all(app, client, test_channel_with_tags):
    """Test getting all tags"""
    with app.app_context():
        response = client.get("/api/tags")
        assert response.status_code == 200

        data = response.json
        assert isinstance(data, list)
        assert len(data) == 2  # HD and US tags

        tag_names = [t["name"] for t in data]
        assert "HD" in tag_names
        assert "US" in tag_names

        # Check structure
        for tag in data:
            assert "id" in tag
            assert "name" in tag
            assert "created_at" in tag
            assert "channel_count" not in tag  # No counts without flag


def test_get_tags_with_counts(app, client, test_channel_with_tags):
    """Test getting tags with channel counts"""
    with app.app_context():
        response = client.get("/api/tags?with_counts=true")
        assert response.status_code == 200

        data = response.json
        assert isinstance(data, list)
        assert len(data) == 2

        # Check counts are present
        for tag in data:
            assert "channel_count" in tag
            assert tag["channel_count"] == 1  # Each tag used by 1 channel


def test_get_tags_filtered_by_account(app, client, test_channel_with_tags, test_account):
    """Test getting tags filtered by account"""
    with app.app_context():
        # Create another account with different tag
        other_account = Account(
            name="Other Account",
            username="other_user",
            password="other_pass",
            server="http://example.com",
            enabled=True,
        )
        db.session.add(other_account)
        db.session.flush()

        # Create category for other account
        other_category = Category(account_id=other_account.id, category_id="200", category_name="Other Category")
        db.session.add(other_category)
        db.session.flush()

        # Create channel with different tag
        other_channel = Channel(
            account_id=other_account.id,
            stream_id="ch2",
            name="Other Channel",
            category_id=other_category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(other_channel)
        db.session.flush()

        other_tag = Tag(name="4K")
        db.session.add(other_tag)
        db.session.flush()

        other_channel_tag = ChannelTag(account_id=other_account.id, stream_id="ch2", tag_id=other_tag.id)
        db.session.add(other_channel_tag)
        db.session.commit()

        # Query tags for first account only
        response = client.get(f"/api/tags?account_id={test_account.id}")
        assert response.status_code == 200

        data = response.json
        tag_names = [t["name"] for t in data]
        assert "HD" in tag_names
        assert "US" in tag_names
        assert "4K" not in tag_names  # Not in test_account


def test_get_tags_with_counts_filtered_by_account(app, client, test_channel_with_tags, test_account):
    """Test getting tags with counts filtered by account"""
    with app.app_context():
        response = client.get(f"/api/tags?account_id={test_account.id}&with_counts=true")
        assert response.status_code == 200

        data = response.json
        assert len(data) == 2

        for tag in data:
            assert "channel_count" in tag
            assert tag["channel_count"] == 1


# ============================================================================
# Cache Management Tests
# ============================================================================


def test_clear_all_cache(app, client):
    """Test clearing all caches"""
    with app.app_context():
        with patch("routes.api.cache_service.clear_all") as mock_clear:
            response = client.post("/api/cache/clear")
            assert response.status_code == 200

            data = response.json
            assert data["success"] is True
            assert "cleared" in data["message"].lower()

            # Verify clear was called
            mock_clear.assert_called_once()


def test_clear_account_cache(app, client, test_account):
    """Test clearing cache for specific account"""
    with app.app_context():
        with patch("routes.api.cache_service.clear_account_cache") as mock_clear:
            response = client.post(f"/api/cache/clear/{test_account.id}")
            assert response.status_code == 200

            data = response.json
            assert data["success"] is True
            assert str(test_account.id) in data["message"]

            # Verify clear was called with correct account ID
            mock_clear.assert_called_once_with(test_account.id)


def test_clear_account_cache_nonexistent_account(app, client):
    """Test clearing cache for nonexistent account returns 404"""
    with app.app_context():
        response = client.post("/api/cache/clear/99999")
        assert response.status_code == 404


# ============================================================================
# Channel Preview Tests
# ============================================================================


def test_preview_channels_all(app, client, test_channel_with_tags):
    """Test previewing all channels across accounts"""
    with app.app_context():
        response = client.get("/api/channels/preview")
        assert response.status_code == 200

        data = response.json
        assert "total" in data
        assert "channels" in data
        assert data["total"] == 1
        assert len(data["channels"]) == 1

        # Check channel structure
        channel = data["channels"][0]
        assert "id" in channel
        assert "stream_id" in channel
        assert "account_id" in channel
        assert "name" in channel
        assert "cleaned_name" in channel
        assert "category_id" in channel
        assert "is_visible" in channel
        assert "tags" in channel
        assert isinstance(channel["tags"], list)
        assert len(channel["tags"]) == 2  # HD and US
        assert "HD" in channel["tags"]
        assert "US" in channel["tags"]


def test_preview_channels_with_pagination(app, client, test_account):
    """Test channel preview with pagination"""
    with app.app_context():
        # Create multiple channels
        category = Category(account_id=test_account.id, category_id="100", category_name="Test Category")
        db.session.add(category)
        db.session.flush()

        for i in range(5):
            channel = Channel(
                account_id=test_account.id,
                stream_id=f"ch{i}",
                name=f"Channel {i}",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
        db.session.commit()

        # Test first page
        response = client.get("/api/channels/preview?limit=2&offset=0")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["channels"]) == 2
        assert data["has_more"] is True

        # Test second page
        response = client.get("/api/channels/preview?limit=2&offset=2")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 5
        assert len(data["channels"]) == 2
        assert data["has_more"] is True

        # Test last page
        response = client.get("/api/channels/preview?limit=2&offset=4")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 5
        assert len(data["channels"]) == 1
        assert data["has_more"] is False


def test_preview_channels_filtered_by_account(app, client, test_channel_with_tags, test_account):
    """Test channel preview filtered by specific account"""
    with app.app_context():
        # Create another account with channel
        other_account = Account(
            name="Other Account",
            username="other_user",
            password="other_pass",
            server="http://example.com",
            enabled=True,
        )
        db.session.add(other_account)
        db.session.flush()

        other_category = Category(account_id=other_account.id, category_id="200", category_name="Other Category")
        db.session.add(other_category)
        db.session.flush()

        other_channel = Channel(
            account_id=other_account.id,
            stream_id="other_ch",
            name="Other Channel",
            category_id=other_category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(other_channel)
        db.session.commit()

        # Query only test_account channels
        response = client.get(f"/api/channels/preview?account_id={test_account.id}")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 1
        assert len(data["channels"]) == 1
        assert data["channels"][0]["account_id"] == test_account.id


def test_preview_channels_nonexistent_account(app, client):
    """Test channel preview with nonexistent account returns 404"""
    with app.app_context():
        response = client.get("/api/channels/preview?account_id=99999")
        assert response.status_code == 404


def test_preview_channels_only_visible_and_active(app, client, test_account):
    """Test channel preview only shows visible and active channels"""
    with app.app_context():
        category = Category(account_id=test_account.id, category_id="100", category_name="Test Category")
        db.session.add(category)
        db.session.flush()

        # Create visible+active channel
        visible_channel = Channel(
            account_id=test_account.id,
            stream_id="visible",
            name="Visible Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        # Create invisible channel
        invisible_channel = Channel(
            account_id=test_account.id,
            stream_id="invisible",
            name="Invisible Channel",
            category_id=category.id,
            is_active=True,
            is_visible=False,
        )
        # Create inactive channel
        inactive_channel = Channel(
            account_id=test_account.id,
            stream_id="inactive",
            name="Inactive Channel",
            category_id=category.id,
            is_active=False,
            is_visible=True,
        )
        db.session.add_all([visible_channel, invisible_channel, inactive_channel])
        db.session.commit()

        response = client.get("/api/channels/preview")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 1  # Only visible + active
        assert data["channels"][0]["stream_id"] == "visible"


# ============================================================================
# Channel Details API Tests
# ============================================================================


def test_get_channel_details(app, client, test_channel_with_tags, test_account):
    """Test getting detailed information for a specific channel"""
    with app.app_context():
        response = client.get(f"/api/accounts/{test_account.id}/channels/ch1")
        assert response.status_code == 200

        data = response.json
        assert data["stream_id"] == "ch1"
        assert data["name"] == "Test Channel"
        assert data["cleaned_name"] == "Test Channel"
        assert data["account_id"] == test_account.id
        assert data["account_name"] == "Test Account"
        assert data["category"] == "Test Category"

        # Check tags are included
        assert "tags" in data
        assert len(data["tags"]) == 2
        assert "HD" in data["tags"]
        assert "US" in data["tags"]

        # Check other fields are present
        assert "stream_type" in data
        assert "stream_icon" in data
        assert "epg_channel_id" in data
        assert "tv_archive" in data
        assert "tv_archive_duration" in data
        assert "is_active" in data
        assert "is_visible" in data
        assert "created_at" in data
        assert "updated_at" in data


def test_get_channel_details_not_found(app, client, test_account):
    """Test getting channel details for non-existent channel"""
    with app.app_context():
        response = client.get(f"/api/accounts/{test_account.id}/channels/nonexistent")
        assert response.status_code == 404


def test_get_channel_details_wrong_account(app, client, test_channel_with_tags, test_account):
    """Test getting channel details with wrong account returns 404"""
    with app.app_context():
        # Create another account
        other_account = Account(
            name="Other Account",
            username="other_user",
            password="other_pass",
            server="http://example.com",
            enabled=True,
        )
        db.session.add(other_account)
        db.session.commit()

        # Try to get test_channel_with_tags using other_account's ID
        response = client.get(f"/api/accounts/{other_account.id}/channels/ch1")
        assert response.status_code == 404
