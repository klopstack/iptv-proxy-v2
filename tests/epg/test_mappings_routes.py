"""Tests for channel-to-EPG mapping endpoints."""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


class TestEpgMappings:
    """Tests for EPG mapping endpoints"""

    def test_get_epg_mappings_empty(self, app, client):
        """Test getting mappings when none exist"""
        response = client.get("/api/epg/mappings")
        assert response.status_code == 200

    def test_get_epg_mappings_unmapped_only(self, app, client, test_channel):
        """Test getting unmapped channels"""
        response = client.get("/api/epg/mappings?unmapped_only=true")
        assert response.status_code == 200
        data = response.json
        assert "unmapped_channels" in data
        assert data["total"] >= 1

    def test_get_epg_mappings_unmapped_with_category_filter(self, app, client, test_account):
        """Test getting unmapped channels filtered by category"""
        with app.app_context():
            # Create two categories
            cat1 = Category(
                account_id=test_account,
                category_id="cat_filter1",
                category_name="Category 1",
            )
            cat2 = Category(
                account_id=test_account,
                category_id="cat_filter2",
                category_name="Category 2",
            )
            db.session.add_all([cat1, cat2])
            db.session.flush()

            # Create channels in different categories
            ch1 = Channel(
                account_id=test_account,
                stream_id="ch_cat1",
                name="Channel in Cat1",
                category_id=cat1.id,
                is_active=True,
                is_visible=True,
            )
            ch2 = Channel(
                account_id=test_account,
                stream_id="ch_cat2",
                name="Channel in Cat2",
                category_id=cat2.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add_all([ch1, ch2])
            db.session.commit()

            # Test filter by category 1
            response = client.get(
                f"/api/epg/mappings?unmapped_only=true&account_id={test_account}&category_id={cat1.id}"
            )
            assert response.status_code == 200
            data = response.json
            assert "unmapped_channels" in data
            # Should only return channels in cat1
            for ch in data["unmapped_channels"]:
                assert ch["category_id"] == cat1.id

            # Test filter by category 2
            response = client.get(
                f"/api/epg/mappings?unmapped_only=true&account_id={test_account}&category_id={cat2.id}"
            )
            assert response.status_code == 200
            data = response.json
            # Should only return channels in cat2
            for ch in data["unmapped_channels"]:
                assert ch["category_id"] == cat2.id

    def test_unmapped_mappings_exclude_ppv_hide_all(self, app, client):
        """Unmapped list uses playlist-visible semantics when show_filtered is false."""
        with app.app_context():
            account = Account(
                name="PPV EPG",
                username="ppv_user",
                password="ppv_pass",
                server="example.com",
                enabled=True,
                ppv_visibility="hide_all",
            )
            db.session.add(account)
            db.session.commit()

            db.session.add_all(
                [
                    Channel(
                        account_id=account.id,
                        stream_id="reg1",
                        name="Regular",
                        is_active=True,
                        is_ppv=False,
                    ),
                    Channel(
                        account_id=account.id,
                        stream_id="ppv1",
                        name="UFC 300",
                        is_active=True,
                        is_ppv=True,
                    ),
                ]
            )
            db.session.commit()
            account_id = account.id

        response = client.get(
            f"/api/epg/mappings?view_mode=unmapped&account_id={account_id}"
        )
        assert response.status_code == 200
        stream_ids = {ch["stream_id"] for ch in response.json["unmapped_channels"]}
        assert stream_ids == {"reg1"}

    def test_get_epg_mappings_unmapped_includes_category_info(self, app, client, test_channel, test_account):
        """Test that unmapped channels include category info in response"""
        response = client.get(f"/api/epg/mappings?unmapped_only=true&account_id={test_account}")
        assert response.status_code == 200
        data = response.json
        assert "unmapped_channels" in data
        assert len(data["unmapped_channels"]) > 0
        # Check that category info is included
        ch = data["unmapped_channels"][0]
        assert "category_id" in ch
        assert "category_name" in ch

    def test_get_epg_mappings_mapped_view(self, app, client, test_epg_mapping):
        """Test mapped view returns existing mappings"""
        response = client.get("/api/epg/mappings?view_mode=mapped")
        assert response.status_code == 200
        assert response.json["view_mode"] == "mapped"
        assert response.json["total"] >= 1

    def test_get_epg_mappings_all_view(self, app, client, test_channel, test_account):
        """Test all view includes mapping info for channels"""
        response = client.get(f"/api/epg/mappings?view_mode=all&account_id={test_account}")
        assert response.status_code == 200
        assert response.json["view_mode"] == "all"

    def test_create_epg_mapping_missing_channel_id(self, app, client):
        """Test creating mapping without channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"epg_channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "channel_id" in response.json["error"]

    def test_create_epg_mapping_missing_epg_channel_id(self, app, client):
        """Test creating mapping without epg_channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "epg_channel_id" in response.json["error"]

    def test_create_epg_mapping_channel_not_found(self, app, client, test_epg_channel):
        """Test creating mapping with non-existent channel"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 999, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_create_epg_mapping_invalid_epg_channel(self, app, client, test_channel):
        """Test creating mapping with non-existent EPG channel"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": 99999},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_create_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successful mapping creation"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 201
        assert "mapping_id" in response.json

    def test_create_epg_mapping_duplicate(self, app, client, test_channel, test_epg_channel):
        """Test creating duplicate mapping"""
        # Create first mapping
        client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )

        # Try to create duplicate
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_create_epg_mapping_with_time_offset(self, app, client, test_channel, test_epg_channel):
        """Test creating mapping with time offset"""
        response = client.post(
            "/api/epg/mappings",
            json={
                "channel_id": test_channel,
                "epg_channel_id": test_epg_channel,
                "time_offset_hours": -5,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        with app.app_context():
            mapping = db.session.get(ChannelEpgMapping, response.json["mapping_id"])
            assert mapping.time_offset_hours == -5

    def test_delete_epg_mapping_not_found(self, app, client):
        """Test deleting non-existent mapping"""
        response = client.delete("/api/epg/mappings/999")
        assert response.status_code == 404

    def test_delete_epg_mapping_success(self, app, client, test_channel, test_epg_channel):
        """Test successful mapping deletion"""
        # Create mapping first
        create_response = client.post(
            "/api/epg/mappings",
            json={"channel_id": test_channel, "epg_channel_id": test_epg_channel},
            content_type="application/json",
        )
        mapping_id = create_response.json["mapping_id"]

        # Delete it
        response = client.delete(f"/api/epg/mappings/{mapping_id}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_bulk_delete_mappings_missing_account_id(self, app, client):
        """Test bulk delete with missing account_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"category_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "account_id is required" in response.json["error"]

    def test_bulk_delete_mappings_missing_category_id(self, app, client):
        """Test bulk delete with missing category_id"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "category_id is required" in response.json["error"]

    def test_bulk_delete_mappings_success(self, app, client, test_account, test_epg_source):
        """Test bulk delete of mappings in a category"""
        from models import Category, Channel, ChannelEpgMapping, EpgChannel

        with app.app_context():
            # Create a category
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test Category",
            )
            db.session.add(category)
            db.session.flush()

            # Create EPG channel
            epg_ch = EpgChannel(
                source_id=test_epg_source,
                channel_id="epg1",
                display_name="EPG Channel",
            )
            db.session.add(epg_ch)
            db.session.flush()

            # Create channels with mappings
            channel_ids = []
            for i in range(3):
                ch = Channel(
                    account_id=test_account,
                    stream_id=f"stream{i}",
                    name=f"Channel {i}",
                    category_id=category.id,
                    is_active=True,
                )
                db.session.add(ch)
                db.session.flush()
                channel_ids.append(ch.id)

                mapping = ChannelEpgMapping(
                    channel_id=ch.id,
                    epg_channel_id=epg_ch.id,
                    mapping_type="manual",
                    confidence=1.0,
                )
                db.session.add(mapping)

            db.session.commit()
            category_id = category.id

        # Bulk delete
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": category_id},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True
        assert response.json["deleted_count"] == 3

    def test_bulk_delete_mappings_empty_category(self, app, client, test_account):
        """Test bulk delete when category has no channels"""
        response = client.post(
            "/api/epg/mappings/bulk-delete",
            json={"account_id": test_account, "category_id": 999},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["deleted_count"] == 0
