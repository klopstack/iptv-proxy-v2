"""
Test Phase 4: Database-First Enforcement

Tests that:
1. Tag processing returns 503 when not synced
2. Tag processing works when synced
3. Preview returns 503 when not synced
4. Preview works when synced
5. Playlist generation returns 503 when not synced
6. All backward compatibility code removed
"""
import pytest

from models import Account, Channel, Category, db


@pytest.fixture
def test_account(app):
    """Create test account"""
    with app.app_context():
        account = Account(
            name="Phase4 Test Account",
            server="test.example.com",
            username="phase4user",
            password="phase4pass",
            enabled=True
        )
        db.session.add(account)
        db.session.commit()
        yield account
        db.session.delete(account)
        db.session.commit()


@pytest.fixture
def synced_account_with_channels(app, test_account):
    """Create account with synced channels"""
    with app.app_context():
        # Create category
        category = Category(
            account_id=test_account.id,
            category_id="100",
            category_name="Test Category"
        )
        db.session.add(category)
        db.session.flush()
        
        # Create channels
        channels = [
            Channel(
                account_id=test_account.id,
                stream_id=f"ch{i}",
                name=f"Test Channel {i}",
                cleaned_name=f"Test Channel {i}",
                category_id=category.id,
                is_active=True,
                is_visible=True
            )
            for i in range(1, 6)
        ]
        db.session.add_all(channels)
        db.session.commit()
        
        yield test_account


# ============================================================================
# Tag Processing Tests
# ============================================================================

def test_tag_processing_returns_503_when_not_synced(app, client, test_account):
    """Test that tag processing requires synced channels"""
    with app.app_context():
        # No channels synced for this account
        channel_count = Channel.query.filter_by(
            account_id=test_account.id,
            is_active=True
        ).count()
        assert channel_count == 0
        
        # Try to process tags
        response = client.post(f"/api/accounts/{test_account.id}/process-tags")
        
        # Should return 503 Service Unavailable
        assert response.status_code == 503
        data = response.json
        assert data["success"] is False
        assert "not synced" in data["error"].lower()


def test_tag_processing_works_when_synced(app, client, synced_account_with_channels):
    """Test that tag processing works with synced channels"""
    with app.app_context():
        # Channels exist
        channel_count = Channel.query.filter_by(
            account_id=synced_account_with_channels.id,
            is_active=True
        ).count()
        assert channel_count > 0
        
        # Process tags should work
        response = client.post(f"/api/accounts/{synced_account_with_channels.id}/process-tags")
        
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "processed" in data
        assert data["using_database"] is True


# ============================================================================
# Preview Tests
# ============================================================================

def test_preview_returns_503_when_not_synced(app, client, test_account):
    """Test that preview requires synced channels"""
    with app.app_context():
        # No channels synced
        channel_count = Channel.query.filter_by(
            account_id=test_account.id,
            is_active=True
        ).count()
        assert channel_count == 0
        
        # Try to preview
        response = client.get(f"/api/accounts/{test_account.id}/preview")
        
        # Should return 503 with standardized error format
        assert response.status_code == 503
        data = response.json
        assert data["success"] is False
        assert "error" in data
        assert "not synced" in data["error"].lower()


def test_preview_works_when_synced(app, client, synced_account_with_channels):
    """Test that preview works with synced channels"""
    with app.app_context():
        response = client.get(f"/api/accounts/{synced_account_with_channels.id}/preview")
        
        assert response.status_code == 200
        data = response.json
        assert data["total"] > 0
        assert len(data["channels"]) > 0
        assert data["using_database"] is True


def test_preview_with_pagination(app, client, synced_account_with_channels):
    """Test preview pagination with synced channels"""
    with app.app_context():
        # Request page 1
        response = client.get(
            f"/api/accounts/{synced_account_with_channels.id}/preview?limit=2&offset=0"
        )
        
        assert response.status_code == 200
        data = response.json
        assert len(data["channels"]) == 2
        assert data["total"] == 5
        
        # Request page 2
        response2 = client.get(
            f"/api/accounts/{synced_account_with_channels.id}/preview?limit=2&offset=2"
        )
        
        assert response2.status_code == 200
        data2 = response2.json
        assert len(data2["channels"]) == 2
        assert data2["total"] == 5


# ============================================================================
# Playlist Generation Tests
# ============================================================================

def test_playlist_returns_503_when_not_synced(app, client, test_account):
    """Test that playlist generation requires synced channels"""
    with app.app_context():
        # No channels synced
        channel_count = Channel.query.filter_by(
            account_id=test_account.id,
            is_active=True
        ).count()
        assert channel_count == 0
        
        # Try to generate playlist
        response = client.get(f"/playlist/{test_account.id}.m3u")
        
        # Should return 503 with text error (M3U endpoint)
        assert response.status_code == 503
        error_msg = response.data.decode('utf-8')
        assert "not synced" in error_msg.lower()


def test_playlist_works_when_synced(app, client, synced_account_with_channels):
    """Test that playlist generation works with synced channels"""
    with app.app_context():
        response = client.get(f"/playlist/{synced_account_with_channels.id}.m3u")
        
        assert response.status_code == 200
        playlist = response.data.decode('utf-8')
        
        # Should be valid M3U
        assert playlist.startswith("#EXTM3U")
        assert "Test Channel" in playlist
        
        # Should have entries for all visible channels
        assert playlist.count("#EXTINF") == 5


# ============================================================================
# Backward Compatibility Removal Tests
# ============================================================================

def test_no_api_fallback_in_tag_processing(app, client, test_account):
    """Test that tag processing does not fall back to API"""
    with app.app_context():
        # Without synced channels, should get 503, not try API
        response = client.post(f"/api/accounts/{test_account.id}/process-tags")
        
        # Should fail immediately with 503, not attempt API call
        assert response.status_code == 503
        data = response.json
        
        # New standardized error format
        assert data["success"] is False
        assert "error" in data


def test_no_api_fallback_in_preview(app, client, test_account):
    """Test that preview does not fall back to API"""
    with app.app_context():
        response = client.get(f"/api/accounts/{test_account.id}/preview")
        
        # Should return 503, not try API
        assert response.status_code == 503
        data = response.json
        
        # New standardized error format
        assert data["success"] is False
        assert "error" in data


def test_database_first_workflow(app, client, test_account):
    """Test the enforced database-first workflow"""
    with app.app_context():
        # Step 1: Account exists but not synced - operations should fail
        
        # Tag processing fails
        tag_response = client.post(f"/api/accounts/{test_account.id}/process-tags")
        assert tag_response.status_code == 503
        
        # Preview fails
        preview_response = client.get(f"/api/accounts/{test_account.id}/preview")
        assert preview_response.status_code == 503
        
        # Playlist fails
        playlist_response = client.get(f"/playlist/{test_account.id}.m3u")
        assert playlist_response.status_code == 503
        
        # Step 2: Create synced channels (simulating sync)
        category = Category(
            account_id=test_account.id,
            category_id="200",
            category_name="Synced Category"
        )
        db.session.add(category)
        db.session.flush()
        
        channel = Channel(
            account_id=test_account.id,
            stream_id="synced_ch1",
            name="Synced Channel",
            cleaned_name="Synced Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True
        )
        db.session.add(channel)
        db.session.commit()
        
        # Step 3: Now operations should work
        
        # Tag processing works
        tag_response2 = client.post(f"/api/accounts/{test_account.id}/process-tags")
        assert tag_response2.status_code == 200
        
        # Preview works
        preview_response2 = client.get(f"/api/accounts/{test_account.id}/preview")
        assert preview_response2.status_code == 200
        
        # Playlist works
        playlist_response2 = client.get(f"/playlist/{test_account.id}.m3u")
        assert playlist_response2.status_code == 200


def test_error_messages_are_clear(app, client, test_account):
    """Test that 503 errors have clear, actionable messages"""
    with app.app_context():
        # Tag processing error
        tag_response = client.post(f"/api/accounts/{test_account.id}/process-tags")
        tag_data = tag_response.json
        assert "sync" in tag_data["error"].lower()
        assert "first" in tag_data["error"].lower()
        
        # Preview error
        preview_response = client.get(f"/api/accounts/{test_account.id}/preview")
        preview_data = preview_response.json
        assert "sync" in preview_data["error"].lower()
        
        # Playlist error (text response)
        playlist_response = client.get(f"/playlist/{test_account.id}.m3u")
        playlist_text = playlist_response.data.decode('utf-8')
        assert "sync" in playlist_text.lower()


def test_inactive_channels_ignored(app, client, test_account):
    """Test that only active channels are considered for sync status"""
    with app.app_context():
        # Create inactive channel
        category = Category(
            account_id=test_account.id,
            category_id="300",
            category_name="Test"
        )
        db.session.add(category)
        db.session.flush()
        
        inactive_channel = Channel(
            account_id=test_account.id,
            stream_id="inactive_ch",
            name="Inactive Channel",
            category_id=category.id,
            is_active=False  # Inactive
        )
        db.session.add(inactive_channel)
        db.session.commit()
        
        # Should still be considered "not synced" since no active channels
        response = client.get(f"/api/accounts/{test_account.id}/preview")
        assert response.status_code == 503
