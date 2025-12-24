"""
Channel Health API Routes

Provides endpoints for:
- Viewing channel health reports
- Testing individual channels
- Re-enabling and ignoring channels
- Configuring health monitoring settings
"""

import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Category, ChannelHealthConfig, ChannelHealthStatus
from services.channel_health_service import ChannelHealthService

logger = logging.getLogger(__name__)

# Create blueprint
channel_health_bp = Blueprint("channel_health", __name__)


# ============================================================================
# Health Report Endpoints
# ============================================================================


@channel_health_bp.route("/api/channel-health/report", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching health report")
def get_health_report():
    """
    Get comprehensive channel health report.

    Query parameters:
    - account_id (optional): Filter by account ID
    - status (optional): Filter by status (down, degraded, healthy, unknown, ignored)
    - include_epg (optional): Include EPG mapping info (default: true)
    """
    account_id = request.args.get("account_id", type=int)
    status_filter = request.args.get("status")
    include_epg = request.args.get("include_epg", "true").lower() == "true"

    # Validate status filter
    valid_statuses = [
        ChannelHealthStatus.STATUS_UNKNOWN,
        ChannelHealthStatus.STATUS_HEALTHY,
        ChannelHealthStatus.STATUS_DEGRADED,
        ChannelHealthStatus.STATUS_DOWN,
        ChannelHealthStatus.STATUS_IGNORED,
    ]
    if status_filter and status_filter not in valid_statuses:
        return jsonify({"success": False, "error": f"Invalid status. Valid values: {valid_statuses}"}), 400

    report = ChannelHealthService.get_health_report(
        account_id=account_id,
        status_filter=status_filter,
        include_epg=include_epg,
    )

    return jsonify({"success": True, **report})


@channel_health_bp.route("/api/channel-health/summary", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching health summary")
def get_health_summary():
    """
    Get a summary of channel health across all accounts.

    Returns counts by status without full channel details.
    """
    account_id = request.args.get("account_id", type=int)
    category_id = request.args.get("category_id", type=int)

    report = ChannelHealthService.get_health_summary(
        account_id=account_id,
        category_id=category_id,
    )

    return jsonify(
        {
            "success": True,
            "summary": report["summary"],
            "config": report["config"],
        }
    )


@channel_health_bp.route("/api/channel-health/channels", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching channels")
def get_channels_paginated():
    """
    Get paginated channel health data with filtering.

    Query parameters:
    - account_id (optional): Filter by account ID
    - category_id (optional): Filter by category ID
    - status (optional): Filter by status (down, degraded, healthy, unknown, ignored)
    - visibility (optional): Filter by visibility (visible, hidden)
    - epg (optional): Filter by EPG presence (with, without)
    - ppv (optional): Filter by PPV status (ppv, non-ppv, all). Default: non-ppv (excludes PPV)
    - search (optional): Search by channel name
    - page (optional): Page number (default: 1)
    - per_page (optional): Items per page (default: 100, max: 500)
    - include_epg (optional): Include EPG mapping info (default: true)
    """
    account_id = request.args.get("account_id", type=int)
    category_id = request.args.get("category_id", type=int)
    status_filter = request.args.get("status")
    visibility_filter = request.args.get("visibility")
    epg_filter = request.args.get("epg")
    ppv_filter = request.args.get("ppv")
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 100, type=int), 500)
    include_epg = request.args.get("include_epg", "true").lower() == "true"

    # Validate status filter
    valid_statuses = [
        ChannelHealthStatus.STATUS_UNKNOWN,
        ChannelHealthStatus.STATUS_HEALTHY,
        ChannelHealthStatus.STATUS_DEGRADED,
        ChannelHealthStatus.STATUS_DOWN,
        ChannelHealthStatus.STATUS_IGNORED,
    ]
    if status_filter and status_filter not in valid_statuses:
        return jsonify({"success": False, "error": f"Invalid status. Valid values: {valid_statuses}"}), 400

    if visibility_filter and visibility_filter not in ["visible", "hidden"]:
        return jsonify({"success": False, "error": "Invalid visibility. Valid values: visible, hidden"}), 400

    if epg_filter and epg_filter not in ["with", "without"]:
        return jsonify({"success": False, "error": "Invalid epg filter. Valid values: with, without"}), 400

    if ppv_filter and ppv_filter not in ["ppv", "non-ppv", "all"]:
        return jsonify({"success": False, "error": "Invalid ppv filter. Valid values: ppv, non-ppv, all"}), 400

    result = ChannelHealthService.get_channels_paginated(
        account_id=account_id,
        category_id=category_id,
        status_filter=status_filter,
        visibility_filter=visibility_filter,
        epg_filter=epg_filter,
        ppv_filter=ppv_filter,
        search=search,
        page=page,
        per_page=per_page,
        include_epg=include_epg,
    )

    return jsonify({"success": True, **result})


@channel_health_bp.route("/api/channel-health/categories", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching categories")
def get_categories():
    """
    Get list of categories for filtering.

    Query parameters:
    - account_id (optional): Filter categories by account ID
    """
    account_id = request.args.get("account_id", type=int)

    query = Category.query
    if account_id:
        query = query.filter(Category.account_id == account_id)

    query = query.order_by(Category.category_name)

    categories = [
        {
            "id": cat.id,
            "category_id": cat.category_id,
            "name": cat.category_name,
            "account_id": cat.account_id,
        }
        for cat in query.all()
    ]

    return jsonify({"success": True, "categories": categories})


# ============================================================================
# Channel Action Endpoints
# ============================================================================


@channel_health_bp.route("/api/channel-health/test/<int:channel_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing channel")
def test_channel(channel_id: int):
    """
    Manually test a specific channel's health.

    This performs a health check immediately and records the result.
    """
    result = ChannelHealthService.test_channel(channel_id)

    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 400


@channel_health_bp.route("/api/channel-health/reenable/<int:channel_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error re-enabling channel")
def reenable_channel(channel_id: int):
    """
    Re-enable a channel that was marked as down or disabled.

    This resets the health status and makes the channel visible again.
    """
    result = ChannelHealthService.reenable_channel(channel_id)

    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 400


@channel_health_bp.route("/api/channel-health/ignore/<int:channel_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error ignoring channel")
def ignore_channel(channel_id: int):
    """
    Mark a channel as ignored (won't be scanned again).

    Request body (optional):
    - reason: String explaining why the channel is being ignored
    """
    data = request.get_json() or {}
    reason = data.get("reason")

    result = ChannelHealthService.ignore_channel(channel_id, reason)

    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 400


@channel_health_bp.route("/api/channel-health/history/<int:channel_id>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching channel history")
def get_channel_history(channel_id: int):
    """
    Get the health check history for a specific channel.

    Query parameters:
    - limit (optional): Maximum records to return (default: 50)
    """
    limit = request.args.get("limit", 50, type=int)
    limit = min(max(1, limit), 500)  # Clamp between 1 and 500

    history = ChannelHealthService.get_channel_history(channel_id, limit)

    return jsonify(
        {
            "success": True,
            "channel_id": channel_id,
            "history": history,
        }
    )


# ============================================================================
# Scan Control Endpoints
# ============================================================================


@channel_health_bp.route("/api/channel-health/scan-status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching scan status")
def get_scan_status():
    """
    Get the current scanning status.

    Query parameters:
    - account_id (optional): Get status for specific account
    """
    account_id = request.args.get("account_id", type=int)

    status = ChannelHealthService.get_scan_status(account_id)

    return jsonify({"success": True, **status})


@channel_health_bp.route("/api/channel-health/scan/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error triggering scan")
def trigger_scan(account_id: int):
    """
    Manually trigger a channel health scan for an account.

    Request body (optional):
    - max_channels: Maximum channels to scan (default: 10)
    """
    data = request.get_json() or {}
    max_channels = data.get("max_channels", 10)
    max_channels = min(max(1, max_channels), 100)  # Clamp between 1 and 100

    # Temporarily enable scanning for this request
    was_enabled = ChannelHealthConfig.get_bool("scanning_enabled", False)
    if not was_enabled:
        ChannelHealthConfig.set("scanning_enabled", "true")

    try:
        result = ChannelHealthService.scan_channels(account_id, max_channels)
    finally:
        # Restore previous state
        if not was_enabled:
            ChannelHealthConfig.set("scanning_enabled", "false")

    return jsonify({"success": True, **result})


# ============================================================================
# Configuration Endpoints
# ============================================================================


@channel_health_bp.route("/api/channel-health/config", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching config")
def get_config():
    """Get all health monitoring configuration values."""
    config = ChannelHealthConfig.get_all()
    return jsonify({"success": True, "config": config})


@channel_health_bp.route("/api/channel-health/config", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating config")
def update_config():
    """
    Update health monitoring configuration values.

    Request body:
    - key: Configuration key
    - value: New value

    Or batch update:
    - config: Dict of key-value pairs to update
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    if "config" in data:
        # Batch update
        results = {}
        for key, value in data["config"].items():
            result = ChannelHealthService.update_config(key, str(value))
            results[key] = result
        return jsonify({"success": True, "results": results})
    elif "key" in data and "value" in data:
        # Single update
        result = ChannelHealthService.update_config(data["key"], str(data["value"]))
        if result.get("success"):
            return jsonify(result)
        else:
            return jsonify(result), 400
    else:
        return jsonify({"success": False, "error": "Either 'config' dict or 'key'/'value' required"}), 400


@channel_health_bp.route("/api/channel-health/config/<key>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating config")
def update_config_key(key: str):
    """
    Update a specific configuration value.

    Request body:
    - value: New value for the key
    """
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify({"success": False, "error": "Value required in request body"}), 400

    result = ChannelHealthService.update_config(key, str(data["value"]))

    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 400


# ============================================================================
# Bulk Action Endpoints
# ============================================================================


@channel_health_bp.route("/api/channel-health/bulk/reenable", methods=["POST"])
@handle_errors(return_json=True, default_message="Error re-enabling channels")
def bulk_reenable():
    """
    Re-enable multiple channels.

    Request body:
    - channel_ids: List of channel IDs to re-enable
    """
    data = request.get_json()
    if not data or "channel_ids" not in data:
        return jsonify({"success": False, "error": "channel_ids required"}), 400

    channel_ids = data["channel_ids"]
    if not isinstance(channel_ids, list):
        return jsonify({"success": False, "error": "channel_ids must be a list"}), 400

    results = []
    for channel_id in channel_ids:
        result = ChannelHealthService.reenable_channel(channel_id)
        results.append({"channel_id": channel_id, **result})

    return jsonify(
        {
            "success": True,
            "processed": len(results),
            "results": results,
        }
    )


@channel_health_bp.route("/api/channel-health/bulk/ignore", methods=["POST"])
@handle_errors(return_json=True, default_message="Error ignoring channels")
def bulk_ignore():
    """
    Ignore multiple channels.

    Request body:
    - channel_ids: List of channel IDs to ignore
    - reason (optional): Reason for ignoring
    """
    data = request.get_json()
    if not data or "channel_ids" not in data:
        return jsonify({"success": False, "error": "channel_ids required"}), 400

    channel_ids = data["channel_ids"]
    if not isinstance(channel_ids, list):
        return jsonify({"success": False, "error": "channel_ids must be a list"}), 400

    reason = data.get("reason")

    results = []
    for channel_id in channel_ids:
        result = ChannelHealthService.ignore_channel(channel_id, reason)
        results.append({"channel_id": channel_id, **result})

    return jsonify(
        {
            "success": True,
            "processed": len(results),
            "results": results,
        }
    )
