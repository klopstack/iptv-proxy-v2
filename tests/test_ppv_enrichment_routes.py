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

    @patch("services.jobs.ppv_enrichment.run_ppv_enrichment")
    def test_process_enrichment(self, mock_run, client, test_account, test_ppv_channels):
        """Test processing enrichment."""
        mock_run.return_value = {
            "channels_processed": 2,
            "channels_matched": 1,
            "channels_no_match": 1,
            "batches_run": 1,
        }

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        assert "channels_processed" in data

    @patch("services.ppv.orchestrator.get_ppv_orchestrator")
    def test_process_with_account_id(self, mock_get_orchestrator, client, test_account, test_ppv_channels):
        """Test processing with account_id parameter."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.enrich_pending_channels.return_value = {
            "channels_processed": 3,
            "channels_matched": 2,
            "channels_no_match": 1,
        }
        mock_orchestrator.get_queue_stats.return_value = {"queued_count": 0}
        mock_get_orchestrator.return_value = mock_orchestrator

        response = client.post(
            "/api/ppv-enrichment/process",
            json={"account_id": test_account},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "channels_processed" in data

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

    @patch("services.jobs.ppv_enrichment.run_ppv_enrichment")
    def test_process_error_handling(self, mock_run, client, test_account, test_ppv_channels):
        """Test error handling when processing fails."""
        mock_run.side_effect = Exception("Test error")

        response = client.post("/api/ppv-enrichment/process", json={}, content_type="application/json")
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert "error" in data
        assert "Test error" not in data["error"]

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    def test_get_status_error_handling(self, mock_get_service, client):
        """Test error handling when getting status fails."""
        mock_service = MagicMock()
        mock_service.get_status.side_effect = Exception("Status error")
        mock_get_service.return_value = mock_service

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert "error" in data
        assert "Status error" not in data["error"]

    @patch("routes.ppv_enrichment.get_calendar_enrichment_service")
    @patch("services.ppv.orchestrator.get_ppv_orchestrator")
    def test_get_status_queue_stats_degraded(self, mock_get_orchestrator, mock_get_service, client):
        """Queue stats failure is logged and flagged in the response."""
        mock_service = MagicMock()
        mock_service.get_status.return_value = {
            "detail_queue_size": 0,
            "detail_thread_running": False,
            "calendar_cache_stats": {},
            "cumulative_stats": {},
            "session_stats": {},
        }
        mock_get_service.return_value = mock_service
        mock_get_orchestrator.return_value.get_queue_stats.side_effect = RuntimeError("queue unavailable")

        response = client.get("/api/ppv-enrichment/status")
        assert response.status_code == 200
        data = response.get_json()
        assert data["queue_stats_error"] is True
        assert "queued_count" not in data

    @patch("services.jobs.ppv_enrichment.run_ppv_enrichment")
    @patch("services.ppv.orchestrator.get_ppv_orchestrator")
    def test_process_include_no_match_requeues_then_drains(
        self, mock_get_orchestrator, mock_run, client, test_account, test_ppv_channels
    ):
        """include_no_match re-queues via bulk update instead of loading all channels."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.requeue_no_match_channels.return_value = 2
        mock_get_orchestrator.return_value = mock_orchestrator
        mock_run.return_value = {"channels_processed": 2, "channels_matched": 1, "channels_no_match": 0}

        response = client.post(
            "/api/ppv-enrichment/process",
            json={"include_no_match": True},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        mock_orchestrator.requeue_no_match_channels.assert_called_once_with(account_id=None)
        mock_run.assert_called_once()
        assert data["no_match_requeued"] == 2

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

    # ------------------------------------------------------------------
    # Provider settings endpoints
    # ------------------------------------------------------------------

    def test_get_provider_settings_returns_list(self, client):
        """GET /api/ppv-enrichment/provider-settings returns a providers list."""
        response = client.get("/api/ppv-enrichment/provider-settings")
        assert response.status_code == 200
        data = response.get_json()
        assert "providers" in data
        # The LLM enrichment virtual provider should always be present
        names = [p["name"] for p in data["providers"]]
        assert "llm_enrichment" in names

    def test_get_provider_settings_football_data_fields(self, client):
        """football_data provider exposes an api_key field."""
        response = client.get("/api/ppv-enrichment/provider-settings")
        assert response.status_code == 200
        providers = {p["name"]: p for p in response.get_json()["providers"]}
        assert "football_data" in providers
        keys = [f["key"] for f in providers["football_data"]["fields"]]
        assert "api_key" in keys

    def test_set_provider_setting_stores_value(self, client, app):
        """PUT /api/ppv-enrichment/provider-settings stores a value."""
        from models.provider_settings import ProviderSettings

        response = client.put(
            "/api/ppv-enrichment/provider-settings/football_data/api_key",
            json={"value": "test-key-123"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["key"] == "api_key"
        assert data["provider"] == "football_data"

        with app.app_context():
            assert ProviderSettings.get("football_data", "api_key") == "test-key-123"

    def test_set_provider_setting_unknown_provider(self, client):
        """PUT for unknown provider returns 404."""
        response = client.put(
            "/api/ppv-enrichment/provider-settings/nonexistent/api_key",
            json={"value": "x"},
        )
        assert response.status_code == 404

    def test_set_provider_setting_unknown_key(self, client):
        """PUT for unknown key on a known provider returns 400."""
        response = client.put(
            "/api/ppv-enrichment/provider-settings/football_data/nonexistent_key",
            json={"value": "x"},
        )
        assert response.status_code == 400

    def test_set_provider_setting_missing_body(self, client):
        """PUT without a body returns 400."""
        response = client.put(
            "/api/ppv-enrichment/provider-settings/football_data/api_key",
            json={},
        )
        assert response.status_code == 400

    def test_password_fields_are_masked(self, client, app):
        """Password field values are masked in GET response."""
        from models.provider_settings import ProviderSettings

        with app.app_context():
            ProviderSettings.set("football_data", "api_key", "secretvalue")

        response = client.get("/api/ppv-enrichment/provider-settings")
        providers = {p["name"]: p for p in response.get_json()["providers"]}
        api_key_field = next(f for f in providers["football_data"]["fields"] if f["key"] == "api_key")
        assert "****" in api_key_field["current_value"]
        assert "secretvalue" not in api_key_field["current_value"]
