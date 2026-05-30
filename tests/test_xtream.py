"""
Tests for Xtream Codes API emulation routes (routes/xtream.py)

Covers:
- Authentication mechanisms
- Player API endpoints (user info, categories, streams)
- Direct stream URL handling
- Credential CRUD operations
- Channel filtering and collapsing
"""
import json
from unittest.mock import patch

import pytest

from models import Account, Channel, ChannelTag, PlaylistConfig, Tag, XtreamCredential, db

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_channels(app, test_account, test_category):
    """Create test channels"""
    with app.app_context():
        channels = []
        for i in range(3):
            channel = Channel(
                account_id=test_account,
                stream_id=str(1000 + i),
                name=f"Channel {i + 1}",
                cleaned_name=f"Channel {i + 1}",
                category_id=test_category,
                stream_icon=f"http://example.com/icon{i + 1}.png",
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            channels.append(channel)
        db.session.commit()
        # Get IDs before yielding
        for channel in channels:
            db.session.refresh(channel)
        yield channels


@pytest.fixture
def xtream_credential(app, test_account):
    """Create an Xtream credential linked to account"""
    with app.app_context():
        cred = XtreamCredential(
            username="xtream_user",
            password="xtream_pass",
            account_id=test_account,
            enabled=True,
            use_filters=False,
            collapse_duplicates=False,
        )
        db.session.add(cred)
        db.session.commit()
        db.session.refresh(cred)
        yield cred


@pytest.fixture
def playlist_config(app, test_account):
    """Create a playlist config"""
    with app.app_context():
        config = PlaylistConfig(
            name="Test Playlist",
            include_accounts=json.dumps([test_account]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def xtream_credential_playlist(app, playlist_config):
    """Create an Xtream credential linked to playlist config"""
    with app.app_context():
        cred = XtreamCredential(
            username="playlist_user",
            password="playlist_pass",
            playlist_config_id=playlist_config.id,
            enabled=True,
            use_filters=False,
            collapse_duplicates=False,
        )
        db.session.add(cred)
        db.session.commit()
        db.session.refresh(cred)
        yield cred


# ============================================================================
# Authentication Tests
# ============================================================================


class TestXtreamAuthentication:
    """Test Xtream authentication"""

    def test_authenticate_valid_account_credentials(self, app, client, xtream_credential, test_channels):
        """Test authentication with valid account credentials"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "xtream_user", "password": "xtream_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert data["user_info"]["auth"] == 1
            assert data["user_info"]["username"] == "xtream_user"

    def test_authenticate_invalid_credentials(self, app, client):
        """Test authentication with invalid credentials"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "invalid", "password": "invalid"},
            )
            assert response.status_code == 401
            assert response.json["user_info"]["auth"] == 0

    def test_authenticate_missing_credentials(self, app, client):
        """Test authentication with missing credentials"""
        with app.app_context():
            response = client.get("/player_api.php")
            assert response.status_code == 401

    def test_authenticate_disabled_credential(self, app, client, xtream_credential):
        """Test authentication with disabled credential"""
        with app.app_context():
            # Fetch and update within same session
            cred = db.session.get(XtreamCredential, xtream_credential.id)
            cred.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "xtream_user", "password": "xtream_pass"},
        )
        assert response.status_code == 401

    def test_authenticate_disabled_account(self, app, client, xtream_credential, test_account):
        """Test authentication with disabled account"""
        with app.app_context():
            # Fetch and update within same session
            acc = db.session.get(Account, test_account)
            acc.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "xtream_user", "password": "xtream_pass"},
        )
        assert response.status_code == 401

    def test_authenticate_playlist_config(self, app, client, xtream_credential_playlist, test_channels):
        """Test authentication with playlist config credential"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "playlist_user", "password": "playlist_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert data["user_info"]["auth"] == 1

    def test_authenticate_disabled_playlist_config(self, app, client, xtream_credential_playlist, playlist_config):
        """Test authentication with disabled playlist config"""
        with app.app_context():
            # Fetch and update within same session
            config = db.session.get(PlaylistConfig, playlist_config.id)
            config.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "playlist_user", "password": "playlist_pass"},
        )
        assert response.status_code == 401


# ============================================================================
# Player API Tests
# ============================================================================


class TestXtreamPlayerAPI:
    """Test Xtream player API endpoints"""

    def test_get_user_info(self, app, client, xtream_credential):
        """Test get_user_info endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "xtream_user", "password": "xtream_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert "user_info" in data
            assert "server_info" in data
            assert data["user_info"]["username"] == "xtream_user"
            assert data["user_info"]["auth"] == 1

    def test_get_live_categories(self, app, client, xtream_credential, test_channels):
        """Test get_live_categories endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_categories",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["category_name"] == "Test Category"

    def test_get_live_streams(self, app, client, xtream_credential, test_channels):
        """Test get_live_streams endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 3
            assert data[0]["name"] == "Channel 1"
            assert data[0]["stream_type"] == "live"

    def test_get_live_streams_by_category(self, app, client, xtream_credential, test_channels, test_category):
        """Test get_live_streams filtered by category"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                    "category_id": str(test_category),
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 3

    def test_get_vod_categories(self, app, client, xtream_credential):
        """VOD is not supported (live-only Xtream API)."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_categories",
                },
            )
            assert response.status_code == 400
            assert "Unknown action" in response.json["error"]

    def test_get_vod_streams(self, app, client, xtream_credential):
        """VOD is not supported (live-only Xtream API)."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_streams",
                },
            )
            assert response.status_code == 400

    def test_get_series_categories(self, app, client, xtream_credential):
        """Series is not supported (live-only Xtream API)."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_series_categories",
                },
            )
            assert response.status_code == 400

    def test_get_series(self, app, client, xtream_credential):
        """Series is not supported (live-only Xtream API)."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_series",
                },
            )
            assert response.status_code == 400

    def test_unknown_action(self, app, client, xtream_credential):
        """Test unknown action"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "unknown_action",
                },
            )
            assert response.status_code == 400
            assert "error" in response.json

    def test_get_short_epg(self, app, client, xtream_credential):
        """Test get_short_epg endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_short_epg",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert "epg_listings" in data

    def test_get_simple_data_table(self, app, client, xtream_credential, test_channels):
        """Test get_simple_data_table endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                    "stream_id": "1000",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert data["stream_id"] == 1000
            assert data["name"] == "Channel 1"

    def test_get_simple_data_table_missing_stream(self, app, client, xtream_credential):
        """Test get_simple_data_table with missing stream_id"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                },
            )
            assert response.status_code == 400
            assert "error" in response.json

    def test_get_simple_data_table_not_found(self, app, client, xtream_credential):
        """Test get_simple_data_table with non-existent stream"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                    "stream_id": "99999",
                },
            )
            assert response.status_code == 404


# ============================================================================
# Stream URL Tests
# ============================================================================


class TestXtreamStreamURLs:
    """Test Xtream stream URLs"""

    def test_live_stream_valid(self, app, client, xtream_credential, test_channels):
        """Test valid live stream URL - stream_id type conversion"""
        with app.app_context():
            # Stream ID in URL is parsed as integer (1000) but must be compared
            # to string stream IDs in database ("1000"). The route should handle conversion.
            response = client.get("/live/xtream_user/xtream_pass/1000.ts")
            # Should redirect to internal stream proxy when found
            assert response.status_code == 302

    def test_live_stream_type_mismatch_fix(self, app, client, xtream_credential, test_channels):
        """Test that stream_id integer from route matches string in database"""
        with app.app_context():
            # Create a channel with specific stream_id
            channel = db.session.query(Channel).filter_by(stream_id="1000").first()
            assert channel is not None, "Test channel with stream_id='1000' should exist"
            assert isinstance(channel.stream_id, str), "Channel stream_id should be stored as string"

            # Request using integer in URL
            response = client.get("/live/xtream_user/xtream_pass/1000.ts")
            assert response.status_code == 302, "Integer stream_id from URL should match string in database"

            # Verify the redirect location contains the correct stream_id
            location = response.headers.get("Location")
            assert location is not None
            assert "1000" in location

    def test_live_stream_invalid_credentials(self, app, client):
        """Test live stream with invalid credentials"""
        with app.app_context():
            response = client.get("/live/invalid/invalid/1000.ts")
            assert response.status_code == 401

    def test_live_stream_not_found(self, app, client, xtream_credential):
        """Test live stream with non-existent stream ID"""
        with app.app_context():
            response = client.get("/live/xtream_user/xtream_pass/99999.ts")
            assert response.status_code == 404

    def test_live_stream_without_extension(self, app, client, xtream_credential, test_channels):
        """Test live stream URL without extension"""
        with app.app_context():
            response = client.get("/live/xtream_user/xtream_pass/1000")
            # Should redirect same as with extension
            assert response.status_code == 302

    def test_movie_stream(self, app, client, xtream_credential):
        """Test movie stream URL (not implemented)"""
        with app.app_context():
            response = client.get("/movie/xtream_user/xtream_pass/1000.mp4")
            assert response.status_code == 404
            assert "VOD not available" in response.json["error"]

    def test_series_stream(self, app, client, xtream_credential):
        """Test series stream URL (not implemented)"""
        with app.app_context():
            response = client.get("/series/xtream_user/xtream_pass/1000.mp4")
            assert response.status_code == 404
            assert "Series not available" in response.json["error"]

    def test_xmltv_epg_account(self, app, client, xtream_credential, test_account):
        """Test XMLTV EPG endpoint with account"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "xtream_user", "password": "xtream_pass"})
            assert response.status_code == 302
            assert f"/epg/{test_account}.xml" in response.location

    def test_xmltv_epg_playlist_config(self, app, client, xtream_credential_playlist, playlist_config):
        """Test XMLTV EPG endpoint with playlist config"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "playlist_user", "password": "playlist_pass"})
            assert response.status_code == 302
            assert f"/epg/config/{playlist_config.slug}.xml" in response.location

    def test_xmltv_epg_invalid_credentials(self, app, client):
        """Test XMLTV EPG with invalid credentials"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "invalid", "password": "invalid"})
            assert response.status_code == 401


# ============================================================================
# Credential Management Tests
# ============================================================================


class TestXtreamCredentialManagement:
    """Test Xtream credential CRUD operations"""

    def test_list_credentials(self, app, client, xtream_credential):
        """Test listing credentials"""
        with app.app_context():
            response = client.get("/api/xtream-credentials")
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["username"] == "xtream_user"

    def test_create_credential_account(self, app, client, test_account):
        """Test creating credential for account"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "new_user",
                    "password": "new_pass",
                    "account_id": test_account,
                    "use_filters": True,
                    "collapse_duplicates": False,
                },
            )
            assert response.status_code == 201
            data = response.json
            assert data["username"] == "new_user"
            assert data["account_id"] == test_account

    def test_create_credential_playlist_config(self, app, client, playlist_config):
        """Test creating credential for playlist config"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "config_user",
                    "password": "config_pass",
                    "playlist_config_id": playlist_config.id,
                },
            )
            assert response.status_code == 201
            data = response.json
            assert data["playlist_config_id"] == playlist_config.id

    def test_create_credential_missing_username(self, app, client, test_account):
        """Test creating credential without username"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={"password": "pass", "account_id": test_account},
            )
            assert response.status_code == 400

    def test_create_credential_missing_target(self, app, client):
        """Test creating credential without account or playlist config"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={"username": "user", "password": "pass"},
            )
            assert response.status_code == 400

    def test_create_credential_duplicate_username(self, app, client, xtream_credential, test_account):
        """Test creating credential with duplicate username"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "xtream_user",
                    "password": "different_pass",
                    "account_id": test_account,
                },
            )
            assert response.status_code == 409

    def test_update_credential(self, app, client, xtream_credential):
        """Test updating credential"""
        with app.app_context():
            response = client.put(
                f"/api/xtream-credentials/{xtream_credential.id}",
                json={"password": "new_password", "use_filters": True},
            )
            assert response.status_code == 200
            data = response.json
            assert data["username"] == "xtream_user"

            # Verify update
            updated = db.session.get(XtreamCredential, xtream_credential.id)
            assert updated.password == "new_password"
            assert updated.use_filters is True

    def test_update_credential_not_found(self, app, client):
        """Test updating non-existent credential"""
        with app.app_context():
            response = client.put("/api/xtream-credentials/99999", json={"password": "new_pass"})
            assert response.status_code == 404

    def test_delete_credential(self, app, client, xtream_credential):
        """Test deleting credential"""
        with app.app_context():
            response = client.delete(f"/api/xtream-credentials/{xtream_credential.id}")
            assert response.status_code == 204

            # Verify deletion
            deleted = db.session.get(XtreamCredential, xtream_credential.id)
            assert deleted is None

    def test_delete_credential_not_found(self, app, client):
        """Test deleting non-existent credential"""
        with app.app_context():
            response = client.delete("/api/xtream-credentials/99999")
            assert response.status_code == 404


# ============================================================================
# Channel Filtering Tests
# ============================================================================


class TestXtreamChannelFiltering:
    """Test channel filtering functionality"""

    def test_channels_with_filters_enabled(self, app, client, test_account, test_channels):
        """Test that filters are applied when enabled"""
        with app.app_context():
            # Create credential with filters enabled
            cred = XtreamCredential(
                username="filter_user",
                password="filter_pass",
                account_id=test_account,
                enabled=True,
                use_filters=True,
            )
            db.session.add(cred)
            db.session.commit()

            with patch("services.filter_service.FilterService.apply_filters_to_channels") as mock_filter:
                mock_filter.return_value = test_channels[:2]  # Return only 2 channels

                response = client.get(
                    "/player_api.php",
                    query_string={
                        "username": "filter_user",
                        "password": "filter_pass",
                        "action": "get_live_streams",
                    },
                )
                assert response.status_code == 200
                data = response.json
                assert len(data) == 2
                mock_filter.assert_called_once()

    def test_channels_inactive_excluded(self, app, client, xtream_credential, test_channels):
        """Test that inactive channels are excluded"""
        with app.app_context():
            # Mark one channel as inactive and commit
            channel = Channel.query.filter_by(stream_id="1000").first()
            channel.is_active = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
            },
        )
        assert response.status_code == 200
        data = response.json
        # Check that the inactive channel is not in the results
        stream_ids = [s["stream_id"] for s in data]
        assert 1000 not in stream_ids
        assert len(data) == 2  # Only 2 active channels

    def test_playlist_config_with_tag_filters(self, app, client, test_account, test_channels, playlist_config):
        """Test playlist config with tag filtering"""
        with app.app_context():
            # Create tags
            tag = Tag(name="HD")
            db.session.add(tag)
            db.session.flush()

            # Link tag to first channel
            channel_tag = ChannelTag(account_id=test_account, stream_id=test_channels[0].stream_id, tag_id=tag.id)
            db.session.add(channel_tag)
            db.session.commit()

            # Re-fetch playlist config from database to ensure it's attached to this session
            config = db.session.get(PlaylistConfig, playlist_config.id)
            # Update playlist config to include only HD tag
            config.include_tags = json.dumps([tag.id])
            db.session.commit()

            # Create credential for playlist config
            cred = XtreamCredential(
                username="tag_user",
                password="tag_pass",
                playlist_config_id=playlist_config.id,
                enabled=True,
            )
            db.session.add(cred)
            db.session.commit()

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "tag_user",
                    "password": "tag_pass",
                    "action": "get_live_streams",
                },
            )
            assert response.status_code == 200
            data = response.json
            # Should only include channel with HD tag
            assert len(data) == 1
            assert data[0]["stream_id"] == 1000

    def test_collapse_duplicates(self, app, client, test_account, test_category):
        """Test duplicate channel collapsing"""
        with app.app_context():
            # Create duplicate channels with different names but same base name
            for i, quality in enumerate(["SD", "HD", "4K"]):
                channel = Channel(
                    account_id=test_account,
                    stream_id=f"{2000 + i}",
                    name=f"Test Channel {quality}",
                    cleaned_name="Test Channel",
                    category_id=test_category,
                    is_active=True,
                    is_visible=True,
                )
                db.session.add(channel)
            db.session.commit()

            # Create credential with collapse enabled
            cred = XtreamCredential(
                username="collapse_user",
                password="collapse_pass",
                account_id=test_account,
                enabled=True,
                collapse_duplicates=True,
            )
            db.session.add(cred)
            db.session.commit()

        with patch("services.quality_service.QualityService.collapse_duplicates") as mock_collapse:
            # Mock returns only one channel (highest quality)
            with app.app_context():
                ch = Channel.query.filter_by(stream_id="2002").first()
                mock_collapse.return_value = [
                    {
                        "channel": ch,
                        "stream_id": "2002",
                        "cleaned_name": "Test Channel",
                        "tags": ["4K"],
                    }
                ]

                response = client.get(
                    "/player_api.php",
                    query_string={
                        "username": "collapse_user",
                        "password": "collapse_pass",
                        "action": "get_live_streams",
                    },
                )
                assert response.status_code == 200
                # Should have called collapse
                assert mock_collapse.called


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestXtreamHelpers:
    """Test helper functions"""

    def test_get_proxy_base_url_default(self, app, client):
        """Test getting proxy base URL without custom hostname"""
        with app.app_context():
            from services.url_service import get_proxy_base_url

            with client:
                client.get("/")  # Establish request context
                base_url = get_proxy_base_url()
                assert base_url.startswith("http://")

    def test_get_proxy_base_url_custom(self, app, client):
        """Test getting proxy base URL with custom hostname"""
        with app.app_context():
            from models import Settings
            from services.url_service import get_proxy_base_url

            # Set custom proxy hostname
            Settings.set("proxy_hostname", "proxy.example.com")
            db.session.commit()

            with client:
                client.get("/")  # Establish request context
                base_url = get_proxy_base_url()
                assert "proxy.example.com" in base_url
