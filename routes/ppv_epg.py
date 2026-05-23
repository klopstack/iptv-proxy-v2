"""
PPV EPG Routes

API endpoints for managing and generating EPG data from PPV events
with enriched TheSportsDB data.
"""
import logging

from flask import Blueprint, Response, jsonify, request
from flask_cors import cross_origin

from error_handling import handle_errors
from models import Account, db
from services.ppv.epg import PPVEpgService

logger = logging.getLogger(__name__)

ppv_epg_bp = Blueprint("ppv_epg", __name__, url_prefix="/api/ppv-epg")


@ppv_epg_bp.route("/xmltv", methods=["GET"])
@handle_errors(return_json=False, default_message="Error generating PPV EPG")
def get_ppv_epg_xmltv():
    """
    Generate XMLTV EPG data from PPV Event records.

    Query Parameters:
        account_id (optional): Filter to specific account
        include_inactive (optional): Include channels without events (default: false)
        event_duration_hours (optional): Default event duration in hours (default: 4)

    Returns:
        XMLTV XML data
    """
    account_id = request.args.get("account_id", type=int)
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    event_duration_hours = request.args.get("event_duration_hours", 4, type=int)

    # Validate account if specified
    if account_id:
        account = db.session.get(Account, account_id)
        if not account:
            return Response(
                b'<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>\n', mimetype="application/xml", status=404
            )

    # Generate EPG
    epg_xml = PPVEpgService.generate_ppv_epg_xmltv(
        account_id=account_id,
        include_inactive=include_inactive,
        event_duration_hours=event_duration_hours,
    )

    return Response(epg_xml, mimetype="application/xml")


@ppv_epg_bp.route("/events", methods=["GET"])
@cross_origin()
@handle_errors()
def get_ppv_events():
    """
    Get PPV events with optional filtering.

    Query Parameters:
        account_id (optional): Filter to specific account
        days_ahead (optional): Number of days ahead for upcoming events (default: 7)
        mode (optional): "upcoming" or "all" (default: "all")

    Returns:
        JSON list of event records
    """
    account_id = request.args.get("account_id", type=int)
    days_ahead = request.args.get("days_ahead", 7, type=int)
    mode = request.args.get("mode", "all")

    if mode == "upcoming":
        events = PPVEpgService.get_upcoming_ppv_events(days_ahead=days_ahead)
        return jsonify({"events": events, "count": len(events)})
    elif account_id:
        events = PPVEpgService.get_ppv_events_for_account(account_id)
        return jsonify({"events": events, "count": len(events)})
    else:
        return jsonify({"error": "Either mode=upcoming or account_id must be specified"}), 400


@ppv_epg_bp.route("/events/<int:event_id>/channels", methods=["GET"])
@cross_origin()
@handle_errors()
def get_event_channels(event_id):
    """
    Get all channels broadcasting a specific event.

    Path Parameters:
        event_id: Event ID

    Returns:
        JSON list of channels with link metadata
    """
    channels = PPVEpgService.get_event_channels(event_id)
    return jsonify({"channels": channels, "count": len(channels)})


@ppv_epg_bp.route("/source", methods=["POST"])
@cross_origin()
@handle_errors()
def create_ppv_epg_source():
    """
    Create or get the PPV events EPG source.

    Request Body:
        name (optional): Name for the EPG source (default: "PPV Events")

    Returns:
        JSON with EPG source ID
    """
    data = request.get_json() or {}
    name = data.get("name", "PPV Events")

    source_id = PPVEpgService.create_epg_source_for_ppv_events(name=name)

    return jsonify({"epg_source_id": source_id, "message": f"PPV EPG source created/retrieved with ID {source_id}"})


@ppv_epg_bp.route("/source/<int:source_id>/sync", methods=["POST"])
@cross_origin()
@handle_errors()
def sync_ppv_events_to_source(source_id):
    """
    Sync PPV Event records to EpgChannel entries for a PPV EPG source.

    Path Parameters:
        source_id: EPG source ID

    Returns:
        JSON with sync statistics
    """
    from models import EpgSource

    # Validate source exists and is ppv_events type
    epg_source = db.session.get(EpgSource, source_id)
    if not epg_source:
        return jsonify({"error": "EPG source not found"}), 404

    if epg_source.source_type != "ppv_events":
        return jsonify({"error": f"EPG source is type '{epg_source.source_type}', expected 'ppv_events'"}), 400

    # Sync events to EPG channels
    created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)

    # Update source stats
    epg_source.channel_count = created + updated
    epg_source.last_sync_status = "success"
    from datetime import datetime, timezone

    epg_source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()

    return jsonify(
        {
            "created": created,
            "updated": updated,
            "total": created + updated,
            "message": f"Synced {created + updated} PPV events to EPG channels",
        }
    )


@ppv_epg_bp.route("/source/<int:source_id>/match", methods=["POST"])
@cross_origin()
@handle_errors()
def match_ppv_channels_to_epg(source_id):
    """
    Match PPV channels to EPG data.

    Automatically maps PPV channels to their corresponding EPG channel entries
    in the PPV Events EPG source.

    Path Parameters:
        source_id: PPV Events EPG source ID

    Returns:
        JSON with matching statistics
    """
    from models import EpgSource
    from services.epg_match_rules_service import EpgMatchRulesService

    # Verify source exists and is PPV type
    epg_source = db.session.get(EpgSource, source_id)
    if not epg_source:
        return jsonify({"error": "EPG source not found"}), 404

    if epg_source.source_type != "ppv_events":
        return jsonify({"error": "Source is not a PPV Events source"}), 400

    # Run matching
    batch_size = request.json.get("batch_size", 100) if request.json else 100
    match_stats = EpgMatchRulesService.match_ppv_channels_to_epg(source_id=source_id, batch_size=batch_size)

    # Check for errors
    if "error" in match_stats:
        return jsonify(match_stats), 400

    return jsonify(
        {
            "matched_count": match_stats["matched_count"],
            "unmatched_count": match_stats["unmatched_count"],
            "skipped_existing_count": match_stats["skipped_existing_count"],
            "total_channels": match_stats["total_channels"],
            "message": f"Matched {match_stats['matched_count']} PPV channels to EPG",
        }
    )


@ppv_epg_bp.route("/source/<int:source_id>", methods=["GET"])
@cross_origin()
@handle_errors()
def get_ppv_epg_source_info(source_id):
    """
    Get information about a PPV EPG source.

    Path Parameters:
        source_id: EPG source ID

    Returns:
        JSON with source details
    """
    from models import EpgSource

    epg_source = db.session.get(EpgSource, source_id)
    if not epg_source:
        return jsonify({"error": "EPG source not found"}), 404

    return jsonify(
        {
            "id": epg_source.id,
            "name": epg_source.name,
            "source_type": epg_source.source_type,
            "enabled": epg_source.enabled,
            "priority": epg_source.priority,
            "channel_count": epg_source.channel_count,
            "last_sync": epg_source.last_sync.isoformat() if epg_source.last_sync else None,
            "last_sync_status": epg_source.last_sync_status,
        }
    )
