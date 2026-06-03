"""
Tests for IPTV Proxy v2

Uses shared fixtures from conftest.py for proper test isolation.
"""

from tests.conftest import api_data, api_mutation_data

# client fixture is provided by conftest.py


class TestAccounts:
    """Test account management"""

    def test_list_accounts(self, client, sample_account):
        """Test listing accounts"""
        response = client.get("/api/accounts")

        assert response.status_code == 200
        data = api_data(response)
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
        data = api_mutation_data(response)
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
        assert len(api_data(response)) == 0


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
        data = api_mutation_data(response)
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
        assert len(api_data(response)) == 1

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

        filter_id = api_mutation_data(create_response)["id"]

        # Delete it
        response = client.delete(f"/api/filters/{filter_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/filters")
        assert len(api_data(response)) == 0


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
