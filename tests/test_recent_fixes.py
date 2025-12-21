"""
Tests for recent bug fixes (issues 20-25)
"""
import pytest
from datetime import datetime
from models import Account, Channel, Category, ChannelTag, Tag


@pytest.fixture
def sample_account(client):
    """Create a test account"""
    from models import db
    
    account = Account(
        name="Test Account",
        server="test.example.com",
        username="testuser",
        password="testpass",
        enabled=True,
    )
    db.session.add(account)
    db.session.commit()
    return account


class TestDatetimeTimezoneIssue:
    """Test for Issue 20: Datetime timezone comparison error"""

    def test_process_tags_uses_naive_datetime(self, client, sample_account):
        """Ensure processing_start uses timezone-naive datetime to avoid comparison errors"""
        # Create test channel and category
        from models import db

        category = Category(
            account_id=test_account.id,
            category_id=1,
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel = Channel(
            account_id=test_account.id,
            stream_id=1,
            name="Test Channel",
            category_id=category.id,
            is_active=True,
        )
        db.session.add(channel)
        db.session.commit()

        # This should not raise TypeError about timezone comparison
        response = client.post(f"/api/accounts/{test_account.id}/process-tags")
        assert response.status_code in [200, 503]  # 503 if no tag rules configured


class TestPreviewChannelsAPI:
    """Test for Issue 21: Preview channels API missing fields"""

    def test_preview_includes_showing_field(self, client, test_account):
        """Ensure preview API returns 'showing' field"""
        from models import db

        category = Category(
            account_id=test_account.id,
            category_id=1,
            category_name="Test",
        )
        db.session.add(category)

        # Create test channels
        for i in range(3):
            channel = Channel(
                account_id=test_account.id,
                stream_id=i,
                name=f"Channel {i}",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
        db.session.commit()

        response = client.get(f"/api/accounts/{test_account.id}/preview?limit=2")
        assert response.status_code == 200
        data = response.json

        # Check for required fields
        assert "showing" in data
        assert "has_more" in data
        assert "total" in data
        assert data["showing"] == 2
        assert data["has_more"] is True
        assert data["total"] == 3

    def test_preview_includes_category_and_tags(self, client, test_account):
        """Ensure preview API returns category name and tags"""
        from models import db

        category = Category(
            account_id=test_account.id,
            category_id=1,
            category_name="Test Category",
        )
        db.session.add(category)

        channel = Channel(
            account_id=test_account.id,
            stream_id=1,
            name="Test Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)

        tag = Tag(name="test_tag")
        db.session.add(tag)
        db.session.commit()

        channel_tag = ChannelTag(
            account_id=test_account.id,
            stream_id=channel.stream_id,
            tag_id=tag.id,
        )
        db.session.add(channel_tag)
        db.session.commit()

        response = client.get(f"/api/accounts/{test_account.id}/preview")
        assert response.status_code == 200
        data = response.json

        assert len(data["channels"]) == 1
        channel_data = data["channels"][0]
        assert "category" in channel_data
        assert channel_data["category"] == "Test Category"
        assert "tags" in channel_data
        assert "test_tag" in channel_data["tags"]


class TestAllAccountsPreview:
    """Test for Issue 22: All accounts preview option"""

    def test_channels_preview_endpoint_exists(self, client):
        """Ensure /api/channels/preview endpoint exists"""
        response = client.get("/api/channels/preview")
        # Should return 200 even with no data
        assert response.status_code == 200
        data = response.json
        assert "total" in data
        assert "channels" in data
        assert "has_more" in data


class TestStatsAPI:
    """Test for Issue 24: Dashboard statistics"""

    def test_stats_include_visibility_counts(self, client, test_account):
        """Ensure stats API returns visible/hidden channel counts"""
        from models import db

        category = Category(
            account_id=test_account.id,
            category_id=1,
            category_name="Test",
        )
        db.session.add(category)

        # Create 5 visible and 3 hidden channels
        for i in range(8):
            channel = Channel(
                account_id=test_account.id,
                stream_id=i,
                name=f"Channel {i}",
                category_id=category.id,
                is_active=True,
                is_visible=(i < 5),  # First 5 are visible
            )
            db.session.add(channel)
        db.session.commit()

        response = client.get(f"/api/accounts/{test_account.id}/stats")
        assert response.status_code == 200
        data = response.json

        assert "total_channels" in data
        assert "visible_channels" in data
        assert "hidden_channels" in data
        assert data["total_channels"] == 8
        assert data["visible_channels"] == 5
        assert data["hidden_channels"] == 3


class TestSyncStatusAPI:
    """Test for Issue 25: Accounts page sync status"""

    def test_sync_status_returns_channel_count(self, client, test_account):
        """Ensure sync status API returns channel_count not 'synced' boolean"""
        from models import db

        category = Category(
            account_id=test_account.id,
            category_id=1,
            category_name="Test",
        )
        db.session.add(category)

        channel = Channel(
            account_id=test_account.id,
            stream_id=1,
            name="Test Channel",
            category_id=category.id,
            is_active=True,
        )
        db.session.add(channel)
        db.session.commit()

        response = client.get(f"/api/accounts/{test_account.id}/sync/status")
        assert response.status_code == 200
        data = response.json

        # Should have channel_count not synced boolean
        assert "channel_count" in data
        assert "last_sync" in data
        assert data["channel_count"] == 1
        # Frontend determines synced status from channel_count > 0
