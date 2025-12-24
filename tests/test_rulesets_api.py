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


class TestRulesetExportImport:
    """Test ruleset export/import operations"""

    def test_export_ruleset(self, client):
        """Test exporting a ruleset with rules"""
        # Create a ruleset
        create_response = client.post(
            "/api/rulesets",
            json={"name": "Export Test", "description": "Test export", "enabled": True, "priority": 50},
        )
        ruleset_id = create_response.json["id"]

        # Add some rules
        client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
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
        client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
                "name": "HD Suffix Rule",
                "pattern": " HD",
                "pattern_type": "suffix",
                "tag_name": "HD",
                "source": "channel_name",
                "remove_from_name": True,
                "priority": 20,
                "enabled": True,
            },
        )

        # Export it
        response = client.get(f"/api/rulesets/{ruleset_id}/export")
        assert response.status_code == 200

        data = response.json
        assert data["version"] == "1.0"
        assert data["type"] == "iptv-proxy-ruleset"
        assert data["ruleset"]["name"] == "Export Test"
        assert data["ruleset"]["description"] == "Test export"
        assert data["ruleset"]["priority"] == 50
        assert len(data["ruleset"]["rules"]) == 2

        # Verify rules are sorted by priority
        assert data["ruleset"]["rules"][0]["priority"] == 10
        assert data["ruleset"]["rules"][1]["priority"] == 20

    def test_export_ruleset_not_found(self, client):
        """Test exporting a non-existent ruleset"""
        response = client.get("/api/rulesets/99999/export")
        assert response.status_code == 404

    def test_import_ruleset(self, client):
        """Test importing a ruleset"""
        import_data = {
            "version": "1.0",
            "type": "iptv-proxy-ruleset",
            "ruleset": {
                "name": "Imported Ruleset",
                "description": "Imported from JSON",
                "is_default": False,
                "enabled": True,
                "priority": 75,
                "rules": [
                    {
                        "name": "UK Prefix",
                        "pattern": "UK|",
                        "pattern_type": "prefix",
                        "tag_name": "UK",
                        "source": "both",
                        "remove_from_name": True,
                        "priority": 10,
                        "enabled": True,
                    },
                    {
                        "name": "4K Suffix",
                        "pattern": " 4K",
                        "pattern_type": "suffix",
                        "tag_name": "4K",
                        "source": "channel_name",
                        "remove_from_name": False,
                        "priority": 20,
                        "enabled": True,
                    },
                ],
            },
        }

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 201

        data = response.json
        assert data["success"] is True
        assert data["name"] == "Imported Ruleset"
        assert data["rules_imported"] == 2
        assert data["rules_skipped"] == 0

        # Verify the ruleset exists
        ruleset_response = client.get(f"/api/rulesets/{data['id']}")
        assert ruleset_response.status_code == 200
        assert ruleset_response.json["name"] == "Imported Ruleset"
        assert len(ruleset_response.json["rules"]) == 2

    def test_import_ruleset_with_rename(self, client):
        """Test importing a ruleset with a custom name"""
        import_data = {
            "version": "1.0",
            "type": "iptv-proxy-ruleset",
            "rename": "Custom Name",
            "ruleset": {
                "name": "Original Name",
                "description": "Test rename",
                "enabled": True,
                "priority": 100,
                "rules": [],
            },
        }

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 201

        data = response.json
        assert data["name"] == "Custom Name"

    def test_import_ruleset_duplicate_name(self, client):
        """Test importing a ruleset with an existing name fails"""
        # Create existing ruleset
        client.post("/api/rulesets", json={"name": "Existing Ruleset", "description": "Already exists"})

        import_data = {
            "version": "1.0",
            "type": "iptv-proxy-ruleset",
            "ruleset": {
                "name": "Existing Ruleset",
                "description": "Duplicate name",
                "enabled": True,
                "priority": 100,
                "rules": [],
            },
        }

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 409
        assert "already exists" in response.json["error"]

    def test_import_ruleset_invalid_type(self, client):
        """Test importing with invalid type field fails"""
        import_data = {
            "version": "1.0",
            "type": "invalid-type",
            "ruleset": {"name": "Test", "enabled": True, "priority": 100, "rules": []},
        }

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 400
        assert "Invalid export format" in response.json["error"]

    def test_import_ruleset_missing_ruleset(self, client):
        """Test importing without ruleset field fails"""
        import_data = {"version": "1.0", "type": "iptv-proxy-ruleset"}

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 400
        assert "missing 'ruleset' field" in response.json["error"]

    def test_import_ruleset_skips_invalid_rules(self, client):
        """Test that import skips rules with invalid data"""
        import_data = {
            "version": "1.0",
            "type": "iptv-proxy-ruleset",
            "ruleset": {
                "name": "Partial Import",
                "description": "Some rules will be skipped",
                "enabled": True,
                "priority": 100,
                "rules": [
                    {
                        "name": "Valid Rule",
                        "pattern": "TEST",
                        "pattern_type": "contains",
                        "tag_name": "TEST",
                        "source": "both",
                        "priority": 10,
                        "enabled": True,
                    },
                    {
                        "name": "Missing Pattern Type",
                        "pattern": "BAD",
                        # Missing pattern_type
                        "tag_name": "BAD",
                        "source": "both",
                    },
                    {
                        "name": "Invalid Pattern Type",
                        "pattern": "INVALID",
                        "pattern_type": "invalid_type",
                        "tag_name": "INVALID",
                        "source": "both",
                    },
                ],
            },
        }

        response = client.post("/api/rulesets/import", json=import_data)
        assert response.status_code == 201

        data = response.json
        assert data["rules_imported"] == 1
        assert data["rules_skipped"] == 2

    def test_export_import_roundtrip(self, client):
        """Test exporting and re-importing a ruleset"""
        # Create original ruleset
        create_response = client.post(
            "/api/rulesets",
            json={"name": "Roundtrip Test", "description": "Test roundtrip", "enabled": True, "priority": 42},
        )
        ruleset_id = create_response.json["id"]

        # Add rules
        client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
                "name": "Roundtrip Rule",
                "pattern": "RT|",
                "pattern_type": "prefix",
                "tag_name": "ROUNDTRIP",
                "source": "both",
                "remove_from_name": True,
                "priority": 15,
                "enabled": True,
            },
        )

        # Export
        export_response = client.get(f"/api/rulesets/{ruleset_id}/export")
        export_data = export_response.json

        # Import with new name
        export_data["rename"] = "Roundtrip Copy"
        import_response = client.post("/api/rulesets/import", json=export_data)
        assert import_response.status_code == 201

        # Verify the copy matches
        copy_id = import_response.json["id"]
        copy_response = client.get(f"/api/rulesets/{copy_id}")
        copy_data = copy_response.json

        assert copy_data["name"] == "Roundtrip Copy"
        assert copy_data["description"] == "Test roundtrip"
        assert copy_data["priority"] == 42
        assert len(copy_data["rules"]) == 1
        assert copy_data["rules"][0]["pattern"] == "RT|"
        assert copy_data["rules"][0]["tag_name"] == "ROUNDTRIP"
