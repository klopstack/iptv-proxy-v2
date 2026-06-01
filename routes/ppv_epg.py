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
        mode (optional): "upcoming", "past", or "all" (default: "all")
        status (optional): Filter by event status
        data_completeness (optional): Filter by data completeness
        search (optional): Search teams, league, sport, title
        page (optional): Page number (default: 1)
        per_page (optional): Results per page (default: 50)

    Returns:
        JSON list of event records with pagination and summary
    """
    account_id = request.args.get("account_id", type=int)
    days_ahead = request.args.get("days_ahead", 7, type=int)
    mode = request.args.get("mode", "all")
    status = request.args.get("status")
    data_completeness = request.args.get("data_completeness")
    search = request.args.get("search")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    legacy_upcoming = mode == "upcoming" and page == 1 and not search and not status and not data_completeness
    legacy_account = account_id and mode == "all" and page == 1 and not search and not status and not data_completeness

    if legacy_upcoming and not account_id:
        events = PPVEpgService.get_upcoming_ppv_events(days_ahead=days_ahead)
        return jsonify({"events": events, "count": len(events)})
    if legacy_account:
        events = PPVEpgService.get_ppv_events_for_account(account_id)
        return jsonify({"events": events, "count": len(events)})

    result = PPVEpgService.list_ppv_events(
        mode=mode,
        account_id=account_id,
        days_ahead=days_ahead,
        status=status,
        data_completeness=data_completeness,
        search=search,
        page=page,
        per_page=per_page,
    )
    return jsonify(result)


@ppv_epg_bp.route("/events/<int:event_id>", methods=["GET"])
@cross_origin()
@handle_errors()
def get_ppv_event_detail(event_id):
    """Get full PPV event detail with linked channels."""
    detail = PPVEpgService.get_ppv_event_detail(event_id)
    if not detail:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(detail)


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
    from flask import current_app

    from models import EpgSource
    from services.epg_sync_orchestrator import EpgSyncOrchestrator

    epg_source = db.session.get(EpgSource, source_id)
    if not epg_source:
        return jsonify({"error": "EPG source not found"}), 404

    if epg_source.source_type != "ppv_events":
        return jsonify({"error": f"EPG source is type '{epg_source.source_type}', expected 'ppv_events'"}), 400

    force = request.args.get("force", "false").lower() in ("1", "true", "yes")
    app = current_app._get_current_object()
    result = EpgSyncOrchestrator(app).sync_source_by_id(source_id, force=force)

    if result.get("skipped"):
        return jsonify({"error": result.get("message", "Sync already in progress")}), 409

    if not result.get("success"):
        return jsonify({"error": result.get("message", "Sync failed")}), 400

    stats = result.get("stats") or {}
    created = stats.get("channels_added", 0)
    updated = stats.get("channels_updated", 0)
    total = created + updated

    return jsonify(
        {
            "created": created,
            "updated": updated,
            "total": total,
            "message": result.get("message") or f"Synced {total} PPV events to EPG channels",
            "partial": bool(result.get("partial") or stats.get("partial")),
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
    from services.epg.match_rules import EpgMatchRulesService

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
