"""Tests for EPG channel list endpoints and account EPG source creation."""


from models import EpgChannel, EpgSource, db


class TestEpgChannels:
    """Tests for EPG channel endpoints"""

    def test_get_epg_channels_empty(self, app, client):
        """Test getting EPG channels when none exist"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 0

    def test_get_epg_channels(self, app, client, test_epg_channel):
        """Test getting EPG channels"""
        response = client.get("/api/epg/channels")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["channels"][0]["display_name"] == "Test EPG Channel"

    def test_get_epg_channels_with_source_filter(self, app, client, test_epg_source, test_epg_channel):
        """Test getting EPG channels filtered by source"""
        response = client.get(f"/api/epg/channels?source_id={test_epg_source}")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_get_epg_channels_with_search(self, app, client, test_epg_channel):
        """Test getting EPG channels with search"""
        response = client.get("/api/epg/channels?search=Test")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_get_epg_channels_search_no_match(self, app, client, test_epg_channel):
        """Test search with no matching channels"""
        response = client.get("/api/epg/channels?search=NonExistent")
        assert response.status_code == 200
        assert response.json["total"] == 0

    def test_get_epg_channels_filter_by_source(self, app, client, test_epg_source):
        """Test filtering EPG channels by source when multiple sources exist"""
        with app.app_context():
            source2 = EpgSource(
                name="Source 2",
                source_type="xmltv_url",
                url="http://example.com",
            )
            db.session.add(source2)
            db.session.flush()

            db.session.add_all(
                [
                    EpgChannel(source_id=test_epg_source, channel_id="ch1", display_name="Channel 1"),
                    EpgChannel(source_id=source2.id, channel_id="ch2", display_name="Channel 2"),
                ]
            )
            db.session.commit()

        response = client.get(f"/api/epg/channels?source_id={test_epg_source}")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_epg_channels_pagination(self, app, client, test_epg_source):
        """Test EPG channel pagination"""
        with app.app_context():
            # Create multiple channels
            for i in range(5):
                epg_channel = EpgChannel(
                    source_id=test_epg_source,
                    channel_id=f"ch_{i}",
                    display_name=f"Channel {i}",
                )
                db.session.add(epg_channel)
            db.session.commit()

        response = client.get("/api/epg/channels?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 5
        assert len(data["channels"]) == 2


class TestAccountEpgSource:
    """Tests for account EPG source endpoints"""

    def test_create_account_epg_source_removed(self, app, client, test_account):
        """Provider EPG source helper endpoint is removed (UI-only cleanup)."""
        response = client.post(f"/api/accounts/{test_account}/epg-source")
        assert response.status_code == 404
