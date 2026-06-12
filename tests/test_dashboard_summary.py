"""Tests for dashboard summary API (TODO 106)."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from models import Account, ActiveStream, Category, Channel, Credential, Event, EventChannelLink, db
from tests.conftest import api_data


class TestDashboardSummary:
    def test_dashboard_summary_data_envelope(self, client):
        response = client.get("/api/dashboard/summary")
        assert response.status_code == 200
        data = api_data(response)
        assert "channel_health" in data
        assert "streams" in data
        assert "overview" in data
        assert "ppv" in data
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
        assert "total_max_connections" in streams
        assert "total_active_connections" in streams
        assert "available_connections" in streams
        assert "accounts" in streams
        assert "active_streams" in streams
        assert isinstance(streams["active_sessions"], int)
        assert isinstance(streams["accounts"], list)
        assert isinstance(streams["active_streams"], list)

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
                max_connections=2,
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
        streams = data["streams"]
        assert streams["active_sessions"] == 1
        assert streams["total_active_connections"] == 1
        assert streams["total_max_connections"] >= 2
        assert streams["available_connections"] == streams["total_max_connections"] - 1
        assert len(streams["accounts"]) == 1
        assert streams["accounts"][0]["name"] == sample_account["name"]
        dash_cred = next(c for c in streams["accounts"][0]["credentials"] if c["username"] == "dashuser")
        assert dash_cred["active_connections"] == 1
        assert dash_cred["max_connections"] == 2
        assert len(streams["active_streams"]) == 1
        assert streams["active_streams"][0]["stream_id"] == "100"
        assert streams["active_streams"][0]["credential_username"] == "dashuser"
        assert streams["active_streams"][0]["account_name"] == sample_account["name"]
        assert "session_token" not in streams["active_streams"][0]

    def test_channel_health_summary_matches_dashboard(self, client, app):
        health = client.get("/api/channel-health/summary")
        dash = client.get("/api/dashboard/summary")
        health_summary = json.loads(health.data)["summary"]
        dash_health = api_data(dash)["channel_health"]
        assert dash_health["total"] == health_summary["total"]
        assert dash_health["by_status"] == health_summary["by_status"]

    def test_dashboard_summary_ppv_shape(self, client):
        data = api_data(client.get("/api/dashboard/summary"))
        ppv = data["ppv"]
        assert "ppv_channels" in ppv
        assert "events" in ppv
        assert "channel_links" in ppv
        assert "enrichment" in ppv
        assert "has_issues" in ppv
        assert "upcoming_24h" in ppv["events"]
        assert "upcoming_48h" in ppv["events"]
        assert "without_channels" in ppv["events"]
        assert "queued_count" in ppv["enrichment"]
        assert "no_match_count" in ppv["enrichment"]
        assert "recently_enriched_24h" in ppv["enrichment"]
        assert isinstance(ppv["has_issues"], bool)

    def test_dashboard_summary_ppv_counts(self, app, client):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with app.app_context():
            account = Account(name="PPV Dash", server="http://test.com", username="u", password="p")
            db.session.add(account)
            db.session.flush()

            category = Category(account_id=account.id, category_id="ppv", category_name="PPV")
            db.session.add(category)
            db.session.flush()

            linked_event = Event(
                external_id="dash-linked",
                source=Event.SOURCE_THESPORTSDB,
                sport="Soccer",
                home_team_id="1",
                home_team_name="Home",
                away_team_id="2",
                away_team_name="Away",
                scheduled_at=now + timedelta(hours=12),
                is_ppv=True,
            )
            unlinked_event = Event(
                external_id="dash-unlinked",
                source=Event.SOURCE_THESPORTSDB,
                sport="Soccer",
                home_team_id="3",
                home_team_name="Alpha",
                away_team_id="4",
                away_team_name="Beta",
                scheduled_at=now + timedelta(hours=36),
                is_ppv=True,
            )
            far_event = Event(
                external_id="dash-far",
                source=Event.SOURCE_THESPORTSDB,
                sport="Soccer",
                home_team_id="5",
                home_team_name="Gamma",
                away_team_id="6",
                away_team_name="Delta",
                scheduled_at=now + timedelta(hours=72),
                is_ppv=True,
            )
            db.session.add_all([linked_event, unlinked_event, far_event])
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                category_id=category.id,
                stream_id="ppv1",
                name="PPV Test",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="matched",
                ppv_enrichment_last_attempt=now - timedelta(hours=2),
            )
            no_match_channel = Channel(
                account_id=account.id,
                category_id=category.id,
                stream_id="ppv2",
                name="PPV No Match",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="no_match",
            )
            db.session.add_all([channel, no_match_channel])
            db.session.flush()

            db.session.add(EventChannelLink(event_id=linked_event.id, channel_id=channel.id))
            db.session.commit()

        with patch(
            "services.ppv.dashboard_stats.PPVEnrichmentOrchestrator.get_queue_stats",
            return_value={"queued_count": 3, "hot_queued_count": 1},
        ):
            data = api_data(client.get("/api/dashboard/summary"))

        ppv = data["ppv"]
        assert ppv["ppv_channels"] == 2
        assert ppv["events"]["upcoming_24h"] == 1
        assert ppv["events"]["upcoming_48h"] == 2
        assert ppv["events"]["without_channels"] == 1
        assert ppv["channel_links"] == 1
        assert ppv["enrichment"]["queued_count"] == 3
        assert ppv["enrichment"]["no_match_count"] == 1
        assert ppv["enrichment"]["recently_enriched_24h"] == 1
        assert ppv["has_issues"] is True


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
        stats = api_data(response)
        assert stats["epg"]["coverage"]["percentage"] == 42.5
        assert stats["epg"]["coverage"]["mapped_channels"] == 99
