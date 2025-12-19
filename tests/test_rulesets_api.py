"""
Tests for Ruleset and Tag Rule API endpoints
"""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, db


@pytest.fixture
def client():
    """Test client fixture"""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()


class TestRulesetAPI:
    """Test ruleset CRUD operations"""

    def test_create_ruleset(self, client):
        """Test creating a ruleset"""
        response = client.post(
            "/api/rulesets",
            json={"name": "Custom Ruleset", "description": "My custom rules", "enabled": True, "priority": 50},
        )

        assert response.status_code == 201
        data = response.json
        assert data["name"] == "Custom Ruleset"
        assert data["description"] == "My custom rules"
        assert data["priority"] == 50

    def test_list_rulesets(self, client):
        """Test listing rulesets"""
        # Create a ruleset
        client.post("/api/rulesets", json={"name": "Test Ruleset", "description": "Test", "enabled": True})

        response = client.get("/api/rulesets")

        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["name"] == "Test Ruleset"

    def test_get_single_ruleset(self, client):
        """Test getting a single ruleset by ID"""
        # Create a ruleset
        create_response = client.post(
            "/api/rulesets", json={"name": "Single Ruleset", "description": "Test single get", "enabled": True}
        )

        ruleset_id = create_response.json["id"]

        # Get it
        response = client.get(f"/api/rulesets/{ruleset_id}")

        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Single Ruleset"
        assert data["id"] == ruleset_id

    def test_update_ruleset(self, client):
        """Test updating a ruleset"""
        # Create a ruleset
        create_response = client.post(
            "/api/rulesets", json={"name": "Original Name", "description": "Original description", "enabled": True}
        )

        ruleset_id = create_response.json["id"]

        # Update it
        response = client.put(
            f"/api/rulesets/{ruleset_id}",
            json={"name": "Updated Name", "description": "Updated description", "enabled": False, "priority": 200},
        )

        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
        assert data["enabled"] is False
        assert data["priority"] == 200

    def test_delete_ruleset(self, client):
        """Test deleting a ruleset"""
        # Create a ruleset
        create_response = client.post(
            "/api/rulesets", json={"name": "To Delete", "description": "Will be deleted", "enabled": True}
        )

        ruleset_id = create_response.json["id"]

        # Delete it
        response = client.delete(f"/api/rulesets/{ruleset_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/rulesets")
        assert len(response.json) == 0

    def test_create_default_ruleset(self, client):
        """Test creating default ruleset with preset rules"""
        response = client.post("/api/rulesets/create-default")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert data["name"] == "Default"
        assert data["rule_count"] > 0


class TestTagRuleAPI:
    """Test tag rule CRUD operations"""

    @pytest.fixture
    def sample_ruleset(self, client):
        """Create a sample ruleset"""
        response = client.post(
            "/api/rulesets", json={"name": "Test Ruleset", "description": "For testing rules", "enabled": True}
        )
        return response.json

    def test_create_tag_rule(self, client, sample_ruleset):
        """Test creating a tag rule"""
        response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": sample_ruleset["id"],
                "name": "US Prefix Rule",
                "pattern": "US|",
                "pattern_type": "prefix",
                "tag_name": "US",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
                "enabled": True,
            },
        )

        assert response.status_code == 201
        data = response.json
        assert data["name"] == "US Prefix Rule"
        assert data["pattern"] == "US|"
        assert data["tag_name"] == "US"

    def test_list_tag_rules(self, client, sample_ruleset):
        """Test listing tag rules for a ruleset"""
        # Create a rule
        client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": sample_ruleset["id"],
                "name": "Test Rule",
                "pattern": "TEST",
                "pattern_type": "contains",
                "tag_name": "TEST",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
                "enabled": True,
            },
        )

        response = client.get(f'/api/tag-rules?ruleset_id={sample_ruleset["id"]}')

        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]["name"] == "Test Rule"

    def test_update_tag_rule(self, client, sample_ruleset):
        """Test updating a tag rule"""
        # Create a rule
        create_response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": sample_ruleset["id"],
                "name": "Original Rule",
                "pattern": "ORIG",
                "pattern_type": "contains",
                "tag_name": "ORIG",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
                "enabled": True,
            },
        )

        rule_id = create_response.json["id"]

        # Update it
        response = client.put(
            f"/api/tag-rules/{rule_id}",
            json={
                "name": "Updated Rule",
                "pattern": "UPDT",
                "pattern_type": "prefix",
                "tag_name": "UPDATED",
                "source": "channel_name",
                "remove_from_name": False,
                "priority": 20,
                "enabled": False,
            },
        )

        assert response.status_code == 200
        data = response.json
        assert data["name"] == "Updated Rule"
        assert data["pattern"] == "UPDT"
        assert data["tag_name"] == "UPDATED"
        assert data["enabled"] is False

    def test_delete_tag_rule(self, client, sample_ruleset):
        """Test deleting a tag rule"""
        # Create a rule
        create_response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": sample_ruleset["id"],
                "name": "To Delete",
                "pattern": "DEL",
                "pattern_type": "contains",
                "tag_name": "DELETE",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
                "enabled": True,
            },
        )

        rule_id = create_response.json["id"]

        # Delete it
        response = client.delete(f"/api/tag-rules/{rule_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f'/api/tag-rules?ruleset_id={sample_ruleset["id"]}')
        assert len(response.json) == 0
