from tests.conftest import api_data, api_error_payload, api_mutation_data

"""Tests for settings routes."""

from models import Settings, db


class TestSettingsRoutes:
    """Tests for settings API endpoints."""

    def test_get_all_settings(self, client):
        """Test getting all settings."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = api_data(response)
        assert isinstance(data, dict)

    def test_get_specific_setting_exists(self, client):
        """Test getting a specific setting that exists."""
        # Set a test setting first
        Settings.set("test_key", "test_value", "Test description")
        db.session.commit()

        response = client.get("/api/settings/test_key")
        assert response.status_code == 200
        data = api_data(response)
        assert data["key"] == "test_key"
        assert data["value"] == "test_value"
        assert data["description"] == "Test description"

    def test_get_default_setting(self, client):
        """Test getting a default setting."""
        # proxy_icons is in Settings.DEFAULTS
        response = client.get("/api/settings/proxy_icons")
        assert response.status_code == 200
        data = api_data(response)
        assert data["key"] == "proxy_icons"
        assert data["value"] == "true"  # default value
        assert "proxy" in data["description"].lower()
        assert "description" in data

    def test_get_nonexistent_setting(self, client):
        """Test getting a setting that doesn't exist."""
        response = client.get("/api/settings/nonexistent_key_12345")
        assert response.status_code == 404
        payload = api_error_payload(response)
        assert "error" in payload

    def test_update_setting(self, client):
        """Test updating a setting."""
        response = client.put(
            "/api/settings/test_update_key",
            json={"value": "new_value", "description": "Updated description"},
        )
        assert response.status_code == 200
        data = api_mutation_data(response)
        assert data["key"] == "test_update_key"
        assert data["value"] == "new_value"

        # Verify the setting was actually saved
        saved_value = Settings.get("test_update_key")
        assert saved_value == "new_value"

    def test_update_setting_missing_value(self, client):
        """Test updating a setting without providing value."""
        response = client.put("/api/settings/test_key", json={})
        assert response.status_code == 400
        payload = api_error_payload(response)
        assert "error" in payload

    def test_update_setting_no_json(self, client):
        """Test updating a setting without JSON body."""
        response = client.put("/api/settings/test_key")
        assert response.status_code == 400

    def test_delete_setting(self, client):
        """Test deleting a setting."""
        # Create a setting first
        Settings.set("test_delete_key", "value_to_delete")
        db.session.commit()

        response = client.delete("/api/settings/test_delete_key")
        assert response.status_code == 204
        assert response.data == b""

        # Verify it was deleted
        record = Settings.query.filter_by(key="test_delete_key").first()
        assert record is None

    def test_delete_nonexistent_setting(self, client):
        """Test deleting a setting that doesn't exist."""
        response = client.delete("/api/settings/nonexistent_key_to_delete")
        assert response.status_code == 404
        payload = api_error_payload(response)
        assert "error" in payload

    def test_update_setting_value_only(self, client):
        """Test updating a setting with only value, no description."""
        response = client.put(
            "/api/settings/value_only_key",
            json={"value": "just_value"},
        )
        assert response.status_code == 200
        data = api_mutation_data(response)
        assert data["value"] == "just_value"

    def test_get_all_settings_includes_defaults(self, client):
        """Test that get all settings includes default values."""
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = api_data(response)
        # Should include proxy_hostname and proxy_icons defaults
        assert "proxy_hostname" in data
        assert "proxy_icons" in data

    def test_update_then_delete_setting(self, client):
        """Test full cycle: create, update, delete setting."""
        # Create
        Settings.set("cycle_key", "initial_value")
        db.session.commit()

        # Update
        response = client.put(
            "/api/settings/cycle_key",
            json={"value": "updated_value"},
        )
        assert response.status_code == 200

        # Verify update
        assert Settings.get("cycle_key") == "updated_value"

        # Delete
        response = client.delete("/api/settings/cycle_key")
        assert response.status_code == 204

        # Verify deletion
        assert Settings.query.filter_by(key="cycle_key").first() is None


class TestPpvEnrichmentConfigRoutes:
    """Tests for /api/ppv-enrichment/config (editable PPV settings)."""

    def test_get_ppv_enrichment_config_defaults(self, client):
        response = client.get("/api/ppv-enrichment/config")
        assert response.status_code == 200
        data = api_data(response)
        assert data["has_api_key"] is False
        assert data["api_key_preview"] is None
        assert data["has_site_credentials"] is False
        assert data["site_username_preview"] is None

    def test_update_ppv_enrichment_config(self, client):
        response = client.put(
            "/api/ppv-enrichment/config",
            json={
                "enabled": False,
                "api_key": "secret12345",
                "site_username": "myuser",
                "site_password": "mypassword",
            },
        )
        assert response.status_code == 200
        assert "message" in response.get_json()

        get_response = client.get("/api/ppv-enrichment/config")
        data = api_data(get_response)
        assert data["enabled"] is False
        assert data["has_api_key"] is True
        assert data["api_key_preview"].startswith("secr")
        assert data["has_site_credentials"] is True
        assert data["site_username_preview"].startswith("my")

    def test_clear_ppv_enrichment_site_login(self, client):
        Settings.set("ppv_thesportsdb_site_username", "saveduser")
        Settings.set("ppv_thesportsdb_site_password", "savedpass")
        db.session.commit()

        response = client.put(
            "/api/ppv-enrichment/config",
            json={"site_username": "", "site_password": ""},
        )
        assert response.status_code == 200

        data = api_data(client.get("/api/ppv-enrichment/config"))
        assert data["has_site_credentials"] is False
        assert Settings.get("ppv_thesportsdb_site_username", "") == ""
        assert Settings.get("ppv_thesportsdb_site_password", "") == ""

    def test_clear_ppv_enrichment_api_key(self, client):
        Settings.set("ppv_thesportsdb_api_key", "oldkey")
        db.session.commit()

        response = client.put(
            "/api/ppv-enrichment/config",
            json={"api_key": ""},
        )
        assert response.status_code == 200

        data = api_data(client.get("/api/ppv-enrichment/config"))
        assert data["has_api_key"] is False

    def test_update_ppv_enrichment_config_requires_body(self, client):
        response = client.put("/api/ppv-enrichment/config")
        assert response.status_code == 400


class TestStreamFallbackConfigRoutes:
    def test_get_stream_fallback_config_defaults(self, client):
        response = client.get("/api/stream-fallback/config")
        assert response.status_code == 200
        data = api_data(response)
        assert data["auto_detect"] is True

    def test_update_stream_fallback_config(self, client):
        response = client.put(
            "/api/stream-fallback/config",
            json={"enabled": False, "auto_detect": False},
        )
        assert response.status_code == 200
        data = api_mutation_data(response)
        assert data["auto_detect"] is False
