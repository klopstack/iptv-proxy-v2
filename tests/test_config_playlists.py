"""
Test config-based playlist generation

Tests that:
1. Config playlists use database queries (no API calls)
2. Account/tag filtering works correctly
3. Multi-account playlists work
4. Tag match modes ('any' vs 'all') work
5. Unsynced accounts return 503
6. Pre-computed data (cleaned_name, is_visible) is used
"""
import json

import pytest

from models import Account, Category, Channel, ChannelTag, PlaylistConfig, Tag, db


@pytest.fixture
def test_accounts_with_channels(app):
    """Create two accounts with synced channels"""
    with app.app_context():
        # Create accounts
        account1 = Account(name="Account 1", server="server1.com", username="user1", password="pass1", enabled=True)
        account2 = Account(name="Account 2", server="server2.com", username="user2", password="pass2", enabled=True)
        db.session.add_all([account1, account2])
        db.session.flush()

        # Create categories and channels for account 1
        cat1 = Category(account_id=account1.id, category_id="100", category_name="Sports")
        cat2 = Category(account_id=account1.id, category_id="200", category_name="Movies")
        db.session.add_all([cat1, cat2])
        db.session.flush()

        channels1 = [
            Channel(
                account_id=account1.id,
                stream_id=f"ch{i}",
                name=f"Channel {i}",
                cleaned_name=f"Channel {i}",
                category_id=cat1.id if i <= 2 else cat2.id,
                is_active=True,
                is_visible=True,
            )
            for i in range(1, 5)
        ]

        # Create categories and channels for account 2
        cat3 = Category(account_id=account2.id, category_id="300", category_name="News")
        db.session.add(cat3)
        db.session.flush()

        channels2 = [
            Channel(
                account_id=account2.id,
                stream_id=f"ch{i}",
                name=f"News Channel {i}",
                cleaned_name=f"News Channel {i}",
                category_id=cat3.id,
                is_active=True,
                is_visible=True,
            )
            for i in range(1, 3)
        ]

        db.session.add_all(channels1 + channels2)
        db.session.commit()

        yield {"account1": account1, "account2": account2, "channels1": channels1, "channels2": channels2}


@pytest.fixture
def test_accounts_with_tags(app, test_accounts_with_channels):
    """Add tags to channels"""
    with app.app_context():
        data = test_accounts_with_channels

        # Create tags - use uppercase names for case-insensitive matching
        tag_hd = Tag(name="HD")
        tag_4k = Tag(name="4K")
        tag_sports = Tag(name="SPORTS")
        db.session.add_all([tag_hd, tag_4k, tag_sports])
        db.session.flush()

        # Tag some channels
        # Account 1 channels: ch1 and ch2 get HD tag, ch1 gets Sports tag
        channel_tags = [
            ChannelTag(account_id=data["account1"].id, stream_id="ch1", tag_id=tag_hd.id),
            ChannelTag(account_id=data["account1"].id, stream_id="ch1", tag_id=tag_sports.id),
            ChannelTag(account_id=data["account1"].id, stream_id="ch2", tag_id=tag_hd.id),
            ChannelTag(account_id=data["account1"].id, stream_id="ch3", tag_id=tag_4k.id),
        ]
        db.session.add_all(channel_tags)
        db.session.commit()

        yield data


def test_config_playlist_all_accounts(client, test_accounts_with_channels):
    """Test playlist config with all accounts"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="All Channels",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should have both accounts' channels
    assert "#EXTM3U" in playlist
    assert "Playlist: All Channels" in playlist
    assert "Channel 1" in playlist
    assert "News Channel 1" in playlist

    # Should have 6 channels total (4 from account1, 2 from account2)
    assert playlist.count("#EXTINF") == 6


def test_config_playlist_specific_accounts(client, test_accounts_with_channels):
    """Test playlist config with specific account included"""
    with client.application.app_context():
        data = test_accounts_with_channels
        config = PlaylistConfig(
            name="Account 1 Only",
            include_accounts=json.dumps([data["account1"].id]),
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should only have account1 channels
    assert "Channel 1" in playlist
    assert "News Channel" not in playlist
    assert playlist.count("#EXTINF") == 4


def test_config_playlist_exclude_accounts(client, test_accounts_with_channels):
    """Test playlist config with account excluded"""
    with client.application.app_context():
        data = test_accounts_with_channels
        config = PlaylistConfig(
            name="Exclude Account 2",
            include_accounts="[]",
            exclude_accounts=json.dumps([data["account2"].id]),
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should only have account1 channels
    assert "Channel 1" in playlist
    assert "News Channel" not in playlist
    assert playlist.count("#EXTINF") == 4


def test_config_playlist_include_tags(client, test_accounts_with_tags):
    """Test playlist config with tag inclusion"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="HD Channels",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags=json.dumps(["HD"]),
            exclude_tags="[]",
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should only have channels with HD tag (ch1, ch2)
    assert "Channel 1" in playlist
    assert "Channel 2" in playlist
    assert "Channel 3" not in playlist  # Has 4K, not HD
    assert playlist.count("#EXTINF") == 2


def test_config_playlist_exclude_tags(client, test_accounts_with_tags):
    """Test playlist config with tag exclusion"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="No 4K",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags=json.dumps(["4K"]),
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should exclude ch3 which has 4K tag
    assert "Channel 1" in playlist
    assert "Channel 2" in playlist
    assert "Channel 3" not in playlist
    assert "Channel 4" in playlist  # Has no tags
    assert playlist.count("#EXTINF") == 5  # 3 from account1 (ch1,ch2,ch4) + 2 from account2


def test_config_playlist_tag_match_any(client, test_accounts_with_tags):
    """Test playlist config with tag match mode 'any'"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="HD or Sports",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags=json.dumps(["HD", "SPORTS"]),
            exclude_tags="[]",
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should have ch1 (HD+Sports) and ch2 (HD)
    assert "Channel 1" in playlist
    assert "Channel 2" in playlist
    assert "Channel 3" not in playlist
    assert playlist.count("#EXTINF") == 2


def test_config_playlist_tag_match_all(client, test_accounts_with_tags):
    """Test playlist config with tag match mode 'all'"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="HD AND Sports",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags=json.dumps(["HD", "SPORTS"]),
            exclude_tags="[]",
            tag_match_mode="all",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should only have ch1 which has BOTH HD and Sports tags
    assert "Channel 1" in playlist
    assert "Channel 2" not in playlist  # Only has HD
    assert playlist.count("#EXTINF") == 1


def test_config_playlist_unsynced_account_returns_503(app, client):
    """Test that unsynced accounts return 503 error"""
    with app.app_context():
        # Create account without channels
        account = Account(name="Unsynced", server="test.com", username="user", password="pass", enabled=True)
        db.session.add(account)
        db.session.flush()

        config = PlaylistConfig(
            name="Test",
            include_accounts=json.dumps([account.id]),
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 503
    assert b"not synced" in response.data


def test_config_playlist_disabled_returns_403(app, client, test_accounts_with_channels):
    """Test that disabled config returns 403"""
    with app.app_context():
        config = PlaylistConfig(
            name="Disabled",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=False,  # Disabled
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 403


def test_config_playlist_uses_cleaned_names(app, client):
    """Test that config playlists use pre-computed cleaned names"""
    with app.app_context():
        account = Account(name="Test", server="test.com", username="user", password="pass", enabled=True)
        db.session.add(account)
        db.session.flush()

        cat = Category(account_id=account.id, category_id="100", category_name="Test")
        db.session.add(cat)
        db.session.flush()

        channel = Channel(
            account_id=account.id,
            stream_id="ch1",
            name="US| HD Channel 4K",  # Original name with tags
            cleaned_name="Channel",  # Cleaned name (tags removed)
            category_id=cat.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.flush()

        config = PlaylistConfig(
            name="Test",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Should use cleaned name, not original
    assert 'tvg-name="Channel"' in playlist
    assert ",Channel\n" in playlist
    assert "US|" not in playlist


def test_config_playlist_multi_account_group_titles(client, test_accounts_with_channels):
    """Test that multi-account playlists include account name in group title"""
    with client.application.app_context():
        config = PlaylistConfig(
            name="Multi Account",
            include_accounts="[]",
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Group titles should include account names for multi-account playlists
    assert "Sports (Account 1)" in playlist
    assert "Movies (Account 1)" in playlist
    assert "News (Account 2)" in playlist


def test_config_playlist_single_account_no_account_in_group(client, test_accounts_with_channels):
    """Test that single-account playlists don't include account name in group title"""
    with client.application.app_context():
        data = test_accounts_with_channels
        config = PlaylistConfig(
            name="Single Account",
            include_accounts=json.dumps([data["account1"].id]),
            exclude_accounts="[]",
            include_tags="[]",
            exclude_tags="[]",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")

    assert response.status_code == 200
    playlist = response.data.decode("utf-8")

    # Group titles should NOT include account name for single-account playlists
    assert 'group-title="Sports"' in playlist
    assert 'group-title="Movies"' in playlist
    assert "(Account 1)" not in playlist
