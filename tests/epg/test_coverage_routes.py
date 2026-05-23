"""Tests for EPG coverage and matching endpoints."""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db


class TestEpgCoverage:
    """Tests for EPG coverage endpoints"""

    @patch("routes.epg.sources.get_epg_coverage_stats")
    def test_get_epg_coverage(self, mock_coverage, app, client):
        """Test getting EPG coverage stats"""
        mock_coverage.return_value = {"total_channels": 100, "mapped_channels": 50}

        response = client.get("/api/epg/coverage")
        assert response.status_code == 200
        assert "total_channels" in response.json

    @patch("routes.epg.sources.get_epg_coverage_stats")
    def test_get_epg_coverage_with_account(self, mock_coverage, app, client, test_account):
        """Test getting EPG coverage stats for specific account"""
        mock_coverage.return_value = {"total_channels": 50, "mapped_channels": 25}

        response = client.get(f"/api/epg/coverage?account_id={test_account}")
        assert response.status_code == 200
        mock_coverage.assert_called_once_with(test_account)

    @patch("routes.epg.sources.get_category_epg_coverage")
    def test_get_category_coverage(self, mock_coverage, app, client, test_account):
        """Test getting EPG coverage by category"""
        mock_coverage.return_value = [{"category_id": 1, "total": 10, "mapped": 5}]

        response = client.get(f"/api/epg/coverage/categories/{test_account}")
        assert response.status_code == 200

    def test_get_category_coverage_account_not_found(self, app, client):
        """Test category coverage for non-existent account"""
        response = client.get("/api/epg/coverage/categories/999")
        assert response.status_code == 404


# ============================================================================
# EPG Matching Tests
# ============================================================================


class TestEpgMatching:
    """Tests for EPG matching endpoints"""

    def test_match_channels_account_not_found(self, app, client):
        """Test matching channels for non-existent account"""
        response = client.post("/api/epg/match/999")
        assert response.status_code == 404

    @patch("services.epg.match_rules.EpgMatchRulesService.match_channels_with_rules")
    def test_match_channels_success(self, mock_match, app, client, test_account):
        """Test successful channel matching (redirects to rule-based matching)"""
        mock_match.return_value = {
            "total_channels": 20,
            "skipped_existing": 2,
            "excluded": 0,
            "matched": 18,
            "unmatched": 0,
        }

        response = client.post(f"/api/epg/match/{test_account}")
        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"
        assert "match-with-rules" in response.headers.get("Link", "")
        assert response.json["success"] is True
        assert "18 channels" in response.json["message"]
        assert "skipped 2" in response.json["message"]
