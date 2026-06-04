"""Tests for TODO 69 — destructive admin endpoint hardening."""

import json

from click.testing import CliRunner

from models import FccMatchNetwork, db
from services.config_bundle_validation import validate_config_import_bundle
from services.fcc_pattern_reset import reset_fcc_patterns_to_defaults


class TestFccResetCliOnly:
    def test_reset_defaults_http_route_removed(self, client):
        response = client.post("/api/fcc-match-patterns/reset-defaults")
        assert response.status_code == 404

    def test_reset_fcc_patterns_cli_success(self, app):
        with app.app_context():
            db.create_all()
            db.session.add(
                FccMatchNetwork(
                    name="Custom",
                    display_name="Custom",
                    fcc_affiliation_pattern="%X%",
                    tag_patterns=json.dumps(["X"]),
                    enabled=True,
                    priority=99,
                )
            )
            db.session.commit()

            success, message = reset_fcc_patterns_to_defaults()
            assert success is True
            assert "restored" in message.lower()

            names = {n.name for n in FccMatchNetwork.query.all()}
            assert "Custom" not in names
            assert len(names) > 0

        with app.app_context():
            db.session.remove()
            db.engine.dispose()
            db.create_all()

    def test_flask_reset_fcc_patterns_command(self, app):
        with app.app_context():
            db.create_all()

        runner = CliRunner()
        result = runner.invoke(app.cli, ["reset-fcc-patterns"])
        assert result.exit_code == 0
        assert "restored" in result.output.lower()

        with app.app_context():
            db.session.remove()
            db.engine.dispose()
            db.create_all()


class TestConfigImportValidation:
    def test_valid_minimal_bundle(self):
        assert (
            validate_config_import_bundle(
                {
                    "type": "iptv-proxy-config-bundle",
                    "version": "1.0",
                    "accounts": [],
                }
            )
            is None
        )

    def test_rejects_invalid_type(self):
        assert "Invalid bundle type" in validate_config_import_bundle({"type": "other"})

    def test_rejects_unsupported_version(self):
        err = validate_config_import_bundle({"type": "iptv-proxy-config-bundle", "version": "9.9"})
        assert err and "version" in err

    def test_rejects_non_list_accounts(self):
        err = validate_config_import_bundle({"type": "iptv-proxy-config-bundle", "accounts": "bad"})
        assert err and "accounts" in err

    def test_rejects_invalid_options(self):
        err = validate_config_import_bundle(
            {
                "type": "iptv-proxy-config-bundle",
                "options": {"overwrite": "yes"},
            }
        )
        assert err and "overwrite" in err

    def test_import_rejects_invalid_bundle_via_api(self, client):
        response = client.post(
            "/api/config/import",
            json={"type": "wrong-bundle", "accounts": []},
        )
        assert response.status_code == 400
        assert "Invalid bundle type" in response.json["error"]

    def test_import_rejects_malformed_fcc_patterns(self, client):
        response = client.post(
            "/api/config/import",
            json={
                "type": "iptv-proxy-config-bundle",
                "fcc_patterns": {"networks": "not-a-list"},
            },
        )
        assert response.status_code == 400
        assert "fcc_patterns.networks" in response.json["error"]
