"""Tests for error-handling hygiene improvements (TODO 33)."""
import os
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_cache_dir():
    """Mock the EPG cache directory to use a temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"EPG_CACHE_DIR": tmpdir}):
            yield tmpdir


class TestOverviewStatsErrorHandling:
    """Overview stats should log failures and return structured fallbacks."""

    def test_overview_stats_epg_coverage_failure_returns_defaults(self, app, client):
        with patch("services.epg.coverage.get_epg_coverage_stats", side_effect=RuntimeError("coverage down")):
            response = client.get("/api/overview/stats")

        assert response.status_code == 200
        coverage = response.json["epg"]["coverage"]
        assert coverage["percentage"] == 0
        assert coverage["mapped_channels"] == 0
        assert coverage["error"] == "coverage down"

    def test_overview_stats_sync_metadata_failure_returns_null_sync_times(self, app, client):
        with patch("routes.api._scheduler") as mock_scheduler:
            mock_scheduler.get_status.return_value = {"running": False}
            with patch("models.SyncMetadata.get", side_effect=RuntimeError("metadata unavailable")):
                response = client.get("/api/overview/stats")

        assert response.status_code == 200
        last_sync = response.json["last_full_sync"]
        assert last_sync["accounts"] is None
        assert last_sync["epg"] is None
        assert last_sync["error"] == "metadata unavailable"


class TestEpgCacheErrorHandling:
    """Cache validity checks should fail safely when metadata is corrupt."""

    def test_is_cache_valid_invalid_metadata_returns_false(self, app, mock_cache_dir, caplog):
        import json

        from services.epg.cache import get_cache_meta_path, is_cache_valid, save_to_cache

        save_to_cache(1, b"<tv></tv>")
        meta_path = get_cache_meta_path(1)
        meta_path.write_text(json.dumps({"cached_at": "not-a-datetime", "source_id": 1}))

        with caplog.at_level("WARNING"):
            assert is_cache_valid(1, max_age_hours=24) is False

        assert any("Invalid cache metadata for source 1" in record.message for record in caplog.records)


class TestEpgParsingErrorHandling:
    """EPG parsing should skip malformed programme timestamps without aborting sync."""

    def test_sync_epg_source_skips_invalid_programme_times(self, app):
        from models import EpgSource, db
        from services.epg.parsing import sync_epg_source

        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="ch1"><display-name>Channel 1</display-name></channel>
  <programme start="not-a-time" stop="also-bad" channel="ch1">
    <title>Bad Times</title>
  </programme>
  <programme start="20260101120000 +0000" stop="20260101130000 +0000" channel="ch1">
    <title>Good Times</title>
  </programme>
</tv>"""

        with app.app_context():
            source = EpgSource(
                name="Parsing Test Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            stats = sync_epg_source(source, xml_content)

            assert stats["channels_added"] == 1
            assert stats["total_programs"] == 2


class TestMatchRulesPreviewErrorHandling:
    """Match rule preview endpoints should surface internal failures."""

    def test_preview_name_mapping_query_failure_returns_error_json(self, app, client):
        with patch("models.Channel.query") as mock_query:
            mock_query.filter.return_value.limit.return_value.all.side_effect = RuntimeError("database unavailable")
            response = client.post(
                "/api/epg-match-rules/name-mappings/preview",
                json={"old_name": "ESPN", "match_type": "contains"},
            )

        assert response.status_code == 500
        assert response.json["error"] == "database unavailable"
        assert response.json["matches"] == []

    def test_preview_rule_pattern_query_failure_returns_error_json(self, app, client):
        with patch(
            "services.epg.match_rules.route_service.db.session.query",
            side_effect=RuntimeError("rules preview failed"),
        ):
            response = client.post(
                "/api/epg-match-rules/rules/preview",
                json={"match_type": "regex", "source": "channel_name", "pattern": "ESPN"},
            )

        assert response.status_code == 200
        assert response.json["error"] == "rules preview failed"
        assert response.json["matches"] == []

    def test_preview_exclusion_pattern_query_failure_returns_error_json(self, app, client):
        with patch(
            "services.epg.match_rules.route_service.db.session.query",
            side_effect=RuntimeError("exclusion preview failed"),
        ):
            response = client.post(
                "/api/epg-match-rules/exclusions/preview",
                json={"pattern_type": "channel_name", "pattern": "PPV", "is_regex": False},
            )

        assert response.status_code == 200
        assert response.json["error"] == "exclusion preview failed"
        assert response.json["matches"] == []
