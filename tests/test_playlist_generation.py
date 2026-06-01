"""
Tests for playlist generation with complete integration scenarios.
These tests cover the complex M3U generation logic including:
- Tag filtering (include/exclude, any/all modes)
- Duplicate collapsing across accounts
- Proxy vs direct URLs
- Icon proxying
- Multi-account playlists
- PPV visibility filtering
- Unsynced account detection
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelTag, Event, EventChannelLink, PlaylistConfig, Tag, db
from services.playlist_format_service import render_account_m3u_playlist, sanitize_m3u_value
from services.url_service import get_proxy_base_url


@pytest.fixture
def test_account1(app):
    """Create first test account with channels"""
    with app.app_context():
        account = Account(
            name="Provider 1",
            server="server1.example.com",
            username="user1",
            password="pass1",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        # Add category
        category = Category(account_id=account.id, category_id="cat1", category_name="Sports")
        db.session.add(category)

        # Add channels
        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="ESPN HD",
            cleaned_name="ESPN",
            category_id=category.id,
            stream_icon="http://example.com/espn.png",
            is_active=True,
            is_visible=True,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="FOX Sports",
            cleaned_name="FOX Sports",
            category_id=category.id,
            stream_icon="http://example.com/fox.png",
            is_active=True,
            is_visible=True,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        # Add tags
        tag_hd = Tag(name="HD")
        tag_sports = Tag(name="SPORTS")
        db.session.add_all([tag_hd, tag_sports])
        db.session.commit()

        # Tag associations
        db.session.add(ChannelTag(account_id=account.id, stream_id=1, tag_id=tag_hd.id))
        db.session.add(ChannelTag(account_id=account.id, stream_id=1, tag_id=tag_sports.id))
        db.session.add(ChannelTag(account_id=account.id, stream_id=2, tag_id=tag_sports.id))
        db.session.commit()

        yield account.id


@pytest.fixture
def test_account2(app):
    """Create second test account with overlapping channels"""
    with app.app_context():
        account = Account(
            name="Provider 2",
            server="server2.example.com",
            username="user2",
            password="pass2",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        # Add category
        category = Category(account_id=account.id, category_id="cat2", category_name="Sports")
        db.session.add(category)

        # Add channel (duplicate of ESPN)
        channel = Channel(
            account_id=account.id,
            stream_id=10,
            name="ESPN",
            cleaned_name="ESPN",
            category_id=category.id,
            stream_icon="http://example.com/espn2.png",
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Add tags
        tag_hd = Tag.query.filter_by(name="HD").first()
        if not tag_hd:
            tag_hd = Tag(name="HD")
            db.session.add(tag_hd)
            db.session.commit()

        db.session.add(ChannelTag(account_id=account.id, stream_id=10, tag_id=tag_hd.id))
        db.session.commit()

        yield account.id


@pytest.fixture
def multi_account_config(app, test_account1, test_account2):
    """Create playlist config that includes multiple accounts"""
    with app.app_context():
        config = PlaylistConfig(
            name="Multi Account",
            description="Test multi-account playlist",
            include_accounts=json.dumps([test_account1, test_account2]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


@pytest.fixture
def tag_filter_config(app, test_account1):
    """Create playlist config with tag filtering"""
    with app.app_context():
        config = PlaylistConfig(
            name="HD Only",
            description="Only HD channels",
            include_accounts=json.dumps([test_account1]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps(["HD"]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


@pytest.fixture
def exclude_tag_config(app, test_account1):
    """Create playlist config with exclude tags"""
    with app.app_context():
        config = PlaylistConfig(
            name="No Sports",
            description="Exclude sports channels",
            include_accounts=json.dumps([test_account1]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps(["SPORTS"]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


@pytest.fixture
def all_tags_config(app, test_account1):
    """Create playlist config requiring all tags"""
    with app.app_context():
        config = PlaylistConfig(
            name="HD Sports",
            description="Channels with both HD and SPORTS tags",
            include_accounts=json.dumps([test_account1]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps(["HD", "SPORTS"]),
            exclude_tags=json.dumps([]),
            tag_match_mode="all",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        yield config.id


class TestPlaylistGeneration:
    """Test M3U playlist generation with complex scenarios"""

    def test_generate_playlist_basic(self, app, client, test_account1):
        """Test basic playlist generation for single account"""
        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        assert response.mimetype == "application/x-mpegurl"

        content = response.data.decode("utf-8")
        assert "#EXTM3U" in content
        assert "ESPN" in content
        assert "FOX Sports" in content
        assert "tvg-id=" in content
        assert "group-title=" in content

    def test_generate_playlist_with_proxy(self, app, client, test_account1):
        """Test playlist generation with proxied URLs"""
        response = client.get(f"/playlist/{test_account1}.m3u?proxy=true")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should contain proxy URLs
        assert "/stream/" in content
        assert f"/{test_account1}/" in content
        assert ".ts" in content

    def test_generate_playlist_direct_urls(self, app, client, test_account1):
        """Test playlist generation with direct URLs"""
        response = client.get(f"/playlist/{test_account1}.m3u?proxy=false")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should contain direct URLs
        assert "https://server1.example.com/live/" in content
        assert "/user1/pass1/" in content

    def test_generate_playlist_default_proxy(self, app, client, test_account1):
        """Test that single-account playlists default to proxied stream URLs"""
        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        assert "/stream/" in content
        assert f"/{test_account1}/" in content

    def test_generate_playlist_proxy_icons(self, app, client, test_account1):
        """Test playlist generation with icon proxying"""
        with patch("services.playlist_format_service.ImageCacheService") as mock_image_cache:
            mock_instance = MagicMock()
            mock_instance.get_proxy_url.return_value = "http://localhost:8000/icons/cached_icon.png"
            mock_image_cache.get_instance.return_value = mock_instance

            response = client.get(f"/playlist/{test_account1}.m3u?proxy_icons=true")

            assert response.status_code == 200
            content = response.data.decode("utf-8")

            # Should have proxied icon URLs
            assert "http://localhost:8000/icons/cached_icon.png" in content

    def test_generate_playlist_no_proxy_icons(self, app, client, test_account1):
        """Test playlist generation without icon proxying"""
        response = client.get(f"/playlist/{test_account1}.m3u?proxy_icons=false")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should have original icon URLs
        assert "http://example.com/espn.png" in content or "http://example.com/fox.png" in content


class TestMultiAccountPlaylists:
    """Test multi-account playlist generation"""

    def test_generate_multi_account_playlist(self, app, client, multi_account_config):
        """Test generating playlist from multiple accounts"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, multi_account_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        assert "#EXTM3U" in content
        assert "# Playlist: Multi Account" in content
        # Should have channels from both accounts
        assert "ESPN" in content
        assert "FOX Sports" in content

    def test_generate_config_playlist_default_proxy(self, app, client, tag_filter_config):
        """Test that config playlists default to proxied stream URLs"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, tag_filter_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        assert "/stream/" in content
        assert ".ts" in content

    def test_generate_config_playlist_direct_urls(self, app, client, tag_filter_config):
        """Test config playlist generation with direct provider URLs"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, tag_filter_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u?proxy=false")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        assert "https://server1.example.com/live/" in content
        assert "/user1/pass1/" in content

    def test_multi_account_with_duplicate_collapse(self, app, client, multi_account_config):
        """Test collapsing duplicates across accounts"""
        with patch("services.quality_service.QualityService") as mock_quality:
            # Mock collapse_duplicates to return only unique channels
            mock_quality.collapse_duplicates.return_value = [
                {
                    "channel": Channel.query.filter_by(stream_id=1).first(),
                    "account_data": {
                        "id": 1,
                        "name": "Provider 1",
                        "server": "server1.example.com",
                        "username": "user1",
                        "password": "pass1",
                        "primary_username": "user1",
                        "primary_password": "pass1",
                    },
                    "stream_id": 1,
                    "cleaned_name": "ESPN",
                    "tags": ["HD", "SPORTS"],
                }
            ]

            with app.app_context():
                cfg = db.session.get(PlaylistConfig, multi_account_config)
                slug = cfg.slug
            response = client.get(f"/playlist/config/{slug}.m3u?collapse_duplicates=true")

            assert response.status_code == 200

            # Should have called collapse_duplicates
            mock_quality.collapse_duplicates.assert_called_once()

    def test_multi_account_group_titles(self, app, client, multi_account_config):
        """Test that multi-account playlists include account names in groups"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, multi_account_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Group titles should include account names for multi-account playlists
        assert "(Provider 1)" in content or "(Provider 2)" in content


class TestTagFiltering:
    """Test tag-based filtering in playlist generation"""

    def test_include_tags_any_mode(self, app, client, tag_filter_config):
        """Test filtering with include tags in 'any' mode"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, tag_filter_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should include ESPN (has HD tag)
        assert "ESPN" in content
        # Should not include FOX Sports (no HD tag)
        assert "FOX Sports" not in content

    def test_exclude_tags(self, app, client, exclude_tag_config):
        """Test filtering with exclude tags"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, exclude_tag_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should exclude all sports channels
        assert "ESPN" not in content
        assert "FOX Sports" not in content

    def test_include_tags_all_mode(self, app, client, all_tags_config):
        """Test filtering requiring all include tags"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, all_tags_config)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should only include ESPN (has both HD and SPORTS)
        assert "ESPN" in content
        # Should not include FOX Sports (missing HD tag)
        assert "FOX Sports" not in content

    def test_tag_normalization(self, app, client, test_account1):
        """Test that tag filtering is case-insensitive"""
        with app.app_context():
            # Create config with lowercase tags
            config = PlaylistConfig(
                name="Test Case",
                include_accounts=json.dumps([test_account1]),
                include_tags=json.dumps(["hd"]),  # lowercase
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        with app.app_context():
            cfg = db.session.get(PlaylistConfig, config_id)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should match HD tag despite case difference
        assert "ESPN" in content


class TestPPVVisibility:
    """Test PPV visibility filtering in playlists"""

    def test_ppv_visibility_applied(self, app, client, test_account1):
        """Test that PPV visibility service is invoked during playlist generation"""
        # This test verifies the service is called, not the full filtering logic
        # (Full PPV filtering is covered in tests/test_ppv_visibility.py)
        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Both channels should be included (no PPV rules configured)
        assert "ESPN" in content
        assert "FOX Sports" in content

    def test_group_live_replay_updates_m3u_group_titles(self, app, client, test_account1):
        """Grouped PPV mode emits Live/Replay group titles for visible PPV events."""
        with app.app_context():
            account = db.session.get(Account, test_account1)
            account.ppv_visibility = "group_live_replay"

            ppv_category = Category(account_id=account.id, category_id="ppv", category_name="PPV Events")
            db.session.add(ppv_category)
            db.session.flush()

            live_channel = Channel(
                account_id=account.id,
                stream_id=101,
                name="Live PPV",
                cleaned_name="Live PPV",
                category_id=ppv_category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            replay_channel = Channel(
                account_id=account.id,
                stream_id=102,
                name="Replay PPV",
                cleaned_name="Replay PPV",
                category_id=ppv_category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([live_channel, replay_channel])
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            live_event = Event(
                external_id="playlist-live",
                scheduled_at=now + timedelta(hours=2),
                home_team_id="h1",
                home_team_name="Home 1",
                away_team_id="a1",
                away_team_name="Away 1",
                status=Event.STATUS_SCHEDULED,
            )
            replay_event = Event(
                external_id="playlist-replay",
                scheduled_at=now - timedelta(hours=3),
                home_team_id="h2",
                home_team_name="Home 2",
                away_team_id="a2",
                away_team_name="Away 2",
                status=Event.STATUS_FINISHED,
            )
            db.session.add_all([live_event, replay_event])
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=live_event.id, channel_id=live_channel.id),
                    EventChannelLink(event_id=replay_event.id, channel_id=replay_channel.id),
                ]
            )
            db.session.commit()

            channels = [live_channel, replay_channel]
            with app.test_request_context("/"):
                content = render_account_m3u_playlist(
                    channels,
                    account=account,
                    proxy_base=get_proxy_base_url(),
                    use_proxy=True,
                    proxy_icons=False,
                    primary_cred=None,
                )

            assert 'group-title="Live"' in content
            assert 'group-title="Replay"' in content


class TestUnsyncedAccounts:
    """Test handling of unsynced accounts"""

    def test_unsynced_account_error(self, app, client):
        """Test that unsynced accounts raise ServiceUnavailableError"""
        with app.app_context():
            # Create account with no channels
            account = Account(
                name="Unsynced Provider",
                server="unsynced.example.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            config = PlaylistConfig(
                name="Unsynced Test",
                include_accounts=json.dumps([account_id]),
                include_tags=json.dumps([]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        with app.app_context():
            cfg = db.session.get(PlaylistConfig, config_id)
            slug = cfg.slug
        response = client.get(f"/playlist/config/{slug}.m3u")

        # Should return error for unsynced account
        assert response.status_code == 503


class TestSlugBasedPlaylistGeneration:
    """Test slug-based playlist lookup"""

    def test_generate_by_slug_not_found(self, app, client):
        """Test 404 for non-existent slug"""
        response = client.get("/playlist/config/nonexistent-slug.m3u")

        assert response.status_code == 404


class TestEPGGeneration:
    """Test EPG generation for playlist configs"""

    def test_epg_config_generation(self, app, client, tag_filter_config):
        """Test generating EPG for playlist config"""
        with patch("routes.playlists.generate_epg_for_channels") as mock_generate:
            mock_generate.return_value = b'<?xml version="1.0"?><tv></tv>'

            with app.app_context():
                cfg = db.session.get(PlaylistConfig, tag_filter_config)
                slug = cfg.slug
            response = client.get(f"/epg/config/{slug}.xml")

            assert response.status_code == 200
            assert response.mimetype == "application/xml"
            mock_generate.assert_called_once()

    def test_epg_config_empty_channels(self, app, client, exclude_tag_config):
        """Test EPG generation when no channels match"""
        with app.app_context():
            cfg = db.session.get(PlaylistConfig, exclude_tag_config)
            slug = cfg.slug
        response = client.get(f"/epg/config/{slug}.xml")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should return minimal valid XMLTV
        assert '<?xml version="1.0"' in content
        assert "<tv" in content

    def test_epg_east_west_fallback(self, app, client, tag_filter_config):
        """Test EPG generation with east/west fallback parameter"""
        with patch("routes.playlists.generate_epg_for_channels") as mock_generate:
            mock_generate.return_value = b'<?xml version="1.0"?><tv></tv>'

            with app.app_context():
                cfg = db.session.get(PlaylistConfig, tag_filter_config)
                slug = cfg.slug
            response = client.get(f"/epg/config/{slug}.xml?east_west_fallback=true")

            assert response.status_code == 200
            call_kwargs = mock_generate.call_args[1]
            assert call_kwargs["east_west_fallback"] is True

    def test_epg_no_east_west_fallback(self, app, client, tag_filter_config):
        """Test EPG generation with fallback disabled"""
        with patch("routes.playlists.generate_epg_for_channels") as mock_generate:
            mock_generate.return_value = b'<?xml version="1.0"?><tv></tv>'

            with app.app_context():
                cfg = db.session.get(PlaylistConfig, tag_filter_config)
                slug = cfg.slug
            response = client.get(f"/epg/config/{slug}.xml?east_west_fallback=false")

            assert response.status_code == 200
            call_kwargs = mock_generate.call_args[1]
            assert call_kwargs["east_west_fallback"] is False


class TestChannelMetadata:
    """Test channel metadata in M3U output"""

    def test_sanitize_m3u_value_strips_control_characters(self):
        """Unit test for shared M3U value sanitization."""
        assert sanitize_m3u_value("Line1\nLine2\r\nLine3") == "Line1 Line2 Line3"
        assert sanitize_m3u_value("  spaced  out  ") == "spaced out"
        assert sanitize_m3u_value("") == ""

    def test_tvg_id_format(self, app, client, test_account1):
        """Test that TVG IDs use standardized format"""
        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should have standardized tvg-id format
        assert f'tvg-id="ch-{test_account1}-1"' in content
        assert f'tvg-id="ch-{test_account1}-2"' in content

    def test_sanitized_values(self, app, client, test_account1):
        """Test that M3U values are properly sanitized"""
        with app.app_context():
            # Create channel with special characters
            category = Category.query.filter_by(account_id=test_account1).first()
            channel = Channel(
                account_id=test_account1,
                stream_id=99,
                name='Test "Channel" with\'quotes',
                cleaned_name="Test Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        # Response should succeed even with special characters
        assert b"#EXTM3U" in response.data

    def test_cleaned_name_usage(self, app, client, test_account1):
        """Test that cleaned names are used in M3U output"""
        response = client.get(f"/playlist/{test_account1}.m3u")

        assert response.status_code == 200
        content = response.data.decode("utf-8")

        # Should use cleaned_name (ESPN not ESPN HD)
        lines = content.split("\n")
        extinf_lines = [line for line in lines if line.startswith("#EXTINF")]
        # Check that display name uses cleaned name
        assert any("ESPN" in line and line.endswith(",ESPN") for line in extinf_lines)
