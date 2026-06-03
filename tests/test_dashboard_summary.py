"""Tests for dashboard summary API (TODO 106)."""

import json
from unittest.mock import patch

from models import ActiveStream, Credential, db
from tests.conftest import api_data


class TestDashboardSummary:
    def test_dashboard_summary_data_envelope(self, client):
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 200
        data = api_data(response)
        assert "channel_health" in data
        assert "streams" in data
        assert "overview" in data
        assert "generated_at" in data
        assert "by_status" in data["channel_health"]
        assert "total" in data["channel_health"]

    def test_dashboard_summary_streams_shape(self, client):
        data = api_data(client.get("/api/dashboard/summary"))
        streams = data["streams"]
        assert "active_sessions" in streams
        assert "shared_upstream" in streams
        assert "subscribers" in streams
        assert "backend" in streams
        assert isinstance(streams["active_sessions"], int)

    def test_dashboard_summary_overview_scheduler(self, client):
        data = api_data(client.get("/api/dashboard/summary"))
        overview = data["overview"]
        assert "accounts" in overview
        assert "scheduler" in overview
        assert "total" in overview["accounts"]
        assert "has_sync_issues" in overview["scheduler"]

    def test_dashboard_summary_active_sessions_count(self, app, client, sample_account):
        with app.app_context():
            account_id = sample_account["id"]
            cred = Credential(
                account_id=account_id,
                username="dashuser",
                password="dashpass",
                enabled=True,
            )
            db.session.add(cred)
            db.session.flush()
            db.session.add(
                ActiveStream(
                    credential_id=cred.id,
                    stream_id="100",
                    client_ip="127.0.0.1",
                    session_token="dash-session-1",
                )
            )
            db.session.commit()

        data = api_data(client.get("/api/dashboard/summary"))
        assert data["streams"]["active_sessions"] == 1

    def test_channel_health_summary_matches_dashboard(self, client, app):
        health = client.get("/api/channel-health/summary")
        dash = client.get("/api/dashboard/summary")
        health_summary = json.loads(health.data)["summary"]
        dash_health = api_data(dash)["channel_health"]
        assert dash_health["total"] == health_summary["total"]
        assert dash_health["by_status"] == health_summary["by_status"]


class TestOverviewStatsCoverageFix:
    def test_overview_stats_uses_coverage_percent_key(self, app, client):
        with patch(
            "services.epg.coverage.get_epg_coverage_stats",
            return_value={
                "coverage_percent": 42.5,
                "channels_with_epg_mapping": 99,
            },
        ):
            response = client.get("/api/overview/stats")

        assert response.status_code == 200
        payload = response.get_json()
        stats = payload.get("data", payload)
        assert stats["epg"]["coverage"]["percentage"] == 42.5
        assert stats["epg"]["coverage"]["mapped_channels"] == 99
