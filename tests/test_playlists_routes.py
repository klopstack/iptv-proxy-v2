"""
Tests for playlist routes - configuration and M3U generation
"""
import json

import pytest

from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Tag, db


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
        yield account


@pytest.fixture
def test_channel_with_tag(app, test_account):
    """Create a test channel with tags"""
    with app.app_context():
        category = Category(
            account_id=test_account.id,
            category_id="cat1",
            category_name="Movies",
        )
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account.id,
            stream_id="ch1",
            name="Movie Channel HD",
            cleaned_name="Movie Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.flush()

        tag = Tag(name="HD")
        db.session.add(tag)
        db.session.flush()

        channel_tag = ChannelTag(
            account_id=test_account.id,
            stream_id="ch1",
            tag_id=tag.id,
        )
        db.session.add(channel_tag)
        db.session.commit()

        yield channel


@pytest.fixture
def test_playlist_config(app, test_account):
    """Create a test playlist configuration"""
    with app.app_context():
        config = PlaylistConfig(
            name="Test Playlist",
            description="Test playlist description",
            include_accounts=json.dumps([test_account.id]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config


# ============================================================================
# Playlist Config CRUD Tests
# ============================================================================


class TestPlaylistConfigCRUD:
    """Tests for playlist configuration CRUD operations"""

    def test_get_playlist_configs_empty(self, app, client):
        """Test getting playlist configs when none exist"""
        response = client.get("/api/playlist-configs")
        assert response.status_code == 200
        assert response.json == []

    def test_get_playlist_configs(self, app, client, test_playlist_config):
        """Test getting playlist configs"""
        response = client.get("/api/playlist-configs")
        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["name"] == "Test Playlist"
        assert "slug" in data[0]

    def test_create_playlist_config(self, app, client, test_account):
        """Test creating a new playlist config"""
        response = client.post(
            "/api/playlist-configs",
            json={
                "name": "New Playlist",
                "description": "A new test playlist",
                "include_accounts": [test_account.id],
                "exclude_accounts": [],
                "include_tags": ["HD"],
                "exclude_tags": ["SD"],
                "tag_match_mode": "any",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "New Playlist"
        assert data["include_accounts"] == [test_account.id]
        assert data["include_tags"] == ["HD"]

    def test_create_playlist_config_minimal(self, app, client):
        """Test creating a playlist config with minimal data"""
        response = client.post(
            "/api/playlist-configs",
            json={"name": "Minimal Playlist"},
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "Minimal Playlist"
        assert data["include_accounts"] == []
        assert data["tag_match_mode"] == "all"  # Default is 'all' per schema

    def test_create_playlist_config_missing_name(self, app, client):
        """Test creating a playlist config without name fails"""
        response = client.post(
            "/api/playlist-configs",
            json={"description": "No name provided"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_update_playlist_config(self, app, client, test_playlist_config):
        """Test updating a playlist config"""
        response = client.put(
            f"/api/playlist-configs/{test_playlist_config.id}",
            json={
                "name": "Updated Playlist",
                "description": "Updated description",
                "include_tags": ["HD", "4K"],
                "tag_match_mode": "all",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Updated Playlist"
        assert data["include_tags"] == ["HD", "4K"]
        assert data["tag_match_mode"] == "all"

    def test_update_playlist_config_not_found(self, app, client):
        """Test updating non-existent playlist config"""
        response = client.put(
            "/api/playlist-configs/999",
            json={"name": "Updated"},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_delete_playlist_config(self, app, client, test_playlist_config):
        """Test deleting a playlist config"""
        response = client.delete(f"/api/playlist-configs/{test_playlist_config.id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/playlist-configs")
        assert len(response.json) == 0

    def test_delete_playlist_config_not_found(self, app, client):
        """Test deleting non-existent playlist config"""
        response = client.delete("/api/playlist-configs/999")
        assert response.status_code == 404


# ============================================================================
# Playlist Preview Tests
# ============================================================================


class TestPlaylistPreview:
    """Tests for playlist preview functionality"""

    def test_preview_playlist_config(self, app, client, test_playlist_config, test_channel_with_tag):
        """Test previewing a playlist config"""
        from unittest.mock import patch

        mock_streams = [
            {"stream_id": 1, "name": "Channel 1", "category_id": "cat1", "stream_icon": "icon.png"},
            {"stream_id": 2, "name": "US| Channel 2", "category_id": "cat1", "stream_icon": "icon2.png"},
        ]
        mock_categories = [{"category_id": "cat1", "category_name": "Movies"}]

        with patch("routes.playlists.IPTVService"):
            with patch("routes.playlists.cache_service") as mock_cache:
                # Setup mocks
                mock_cache.get_cached_streams.return_value = mock_streams
                mock_cache.get_cached_categories.return_value = mock_categories

                response = client.get(f"/api/playlist-configs/{test_playlist_config.id}/preview")
                # Preview should return 200 and have expected structure
                assert response.status_code == 200
                data = response.json
                assert "total" in data
                assert "channels" in data

    def test_preview_playlist_config_not_found(self, app, client):
        """Test previewing non-existent playlist config"""
        response = client.get("/api/playlist-configs/999/preview")
        assert response.status_code == 404

    def test_preview_playlist_config_with_pagination(self, app, client, test_playlist_config):
        """Test previewing with pagination"""
        from unittest.mock import patch

        mock_streams = [
            {"stream_id": i, "name": f"Channel {i}", "category_id": "cat1", "stream_icon": "icon.png"}
            for i in range(20)
        ]
        mock_categories = [{"category_id": "cat1", "category_name": "Movies"}]

        with patch("routes.playlists.IPTVService"):
            with patch("routes.playlists.cache_service") as mock_cache:
                # Setup mocks
                mock_cache.get_cached_streams.return_value = mock_streams
                mock_cache.get_cached_categories.return_value = mock_categories

                response = client.get(f"/api/playlist-configs/{test_playlist_config.id}/preview?limit=10&offset=0")
                assert response.status_code == 200
                data = response.json
                # Response should have pagination structure
                assert "total" in data
                assert "limit" in data
                assert "offset" in data
                assert data["limit"] == 10
                assert data["offset"] == 0


# ============================================================================
# Slugify Tests
# ============================================================================


class TestSlugify:
    """Tests for slug generation"""

    def test_slug_in_response(self, app, client, test_playlist_config):
        """Test that slug is included in playlist config response"""
        response = client.get("/api/playlist-configs")
        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["slug"] == "test-playlist"  # "Test Playlist" -> "test-playlist"
