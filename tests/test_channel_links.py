"""
Tests for channel link management routes
"""
from models import Account, Category, Channel, ChannelLink, ChannelTag, Tag, db


class TestChannelLinksAPI:
    """Test channel link CRUD operations"""

    def test_get_channel_links_empty(self, client):
        """Test getting channel links when none exist"""
        response = client.get("/api/channel-links")
        assert response.status_code == 200
        assert response.json == []

    def test_create_channel_link(self, client):
        """Test creating a channel link"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        # Create east and west channels
        east_channel = Channel(
            account_id=account.id,
            stream_id=1,
            name="CNN East",
            epg_channel_id="CNN.east",
            category_id=category.id,
        )
        west_channel = Channel(
            account_id=account.id,
            stream_id=2,
            name="CNN West",
            epg_channel_id="CNN.west",
            category_id=category.id,
        )
        db.session.add_all([east_channel, west_channel])
        db.session.commit()

        # Create link
        response = client.post(
            "/api/channel-links",
            json={
                "channel_id": west_channel.id,
                "source_channel_id": east_channel.id,
                "time_offset_hours": -3,
                "link_type": "time_shifted",
            },
        )
        assert response.status_code == 201
        data = response.json
        assert data["channel_id"] == west_channel.id
        assert data["source_channel_id"] == east_channel.id
        assert data["time_offset_hours"] == -3
        assert data["link_type"] == "time_shifted"
        assert data["auto_detected"] is False

    def test_create_channel_link_missing_fields(self, client):
        """Test creating a channel link with missing fields"""
        response = client.post(
            "/api/channel-links",
            json={"channel_id": 1},
        )
        assert response.status_code == 400
        assert "source_channel_id" in response.json["error"]

    def test_create_channel_link_channel_not_found(self, client):
        """Test creating a channel link with nonexistent channel"""
        response = client.post(
            "/api/channel-links",
            json={"channel_id": 9999, "source_channel_id": 9998},
        )
        assert response.status_code == 404

    def test_create_channel_link_self_link(self, client):
        """Test that self-linking is prevented"""
        # Create account and channel
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel = Channel(
            account_id=account.id,
            stream_id=1,
            name="Test Channel",
            category_id=category.id,
        )
        db.session.add(channel)
        db.session.commit()

        response = client.post(
            "/api/channel-links",
            json={"channel_id": channel.id, "source_channel_id": channel.id},
        )
        assert response.status_code == 400
        assert "itself" in response.json["error"]

    def test_create_channel_link_duplicate(self, client):
        """Test that duplicate links return conflict"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        # Create first link
        response = client.post(
            "/api/channel-links",
            json={"channel_id": channel1.id, "source_channel_id": channel2.id},
        )
        assert response.status_code == 201

        # Try to create duplicate
        response = client.post(
            "/api/channel-links",
            json={"channel_id": channel1.id, "source_channel_id": channel2.id},
        )
        assert response.status_code == 409
        assert "already exists" in response.json["error"]

    def test_get_channel_link(self, client):
        """Test getting a specific channel link"""
        # Create account, channels, and link
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        link = ChannelLink(
            channel_id=channel1.id,
            source_channel_id=channel2.id,
            time_offset_hours=-3,
        )
        db.session.add(link)
        db.session.commit()

        response = client.get(f"/api/channel-links/{link.id}")
        assert response.status_code == 200
        assert response.json["id"] == link.id
        assert response.json["time_offset_hours"] == -3

    def test_get_channel_link_not_found(self, client):
        """Test getting a nonexistent channel link"""
        response = client.get("/api/channel-links/9999")
        assert response.status_code == 404

    def test_update_channel_link(self, client):
        """Test updating a channel link"""
        # Create account, channels, and link
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        link = ChannelLink(
            channel_id=channel1.id,
            source_channel_id=channel2.id,
            time_offset_hours=-3,
        )
        db.session.add(link)
        db.session.commit()

        response = client.put(
            f"/api/channel-links/{link.id}",
            json={"time_offset_hours": -2, "link_type": "simulcast"},
        )
        assert response.status_code == 200
        assert response.json["time_offset_hours"] == -2
        assert response.json["link_type"] == "simulcast"

    def test_update_channel_link_not_found(self, client):
        """Test updating a nonexistent channel link"""
        response = client.put(
            "/api/channel-links/9999",
            json={"time_offset_hours": -2},
        )
        assert response.status_code == 404

    def test_delete_channel_link(self, client):
        """Test deleting a channel link"""
        # Create account, channels, and link
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        link = ChannelLink(
            channel_id=channel1.id,
            source_channel_id=channel2.id,
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

        response = client.delete(f"/api/channel-links/{link_id}")
        assert response.status_code == 200

        # Verify deleted
        assert db.session.get(ChannelLink, link_id) is None

    def test_delete_channel_link_not_found(self, client):
        """Test deleting a nonexistent channel link"""
        response = client.delete("/api/channel-links/9999")
        assert response.status_code == 404


class TestChannelLinksBulkOperations:
    """Test bulk channel link operations"""

    def test_bulk_create_channel_links(self, client):
        """Test bulk creating channel links"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channels = []
        for i in range(4):
            channel = Channel(
                account_id=account.id,
                stream_id=i + 1,
                name=f"Channel {i + 1}",
                category_id=category.id,
            )
            channels.append(channel)
        db.session.add_all(channels)
        db.session.commit()

        response = client.post(
            "/api/channel-links/bulk",
            json={
                "links": [
                    {
                        "channel_id": channels[0].id,
                        "source_channel_id": channels[1].id,
                        "time_offset_hours": -3,
                    },
                    {
                        "channel_id": channels[2].id,
                        "source_channel_id": channels[3].id,
                        "time_offset_hours": -3,
                    },
                ]
            },
        )
        assert response.status_code == 200
        assert response.json["created"] == 2
        assert len(response.json["links"]) == 2
        assert len(response.json["errors"]) == 0

    def test_bulk_create_with_errors(self, client):
        """Test bulk creating channel links with some errors"""
        # Create account and channel
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        db.session.add(channel)
        db.session.commit()

        response = client.post(
            "/api/channel-links/bulk",
            json={
                "links": [
                    # Missing source_channel_id
                    {"channel_id": channel.id},
                    # Self-link
                    {"channel_id": channel.id, "source_channel_id": channel.id},
                    # Nonexistent channel
                    {"channel_id": 9999, "source_channel_id": 9998},
                ]
            },
        )
        assert response.status_code == 200
        assert response.json["created"] == 0
        assert len(response.json["errors"]) == 3

    def test_delete_auto_detected_links(self, client):
        """Test deleting auto-detected links"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        # Create auto-detected and manual links
        auto_link = ChannelLink(
            channel_id=channel1.id,
            source_channel_id=channel2.id,
            auto_detected=True,
        )
        manual_link = ChannelLink(
            channel_id=channel2.id,
            source_channel_id=channel1.id,
            auto_detected=False,
        )
        db.session.add_all([auto_link, manual_link])
        db.session.commit()

        # Save IDs before delete
        auto_link_id = auto_link.id
        manual_link_id = manual_link.id

        response = client.delete("/api/channel-links/auto-detected")
        assert response.status_code == 200
        assert response.json["deleted"] == 1

        # Verify only auto-detected was deleted
        assert db.session.get(ChannelLink, auto_link_id) is None
        assert db.session.get(ChannelLink, manual_link_id) is not None


class TestChannelLinksFiltering:
    """Test channel link filtering"""

    def test_filter_by_account(self, client):
        """Test filtering channel links by account"""
        # Create two accounts
        account1 = Account(
            name="Account 1",
            server="http://test1.com",
            username="user1",
            password="pass1",
            enabled=True,
        )
        account2 = Account(
            name="Account 2",
            server="http://test2.com",
            username="user2",
            password="pass2",
            enabled=True,
        )
        db.session.add_all([account1, account2])
        db.session.commit()

        # Create categories
        cat1 = Category(
            account_id=account1.id,
            category_id="1",
            category_name="Category 1",
        )
        cat2 = Category(
            account_id=account2.id,
            category_id="2",
            category_name="Category 2",
        )
        db.session.add_all([cat1, cat2])
        db.session.commit()

        # Create channels for each account
        ch1_a = Channel(
            account_id=account1.id,
            stream_id=1,
            name="Ch 1A",
            category_id=cat1.id,
        )
        ch1_b = Channel(
            account_id=account1.id,
            stream_id=2,
            name="Ch 1B",
            category_id=cat1.id,
        )
        ch2_a = Channel(
            account_id=account2.id,
            stream_id=3,
            name="Ch 2A",
            category_id=cat2.id,
        )
        ch2_b = Channel(
            account_id=account2.id,
            stream_id=4,
            name="Ch 2B",
            category_id=cat2.id,
        )
        db.session.add_all([ch1_a, ch1_b, ch2_a, ch2_b])
        db.session.commit()

        # Create links for each account
        link1 = ChannelLink(channel_id=ch1_a.id, source_channel_id=ch1_b.id)
        link2 = ChannelLink(channel_id=ch2_a.id, source_channel_id=ch2_b.id)
        db.session.add_all([link1, link2])
        db.session.commit()

        # Filter by account1
        response = client.get(f"/api/channel-links?account_id={account1.id}")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["id"] == link1.id

    def test_filter_by_link_type(self, client):
        """Test filtering channel links by link type"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channels = []
        for i in range(4):
            ch = Channel(
                account_id=account.id,
                stream_id=i + 1,
                name=f"Channel {i + 1}",
                category_id=category.id,
            )
            channels.append(ch)
        db.session.add_all(channels)
        db.session.commit()

        # Create links of different types
        link1 = ChannelLink(
            channel_id=channels[0].id,
            source_channel_id=channels[1].id,
            link_type="time_shifted",
        )
        link2 = ChannelLink(
            channel_id=channels[2].id,
            source_channel_id=channels[3].id,
            link_type="simulcast",
        )
        db.session.add_all([link1, link2])
        db.session.commit()

        # Filter by time_shifted
        response = client.get("/api/channel-links?link_type=time_shifted")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["link_type"] == "time_shifted"

    def test_filter_by_auto_detected(self, client):
        """Test filtering channel links by auto_detected"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channels = []
        for i in range(4):
            ch = Channel(
                account_id=account.id,
                stream_id=i + 1,
                name=f"Channel {i + 1}",
                category_id=category.id,
            )
            channels.append(ch)
        db.session.add_all(channels)
        db.session.commit()

        # Create auto and manual links
        link1 = ChannelLink(
            channel_id=channels[0].id,
            source_channel_id=channels[1].id,
            auto_detected=True,
        )
        link2 = ChannelLink(
            channel_id=channels[2].id,
            source_channel_id=channels[3].id,
            auto_detected=False,
        )
        db.session.add_all([link1, link2])
        db.session.commit()

        # Filter by auto_detected=true
        response = client.get("/api/channel-links?auto_detected=true")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["auto_detected"] is True


class TestChannelLinksForChannel:
    """Test getting links for a specific channel"""

    def test_get_links_for_channel(self, client):
        """Test getting all links where channel is target or source"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channels = []
        for i in range(3):
            ch = Channel(
                account_id=account.id,
                stream_id=i + 1,
                name=f"Channel {i + 1}",
                category_id=category.id,
            )
            channels.append(ch)
        db.session.add_all(channels)
        db.session.commit()

        # Channel 0 is target in link1, source in link2
        link1 = ChannelLink(
            channel_id=channels[0].id,
            source_channel_id=channels[1].id,
        )
        link2 = ChannelLink(
            channel_id=channels[2].id,
            source_channel_id=channels[0].id,
        )
        db.session.add_all([link1, link2])
        db.session.commit()

        response = client.get(f"/api/channels/{channels[0].id}/links")
        assert response.status_code == 200
        assert len(response.json["as_target"]) == 1
        assert len(response.json["as_source"]) == 1

    def test_get_links_for_channel_not_found(self, client):
        """Test getting links for nonexistent channel"""
        response = client.get("/api/channels/9999/links")
        assert response.status_code == 404


class TestDetectChannelLinks:
    """Test auto-detection of channel links"""

    def test_detect_channel_links_no_pairs(self, client):
        """Test detection when no pairs exist"""
        # Create account and channels without east/west tags
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel = Channel(
            account_id=account.id,
            stream_id=1,
            name="CNN",
            cleaned_name="CNN",
            category_id=category.id,
        )
        db.session.add(channel)
        db.session.commit()

        response = client.post("/api/channel-links/detect")
        assert response.status_code == 200
        assert response.json["links_created"] == 0

    def test_detect_channel_links_finds_pairs(self, client):
        """Test detection finds east/west pairs"""
        # Create account
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        # Create east and west channels with same cleaned name
        east_channel = Channel(
            account_id=account.id,
            stream_id=1,
            name="CNN East",
            cleaned_name="CNN",
            epg_channel_id="CNN.east",
            category_id=category.id,
        )
        west_channel = Channel(
            account_id=account.id,
            stream_id=2,
            name="CNN West",
            cleaned_name="CNN",
            epg_channel_id="CNN.west",
            category_id=category.id,
        )
        db.session.add_all([east_channel, west_channel])
        db.session.commit()

        # Create tags
        east_tag = Tag(name="EAST")
        west_tag = Tag(name="WEST")
        db.session.add_all([east_tag, west_tag])
        db.session.commit()

        # Assign tags
        east_channel_tag = ChannelTag(
            account_id=account.id,
            stream_id=1,
            tag_id=east_tag.id,
        )
        west_channel_tag = ChannelTag(
            account_id=account.id,
            stream_id=2,
            tag_id=west_tag.id,
        )
        db.session.add_all([east_channel_tag, west_channel_tag])
        db.session.commit()

        response = client.post("/api/channel-links/detect")
        assert response.status_code == 200
        assert response.json["links_created"] == 1

        # Verify link was created correctly
        links = ChannelLink.query.all()
        assert len(links) == 1
        assert links[0].channel_id == west_channel.id
        assert links[0].source_channel_id == east_channel.id
        assert links[0].time_offset_hours == -3
        assert links[0].auto_detected is True

    def test_detect_with_clear_existing(self, client):
        """Test detection with clear_existing option"""
        # Create account and channels
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel1 = Channel(
            account_id=account.id,
            stream_id=1,
            name="Channel 1",
            cleaned_name="Channel 1",
            category_id=category.id,
        )
        channel2 = Channel(
            account_id=account.id,
            stream_id=2,
            name="Channel 2",
            cleaned_name="Channel 2",
            category_id=category.id,
        )
        db.session.add_all([channel1, channel2])
        db.session.commit()

        # Create existing auto-detected link
        link = ChannelLink(
            channel_id=channel1.id,
            source_channel_id=channel2.id,
            auto_detected=True,
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

        # Run detection with clear_existing
        response = client.post("/api/channel-links/detect?clear_existing=true")
        assert response.status_code == 200

        # Verify old link was deleted
        assert db.session.get(ChannelLink, link_id) is None
