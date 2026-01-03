"""Tests for PPV enrichment routes."""

from unittest.mock import MagicMock, patch

import pytest

from models import Account, Channel, db


class TestPPVEnrichmentRoutes:
    """Tests for PPV enrichment API endpoints."""

    @pytest.fixture
    def test_account(self):
        """Create a test account."""
        account = Account(
            name="Test Account",
            server="http://test.com",
            username="test",
            password="test",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        return account

    @pytest.fixture
    def test_ppv_channels(self, test_account):
        """Create test PPV channels."""
        channels = []
        for i in range(3):
            channel = Channel(
                account_id=test_account.id,
                stream_id=str(1000 + i),
                name=f"PPV Channel {i}",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            channels.append(channel)
        db.session.commit()
        return channels

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_get_enrichment_status(self, mock_get_queue, client, test_account, test_ppv_channels):
        """Test getting enrichment status."""
        # Mock the queue instance returned by get_enrichment_queue
        mock_queue = MagicMock()
        mock_queue.get_enrichment_status.return_value = {
            "queue_status": {"queued": 3, "processing": 0, "matched": 0},
            "cumulative_stats": {"total_queued": 3, "total_processed": 0},
            "api_usage": {"requests_today": 0, "daily_limit": 500},
            "timing": {},
        }
        mock_get_queue.return_value = mock_queue

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "queue_status" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_queue_all_ppv_channels(self, mock_get_queue, client, test_account, test_ppv_channels):
        """Test queuing all PPV channels."""
        mock_queue = MagicMock()
        mock_queue.queue_channels_for_enrichment.return_value = {
            "queued": 3,
            "skipped_already_matched": 0,
            "total_queued": 3,
        }
        mock_get_queue.return_value = mock_queue

        response = client.post("/api/ppv-enrichment/queue/all-ppv", json={}, content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        assert "queued" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_queue_account_channels(self, mock_get_queue, client, test_account, test_ppv_channels):
        """Test queuing channels for a specific account."""
        mock_queue = MagicMock()
        mock_queue.queue_channels_for_enrichment.return_value = {
            "queued": 3,
            "skipped_already_matched": 0,
            "total_queued": 3,
        }
        mock_get_queue.return_value = mock_queue

        response = client.post(
            "/api/ppv-enrichment/queue/all-ppv",
            json={"account_id": test_account.id},
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

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_process_enrichment_queue(self, mock_get_queue, client):
        """Test processing the enrichment queue."""
        mock_queue = MagicMock()
        mock_queue.process_queue.return_value = {
            "processed": 2,
            "matched": 1,
            "no_match": 1,
            "requests_used": 2,
        }
        mock_get_queue.return_value = mock_queue

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        assert "processed" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_process_with_max_requests(self, mock_get_queue, client):
        """Test processing queue with max_requests parameter."""
        mock_queue = MagicMock()
        mock_queue.process_queue.return_value = {
            "processed": 5,
            "matched": 3,
            "no_match": 2,
            "requests_used": 5,
        }
        mock_get_queue.return_value = mock_queue

        response = client.post(
            "/api/ppv-enrichment/process",
            json={"max_requests": 5},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "processed" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_get_enrichment_settings(self, mock_get_queue, client):
        """Test getting enrichment settings."""
        mock_queue = MagicMock()
        mock_queue.batch_size = 10
        mock_queue.requests_per_minute = 30
        mock_queue.request_interval_seconds = 2.0
        mock_get_queue.return_value = mock_queue

        response = client.get("/api/ppv-enrichment/settings")
        assert response.status_code == 200
        data = response.get_json()
        assert "batch_size" in data
        assert data["batch_size"] == 10

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_queue_specific_channels(self, mock_get_queue, client, test_ppv_channels):
        """Test queuing specific channels by ID."""
        mock_queue = MagicMock()
        mock_queue.queue_channels_for_enrichment.return_value = {
            "queued": 2,
            "skipped_already_matched": 0,
            "total_queued": 2,
        }
        mock_get_queue.return_value = mock_queue

        channel_ids = [test_ppv_channels[0].id, test_ppv_channels[1].id]
        response = client.post(
            "/api/ppv-enrichment/queue/channels",
            json={"channel_ids": channel_ids},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "queued" in data

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

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_process_queue_error_handling(self, mock_get_queue, client):
        """Test error handling when processing queue fails."""
        mock_queue = MagicMock()
        mock_queue.process_queue.side_effect = Exception("Test error")
        mock_get_queue.return_value = mock_queue

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_get_status_error_handling(self, mock_get_queue, client):
        """Test error handling when getting status fails."""
        mock_queue = MagicMock()
        mock_queue.get_enrichment_status.side_effect = Exception("Status error")
        mock_get_queue.return_value = mock_queue

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data

    @patch("routes.ppv_enrichment.get_enrichment_queue")
    def test_queue_all_error_handling(self, mock_get_queue, client, test_ppv_channels):
        """Test error handling when queuing all fails."""
        mock_queue = MagicMock()
        mock_queue.queue_channels_for_enrichment.side_effect = Exception("Queue error")
        mock_get_queue.return_value = mock_queue

        response = client.post("/api/ppv-enrichment/queue/all-ppv", json={}, content_type="application/json")
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data
