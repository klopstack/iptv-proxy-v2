"""
Tests for new sync endpoints
"""
from unittest.mock import MagicMock, patch

import pytest


class TestSyncEndpoints:
    """Test the new per-category sync endpoints"""

    @patch("services.epg_sync_service.EpgSyncService.sync_source")
    @patch("services.epg_sync_service.EpgSyncService.update_source_sync_status")
    def test_sync_epg_sources(self, mock_update, mock_sync, app, client):
        """Test syncing all EPG sources"""
        from models import EpgSource, db

        with app.app_context():
            # Create test EPG sources
            source1 = EpgSource(
                name="Test EPG 1",
                source_type="xmltv_url",
                url="http://test.com/epg1.xml",
                enabled=True,
            )
            source2 = EpgSource(
                name="Test EPG 2",
                source_type="xmltv_url",
                url="http://test.com/epg2.xml",
                enabled=True,
            )
            source3 = EpgSource(
                name="Test EPG 3 (disabled)",
                source_type="xmltv_url",
                url="http://test.com/epg3.xml",
                enabled=False,
            )
            db.session.add_all([source1, source2, source3])
            db.session.commit()

            # Mock successful sync
            mock_sync.return_value = (True, "Synced successfully", {"channels_added": 10})

            response = client.post("/api/sync/epg")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert data["sources_synced"] == 2  # Only enabled sources
            assert data["total_sources"] == 2
            assert len(data["results"]) == 2

            # Verify sync was called for each enabled source
            assert mock_sync.call_count == 2

    @patch("services.epg_sync_service.EpgSyncService.sync_source")
    @patch("services.epg_sync_service.EpgSyncService.update_source_sync_status")
    def test_sync_epg_sources_with_errors(self, mock_update, mock_sync, app, client):
        """Test syncing EPG sources when some fail"""
        from models import EpgSource, db

        with app.app_context():
            source1 = EpgSource(
                name="Test EPG Success",
                source_type="xmltv_url",
                url="http://test.com/epg1.xml",
                enabled=True,
            )
            source2 = EpgSource(
                name="Test EPG Fail",
                source_type="xmltv_url",
                url="http://test.com/epg2.xml",
                enabled=True,
            )
            db.session.add_all([source1, source2])
            db.session.commit()

            # Mock one success, one failure
            mock_sync.side_effect = [
                (True, "Synced successfully", {"channels_added": 10}),
                (False, "Failed to sync", {}),
            ]

            response = client.post("/api/sync/epg")
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert data["sources_synced"] == 1
            assert data["total_sources"] == 2

    @patch("services.fcc_facility_service.FccFacilityService.full_sync")
    def test_sync_fcc_data_success(self, mock_full_sync, app, client):
        """Test successful FCC data sync"""
        mock_full_sync.return_value = {
            "success": True,
            "stats": {"added": 100, "updated": 50, "total": 1000},
        }

        response = client.post("/api/sync/fcc")
        assert response.status_code == 200

        data = response.get_json()
        assert data["success"] is True
        assert "stats" in data
        assert "100 added" in data["message"]
        assert "50 updated" in data["message"]
        assert "1000 total" in data["message"]

    @patch("services.fcc_facility_service.FccFacilityService.full_sync")
    def test_sync_fcc_data_failure(self, mock_full_sync, app, client):
        """Test failed FCC data sync"""
        mock_full_sync.return_value = {"success": False, "message": "Download failed"}

        response = client.post("/api/sync/fcc")
        assert response.status_code == 500

        data = response.get_json()
        assert data["success"] is False
        assert "error" in data
