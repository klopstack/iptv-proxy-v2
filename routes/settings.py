"""
Settings routes - Global application settings management
"""

import logging
from typing import Optional

from flask import Blueprint, jsonify, request

from models import Settings, db

settings_bp = Blueprint("settings", __name__)
logger = logging.getLogger(__name__)


def _preview_secret(value: str, visible_chars: int = 4) -> Optional[str]:
    """Return a masked preview of a stored secret."""
    if not value:
        return None
    if len(value) <= visible_chars:
        return "*" * len(value)
    return value[:visible_chars] + "****"


def _preview_username(value: str) -> Optional[str]:
    """Return a masked preview of a stored username."""
    if not value:
        return None
    if len(value) <= 2:
        return value[0] + "****"
    return value[:2] + "****"


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
        site_username = (Settings.get("ppv_thesportsdb_site_username", "") or "").strip()
        site_password = Settings.get("ppv_thesportsdb_site_password", "") or ""

        return jsonify(
            {
                "enabled": enabled,
                "has_api_key": bool(api_key),
                "api_key_preview": _preview_secret(api_key),
                "has_site_credentials": bool(site_username and site_password),
                "site_username_preview": _preview_username(site_username),
            }
        )
    except Exception as e:
        logger.error(f"Error fetching PPV enrichment config: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/ppv-enrichment/config", methods=["PUT"])
def update_ppv_enrichment_config():
    """Update PPV enrichment configuration."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body required"}), 400

        if "enabled" in data:
            Settings.set("ppv_enrichment_enabled", "true" if data["enabled"] else "false")

        if "api_key" in data:
            raw = data.get("api_key")
            api_key = "" if raw is None else str(raw).strip()
            Settings.set("ppv_thesportsdb_api_key", api_key)
            from services.thesportsdb_service import reset_thesportsdb_api_key_config

            reset_thesportsdb_api_key_config()

        credentials_changed = False

        if "site_username" in data:
            raw_username = data.get("site_username")
            site_username = "" if raw_username is None else str(raw_username).strip()
            Settings.set("ppv_thesportsdb_site_username", site_username)
            credentials_changed = True
            if not site_username:
                Settings.set("ppv_thesportsdb_site_password", "")

        if "site_password" in data:
            raw_password = data.get("site_password")
            if raw_password is not None:
                Settings.set("ppv_thesportsdb_site_password", str(raw_password))
                credentials_changed = True

        if credentials_changed:
            from services.thesportsdb_calendar_scraper import reset_calendar_scraper

            reset_calendar_scraper()

        return jsonify({"message": "PPV enrichment configuration updated successfully"})
    except Exception as e:
        logger.error(f"Error updating PPV enrichment config: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/stream-fallback/config", methods=["GET"])
def get_stream_fallback_config():
    """Get stream proxy fallback configuration."""
    try:
        enabled = Settings.get("stream_fallback_enabled", "true") != "false"
        auto_detect = Settings.get("stream_fallback_auto_detect", "true") != "false"
        return jsonify({"enabled": enabled, "auto_detect": auto_detect})
    except Exception as e:
        logger.error(f"Error fetching stream fallback config: {e}")
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/stream-fallback/config", methods=["PUT"])
def update_stream_fallback_config():
    """Update stream proxy fallback configuration."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body required"}), 400

        if "enabled" in data:
            Settings.set("stream_fallback_enabled", "true" if data["enabled"] else "false")
        if "auto_detect" in data:
            Settings.set("stream_fallback_auto_detect", "true" if data["auto_detect"] else "false")

        from services.stream_fallback_service import invalidate_cache

        invalidate_cache()

        return jsonify(
            {
                "enabled": Settings.get("stream_fallback_enabled", "true") != "false",
                "auto_detect": Settings.get("stream_fallback_auto_detect", "true") != "false",
                "message": "Stream fallback settings updated",
            }
        )
    except Exception as e:
        logger.error(f"Error updating stream fallback config: {e}")
        return jsonify({"error": str(e)}), 500
