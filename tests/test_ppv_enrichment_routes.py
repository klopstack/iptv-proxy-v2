"""Tests for PPV enrichment routes."""

from unittest.mock import MagicMock, patch

import pytest

from models import Channel, db


class TestPPVEnrichmentRoutes:
    """Tests for PPV enrichment API endpoints."""

    @pytest.fixture
    def test_ppv_channels(self, app, test_account):
        """Create test PPV channels."""
        with app.app_context():
            channels = []
            for i in range(3):
                channel = Channel(
                    account_id=test_account,
                    stream_id=str(1000 + i),
                    name=f"PPV Channel {i}",
                    is_ppv=True,
                    ppv_enrichment_status="queued",
                )
                db.session.add(channel)
                channels.append(channel)
            db.session.commit()
            return [channel.id for channel in channels]

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_get_enrichment_status(self, mock_get_service, client, test_account, test_ppv_channels):
        """Test getting enrichment status."""
        # Mock the service instance
        mock_service = MagicMock()
        mock_service.get_status.return_value = {
            "detail_queue_size": 3,
            "detail_thread_running": False,
            "calendar_cache_stats": {"size": 0},
            "cumulative_stats": {"calendar_processed": "0", "calendar_matched": "0"},
            "session_stats": {},
        }
        mock_get_service.return_value = mock_service

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "detail_queue_size" in data

    def test_queue_all_ppv_channels(self, client, test_account, test_ppv_channels):
        """Test queuing all PPV channels."""
        response = client.post("/api/ppv-enrichment/queue/all-ppv", json={}, content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        assert "queued" in data
        assert data["queued"] == 3

    def test_queue_account_channels(self, client, test_account, test_ppv_channels):
        """Test queuing channels for a specific account."""
        response = client.post(
            "/api/ppv-enrichment/queue/all-ppv",
            json={"account_id": test_account},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "queued" in data

    def test_queue_account_not_found(self, client):
        """Test queuing channels when no PPV channels exist."""
        response = client.post(
            "/api/ppv-enrichment/queue/all-ppv",
            json={"account_id": 99999},
            content_type="application/json",
        )
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_process_enrichment(self, mock_get_service, client, test_account, test_ppv_channels):
        """Test processing enrichment."""
        mock_service = MagicMock()
        mock_service.enrich_channels.return_value = {
            "processed": 2,
            "matched": 1,
            "no_match": 1,
        }
        mock_get_service.return_value = mock_service

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        assert "processed" in data

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_process_with_account_id(self, mock_get_service, client, test_account, test_ppv_channels):
        """Test processing with account_id parameter."""
        mock_service = MagicMock()
        mock_service.enrich_channels.return_value = {
            "processed": 3,
            "matched": 2,
            "no_match": 1,
        }
        mock_get_service.return_value = mock_service

        response = client.post(
            "/api/ppv-enrichment/process",
            json={"account_id": test_account},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "processed" in data

    def test_get_enrichment_settings(self, client):
        """Test getting enrichment settings."""
        response = client.get("/api/ppv-enrichment/settings")
        assert response.status_code == 200
        data = response.get_json()
        assert "detail_fetch_batch_size" in data
        assert "calendar_scraping" in data
        assert "detail_fetching" in data

    def test_queue_specific_channels(self, client, test_ppv_channels):
        """Test queuing specific channels by ID."""
        channel_ids = test_ppv_channels[:2]
        response = client.post(
            "/api/ppv-enrichment/queue/channels",
            json={"channel_ids": channel_ids},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "queued" in data
        assert data["queued"] == 2

    def test_queue_channels_missing_channel_ids(self, client):
        """Test queuing channels without providing channel_ids."""
        response = client.post(
            "/api/ppv-enrichment/queue/channels",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_queue_channels_not_found(self, client):
        """Test queuing channels with non-existent IDs."""
        response = client.post(
            "/api/ppv-enrichment/queue/channels",
            json={"channel_ids": [99999, 99998]},
            content_type="application/json",
        )
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_process_error_handling(self, mock_get_service, client, test_account, test_ppv_channels):
        """Test error handling when processing fails."""
        mock_service = MagicMock()
        mock_service.enrich_channels.side_effect = Exception("Test error")
        mock_get_service.return_value = mock_service

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_get_status_error_handling(self, mock_get_service, client):
        """Test error handling when getting status fails."""
        mock_service = MagicMock()
        mock_service.get_status.side_effect = Exception("Status error")
        mock_get_service.return_value = mock_service

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_start_detail_thread(self, mock_get_service, client):
        """Test starting the detail fetcher thread."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        response = client.post("/api/ppv-enrichment/detail-thread/start")
        assert response.status_code == 200
        data = response.get_json()
        assert data["running"] is True
        mock_service.start_detail_fetcher.assert_called_once()

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_stop_detail_thread(self, mock_get_service, client):
        """Test stopping the detail fetcher thread."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        response = client.post("/api/ppv-enrichment/detail-thread/stop")
        assert response.status_code == 200
        data = response.get_json()
        assert data["running"] is False
        mock_service.stop_detail_fetcher.assert_called_once()

    def test_get_enrichment_channels(self, client, test_account, test_ppv_channels):
        """Test listing PPV channels with enrichment status."""
        response = client.get("/api/ppv-enrichment/channels")
        assert response.status_code == 200
        data = response.get_json()

        assert "channels" in data
        assert "pagination" in data
        assert "summary" in data
        assert data["pagination"]["total"] == 3
        assert len(data["channels"]) == 3
        assert all(ch["ppv_enrichment_status"] == "queued" for ch in data["channels"])

    def test_get_enrichment_channels_account_filter(self, client, test_account, test_ppv_channels):
        """Test account filter on enrichment channels endpoint."""
        response = client.get(f"/api/ppv-enrichment/channels?account_id={test_account}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["pagination"]["total"] == 3

    def test_get_enrichment_channels_status_filter(self, client, test_account, test_ppv_channels):
        """Test status filter on enrichment channels endpoint."""
        with client.application.app_context():
            channel = db.session.get(Channel, test_ppv_channels[0])
            channel.ppv_enrichment_status = "no_match"
            db.session.commit()

        response = client.get("/api/ppv-enrichment/channels?status=no_match")
        assert response.status_code == 200
        data = response.get_json()
        assert data["pagination"]["total"] == 1
        assert data["channels"][0]["ppv_enrichment_status"] == "no_match"
