"""
Tests for IPTV Proxy v2
"""

import pytest


@pytest.fixture
def client():
    """Test client fixture"""
    # Import app after setting environment to avoid database path issues
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


class TestAccounts:
    """Test account management"""

    def test_create_account(self, client):
        """Test creating an account"""
        response = client.post(
            "/api/accounts",
            json={
                "name": "My IPTV",
                "server": "example.com",
                "username": "user123",
                "password": "pass123",
                "enabled": True,
            },
        )

        assert response.status_code == 201
        data = response.json
        assert data["name"] == "My IPTV"
        assert data["server"] == "example.com"
        assert data["username"] == "user123"
        assert "password" not in data  # Password should not be returned

    def test_list_accounts(self, client, sample_account):
        """Test listing accounts"""
        response = client.get("/api/accounts")

        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["name"] == "Test Account"

    def test_update_account(self, client, sample_account):
        """Test updating an account"""
        account_id = sample_account["id"]

        response = client.put(
            f"/api/accounts/{account_id}",
            json={"name": "Updated Account", "server": "updated.server.com", "username": "newuser", "enabled": False},
        )

        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Updated Account"
        assert data["server"] == "updated.server.com"
        assert data["enabled"] is False

    def test_delete_account(self, client, sample_account):
        """Test deleting an account"""
        account_id = sample_account["id"]

        response = client.delete(f"/api/accounts/{account_id}")
        assert response.status_code == 204

        # Verify account is gone
        response = client.get("/api/accounts")
        assert len(response.json) == 0


class TestFilters:
    """Test filter management"""

    def test_create_filter(self, client, sample_account):
        """Test creating a filter"""
        account_id = sample_account["id"]

        response = client.post(
            "/api/filters",
            json={
                "account_id": account_id,
                "name": "UK Only",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "UK",
                "enabled": True,
            },
        )

        # Debug output if failed
        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response data: {response.get_json()}")

        assert response.status_code == 201
        data = response.json
        assert data["name"] == "UK Only"
        assert data["filter_type"] == "category"
        assert data["filter_action"] == "whitelist"

    def test_list_filters(self, client, sample_account):
        """Test listing filters"""
        account_id = sample_account["id"]

        # Create a filter
        client.post(
            "/api/filters",
            json={
                "account_id": account_id,
                "name": "Test Filter",
                "filter_type": "channel_name",
                "filter_action": "blacklist",
                "filter_value": "XXX",
                "enabled": True,
            },
        )

        response = client.get("/api/filters")
        assert response.status_code == 200
        assert len(response.json) == 1

    def test_delete_filter(self, client, sample_account):
        """Test deleting a filter"""
        account_id = sample_account["id"]

        # Create a filter
        create_response = client.post(
            "/api/filters",
            json={
                "account_id": account_id,
                "name": "Temp Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "SPORT",
                "enabled": True,
            },
        )

        filter_id = create_response.json["id"]

        # Delete it
        response = client.delete(f"/api/filters/{filter_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/filters")
        assert len(response.json) == 0


class TestAPI:
    """Test API endpoints"""

    def test_index_page(self, client):
        """Test home page loads"""
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


def test_cache_service():
    """Test cache service"""
    from services.cache_service import CacheService

    cache = CacheService(default_ttl=10)

    # Test caching streams
    streams = [{"id": 1}, {"id": 2}]
    cache.cache_streams(1, streams)

    cached = cache.get_cached_streams(1)
    assert cached == streams

    # Test cache miss
    assert cache.get_cached_streams(999) is None

    # Test clearing
    cache.clear_account_cache(1)
    assert cache.get_cached_streams(1) is None
