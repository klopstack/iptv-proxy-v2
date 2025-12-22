"""
Tests for collapse duplicates feature in the preview endpoint.
"""
import pytest

from models import Account, Category, Channel, ChannelTag, Tag, db


@pytest.fixture
def account_with_duplicate_channels(app):
    """Create an account with duplicate channels at different quality levels"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="test_user",
            password="test_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        category = Category(
            account_id=account.id,
            category_id="cat1",
            category_name="US| MAX ESPN ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
        )
        db.session.add(category)
        db.session.flush()

        # Create quality tags
        tags = {}
        for tag_name in ["HD", "4K", "RAW", "60FPS", "US"]:
            tag = Tag(name=tag_name)
            db.session.add(tag)
            db.session.flush()
            tags[tag_name] = tag

        # Create ESPN channels at different quality levels
        # All have the same cleaned_name "ESPN" but different original names/tags
        espn_channels = [
            {
                "stream_id": "espn_hd",
                "name": "US| ESPN ᴴᴰ",
                "cleaned_name": "ESPN",
                "tags": ["US", "HD"],
            },
            {
                "stream_id": "espn_60fps",
                "name": "US| ESPN ⁶⁰ᶠᵖˢ",
                "cleaned_name": "ESPN",
                "tags": ["US", "60FPS"],
            },
            {
                "stream_id": "espn_raw_60fps",
                "name": "US| ESPN ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
                "cleaned_name": "ESPN",
                "tags": ["US", "RAW", "60FPS"],
            },
        ]

        for ch_data in espn_channels:
            channel = Channel(
                account_id=account.id,
                stream_id=ch_data["stream_id"],
                name=ch_data["name"],
                cleaned_name=ch_data["cleaned_name"],
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Add tags
            for tag_name in ch_data["tags"]:
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=ch_data["stream_id"],
                    tag_id=tags[tag_name].id,
                )
                db.session.add(channel_tag)

        # Add a unique channel (CNN) to verify it's not collapsed
        cnn_channel = Channel(
            account_id=account.id,
            stream_id="cnn_hd",
            name="US| CNN ᴴᴰ",
            cleaned_name="CNN",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(cnn_channel)
        db.session.flush()

        cnn_tag = ChannelTag(
            account_id=account.id,
            stream_id="cnn_hd",
            tag_id=tags["HD"].id,
        )
        db.session.add(cnn_tag)

        us_tag_cnn = ChannelTag(
            account_id=account.id,
            stream_id="cnn_hd",
            tag_id=tags["US"].id,
        )
        db.session.add(us_tag_cnn)

        db.session.commit()
        yield account.id


class TestCollapseDuplicatesEndpoint:
    """Tests for the collapse_duplicates query parameter in preview endpoint"""

    def test_preview_without_collapse(self, app, client, account_with_duplicate_channels):
        """Preview without collapse shows all channels"""
        response = client.get(f"/api/accounts/{account_with_duplicate_channels}/preview")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 4  # 3 ESPN + 1 CNN
        assert len(data["channels"]) == 4
        assert data.get("collapse_duplicates", False) is False

    def test_preview_with_collapse_enabled(self, app, client, account_with_duplicate_channels):
        """Preview with collapse_duplicates=true collapses duplicates"""
        response = client.get(f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=true")
        assert response.status_code == 200

        data = response.json
        assert data["collapse_duplicates"] is True
        assert data["total"] == 2  # 1 ESPN (best quality) + 1 CNN
        assert data["duplicates_collapsed"] == 2  # 2 ESPN variants collapsed

    def test_collapse_keeps_highest_quality(self, app, client, account_with_duplicate_channels):
        """Collapse keeps the RAW+60FPS version (highest quality)"""
        response = client.get(f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=true")
        assert response.status_code == 200

        data = response.json
        # Find the ESPN channel
        espn = next((ch for ch in data["channels"] if "ESPN" in ch.get("cleaned_name", "")), None)
        assert espn is not None

        # Should be the RAW+60FPS version
        assert espn["stream_id"] == "espn_raw_60fps"
        assert "RAW" in espn["tags"]
        assert "60FPS" in espn["tags"]

    def test_collapse_adds_duplicate_count(self, app, client, account_with_duplicate_channels):
        """Collapsed channels have duplicate_count metadata"""
        response = client.get(f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=true")
        assert response.status_code == 200

        data = response.json
        # Find the ESPN channel
        espn = next((ch for ch in data["channels"] if "ESPN" in ch.get("cleaned_name", "")), None)
        assert espn is not None
        assert espn["duplicate_count"] == 2  # 2 other versions collapsed

        # CNN should have no duplicates
        cnn = next((ch for ch in data["channels"] if "CNN" in ch.get("cleaned_name", "")), None)
        assert cnn is not None
        assert cnn["duplicate_count"] == 0

    def test_collapse_false_is_explicit(self, app, client, account_with_duplicate_channels):
        """collapse_duplicates=false explicitly returns all channels"""
        response = client.get(f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=false")
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 4

    def test_collapse_with_pagination(self, app, client, account_with_duplicate_channels):
        """Collapse works correctly with pagination"""
        # Request with limit of 1
        response = client.get(
            f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=true&limit=1"
        )
        assert response.status_code == 200

        data = response.json
        assert data["total"] == 2
        assert data["showing"] == 1
        assert data["has_more"] is True

        # Get second page
        response2 = client.get(
            f"/api/accounts/{account_with_duplicate_channels}/preview?collapse_duplicates=true&limit=1&offset=1"
        )
        data2 = response2.json
        assert data2["showing"] == 1
        assert data2["has_more"] is False

        # Verify we got different channels
        assert data["channels"][0]["stream_id"] != data2["channels"][0]["stream_id"]


class TestCollapseDuplicatesIntegration:
    """Integration tests for real-world duplicate scenarios"""

    def test_multiple_quality_tiers(self, app):
        """Test collapsing across multiple quality tiers"""
        with app.app_context():
            account = Account(
                name="Test",
                username="u",
                password="p",
                server="s.com",
            )
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="c1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            # Create tags
            tags_data = ["4K", "UHD", "RAW", "60FPS", "HD", "FHD"]
            tags = {}
            for name in tags_data:
                t = Tag(name=name)
                db.session.add(t)
                db.session.flush()
                tags[name] = t

            # Create channels with various quality combinations
            channels_data = [
                ("ch1", "ESPN", ["HD"]),  # Score: 50
                ("ch2", "ESPN", ["FHD"]),  # Score: 60
                ("ch3", "ESPN", ["60FPS"]),  # Score: 70
                ("ch4", "ESPN", ["RAW"]),  # Score: 80
                ("ch5", "ESPN", ["UHD"]),  # Score: 95
                ("ch6", "ESPN", ["4K"]),  # Score: 100 - WINNER
            ]

            for stream_id, name, tag_names in channels_data:
                ch = Channel(
                    account_id=account.id,
                    stream_id=stream_id,
                    name=f"{name} {' '.join(tag_names)}",
                    cleaned_name=name,
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                )
                db.session.add(ch)
                db.session.flush()

                for tag_name in tag_names:
                    ct = ChannelTag(
                        account_id=account.id,
                        stream_id=stream_id,
                        tag_id=tags[tag_name].id,
                    )
                    db.session.add(ct)

            db.session.commit()

            # Test with client
            from app import app as flask_app

            client = flask_app.test_client()
            response = client.get(f"/api/accounts/{account.id}/preview?collapse_duplicates=true")
            assert response.status_code == 200

            data = response.json
            assert data["total"] == 1
            assert data["channels"][0]["stream_id"] == "ch6"  # 4K version
            assert "4K" in data["channels"][0]["tags"]


class TestPlaylistCollapseDuplicates:
    """Tests for collapse_duplicates in M3U playlist generation"""

    def test_playlist_without_collapse(self, app, client, account_with_duplicate_channels):
        """Playlist without collapse includes all channels"""
        response = client.get(f"/playlist/{account_with_duplicate_channels}.m3u")
        assert response.status_code == 200

        m3u_content = response.data.decode("utf-8")
        # Should have all 4 channels (3 ESPN + 1 CNN)
        extinf_count = m3u_content.count("#EXTINF:")
        assert extinf_count == 4

    def test_playlist_with_collapse(self, app, client, account_with_duplicate_channels):
        """Playlist with collapse_duplicates=true only includes best quality"""
        response = client.get(f"/playlist/{account_with_duplicate_channels}.m3u?collapse_duplicates=true")
        assert response.status_code == 200

        m3u_content = response.data.decode("utf-8")
        # Should have 2 channels (1 ESPN best quality + 1 CNN)
        extinf_count = m3u_content.count("#EXTINF:")
        assert extinf_count == 2

        # The ESPN entry should be the RAW 60FPS version (highest score)
        assert "espn_raw_60fps" in m3u_content

    def test_playlist_collapse_preserves_unique_channels(self, app, client, account_with_duplicate_channels):
        """Collapse should not remove unique channels like CNN"""
        response = client.get(f"/playlist/{account_with_duplicate_channels}.m3u?collapse_duplicates=true")
        assert response.status_code == 200

        m3u_content = response.data.decode("utf-8")
        # CNN should still be present
        assert "cnn_hd" in m3u_content
