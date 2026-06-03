"""Contract tests for standardized API envelopes (TODOs 72/73)."""

from models import Settings, db
from tests.conftest import api_data, api_error_payload, api_mutation_data


class TestApiContractFilters:
    def test_get_filters_data_envelope(self, client):
        response = client.get("/api/filters")
        assert response.status_code == 200
        payload = response.get_json()
        assert "data" in payload
        assert isinstance(payload["data"], list)

    def test_create_filter_mutation_envelope(self, client, sample_account):
        response = client.post(
            "/api/filters",
            json={
                "account_id": sample_account["id"],
                "name": "Contract Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "Sports",
            },
        )
        assert response.status_code == 201
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["data"]["name"] == "Contract Filter"
        assert api_mutation_data(response)["id"]

    def test_delete_filter_no_content(self, client, sample_account):
        create = client.post(
            "/api/filters",
            json={
                "account_id": sample_account["id"],
                "name": "To Delete",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "News",
            },
        )
        filter_id = api_mutation_data(create)["id"]
        response = client.delete(f"/api/filters/{filter_id}")
        assert response.status_code == 204
        assert response.data == b""


class TestApiContractAccounts:
    def test_get_accounts_data_envelope(self, client, sample_account):
        response = client.get("/api/accounts")
        assert response.status_code == 200
        data = api_data(response)
        assert len(data) == 1
        assert data[0]["name"] == sample_account["name"]

    def test_create_account_mutation_envelope(self, client):
        response = client.post(
            "/api/accounts",
            json={
                "name": "Contract Account",
                "server": "contract.example.com",
                "username": "user",
                "password": "pass",
            },
        )
        assert response.status_code == 201
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["data"]["server"] == "contract.example.com"

    def test_account_filters_data_envelope(self, client, sample_account):
        response = client.get(f"/api/accounts/{sample_account['id']}/filters")
        assert response.status_code == 200
        assert isinstance(api_data(response), list)


class TestApiContractSettings:
    def test_get_settings_data_envelope(self, client):
        response = client.get("/api/settings")
        assert response.status_code == 200
        assert isinstance(api_data(response), dict)

    def test_delete_setting_no_content(self, client):
        Settings.set("contract_delete_key", "value")
        db.session.commit()
        response = client.delete("/api/settings/contract_delete_key")
        assert response.status_code == 204


class TestApiContractValidationErrors:
    def test_marshmallow_validation_error_shape(self, client):
        response = client.post("/api/accounts", json={"name": "Incomplete"})
        assert response.status_code == 400
        payload = api_error_payload(response)
        assert payload["success"] is False
        assert payload["code"] == "VALIDATION_ERROR"
        assert "details" in payload
        assert "server" in payload["details"]
        assert "validation_errors" not in payload


class TestApiContractCategoriesAndStats:
    def test_get_categories_data_envelope(self, client):
        response = client.get("/api/categories")
        assert response.status_code == 200
        assert isinstance(api_data(response), list)

    def test_overview_stats_data_envelope(self, client):
        response = client.get("/api/overview/stats")
        assert response.status_code == 200
        stats = api_data(response)
        assert "accounts" in stats
        assert "channels" in stats
