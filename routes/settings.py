"""
Settings routes - Global application settings management
"""

import logging

from flask import Blueprint, jsonify, request

from models import Settings, db

settings_bp = Blueprint("settings", __name__)
logger = logging.getLogger(__name__)


@settings_bp.route("/api/settings", methods=["GET"])
def get_settings():
    """Get all application settings."""
    try:
        settings = Settings.get_all()
        return jsonify(settings)
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/settings/<key>", methods=["GET"])
def get_setting(key):
    """Get a specific setting by key."""
    try:
        value = Settings.get(key)
        if value is None and key not in Settings.DEFAULTS:
            return jsonify({"error": "Setting not found"}), 404

        description = None
        if key in Settings.DEFAULTS:
            description = Settings.DEFAULTS[key][1]
        else:
            record = Settings.query.filter_by(key=key).first()
            if record:
                description = record.description

        return jsonify({"key": key, "value": value, "description": description})
    except Exception as e:
        logger.error(f"Error fetching setting {key}: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/settings/<key>", methods=["PUT"])
def update_setting(key):
    """Update a setting value."""
    try:
        data = request.get_json()
        if not data or "value" not in data:
            return jsonify({"error": "value is required"}), 400

        value = data["value"]
        description = data.get("description")

        Settings.set(key, value, description)

        return jsonify({"key": key, "value": value, "message": "Setting updated successfully"})
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/settings/<key>", methods=["DELETE"])
def delete_setting(key):
    """Delete a setting (revert to default)."""
    try:
        record = Settings.query.filter_by(key=key).first()
        if not record:
            return jsonify({"error": "Setting not found"}), 404

        db.session.delete(record)
        db.session.commit()

        return jsonify({"message": "Setting deleted (reverted to default)"})
    except Exception as e:
        logger.error(f"Error deleting setting {key}: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/ppv-enrichment/config", methods=["GET"])
def get_ppv_enrichment_config():
    """Get PPV enrichment configuration."""
    try:
        enabled = Settings.get("ppv_enrichment_enabled", "true") != "false"
        api_key = Settings.get("ppv_thesportsdb_api_key", "")

        return jsonify(
            {
                "enabled": enabled,
                "has_api_key": bool(api_key),
                "api_key_preview": api_key[:4] + "****" if api_key else None,
            }
        )
    except Exception as e:
        logger.error(f"Error fetching PPV enrichment config: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/ppv-enrichment/config", methods=["PUT"])
def update_ppv_enrichment_config():
    """Update PPV enrichment configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        if "enabled" in data:
            Settings.set("ppv_enrichment_enabled", "true" if data["enabled"] else "false")

        if "api_key" in data:
            # Only update if the new key is not None
            api_key = data.get("api_key", "").strip()
            if api_key or data["api_key"] is None:  # Allow clearing the key
                Settings.set("ppv_thesportsdb_api_key", api_key)

        return jsonify({"message": "PPV enrichment configuration updated successfully"})
    except Exception as e:
        logger.error(f"Error updating PPV enrichment config: {e}")
        return jsonify({"error": str(e)}), 500
