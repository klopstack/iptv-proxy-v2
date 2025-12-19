"""
Tests for app.py routes that need coverage
"""

import pytest
from unittest.mock import Mock, patch


# Use fixtures from conftest or test_app
@pytest.fixture
def client():
    """Test client fixture"""
    import os
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from app import app, db
    
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()


@pytest.fixture
def sample_account(client):
    """Create a sample account"""
    response = client.post(
        "/api/accounts",
        json={
            "name": "Test Account",
            "server": "test.server.com",
            "username": "testuser",
            "password": "testpass",
            "enabled": True,
        },
    )
    return response.json


class TestAccountRoutes:
    """Test account-related routes"""

    @patch('routes.accounts.IPTVService')
    def test_test_account_success(self, mock_iptv_service, client, sample_account):
        """Test account connection test - success"""
        mock_service = Mock()
        mock_service.authenticate.return_value = {
            "server_info": {
                "url": "http://test.server.com",
                "time_now": "2024-12-19 10:00:00"
            },
            "user_info": {
                "username": "testuser",
                "status": "Active",
                "exp_date": "1735689600",
                "max_connections": "1"
            }
        }
        mock_iptv_service.return_value = mock_service
        
        response = client.post(f"/api/accounts/{sample_account['id']}/test")
        
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert "server_info" in data
        assert "user_info" in data

    @patch('routes.accounts.IPTVService')
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

    @patch('routes.accounts.IPTVService')
    @patch('routes.accounts.cache_service')
    def test_get_account_categories(self, mock_cache, mock_iptv_service, client, sample_account):
        """Test fetching account categories"""
        mock_service = Mock()
        mock_service.get_live_categories.return_value = [
            {"category_id": "1", "category_name": "Sports"},
            {"category_id": "2", "category_name": "Movies"}
        ]
        mock_iptv_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = None
        
        response = client.get(f"/api/accounts/{sample_account['id']}/categories")
        
        assert response.status_code == 200
        data = response.json
        assert len(data) == 2
        assert data[0]["category_name"] == "Sports"

    @patch('routes.accounts.IPTVService')
    def test_get_account_categories_error(self, mock_iptv_service, client, sample_account):
        """Test fetching account categories - error"""
        mock_service = Mock()
        mock_service.get_live_categories.side_effect = Exception("API Error")
        mock_iptv_service.return_value = mock_service
        
        response = client.get(f"/api/accounts/{sample_account['id']}/categories")
        
        assert response.status_code == 400
        data = response.json
        assert "error" in data

    @patch('routes.accounts.IPTVService')
    @patch('routes.accounts.cache_service')
    def test_get_account_stats(self, mock_cache, mock_iptv_service, client, sample_account):
        """Test fetching account statistics"""
        mock_service = Mock()
        mock_service.get_live_streams.return_value = [
            {"stream_id": 101, "name": "ESPN", "category_id": "1"},
            {"stream_id": 102, "name": "CNN", "category_id": "2"}
        ]
        mock_service.get_live_categories.return_value = [
            {"category_id": "1", "category_name": "Sports"},
            {"category_id": "2", "category_name": "News"}
        ]
        mock_iptv_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = None
        mock_cache.get_cached_categories.return_value = None
        
        response = client.get(f"/api/accounts/{sample_account['id']}/stats")
        
        assert response.status_code == 200
        data = response.json
        assert data["total_channels"] == 2
        assert data["total_categories"] == 2
        assert "category_counts" in data

    @patch('routes.accounts.IPTVService')
    def test_get_account_stats_error(self, mock_iptv_service, client, sample_account):
        """Test fetching account stats - error"""
        mock_service = Mock()
        mock_service.get_live_streams.side_effect = Exception("API Error")
        mock_iptv_service.return_value = mock_service
        
        response = client.get(f"/api/accounts/{sample_account['id']}/stats")
        
        assert response.status_code == 400
        data = response.json
        assert "error" in data


class TestWebUIRoutes:
    """Test web UI template routes"""

    def test_index_page(self, client):
        """Test index page loads"""
        response = client.get("/")
        assert response.status_code == 200

    def test_accounts_page(self, client):
        """Test accounts page loads"""
        response = client.get("/accounts")
        assert response.status_code == 200

    def test_filters_page(self, client):
        """Test filters page loads"""
        response = client.get("/filters")
        assert response.status_code == 200

    def test_test_page(self, client):
        """Test test page loads"""
        response = client.get("/test")
        assert response.status_code == 200

    def test_rulesets_page(self, client):
        """Test rulesets page loads"""
        response = client.get("/rulesets")
        assert response.status_code == 200


class TestAccountFiltersRoute:
    """Test account-specific filters endpoint"""

    def test_get_account_filters_empty(self, client, sample_account):
        """Test getting filters for account with no filters"""
        response = client.get(f"/api/accounts/{sample_account['id']}/filters")
        
        assert response.status_code == 200
        data = response.json
        assert isinstance(data, list)

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
                "enabled": True
            }
        )
        
        response = client.get(f"/api/accounts/{sample_account['id']}/filters")
        
        assert response.status_code == 200
        data = response.json
        assert len(data) >= 1
        assert data[0]["name"] == "Test Filter"

    def test_get_filters_for_nonexistent_account(self, client):
        """Test getting filters for non-existent account"""
        response = client.get("/api/accounts/99999/filters")
        
        # Account doesn't exist, so filters endpoint returns empty list
        # (doesn't validate account exists first)
        assert response.status_code == 200
        assert response.json == []


class TestProcessTagsHelper:
    """Test _process_tags_for_account helper function"""

    @patch('routes.accounts.TagService')
    def test_process_tags_helper(self, mock_tag_service, client, sample_account):
        """Test tag processing helper function"""
        from routes.accounts import _process_tags_for_account
        
        mock_tag_service.get_rules_for_account.return_value = []
        mock_tag_service.extract_tags.return_value = ({"US", "HD"}, "ESPN")
        mock_tag_service.normalize_tag_name.side_effect = lambda x: x.upper()
        
        streams = [
            {"stream_id": "101", "name": "US| ESPN HD", "category_id": "1"}
        ]
        categories = [
            {"category_id": "1", "category_name": "Sports"}
        ]
        
        # Should not raise
        _process_tags_for_account(sample_account["id"], streams, categories)
