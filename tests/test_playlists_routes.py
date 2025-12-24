"""
Tests for playlist routes - configuration and M3U generation
"""
import json

import pytest

from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Tag, db


@pytest.fixture
def test_account(app):
    """Create a test account and return its ID"""
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
        account_id = account.id
    yield account_id


@pytest.fixture
def test_channel_with_tag(app, test_account):
    """Create a test channel with tags"""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Movies",
        )
        db.session.add(category)
        db.session.flush()

        channel = Channel(
            account_id=test_account,
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
            account_id=test_account,
            stream_id="ch1",
            tag_id=tag.id,
        )
        db.session.add(channel_tag)
        db.session.commit()

        channel_id = channel.id
    yield channel_id


@pytest.fixture
def test_playlist_config(app, test_account):
    """Create a test playlist configuration"""
    with app.app_context():
        config = PlaylistConfig(
            name="Test Playlist",
            description="Test playlist description",
            include_accounts=json.dumps([test_account]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id
    yield config_id


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
                "include_accounts": [test_account],
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
        assert data["include_accounts"] == [test_account]
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
            f"/api/playlist-configs/{test_playlist_config}",
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
        response = client.delete(f"/api/playlist-configs/{test_playlist_config}")
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

                response = client.get(f"/api/playlist-configs/{test_playlist_config}/preview")
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

                response = client.get(f"/api/playlist-configs/{test_playlist_config}/preview?limit=10&offset=0")
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


# ============================================================================
# Tag Filter Tests
# ============================================================================


class TestMatchesTagFilter:
    """Tests for _matches_tag_filter function"""

    def test_exclude_tags_takes_precedence(self, app):
        """Test that exclude tags take precedence over include"""
        from routes.playlists import _matches_tag_filter

        # Channel has US and HD tags
        channel_tags = {"US", "HD"}
        # Include US but exclude HD
        include_tags = ["US"]
        exclude_tags = ["HD"]

        # Should not match because HD is excluded
        assert _matches_tag_filter(channel_tags, include_tags, exclude_tags, "any") is False

    def test_include_tags_all_mode(self, app):
        """Test that all mode requires all include tags"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"US", "HD"}
        include_tags = ["US", "HD", "4K"]  # Need all three

        # Should not match - missing 4K
        assert _matches_tag_filter(channel_tags, include_tags, [], "all") is False

        # Should match when channel has all tags
        channel_tags = {"US", "HD", "4K"}
        assert _matches_tag_filter(channel_tags, include_tags, [], "all") is True

    def test_include_tags_any_mode(self, app):
        """Test that any mode requires at least one include tag"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"US", "HD"}
        include_tags = ["UK", "CA"]  # Neither present

        # Should not match - no matching tag
        assert _matches_tag_filter(channel_tags, include_tags, [], "any") is False

        # Add a matching tag
        include_tags = ["US", "UK"]
        assert _matches_tag_filter(channel_tags, include_tags, [], "any") is True

    def test_no_include_tags_includes_all(self, app):
        """Test that no include tags includes all (not excluded)"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"US", "HD"}
        include_tags = []  # No include filter
        exclude_tags = []

        # Should match - no restrictions
        assert _matches_tag_filter(channel_tags, include_tags, exclude_tags, "any") is True

    def test_case_insensitive_matching(self, app):
        """Test that tag matching is case insensitive"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"us", "hd"}  # lowercase
        include_tags = ["US", "HD"]  # uppercase

        assert _matches_tag_filter(channel_tags, include_tags, [], "all") is True


# ============================================================================
# M3U Generation Tests
# ============================================================================


class TestM3UGeneration:
    """Tests for M3U playlist generation"""

    def test_generate_playlist_account_not_found(self, app, client):
        """Test generating playlist for non-existent account"""
        response = client.get("/playlist/99999.m3u")
        assert response.status_code == 404

    def test_generate_playlist_account_disabled(self, app, client, test_account):
        """Test generating playlist for disabled account"""
        with app.app_context():
            from models import Account

            account = Account.query.get(test_account)
            account.enabled = False
            db.session.commit()

        response = client.get(f"/playlist/{test_account}.m3u")
        assert response.status_code == 403

    def test_generate_playlist_not_synced(self, app, client, test_account):
        """Test generating playlist for account without synced channels"""
        response = client.get(f"/playlist/{test_account}.m3u")
        assert response.status_code == 503  # Service unavailable

    def test_generate_playlist_with_channels(self, app, client, test_channel_with_tag, test_account):
        """Test generating playlist with synced channels"""
        from unittest.mock import patch

        with patch("routes.playlists.cache_service") as mock_cache:
            mock_cache.get_cached_categories.return_value = [{"category_id": "cat1", "category_name": "Movies"}]

            response = client.get(f"/playlist/{test_account}.m3u")
            # Should succeed
            assert response.status_code == 200
            assert b"#EXTM3U" in response.data


# ============================================================================
# Playlist Config M3U Generation Tests
# ============================================================================


class TestPlaylistConfigM3U:
    """Tests for playlist config M3U generation"""

    def test_generate_playlist_config_not_found(self, app, client):
        """Test generating M3U for non-existent config"""
        response = client.get("/playlist/config/99999.m3u")
        assert response.status_code == 404

    def test_generate_playlist_config_by_slug_not_found(self, app, client):
        """Test generating M3U by slug for non-existent config"""
        response = client.get("/playlist/config/nonexistent-config.m3u")
        assert response.status_code == 404

    def test_generate_playlist_config_disabled(self, app, client, test_playlist_config):
        """Test generating M3U for disabled config"""
        with app.app_context():
            from models import PlaylistConfig

            config = PlaylistConfig.query.get(test_playlist_config)
            config.enabled = False
            db.session.commit()

        response = client.get(f"/playlist/config/{test_playlist_config}.m3u")
        assert response.status_code == 403


# ============================================================================
# EPG Proxy Tests
# ============================================================================


class TestEPGProxy:
    """Tests for EPG proxy routes"""

    def test_proxy_epg_account_not_found(self, app, client):
        """Test proxying EPG for non-existent account"""
        response = client.get("/epg/99999.xml")
        assert response.status_code == 404

    def test_proxy_epg_account_disabled(self, app, client, test_account):
        """Test proxying EPG for disabled account"""
        with app.app_context():
            from models import Account

            account = Account.query.get(test_account)
            account.enabled = False
            db.session.commit()

        response = client.get(f"/epg/{test_account}.xml")
        assert response.status_code == 403

    def test_generate_epg_config_not_found(self, app, client):
        """Test generating EPG for non-existent config"""
        response = client.get("/epg/config/99999.xml")
        assert response.status_code == 404

    def test_generate_epg_config_by_slug_not_found(self, app, client):
        """Test generating EPG by slug for non-existent config"""
        response = client.get("/epg/config/nonexistent-config.xml")
        assert response.status_code == 404
