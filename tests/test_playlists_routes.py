"""
Tests for playlist routes - configuration and M3U generation
"""
import json

import pytest

from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Tag, db
from services.channel_query_service import ChannelQueryService


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
        """Test previewing a playlist config from synced database channels"""
        response = client.get(f"/api/playlist-configs/{test_playlist_config}/preview")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["showing"] == 1
        assert len(data["channels"]) == 1
        channel = data["channels"][0]
        assert channel["stream_id"] == "ch1"
        assert channel["original_name"] == "Movie Channel HD"
        assert channel["cleaned_name"] == "Movie Channel"
        assert channel["category"] == "Movies"
        assert channel["tags"] == ["HD"]

    def test_preview_playlist_config_not_found(self, app, client):
        """Test previewing non-existent playlist config"""
        response = client.get("/api/playlist-configs/999/preview")
        assert response.status_code == 404

    def test_preview_playlist_config_with_pagination(self, app, client, test_playlist_config, test_account):
        """Test previewing with pagination"""
        with app.app_context():
            category = Category(
                account_id=test_account,
                category_id="cat2",
                category_name="Sports",
            )
            db.session.add(category)
            db.session.flush()

            for i in range(20):
                db.session.add(
                    Channel(
                        account_id=test_account,
                        stream_id=f"ch{i}",
                        name=f"Test Network {i}",
                        cleaned_name=f"Test Network {i}",
                        category_id=category.id,
                        is_active=True,
                        is_visible=True,
                    )
                )
            db.session.commit()

        response = client.get(f"/api/playlist-configs/{test_playlist_config}/preview?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 20
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert data["showing"] == 10
        assert data["has_more"] is True

    def test_preview_playlist_config_unsynced_account(self, app, client):
        """Test preview returns 503 when account is not synced"""
        with app.app_context():
            account = Account(
                name="Unsynced Account",
                username="user",
                password="pass",
                server="example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            config = PlaylistConfig(
                name="Unsynced Preview",
                include_accounts=json.dumps([account.id]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps([]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/api/playlist-configs/{config_id}/preview")
        assert response.status_code == 503

    def test_preview_playlist_config_tag_filter(self, app, client, test_account):
        """Test preview respects include_tags filter from database tags"""
        with app.app_context():
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            hd_channel = Channel(
                account_id=test_account,
                stream_id="hd1",
                name="HD Channel",
                cleaned_name="HD Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            sd_channel = Channel(
                account_id=test_account,
                stream_id="sd1",
                name="SD Channel",
                cleaned_name="SD Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(hd_channel)
            db.session.add(sd_channel)
            db.session.flush()

            hd_tag = Tag(name="HD")
            db.session.add(hd_tag)
            db.session.flush()
            db.session.add(
                ChannelTag(
                    account_id=test_account,
                    stream_id="hd1",
                    tag_id=hd_tag.id,
                )
            )

            config = PlaylistConfig(
                name="HD Only Preview",
                include_accounts=json.dumps([test_account]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps(["HD"]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/api/playlist-configs/{config_id}/preview")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["channels"][0]["stream_id"] == "hd1"

    def test_preview_matches_m3u_channel_list(self, app, client, test_playlist_config, test_channel_with_tag):
        """Test preview channel list matches M3U generation for same config"""
        preview_response = client.get(f"/api/playlist-configs/{test_playlist_config}/preview")
        m3u_response = client.get(f"/playlist/config/{test_playlist_config}.m3u?proxy_icons=false")

        assert preview_response.status_code == 200
        assert m3u_response.status_code == 200

        preview_stream_ids = {ch["stream_id"] for ch in preview_response.json["channels"]}
        with app.app_context():
            config = db.session.get(PlaylistConfig, test_playlist_config)
            expected_channels = ChannelQueryService.channels_for_playlist_config(
                config,
                apply_filters=True,
                apply_ppv_visibility=True,
            )
            expected_stream_ids = {ch.stream_id for ch in expected_channels}

        assert preview_stream_ids == expected_stream_ids


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

            account = db.session.get(Account, test_account)
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
        response = client.get(f"/playlist/{test_account}.m3u")
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

            config = db.session.get(PlaylistConfig, test_playlist_config)
            config.enabled = False
            db.session.commit()

        response = client.get(f"/playlist/config/{test_playlist_config}.m3u")
        assert response.status_code == 403

    def test_generate_playlist_config_default_proxy(self, app, client, test_playlist_config, test_account, test_channel_with_tag):
        """Test that config M3U defaults to proxied stream URLs"""
        response = client.get(f"/playlist/config/{test_playlist_config}.m3u?proxy_icons=false")

        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "/stream/" in content
        assert f"/{test_account}/" in content

    def test_generate_playlist_config_direct_urls(self, app, client, test_playlist_config, test_account, test_channel_with_tag):
        """Test that config M3U honors proxy=false"""
        with app.app_context():
            from models import Account

            account = db.session.get(Account, test_account)

        response = client.get(f"/playlist/config/{test_playlist_config}.m3u?proxy=false&proxy_icons=false")

        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert f"https://{account.server}/live/" in content


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

            account = db.session.get(Account, test_account)
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

    def test_proxy_epg_account_not_synced(self, app, client, test_account):
        """Test proxying EPG for account with no synced channels"""
        response = client.get(f"/epg/{test_account}.xml")
        assert response.status_code == 503  # ServiceUnavailableError

    def test_proxy_epg_with_channels(self, app, client, test_account, test_channel_with_tag):
        """Test proxying EPG with channels synced"""
        response = client.get(f"/epg/{test_account}.xml")
        assert response.status_code == 200
        assert "application/xml" in response.content_type
        # Should contain valid XMLTV structure
        assert b"<?xml version=" in response.data
        assert b"<tv" in response.data

    def test_proxy_epg_no_channels(self, app, client, test_account):
        """Test proxying EPG returns minimal XMLTV when no visible channels"""
        with app.app_context():
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            # Create channel but mark as not visible
            channel = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="Test Channel",
                category_id=category.id,
                is_active=True,
                is_visible=False,  # Not visible
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get(f"/epg/{test_account}.xml")
        assert response.status_code == 200
        assert "application/xml" in response.content_type
        # Should contain minimal valid XMLTV
        assert b"<?xml version=" in response.data
        assert b'generator-info-name="iptv-proxy-v2"' in response.data

    def test_proxy_epg_collapse_duplicates(self, app, client, test_account):
        """Test proxying EPG with collapse_duplicates parameter"""
        with app.app_context():
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            # Create two channels with same base name but different tags
            for i in range(2):
                channel = Channel(
                    account_id=test_account,
                    stream_id=f"ch{i}",
                    name=f"Test Channel {i}",
                    cleaned_name="Test Channel",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                )
                db.session.add(channel)
            db.session.commit()

        response = client.get(f"/epg/{test_account}.xml?collapse_duplicates=true")
        assert response.status_code == 200
        assert "application/xml" in response.content_type
        assert b"<?xml version=" in response.data

    def test_epg_excludes_ppv_hide_all_matching_m3u(self, app, client):
        """PPV channels hidden from M3U (hide_all) must also be absent from account EPG."""
        with app.app_context():
            account = Account(
                name="PPV Hide All",
                username="ppv_user",
                password="ppv_pass",
                server="example.com",
                enabled=True,
                ppv_visibility="hide_all",
            )
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="cat1",
                category_name="Sports",
            )
            db.session.add(category)
            db.session.flush()

            regular = Channel(
                account_id=account.id,
                stream_id="regular1",
                name="Regular Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            ppv = Channel(
                account_id=account.id,
                stream_id="ppv1",
                name="PPV Event",
                category_id=category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([regular, ppv])
            db.session.commit()
            account_id = account.id
            ppv_tvg_id = ChannelQueryService.epg_channel_id_for_channel(ppv)

        m3u_response = client.get(f"/playlist/{account_id}.m3u")
        assert m3u_response.status_code == 200
        m3u_content = m3u_response.data.decode("utf-8")
        assert f'tvg-id="{ppv_tvg_id}"' not in m3u_content
        assert "Regular Channel" in m3u_content

        epg_response = client.get(f"/epg/{account_id}.xml")
        assert epg_response.status_code == 200
        epg_content = epg_response.data.decode("utf-8")
        assert f'<channel id="{ppv_tvg_id}"' not in epg_content
        assert f'id="{ppv_tvg_id}"' not in epg_content
