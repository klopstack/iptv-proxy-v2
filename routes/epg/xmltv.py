"""
XMLTV Grabber integration routes
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors

logger = logging.getLogger(__name__)

# Create blueprint
xmltv_bp = Blueprint("xmltv", __name__, url_prefix="/api/xmltv")

__all__ = ["xmltv_bp"]


# ============================================================================
# API Routes - XMLTV Grabbers
# ============================================================================


@xmltv_bp.route("/grabbers", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting XMLTV grabbers")
def get_xmltv_grabbers():
    """Get list of installed XMLTV grabbers"""
    from services.xmltv_grabber_service import XmltvGrabberService

    grabbers = XmltvGrabberService.get_installed_grabbers()

    return jsonify(
        [
            {
                "name": g.name,
                "description": g.description,
                "path": g.path,
                "capabilities": g.capabilities,
            }
            for g in grabbers
        ]
    )


@xmltv_bp.route("/grabbers/<string:grabber_name>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting grabber info")
def get_xmltv_grabber(grabber_name):
    """Get information about a specific XMLTV grabber"""
    from services.xmltv_grabber_service import XmltvGrabberService

    grabber = XmltvGrabberService.get_grabber_by_name(grabber_name)

    if not grabber:
        return jsonify({"error": f"Grabber '{grabber_name}' not found"}), 404

    return jsonify(
        {
            "name": grabber.name,
            "description": grabber.description,
            "path": grabber.path,
            "capabilities": grabber.capabilities,
        }
    )


@xmltv_bp.route("/grabbers/<string:grabber_name>/channels", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting grabber channels")
def get_xmltv_grabber_channels(grabber_name):
    """Get available channels from an XMLTV grabber"""
    from services.xmltv_grabber_service import XmltvGrabberService

    config_name = request.args.get("config_name")

    success, channels, error = XmltvGrabberService.get_grabber_channels(grabber_name, config_name)

    if not success:
        return jsonify({"error": error}), 500

    return jsonify({"channels": channels, "count": len(channels)})


@xmltv_bp.route("/grabbers/<string:grabber_name>/test", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing grabber")
def test_xmltv_grabber(grabber_name):
    """Test an XMLTV grabber configuration"""
    from services.xmltv_grabber_service import XmltvGrabberService

    data = request.json or {}
    config_name = data.get("config_name")

    result = XmltvGrabberService.test_grabber(grabber_name, config_name)

    return jsonify(result)


@xmltv_bp.route("/configs", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting grabber configs")
def get_xmltv_configs():
    """Get list of saved grabber configurations"""
    from services.xmltv_grabber_service import XmltvGrabberService

    grabber_name = request.args.get("grabber_name")

    configs = XmltvGrabberService.list_grabber_configs(grabber_name)

    return jsonify({"configs": configs, "count": len(configs)})


@xmltv_bp.route("/configs/<string:config_name>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error saving grabber config")
def save_xmltv_config(config_name):
    """Save a grabber configuration"""
    from services.xmltv_grabber_service import XmltvGrabberService

    data = request.json or {}

    if not data.get("grabber_name"):
        return jsonify({"error": "grabber_name is required"}), 400

    config_data = data.get("config_data")

    success, message = XmltvGrabberService.configure_grabber(
        data["grabber_name"],
        config_name,
        config_data,
    )

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 400


@xmltv_bp.route("/configs/<string:config_name>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting grabber config")
def delete_xmltv_config(config_name):
    """Delete a grabber configuration"""
    from services.xmltv_grabber_service import XmltvGrabberService

    success, message = XmltvGrabberService.delete_grabber_config(config_name)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 404
