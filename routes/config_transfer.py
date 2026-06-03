"""
Configuration export/import routes.

Provides a portable JSON bundle for backing up and restoring configuration entities.
HTTP layer only: parse request → ConfigTransferService → JSON response.
"""

import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from services.config_bundle_validation import validate_config_import_bundle
from services.config_transfer_service import ConfigTransferService

logger = logging.getLogger(__name__)

config_transfer_bp = Blueprint("config_transfer", __name__)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@config_transfer_bp.route("/api/config/export", methods=["GET"])
@handle_errors(return_json=True, default_message="Error exporting configuration bundle")
def export_config_bundle():
    """Export a full configuration bundle as JSON."""
    include_accounts = _parse_bool(request.args.get("include_accounts"), default=True)
    bundle = ConfigTransferService.export_bundle(include_accounts=include_accounts)

    response = jsonify(bundle)
    response.headers["Content-Disposition"] = 'attachment; filename="iptv_proxy_config_bundle.json"'
    return response


@config_transfer_bp.route("/api/config/import", methods=["POST"])
@handle_errors(return_json=True, default_message="Error importing configuration bundle")
def import_config_bundle():
    """Import a full configuration bundle.

    Expected body:
    {
      "type": "iptv-proxy-config-bundle",
      ...,
      "options": {
        "overwrite": false,
        "create_missing_accounts": false
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    validation_error = validate_config_import_bundle(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    options = data.get("options") or {}
    overwrite = bool(options.get("overwrite", False))
    create_missing_accounts = bool(options.get("create_missing_accounts", False))

    result = ConfigTransferService.import_bundle(
        data,
        overwrite=overwrite,
        create_missing_accounts=create_missing_accounts,
    )
    return jsonify(result)
