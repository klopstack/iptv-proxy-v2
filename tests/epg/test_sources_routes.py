"""Tests for EPG source CRUD and source-mapping endpoints."""

from datetime import datetime, timezone

from models import Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


class TestEpgSources:
    """Tests for EPG source endpoints"""

    def test_get_epg_sources_empty(self, app, client):
        """Test getting EPG sources when none exist"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        assert response.json == []

    def test_get_epg_sources(self, app, client, test_epg_source):
        """Test getting EPG sources"""
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        sources = response.json
        assert len(sources) == 1
        assert sources[0]["name"] == "Test EPG Source"
        assert sources[0]["source_type"] == "xmltv_url"

    def test_get_epg_sources_last_sync_is_explicit_utc_z(self, app, client):
        with app.app_context():
            source = EpgSource(
                name="Timed Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                last_sync=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        payload = next(s for s in response.json if s["id"] == source_id)
        assert payload["last_sync"].endswith("Z")

    def test_create_epg_source_missing_name(self, app, client):
        """Test creating EPG source without name"""
        response = client.post("/api/epg/sources", json={"source_type": "xmltv_url"}, content_type="application/json")
        assert response.status_code == 400
        assert "name" in response.json["error"].lower()

    def test_create_epg_source_missing_type(self, app, client):
        """Test creating EPG source without source_type"""
        response = client.post("/api/epg/sources", json={"name": "Test"}, content_type="application/json")
        assert response.status_code == 400
        assert "source type" in response.json["error"].lower()

    def test_create_epg_source_invalid_type(self, app, client):
        """Test creating EPG source with invalid type"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "invalid_type"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "invalid" in response.json["error"].lower()

    def test_create_epg_source_rejects_provider_type(self, app, client):
        """Provider EPG source type is no longer supported"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Provider Source", "source_type": "provider", "account_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "invalid" in response.json["error"].lower()

    def test_create_epg_source_success(self, app, client, test_account):
        """Test successful EPG source creation"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "New EPG Source",
                "source_type": "xmltv_url",
                "url": "http://example.com/epg.xml",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert "id" in response.json
        assert response.json["source_type"] == "xmltv_url"

    def test_create_epg_source_xmltv_url(self, app, client):
        """Test creating XMLTV URL source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "XMLTV Source",
                "source_type": "xmltv_url",
                "url": "http://example.com/epg.xml",
            },
            content_type="application/json",
        )
        assert response.status_code == 201

    def test_create_epg_source_xmltv_grabber_missing_name(self, app, client):
        """Test creating XMLTV grabber source without grabber name"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Grabber Source", "source_type": "xmltv_grabber"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "grabber" in response.json["error"].lower()

    def test_create_epg_source_xmltv_grabber_success(self, app, client):
        """Test creating XMLTV grabber source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "Grabber Source",
                "source_type": "xmltv_grabber",
                "xmltv_grabber": "tv_grab_zz_sdjson",
                "xmltv_days": 14,
                "xmltv_offset": 2,
            },
            content_type="application/json",
        )
        assert response.status_code == 201

    def test_update_epg_source_not_found(self, app, client):
        """Test updating non-existent EPG source"""
        response = client.put("/api/epg/sources/999", json={"name": "Updated"}, content_type="application/json")
        assert response.status_code == 404

    def test_update_epg_source_success(self, app, client, test_epg_source):
        """Test successful EPG source update"""
        response = client.put(
            "/api/epg/sources/" + str(test_epg_source),
            json={"name": "Updated Name", "priority": 50, "enabled": False},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_delete_epg_source_not_found(self, app, client):
        """Test deleting non-existent EPG source"""
        response = client.delete("/api/epg/sources/999")
        assert response.status_code == 404

    def test_delete_epg_source_success(self, app, client, test_epg_source):
        """Test successful EPG source deletion"""
        response = client.delete(f"/api/epg/sources/{test_epg_source}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_delete_sd_epg_source_deletes_lineups_and_stations(self, app, client, test_account):
        """Schedules Direct source deletion should remove sd_lineups/sd_stations rows."""
        from models import EpgSource, SdLineup, SdStation, db

        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
                sd_username="u",
                sd_password="p",
            )
            db.session.add(source)
            db.session.flush()

            lineup = SdLineup(
                epg_source_id=source.id,
                lineup_id="USA-TEST-X",
                name="Test Lineup",
            )
            db.session.add(lineup)
            db.session.flush()

            station = SdStation(
                lineup_id=lineup.id,
                station_id="12345",
                callsign="TEST",
                name="Test Station",
            )
            db.session.add(station)
            db.session.commit()

            source_id = source.id
            lineup_id = lineup.id
            station_id = station.id

        resp = client.delete(f"/api/epg/sources/{source_id}")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        with app.app_context():
            assert db.session.get(EpgSource, source_id) is None
            assert db.session.get(SdLineup, lineup_id) is None
            assert db.session.get(SdStation, station_id) is None

    def test_delete_epg_source_with_mappings(self, app, client, test_epg_source, test_epg_mapping):
        """Deleting a source removes channel mappings that reference its EPG channels."""
        from models import ChannelEpgMapping, EpgChannel, EpgSource, db

        with app.app_context():
            assert db.session.get(ChannelEpgMapping, test_epg_mapping) is not None
            assert EpgChannel.query.filter_by(source_id=test_epg_source).count() == 1

        response = client.delete(f"/api/epg/sources/{test_epg_source}")
        assert response.status_code == 200
        assert response.json["success"] is True

        with app.app_context():
            assert db.session.get(EpgSource, test_epg_source) is None
            assert db.session.get(ChannelEpgMapping, test_epg_mapping) is None
            assert EpgChannel.query.filter_by(source_id=test_epg_source).count() == 0

    def test_get_epg_sources_includes_used_mapping_count(self, app, client, test_account):
        """Test that EPG sources include used_mapping_count"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Test Source With Mappings",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create an EPG channel in that source
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_test_ch",
                display_name="Test EPG Ch",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create a category and channel
            category = Category(
                account_id=test_account,
                category_id="test_cat",
                category_name="Test Category",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="test_ch",
                name="Test Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create a mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            source_id = source.id

        # Test the endpoint
        response = client.get("/api/epg/sources")
        assert response.status_code == 200
        sources = response.json
        source_data = next((s for s in sources if s["id"] == source_id), None)
        assert source_data is not None
        assert "used_mapping_count" in source_data
        assert source_data["used_mapping_count"] == 1

    def test_get_source_mappings_not_found(self, app, client):
        """Test getting mappings for non-existent source"""
        response = client.get("/api/epg/sources/999/mappings")
        assert response.status_code == 404

    def test_get_source_mappings_empty(self, app, client, test_epg_source):
        """Test getting mappings when source has no mappings"""
        response = client.get(f"/api/epg/sources/{test_epg_source}/mappings")
        assert response.status_code == 200
        data = response.json
        assert data["source_id"] == test_epg_source
        assert data["total"] == 0
        assert data["mappings"] == []

    def test_get_source_mappings_with_data(self, app, client, test_account):
        """Test getting mappings for a source with data"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Test Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create an EPG channel
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_ch_1",
                display_name="EPG Channel 1",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create category and channel
            category = Category(
                account_id=test_account,
                category_id="cat_1",
                category_name="Category 1",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="ch_1",
                name="Channel 1",
                cleaned_name="Channel 1 Clean",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="auto_fuzzy",
                confidence=0.85,
            )
            db.session.add(mapping)
            db.session.commit()

            source_id = source.id

        # Test the endpoint
        response = client.get(f"/api/epg/sources/{source_id}/mappings")
        assert response.status_code == 200
        data = response.json
        assert data["source_id"] == source_id
        assert data["total"] == 1
        assert len(data["mappings"]) == 1
        mapping_data = data["mappings"][0]
        assert mapping_data["channel_name"] == "Channel 1"
        assert mapping_data["epg_channel_name"] == "EPG Channel 1"
        assert mapping_data["mapping_type"] == "auto_fuzzy"
        assert mapping_data["confidence"] == 0.85
        assert mapping_data["category_name"] == "Category 1"  # category_name from Category model

    def test_get_source_mappings_with_search(self, app, client, test_account):
        """Test searching source mappings"""
        with app.app_context():
            # Create a source
            source = EpgSource(
                name="Search Test Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create EPG channels
            epg_ch1 = EpgChannel(source_id=source.id, channel_id="epg1", display_name="CNN News")
            epg_ch2 = EpgChannel(source_id=source.id, channel_id="epg2", display_name="ESPN Sports")
            db.session.add_all([epg_ch1, epg_ch2])
            db.session.flush()

            # Create channels and mappings
            category = Category(account_id=test_account, category_id="c1", category_name="Cat")
            db.session.add(category)
            db.session.flush()

            ch1 = Channel(
                account_id=test_account, stream_id="s1", name="CNN HD", category_id=category.id, is_active=True
            )
            ch2 = Channel(
                account_id=test_account, stream_id="s2", name="ESPN HD", category_id=category.id, is_active=True
            )
            db.session.add_all([ch1, ch2])
            db.session.flush()

            m1 = ChannelEpgMapping(channel_id=ch1.id, epg_channel_id=epg_ch1.id, mapping_type="manual", confidence=1.0)
            m2 = ChannelEpgMapping(channel_id=ch2.id, epg_channel_id=epg_ch2.id, mapping_type="manual", confidence=1.0)
            db.session.add_all([m1, m2])
            db.session.commit()

            source_id = source.id

        # Search for CNN
        response = client.get(f"/api/epg/sources/{source_id}/mappings?search=CNN")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["mappings"][0]["channel_name"] == "CNN HD"

    def test_get_source_mappings_pagination(self, app, client, test_account):
        """Test pagination of source mappings"""
        with app.app_context():
            source = EpgSource(
                name="Pagination Test", source_type="xmltv_url", url="http://example.com/epg.xml", enabled=True
            )
            db.session.add(source)
            db.session.flush()

            category = Category(account_id=test_account, category_id="pag", category_name="Pag Cat")
            db.session.add(category)
            db.session.flush()

            # Create multiple mappings
            for i in range(5):
                epg_ch = EpgChannel(source_id=source.id, channel_id=f"epg{i}", display_name=f"EPG {i}")
                db.session.add(epg_ch)
                db.session.flush()

                ch = Channel(
                    account_id=test_account,
                    stream_id=f"ch{i}",
                    name=f"Channel {i}",
                    category_id=category.id,
                    is_active=True,
                )
                db.session.add(ch)
                db.session.flush()

                mapping = ChannelEpgMapping(
                    channel_id=ch.id, epg_channel_id=epg_ch.id, mapping_type="manual", confidence=1.0
                )
                db.session.add(mapping)

            db.session.commit()
            source_id = source.id

        # Test pagination
        response = client.get(f"/api/epg/sources/{source_id}/mappings?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 5
        assert len(data["mappings"]) == 2
        assert data["offset"] == 0
        assert data["limit"] == 2

        # Get next page
        response = client.get(f"/api/epg/sources/{source_id}/mappings?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json
        assert len(data["mappings"]) == 2
        assert data["offset"] == 2
