"""
Tests for sync endpoints (accounts, FCC).

Bulk EPG sync (POST /api/sync/epg) lives in test_epg_sync_api.py.
"""
from unittest.mock import patch


class TestSyncEndpoints:
    """Sync endpoints for accounts and FCC data."""

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
