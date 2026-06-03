"""
Tests for app.py routes that need coverage

Uses shared fixtures from conftest.py for proper test isolation.
"""

from unittest.mock import Mock, patch

import pytest

from tests.conftest import api_data

ADMIN_PAGES = [
    "/",
    "/accounts",
    "/filters",
    "/preview",
    "/categories",
    "/rulesets",
    "/settings",
    "/epg",
    "/stations",
    "/channel-health",
    "/ppv",
    "/xtream",
]

# client and sample_account fixtures are provided by conftest.py


class TestAccountRoutes:
    """Test account-related routes"""

    @patch("routes.accounts.IPTVService")
    def test_test_account_success(self, mock_iptv_service, client, sample_account):
        """Test account connection test - success"""
        mock_service = Mock()
        mock_service.authenticate.return_value = {
            "server_info": {"url": "http://test.server.com", "time_now": "2024-12-19 10:00:00"},
            "user_info": {"username": "testuser", "status": "Active", "exp_date": "1735689600", "max_connections": "1"},
        }
        mock_service.get_live_streams.return_value = [
            {"stream_id": 101, "name": "ESPN"},
            {"stream_id": 102, "name": "CNN"},
        ]
        mock_service.get_live_categories.return_value = [
            {"category_id": "1", "category_name": "Sports"},
            {"category_id": "2", "category_name": "News"},
        ]
        mock_iptv_service.return_value = mock_service

        response = client.post(f"/api/accounts/{sample_account['id']}/test")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert data["channels"] == 2
        assert data["categories"] == 2
        # API now returns connection_status and credentials instead of server_info/user_info
        assert "connection_status" in data
        assert "credentials" in data

    @patch("routes.accounts.IPTVService")
    def test_test_account_failure(self, mock_iptv_service, client, sample_account):
        """Test account connection test - failure"""
        mock_service = Mock()
        mock_service.authenticate.side_effect = Exception("Connection failed")
        mock_iptv_service.return_value = mock_service

        response = client.post(f"/api/accounts/{sample_account['id']}/test")

        assert response.status_code == 400
        data = response.json
        assert data["success"] is False
        assert "error" in data

    @patch("routes.accounts.get_iptv_service_for_account")
    @patch("routes.accounts.cache_service")
    def test_get_account_categories(self, mock_cache, mock_get_service, client, sample_account):
        """Test fetching account categories from cache without upstream call"""
        mock_cache.get_cached_categories.return_value = [
            {"category_id": "1", "category_name": "Sports"},
            {"category_id": "2", "category_name": "Movies"},
        ]

        response = client.get(f"/api/accounts/{sample_account['id']}/categories")

        assert response.status_code == 200
        data = api_data(response)
        assert len(data) == 2
        assert data[0]["category_name"] == "Sports"
        mock_get_service.assert_not_called()

    @patch("routes.accounts.get_iptv_service_for_account")
    def test_sync_account_categories_error(self, mock_get_service, client, sample_account):
        """Test syncing account categories - upstream error"""
        mock_service = Mock()
        mock_service.get_live_categories.side_effect = Exception("API Error")
        mock_get_service.return_value = mock_service

        response = client.post(f"/api/accounts/{sample_account['id']}/categories/sync")

        assert response.status_code == 500
        data = response.json
        assert "error" in data

    @patch("routes.accounts.get_iptv_service_for_account")
    @patch("routes.accounts.cache_service")
    def test_get_account_stats(self, mock_cache, mock_get_service, client, sample_account):
        """Test fetching account statistics"""
        mock_service = Mock()
        mock_service.get_live_streams.return_value = [
            {"stream_id": 101, "name": "ESPN", "category_id": "1"},
            {"stream_id": 102, "name": "CNN", "category_id": "2"},
        ]
        mock_service.get_live_categories.return_value = [
            {"category_id": "1", "category_name": "Sports"},
            {"category_id": "2", "category_name": "News"},
        ]
        mock_get_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = None
        mock_cache.get_cached_categories.return_value = None

        response = client.get(f"/api/accounts/{sample_account['id']}/stats")

        assert response.status_code == 200
        data = response.json
        assert data["total_channels"] == 2
        assert data["total_categories"] == 2
        assert "category_counts" in data

    @patch("routes.accounts.get_iptv_service_for_account")
    def test_get_account_stats_error(self, mock_get_service, client, sample_account):
        """Test fetching account stats - error"""
        mock_service = Mock()
        mock_service.get_live_streams.side_effect = Exception("API Error")
        mock_get_service.return_value = mock_service

        response = client.get(f"/api/accounts/{sample_account['id']}/stats")

        assert response.status_code == 400
        data = response.json
        assert "error" in data


class TestWebUIRoutes:
    """Test web UI template routes"""

    @pytest.mark.parametrize("path", ADMIN_PAGES)
    def test_admin_pages_return_200(self, client, path):
        """All admin HTML pages return 200 on GET."""
        response = client.get(path)
        assert response.status_code == 200


class TestAccountFiltersRoute:
    """Test account-specific filters endpoint"""

    def test_get_account_filters_empty(self, client, sample_account):
        """Test getting filters for account with no filters"""
        response = client.get(f"/api/accounts/{sample_account['id']}/filters")

        assert response.status_code == 200
        assert isinstance(api_data(response), list)

    def test_get_account_filters_with_filters(self, client, sample_account):
        """Test getting filters for account with filters"""
        # Create a filter
        client.post(
            "/api/filters",
            json={
                "account_id": sample_account["id"],
                "name": "Test Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "Sports",
                "enabled": True,
            },
        )

        response = client.get(f"/api/accounts/{sample_account['id']}/filters")

        assert response.status_code == 200
        data = api_data(response)
        assert len(data) >= 1
        assert data[0]["name"] == "Test Filter"

    def test_get_filters_for_nonexistent_account(self, client):
        """Test getting filters for non-existent account"""
        response = client.get("/api/accounts/99999/filters")

        # Account doesn't exist, so filters endpoint returns empty list
        # (doesn't validate account exists first)
        assert response.status_code == 200
        assert api_data(response) == []


class TestProcessTagsHelper:
    """Test _process_tags_for_account helper function"""

    @patch("routes.accounts.TagService")
    def test_process_tags_helper(self, mock_tag_service, client, sample_account):
        """Test tag processing helper function"""
        from routes.accounts import _process_tags_for_account

        mock_tag_service.get_rules_for_account.return_value = []
        mock_tag_service.extract_tags.return_value = ({"US", "HD"}, "ESPN", "Sports", "keep")
        mock_tag_service.normalize_tag_name.side_effect = lambda x: x.upper()

        streams = [{"stream_id": "101", "name": "US| ESPN HD", "category_id": "1"}]
        categories = [{"category_id": "1", "category_name": "Sports"}]

        # Should not raise
        _process_tags_for_account(sample_account["id"], streams, categories)
