"""
Tests for remaining app.py routes to reach 80% coverage
"""

import pytest
from unittest.mock import Mock, patch


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


@pytest.fixture
def sample_ruleset(client):
    """Create a sample ruleset"""
    response = client.post(
        "/api/rulesets",
        json={
            "name": "Test Ruleset",
            "description": "For testing",
            "is_default": False,
            "enabled": True,
            "priority": 100
        },
    )
    return response.json


class TestAccountRulesetRoutes:
    """Test account ruleset assignment routes"""

    def test_get_account_rulesets_empty(self, client, sample_account):
        """Test getting rulesets for account with none assigned"""
        response = client.get(f"/api/accounts/{sample_account['id']}/rulesets")
        
        assert response.status_code == 200
        assert response.json == []

    def test_assign_ruleset_to_account(self, client, sample_account, sample_ruleset):
        """Test assigning a ruleset to an account"""
        response = client.post(
            f"/api/accounts/{sample_account['id']}/rulesets",
            json={
                "ruleset_id": sample_ruleset["id"],
                "priority": 50
            }
        )
        
        assert response.status_code == 201
        data = response.json
        assert data["success"] is True

    def test_assign_ruleset_update_priority(self, client, sample_account, sample_ruleset):
        """Test updating priority of assigned ruleset"""
        # First assignment
        client.post(
            f"/api/accounts/{sample_account['id']}/rulesets",
            json={"ruleset_id": sample_ruleset["id"], "priority": 50}
        )
        
        # Update priority
        response = client.post(
            f"/api/accounts/{sample_account['id']}/rulesets",
            json={"ruleset_id": sample_ruleset["id"], "priority": 100}
        )
        
        assert response.status_code == 201
        assert response.json["success"] is True

    def test_unassign_ruleset_from_account(self, client, sample_account, sample_ruleset):
        """Test unassigning a ruleset from an account"""
        # First assign
        client.post(
            f"/api/accounts/{sample_account['id']}/rulesets",
            json={"ruleset_id": sample_ruleset["id"], "priority": 50}
        )
        
        # Then unassign
        response = client.delete(
            f"/api/accounts/{sample_account['id']}/rulesets/{sample_ruleset['id']}"
        )
        
        assert response.status_code == 204

    def test_unassign_nonexistent_ruleset(self, client, sample_account):
        """Test unassigning a ruleset that isn't assigned"""
        response = client.delete(
            f"/api/accounts/{sample_account['id']}/rulesets/99999"
        )
        
        # Route doesn't validate ruleset exists, just deletes if found
        assert response.status_code == 204

    def test_get_account_rulesets_with_assignments(self, client, sample_account, sample_ruleset):
        """Test getting rulesets for account with assignments"""
        # Assign ruleset
        client.post(
            f"/api/accounts/{sample_account['id']}/rulesets",
            json={"ruleset_id": sample_ruleset["id"], "priority": 50}
        )
        
        response = client.get(f"/api/accounts/{sample_account['id']}/rulesets")
        
        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["id"] == sample_ruleset["id"]
        assert data[0]["priority"] == 50


class TestPlaylistConfigRoutes:
    """Test playlist config routes"""

    def test_get_playlist_configs_empty(self, client):
        """Test getting playlist configs when none exist"""
        response = client.get("/api/playlist-configs")
        
        assert response.status_code == 200
        assert response.json == []

    def test_create_playlist_config(self, client, sample_account):
        """Test creating a playlist config"""
        response = client.post(
            "/api/playlist-configs",
            json={
                "name": "My Playlist"
            }
        )
        
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "My Playlist"

    def test_get_playlist_configs_with_data(self, client):  
        """Test getting playlist configs after creating one"""
        # Create config
        config_response = client.post(
            "/api/playlist-configs",
            json={"name": "My Playlist"}
        )
        config_id = config_response.json["id"]
        
        response = client.get("/api/playlist-configs")
        
        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["id"] == config_id

    def test_update_playlist_config(self, client):
        """Test updating a playlist config"""
        # Create config
        config_response = client.post(
            "/api/playlist-configs",
            json={"name": "Original Name"}
        )
        config_id = config_response.json["id"]
        
        # Update it
        response = client.put(
            f"/api/playlist-configs/{config_id}",
            json={"name": "Updated Name"}
        )
        
        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Updated Name"


class TestSyncRoutes:
    """Test sync operation routes"""
    
    pass  # Sync routes need more complex mocking, covered elsewhere
