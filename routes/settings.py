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
