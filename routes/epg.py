"""
EPG (Electronic Program Guide) management routes
"""
import json
import logging
from datetime import datetime
from typing import Dict, List

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, ChannelEpgMapping, EpgChannel, EpgSource, SdLineup, SdStation, db
from services.epg_match_rules_service import EpgMatchRulesService
from services.epg_service import EpgService, make_sd_xmltv_id, normalize_xmltv_url
from services.iptv_service import IPTVService
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError, validate_credentials

logger = logging.getLogger(__name__)

# Create blueprint
epg_bp = Blueprint("epg", __name__)


# ============================================================================
# Helper Functions
# ============================================================================


def _sync_sd_channels_to_epg(source: EpgSource, channels: List[Dict]) -> Dict:
    """
    Sync Schedules Direct channels to EpgChannel records.

    Args:
        source: The EpgSource for Schedules Direct
        channels: List of channel dicts from SchedulesDirectClient.get_lineup_channels()

    Returns:
        Dict with sync statistics
    """
    stats = {
        "channels_added": 0,
        "channels_updated": 0,
        "channels_removed": 0,
    }

    now = datetime.utcnow()
    seen_channel_ids = set()

    # Get existing channels for this source
    existing = {ec.channel_id: ec for ec in EpgChannel.query.filter_by(source_id=source.id).all()}

    for channel in channels:
        station_id = channel.get("stationID")
        if not station_id:
            continue

        # Create XMLTV-style channel ID for SD stations
        channel_id = make_sd_xmltv_id(station_id)
        seen_channel_ids.add(channel_id)

        # Build display names list - include callsign and full name
        display_names = []
        callsign = channel.get("callsign")
        name = channel.get("name")
        if callsign:
            display_names.append(callsign)
        if name and name != callsign:
            display_names.append(name)

        primary_name = callsign or name or f"Station {station_id}"

        # Get logo URL if available
        logo_url = None
        logo_info = channel.get("logo")
        if logo_info and isinstance(logo_info, dict):
            logo_url = logo_info.get("url")

        if channel_id in existing:
            # Update existing channel
            ec = existing[channel_id]
            ec.display_name = primary_name
            ec.display_names_json = json.dumps(display_names) if display_names else None
            ec.icon_url = logo_url
            ec.last_seen = now
            ec.updated_at = now
            stats["channels_updated"] += 1
        else:
            # Create new channel
            ec = EpgChannel(
                source_id=source.id,
                channel_id=channel_id,
                display_name=primary_name,
                display_names_json=json.dumps(display_names) if display_names else None,
                icon_url=logo_url,
                program_count=0,  # Will be updated when schedules are fetched
                last_seen=now,
            )
            db.session.add(ec)
            stats["channels_added"] += 1

    # Count channels not seen (but don't delete them)
    for channel_id in existing:
        if channel_id not in seen_channel_ids:
            stats["channels_removed"] += 1

    db.session.commit()

    logger.info(
        f"SD sync for source {source.id} ({source.name}): "
        f"added={stats['channels_added']}, updated={stats['channels_updated']}, "
        f"not_seen={stats['channels_removed']}"
    )

    return stats


# ============================================================================
# API Routes - EPG Sources
# ============================================================================


@epg_bp.route("/api/epg/sources", methods=["GET"])
def get_epg_sources():
    """Get all EPG sources with usage statistics"""
    sources = EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all()

    # Get mapping counts per source (how many channels are using EPG from each source)
    # Join ChannelEpgMapping -> EpgChannel -> EpgSource to count mappings per source
    mapping_counts = (
        db.session.query(EpgSource.id, db.func.count(ChannelEpgMapping.id).label("mapping_count"))
        .join(EpgChannel, EpgChannel.source_id == EpgSource.id)
        .join(ChannelEpgMapping, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .group_by(EpgSource.id)
        .all()
    )
    mapping_count_map = {row.id: row.mapping_count for row in mapping_counts}

    return jsonify(
        [
            {
                "id": s.id,
                "name": s.name,
                "source_type": s.source_type,
                "account_id": s.account_id,
                "account_name": s.account.name if s.account else None,
                "url": s.url,
                "priority": s.priority,
                "enabled": s.enabled,
                "last_sync": s.last_sync.isoformat() if s.last_sync else None,
                "last_sync_status": s.last_sync_status,
                "last_sync_message": s.last_sync_message,
                "channel_count": s.channel_count,
                "used_mapping_count": mapping_count_map.get(s.id, 0),
                "xmltv_grabber": s.xmltv_grabber,
                "xmltv_config_name": s.xmltv_config_name,
                "xmltv_days": s.xmltv_days,
                "xmltv_offset": s.xmltv_offset,
                "xmltv_extra_args": s.xmltv_extra_args,
            }
            for s in sources
        ]
    )


@epg_bp.route("/api/epg/sources", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG source")
def create_epg_source():
    """Create a new EPG source"""
    data = request.json

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("source_type"):
        return jsonify({"error": "Source type is required"}), 400

    valid_types = ["provider", "schedules_direct", "xmltv_url", "xmltv_file", "xmltv_grabber"]
    if data["source_type"] not in valid_types:
        return jsonify({"error": f"Invalid source type. Must be one of: {valid_types}"}), 400

    # Validate account_id for provider type
    if data["source_type"] == "provider":
        if not data.get("account_id"):
            return jsonify({"error": "Account ID is required for provider sources"}), 400
        Account.query.get_or_404(data["account_id"])

    # Validate xmltv_grabber fields
    if data["source_type"] == "xmltv_grabber":
        if not data.get("xmltv_grabber"):
            return jsonify({"error": "XMLTV grabber name is required"}), 400

    source = EpgSource(
        name=data["name"],
        source_type=data["source_type"],
        account_id=data.get("account_id"),
        url=data.get("url"),
        sd_username=data.get("sd_username"),
        sd_password=data.get("sd_password"),
        sd_lineup=data.get("sd_lineup"),
        xmltv_grabber=data.get("xmltv_grabber"),
        xmltv_config_name=data.get("xmltv_config_name"),
        xmltv_days=data.get("xmltv_days", 7),
        xmltv_offset=data.get("xmltv_offset", 0),
        xmltv_extra_args=data.get("xmltv_extra_args"),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
    )

    db.session.add(source)
    db.session.commit()

    return (
        jsonify(
            {
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "message": "EPG source created successfully",
            }
        ),
        201,
    )


@epg_bp.route("/api/epg/sources/<int:source_id>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating EPG source")
def update_epg_source(source_id):
    """Update an EPG source"""
    source = EpgSource.query.get_or_404(source_id)
    data = request.json

    if "name" in data:
        source.name = data["name"]
    if "url" in data:
        source.url = data["url"]
    if "priority" in data:
        source.priority = data["priority"]
    if "enabled" in data:
        source.enabled = data["enabled"]
    if "sd_username" in data:
        source.sd_username = data["sd_username"]
    if "sd_password" in data:
        source.sd_password = data["sd_password"]
    if "sd_lineup" in data:
        source.sd_lineup = data["sd_lineup"]
    if "xmltv_grabber" in data:
        source.xmltv_grabber = data["xmltv_grabber"]
    if "xmltv_config_name" in data:
        source.xmltv_config_name = data["xmltv_config_name"]
    if "xmltv_days" in data:
        source.xmltv_days = data["xmltv_days"]
    if "xmltv_offset" in data:
        source.xmltv_offset = data["xmltv_offset"]
    if "xmltv_extra_args" in data:
        source.xmltv_extra_args = data["xmltv_extra_args"]

    db.session.commit()

    return jsonify({"success": True, "message": "EPG source updated"})


@epg_bp.route("/api/epg/sources/<int:source_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG source")
def delete_epg_source(source_id):
    """Delete an EPG source and all its channels"""
    source = EpgSource.query.get_or_404(source_id)

    db.session.delete(source)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG source deleted"})


@epg_bp.route("/api/epg/sources/<int:source_id>/mappings", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting source mappings")
def get_source_mappings(source_id):
    """Get all channel mappings that use EPG data from this source.

    This shows which channels are using EPG listings from this provider.

    Query parameters:
    - limit: Max results (default 100)
    - offset: Pagination offset
    - search: Search by channel name
    """
    from models import Category, Channel

    source = EpgSource.query.get_or_404(source_id)

    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    search = request.args.get("search", "")

    # Query mappings through EpgChannel for this source
    query = (
        db.session.query(ChannelEpgMapping, Channel, EpgChannel, Category)
        .join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .join(Channel, ChannelEpgMapping.channel_id == Channel.id)
        .outerjoin(Category, Channel.category_id == Category.id)
        .filter(EpgChannel.source_id == source_id)
    )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Channel.name.ilike(search_term),
                Channel.cleaned_name.ilike(search_term),
                EpgChannel.display_name.ilike(search_term),
            )
        )

    total = query.count()
    results = query.order_by(Channel.name).offset(offset).limit(limit).all()

    mappings = []
    for mapping, channel, epg_channel, category in results:
        mappings.append(
            {
                "mapping_id": mapping.id,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "channel_clean_name": channel.cleaned_name,
                "channel_icon": channel.stream_icon,
                "category_id": category.id if category else None,
                "category_name": category.category_name if category else None,
                "account_id": channel.account_id,
                "epg_channel_id": epg_channel.id,
                "epg_channel_xmltv_id": epg_channel.channel_id,
                "epg_channel_name": epg_channel.display_name,
                "epg_channel_icon": epg_channel.icon_url,
                "mapping_type": mapping.mapping_type,
                "confidence": mapping.confidence,
            }
        )

    return jsonify(
        {
            "source_id": source.id,
            "source_name": source.name,
            "total": total,
            "offset": offset,
            "limit": limit,
            "mappings": mappings,
        }
    )


@epg_bp.route("/api/epg/sources/<int:source_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing EPG source")
def sync_epg_source(source_id):
    """Sync EPG data from a source"""
    from services.epg_service import update_ppv_channel_visibility

    source = EpgSource.query.get_or_404(source_id)

    if source.source_type == "provider":
        if not source.account:
            return jsonify({"error": "Provider source has no associated account"}), 400

        # Get XMLTV from provider
        account = source.account
        cred = account.get_primary_credential()
        if cred:
            service = IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
        else:
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )

        xml_content = service.get_xmltv()
        stats = EpgService.sync_epg_source(source, xml_content)

        # Update PPV channel visibility for this account
        try:
            ppv_stats = update_ppv_channel_visibility(account.id)
            logger.info(f"PPV visibility update after EPG sync: {ppv_stats}")
        except Exception as e:
            logger.warning(f"Failed to update PPV visibility after EPG sync: {e}")

        return jsonify(
            {
                "success": True,
                "message": f"Synced {stats['channels_added'] + stats['channels_updated']} channels",
                "stats": stats,
            }
        )

    elif source.source_type == "xmltv_url":
        if not source.url:
            return jsonify({"error": "No URL configured for this source"}), 400

        import requests

        # Normalize URL (e.g., convert GitHub blob URLs to raw URLs)
        url = normalize_xmltv_url(source.url)
        if url != source.url:
            logger.info(f"Normalized XMLTV URL: {source.url} -> {url}")

        # Use 10 minute timeout for large XMLTV files from rate-limited servers
        response = requests.get(url, timeout=600)
        response.raise_for_status()

        stats = EpgService.sync_epg_source(source, response.content)

        return jsonify(
            {
                "success": True,
                "message": f"Synced {stats['channels_added'] + stats['channels_updated']} channels",
                "stats": stats,
            }
        )

    elif source.source_type == "schedules_direct":
        # Validate SD credentials are configured
        if not source.sd_username or not source.sd_password:
            return jsonify({"error": "Schedules Direct credentials not configured"}), 400

        if not source.sd_lineup:
            return jsonify({"error": "No Schedules Direct lineup selected"}), 400

        try:
            # Initialize SD client and authenticate
            sd_client = SchedulesDirectClient(source.sd_username, source.sd_password)
            sd_client.authenticate()

            # Get channels from the configured lineup
            channels = sd_client.get_lineup_channels(source.sd_lineup)

            if not channels:
                source.last_sync = db.func.now()
                source.last_sync_status = "error"
                source.last_sync_message = "No channels found in lineup"
                db.session.commit()
                return jsonify({"error": "No channels found in lineup"}), 400

            # Sync channels to EpgChannel records
            stats = _sync_sd_channels_to_epg(source, channels)

            source.last_sync = db.func.now()
            source.last_sync_status = "success"
            source.last_sync_message = (
                f"Synced {stats['channels_added'] + stats['channels_updated']} channels from Schedules Direct"
            )
            source.channel_count = stats["channels_added"] + stats["channels_updated"]
            db.session.commit()

            return jsonify(
                {
                    "success": True,
                    "message": source.last_sync_message,
                    "stats": stats,
                }
            )

        except SchedulesDirectError as e:
            logger.error(f"Schedules Direct error for source {source_id}: {e}")
            source.last_sync = db.func.now()
            source.last_sync_status = "error"
            source.last_sync_message = str(e)
            db.session.commit()
            return jsonify({"error": f"Schedules Direct error: {e}"}), 500

    elif source.source_type == "xmltv_grabber":
        # XMLTV Grabber - run tv_grab_* tools
        from services.xmltv_grabber_service import XmltvGrabberService

        if not source.xmltv_grabber:
            return jsonify({"error": "No XMLTV grabber configured for this source"}), 400

        # Parse extra args if provided
        extra_args = None
        if source.xmltv_extra_args:
            import json

            try:
                extra_args = json.loads(source.xmltv_extra_args)
            except json.JSONDecodeError:
                logger.warning(f"Invalid xmltv_extra_args for source {source_id}")

        success, xml_content, error = XmltvGrabberService.run_grabber(
            grabber_name=source.xmltv_grabber,
            config_name=source.xmltv_config_name,
            days=source.xmltv_days or 7,
            offset=source.xmltv_offset or 0,
            extra_args=extra_args,
        )

        if not success:
            source.last_sync = db.func.now()
            source.last_sync_status = "error"
            source.last_sync_message = error
            db.session.commit()
            return jsonify({"error": f"XMLTV grabber failed: {error}"}), 500

        stats = EpgService.sync_epg_source(source, xml_content)

        return jsonify(
            {
                "success": True,
                "message": f"Synced {stats['channels_added'] + stats['channels_updated']} channels",
                "stats": stats,
            }
        )

    else:
        return jsonify({"error": f"Unknown source type: {source.source_type}"}), 400


# ============================================================================
# API Routes - PPV Channel Visibility
# ============================================================================


@epg_bp.route("/api/epg/ppv/update-visibility", methods=["POST"])
@handle_errors(return_json=True, default_message="Error updating PPV channel visibility")
def update_ppv_visibility():
    """
    Update PPV channel visibility based on channel name changes.

    PPV channels from IPTV providers have placeholder names like "PPV 1" when
    no event is scheduled. When an event IS scheduled, the provider changes
    the channel name to the event title (e.g., "UFC 300: Main Event").

    This endpoint:
    1. Finds all PPV channels (by tag)
    2. Checks if channel name is a placeholder or actual event title
    3. Hides placeholder channels, shows channels with event titles

    Query parameters:
    - account_id: Optional - limit update to specific account
    """
    from services.epg_service import update_ppv_channel_visibility

    account_id = request.args.get("account_id", type=int)

    stats = update_ppv_channel_visibility(account_id)

    message_parts = []
    if stats["events_detected"] > 0:
        message_parts.append(f"{stats['events_detected']} active event(s)")
    if stats["channels_shown"] > 0:
        message_parts.append(f"{stats['channels_shown']} channel(s) shown")
    if stats["channels_hidden"] > 0:
        message_parts.append(f"{stats['channels_hidden']} hidden")

    message = ", ".join(message_parts) if message_parts else "No PPV channel visibility changes"

    return jsonify(
        {
            "success": True,
            "message": message,
            "stats": stats,
        }
    )


@epg_bp.route("/api/epg/ppv/xmltv", methods=["GET"])
@handle_errors(return_json=False, default_message="Error generating PPV EPG")
def get_ppv_epg_xmltv():
    """
    Get XMLTV EPG data for active PPV channels.

    Since PPV channels don't have external EPG data, this generates synthetic
    EPG entries using the channel name as the program title. Only visible
    (active event) PPV channels are included.

    Query parameters:
    - account_id: Optional - limit to specific account
    - duration: Optional - event duration in hours (default: 8)

    Returns:
        XMLTV XML document
    """
    from flask import Response

    from services.epg_service import get_ppv_epg_xmltv

    account_id = request.args.get("account_id", type=int)
    duration = request.args.get("duration", default=8, type=int)

    xml_data = get_ppv_epg_xmltv(account_id, duration_hours=duration)

    return Response(xml_data, mimetype="application/xml")


# ============================================================================
# API Routes - EPG Channels
# ============================================================================


@epg_bp.route("/api/epg/channels", methods=["GET"])
def get_epg_channels():
    """Get EPG channels with optional filtering

    Query parameters:
    - source_id: Filter by EPG source
    - search: Search by channel ID or display name (supports fuzzy matching)
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    source_id = request.args.get("source_id", type=int)
    search = request.args.get("search", "")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    query = EpgChannel.query

    if source_id:
        query = query.filter_by(source_id=source_id)

    if search:
        # Support fuzzy matching by splitting search into words and matching each
        search_words = search.strip().split()
        for word in search_words:
            search_term = f"%{word}%"
            query = query.filter(
                db.or_(
                    EpgChannel.channel_id.ilike(search_term),
                    EpgChannel.display_name.ilike(search_term),
                )
            )

    total = query.count()
    channels = query.order_by(EpgChannel.display_name).offset(offset).limit(limit).all()

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "channels": [
                {
                    "id": c.id,
                    "source_id": c.source_id,
                    "channel_id": c.channel_id,
                    "display_name": c.display_name,
                    "icon_url": c.icon_url,
                    "program_count": c.program_count,
                    "first_program": c.first_program.isoformat() if c.first_program else None,
                    "last_program": c.last_program.isoformat() if c.last_program else None,
                    "mapping_count": len(c.channel_mappings),
                }
                for c in channels
            ],
        }
    )


# ============================================================================
# API Routes - EPG Matching
# ============================================================================


@epg_bp.route("/api/epg/match/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error matching channels to EPG")
def match_channels_to_epg(account_id):
    """Run automatic EPG matching for an account's channels

    DEPRECATED: This endpoint now redirects to the rule-based matching system.
    Use /api/epg/match-with-rules/<account_id> instead.

    Query parameters:
    - source_id: Optional EPG source to match against
    - category_id: Optional category to limit matching to
    - include_filtered: Include filtered out channels (default false)
    """
    # Redirect to the rule-based matching endpoint
    return match_channels_to_epg_with_rules(account_id)


@epg_bp.route("/api/epg/match-with-rules/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error matching channels to EPG with rules")
def match_channels_to_epg_with_rules(account_id):
    """Run EPG matching using configurable rulesets

    This uses the new rule-based matching system where matching rules are
    defined in the database and can be configured per-account.

    Query parameters:
    - source_id: Optional EPG source to match against
    - category_id: Optional category to limit matching to
    - include_filtered: Include filtered out channels (default false)
    """
    Account.query.get_or_404(account_id)

    source_id = request.args.get("source_id", type=int)
    category_id = request.args.get("category_id", type=int)
    include_filtered = request.args.get("include_filtered", "false").lower() == "true"

    stats = EpgMatchRulesService.match_channels_with_rules(
        account_id,
        source_id=source_id,
        category_id=category_id,
        include_filtered=include_filtered,
    )

    matched_count = stats.get("matched", 0)

    # Build informative message
    parts = [f"Matched {matched_count} channels"]
    if stats.get("skipped_existing", 0) > 0:
        parts.append(f"skipped {stats['skipped_existing']} already matched")
    if stats.get("excluded", 0) > 0:
        parts.append(f"excluded {stats['excluded']} channels")

    message = ", ".join(parts)

    return jsonify(
        {
            "success": True,
            "message": message,
            "stats": stats,
        }
    )


@epg_bp.route("/api/epg/mappings", methods=["GET"])
def get_epg_mappings():
    """Get EPG mappings with optional filtering

    Query parameters:
    - account_id: Filter by account
    - category_id: Filter by category (internal DB id)
    - view_mode: 'all', 'mapped', or 'unmapped' (default: 'all')
    - unmapped_only: (deprecated) Show only unmapped channels if true
    - show_filtered: Include channels that are filtered out (default: false)
    - limit: Max results
    - offset: Pagination offset
    """
    from models import Channel

    account_id = request.args.get("account_id", type=int)
    category_id = request.args.get("category_id", type=int)
    view_mode = request.args.get("view_mode", "all")
    # Support legacy unmapped_only parameter
    if request.args.get("unmapped_only", "false").lower() == "true":
        view_mode = "unmapped"
    show_filtered = request.args.get("show_filtered", "false").lower() == "true"
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if view_mode == "unmapped":
        # Get channels without mappings
        mapped_ids = db.session.query(ChannelEpgMapping.channel_id).distinct()

        query = Channel.query.filter(Channel.is_active == True, ~Channel.id.in_(mapped_ids))  # noqa: E712

        # By default, only show visible (non-filtered) channels
        if not show_filtered:
            query = query.filter(Channel.is_visible == True)  # noqa: E712

        if account_id:
            query = query.filter_by(account_id=account_id)

        if category_id:
            query = query.filter_by(category_id=category_id)

        total = query.count()
        channels = query.order_by(Channel.name).offset(offset).limit(limit).all()

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(channels) < total,
                "view_mode": view_mode,
                "unmapped_channels": [
                    {
                        "id": c.id,
                        "stream_id": c.stream_id,
                        "name": c.name,
                        "cleaned_name": c.cleaned_name,
                        "epg_channel_id": c.epg_channel_id,
                        "account_id": c.account_id,
                        "category_id": c.category_id,
                        "category_name": c.category.category_name if c.category else None,
                        "is_visible": c.is_visible,
                    }
                    for c in channels
                ],
            }
        )
    elif view_mode == "mapped":
        # Get mappings (existing behavior)
        query = db.session.query(ChannelEpgMapping).join(Channel, ChannelEpgMapping.channel_id == Channel.id)

        if account_id:
            query = query.filter(Channel.account_id == account_id)

        if category_id:
            query = query.filter(Channel.category_id == category_id)

        # By default, only show visible (non-filtered) channels
        if not show_filtered:
            query = query.filter(Channel.is_visible == True)  # noqa: E712

        total = query.count()
        mappings = query.offset(offset).limit(limit).all()

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(mappings) < total,
                "view_mode": view_mode,
                "mappings": [
                    {
                        "id": m.id,
                        "channel_id": m.channel_id,
                        "stream_id": m.channel.stream_id if m.channel else None,
                        "account_id": m.channel.account_id if m.channel else None,
                        "channel_name": m.channel.name if m.channel else None,
                        "cleaned_name": m.channel.cleaned_name if m.channel else None,
                        "epg_channel_id": m.epg_channel_id,
                        "epg_display_name": m.epg_channel.display_name if m.epg_channel else None,
                        "mapping_type": m.mapping_type,
                        "confidence": m.confidence,
                        "time_offset_hours": m.time_offset_hours or 0,
                        "is_override": m.is_override,
                        "is_visible": m.channel.is_visible if m.channel else True,
                    }
                    for m in mappings
                ],
            }
        )
    else:
        # view_mode == "all" - return all channels with mapping info if available
        query = Channel.query.filter(Channel.is_active == True)  # noqa: E712

        if not show_filtered:
            query = query.filter(Channel.is_visible == True)  # noqa: E712

        if account_id:
            query = query.filter_by(account_id=account_id)

        if category_id:
            query = query.filter_by(category_id=category_id)

        total = query.count()
        channels = query.order_by(Channel.name).offset(offset).limit(limit).all()

        # Get mappings for these channels in one query
        channel_ids = [c.id for c in channels]
        mappings_by_channel = {}
        if channel_ids:
            mappings = db.session.query(ChannelEpgMapping).filter(ChannelEpgMapping.channel_id.in_(channel_ids)).all()
            for m in mappings:
                mappings_by_channel[m.channel_id] = m

        return jsonify(
            {
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(channels) < total,
                "view_mode": view_mode,
                "channels": [
                    {
                        "id": c.id,
                        "stream_id": c.stream_id,
                        "name": c.name,
                        "cleaned_name": c.cleaned_name,
                        "epg_channel_id": c.epg_channel_id,
                        "account_id": c.account_id,
                        "category_id": c.category_id,
                        "category_name": c.category.category_name if c.category else None,
                        "is_visible": c.is_visible,
                        "mapping": {
                            "id": mappings_by_channel[c.id].id,
                            "epg_channel_id": mappings_by_channel[c.id].epg_channel_id,
                            "epg_display_name": (
                                mappings_by_channel[c.id].epg_channel.display_name
                                if mappings_by_channel[c.id].epg_channel
                                else None
                            ),
                            "mapping_type": mappings_by_channel[c.id].mapping_type,
                            "confidence": mappings_by_channel[c.id].confidence,
                            "time_offset_hours": mappings_by_channel[c.id].time_offset_hours or 0,
                            "is_override": mappings_by_channel[c.id].is_override,
                        }
                        if c.id in mappings_by_channel
                        else None,
                    }
                    for c in channels
                ],
            }
        )


@epg_bp.route("/api/epg/mappings", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG mapping")
def create_epg_mapping():
    """Create a manual EPG mapping"""
    from models import Channel

    data = request.json

    if not data.get("channel_id"):
        return jsonify({"error": "channel_id is required"}), 400
    if not data.get("epg_channel_id"):
        return jsonify({"error": "epg_channel_id is required"}), 400

    # Validate channel and EPG channel exist
    Channel.query.get_or_404(data["channel_id"])
    EpgChannel.query.get_or_404(data["epg_channel_id"])

    # Check for existing mapping
    existing = ChannelEpgMapping.query.filter_by(
        channel_id=data["channel_id"], epg_channel_id=data["epg_channel_id"]
    ).first()

    if existing:
        return jsonify({"error": "Mapping already exists", "mapping_id": existing.id}), 409

    # Get optional time offset (default 0)
    time_offset = data.get("time_offset_hours", 0)
    if not isinstance(time_offset, int):
        try:
            time_offset = int(time_offset)
        except (ValueError, TypeError):
            time_offset = 0

    mapping = ChannelEpgMapping(
        channel_id=data["channel_id"],
        epg_channel_id=data["epg_channel_id"],
        mapping_type="manual",
        confidence=1.0,
        time_offset_hours=time_offset,
        is_override=True,  # Manual mappings are always overrides
    )

    db.session.add(mapping)
    db.session.commit()

    return (
        jsonify(
            {
                "success": True,
                "mapping_id": mapping.id,
                "message": "EPG mapping created",
            }
        ),
        201,
    )


@epg_bp.route("/api/epg/mappings/<int:mapping_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG mapping")
def delete_epg_mapping(mapping_id):
    """Delete an EPG mapping"""
    mapping = ChannelEpgMapping.query.get_or_404(mapping_id)

    db.session.delete(mapping)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG mapping deleted"})


@epg_bp.route("/api/epg/mappings/bulk-delete", methods=["POST"])
@handle_errors(return_json=True, default_message="Error deleting EPG mappings")
def bulk_delete_epg_mappings():
    """Delete all EPG mappings for channels in a category

    Request body:
    - account_id: Required - the account ID
    - category_id: Required - the category ID to delete mappings for
    """
    from models import Channel

    data = request.get_json()
    account_id = data.get("account_id")
    category_id = data.get("category_id")

    if not account_id:
        return jsonify({"error": "account_id is required"}), 400
    if not category_id:
        return jsonify({"error": "category_id is required"}), 400

    # Get all channels in this category for the account
    channels = Channel.query.filter_by(account_id=account_id, category_id=category_id).all()

    channel_ids = [ch.id for ch in channels]

    if not channel_ids:
        return jsonify({"success": True, "deleted_count": 0, "message": "No channels found in category"})

    # Delete all mappings for these channels
    deleted_count = ChannelEpgMapping.query.filter(ChannelEpgMapping.channel_id.in_(channel_ids)).delete(
        synchronize_session=False
    )

    db.session.commit()

    return jsonify({"success": True, "deleted_count": deleted_count, "message": f"Deleted {deleted_count} mappings"})


# ============================================================================
# API Routes - EPG Coverage Stats
# ============================================================================


@epg_bp.route("/api/epg/coverage", methods=["GET"])
def get_epg_coverage():
    """Get overall EPG coverage statistics

    Query parameters:
    - account_id: Optional - filter to specific account
    """
    account_id = request.args.get("account_id", type=int)

    if account_id:
        Account.query.get_or_404(account_id)

    stats = EpgService.get_epg_coverage_stats(account_id)

    return jsonify(stats)


@epg_bp.route("/api/epg/coverage/categories/<int:account_id>", methods=["GET"])
def get_category_epg_coverage(account_id):
    """Get EPG coverage broken down by category for an account"""
    Account.query.get_or_404(account_id)

    coverage = EpgService.get_category_epg_coverage(account_id)

    return jsonify(
        {
            "account_id": account_id,
            "categories": coverage,
        }
    )


# ============================================================================
# API Routes - Provider EPG Source Helper
# ============================================================================


@epg_bp.route("/api/accounts/<int:account_id>/epg-source", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating provider EPG source")
def create_account_epg_source(account_id):
    """Create or get an EPG source for a provider account, then sync it"""
    Account.query.get_or_404(account_id)

    source = EpgService.create_provider_epg_source(account_id)

    # Optionally sync immediately
    if request.args.get("sync", "false").lower() == "true":
        account = source.account
        cred = account.get_primary_credential()
        if cred:
            service = IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
        else:
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )

        xml_content = service.get_xmltv()
        stats = EpgService.sync_epg_source(source, xml_content)

        return jsonify(
            {
                "success": True,
                "source_id": source.id,
                "message": f"EPG source created and synced ({stats['channels_added'] + stats['channels_updated']} channels)",
                "stats": stats,
            }
        )

    return jsonify(
        {
            "success": True,
            "source_id": source.id,
            "message": "EPG source created",
        }
    )


# ============================================================================
# API Routes - Schedules Direct Integration
# ============================================================================


@epg_bp.route("/api/epg/sd/test", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing Schedules Direct credentials")
def test_sd_credentials():
    """Test Schedules Direct credentials

    Request body:
        username: SD username
        password: SD password
    """
    data = request.json

    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    result = validate_credentials(data["username"], data["password"])

    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 401


@epg_bp.route("/api/epg/sd/lineups/search", methods=["GET"])
@handle_errors(return_json=True, default_message="Error searching Schedules Direct lineups")
def search_sd_lineups():
    """Search for Schedules Direct lineups by location

    Query parameters:
        source_id: EPG source ID with SD credentials
        country: ISO country code (default: USA)
        postalcode: Postal/ZIP code to search
    """
    source_id = request.args.get("source_id", type=int)
    country = request.args.get("country", "USA")
    postalcode = request.args.get("postalcode")

    if not source_id:
        return jsonify({"success": False, "error": "source_id is required"}), 400

    source = EpgSource.query.get_or_404(source_id)

    if source.source_type != "schedules_direct":
        return jsonify({"success": False, "error": "Source is not a Schedules Direct source"}), 400

    if not source.sd_username or not source.sd_password:
        return jsonify({"success": False, "error": "Source does not have SD credentials configured"}), 400

    try:
        client = SchedulesDirectClient(source.sd_username, source.sd_password)
        client.authenticate()

        lineups = client.search_lineups(country=country, postalcode=postalcode)

        return jsonify(
            {
                "success": True,
                "country": country,
                "postalcode": postalcode,
                "lineups": lineups,
                "count": len(lineups),
            }
        )

    except SchedulesDirectError as e:
        return jsonify({"success": False, "error": str(e), "code": e.code}), 400


@epg_bp.route("/api/epg/sd/lineups", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD lineups")
def get_sd_lineups():
    """Get Schedules Direct lineups for an EPG source

    Query parameters:
        source_id: EPG source ID

    Returns:
        JSON object with:
        - lineups: Array of lineup objects
        - account_lineups: Number of lineups on SD account (from API)
        - max_lineups: Maximum lineups allowed (typically 4)
    """
    source_id = request.args.get("source_id", type=int)

    if not source_id:
        return jsonify({"success": False, "error": "source_id is required"}), 400

    source = EpgSource.query.get_or_404(source_id)

    # Get lineups from database
    lineups = SdLineup.query.filter_by(epg_source_id=source_id).all()

    # Get account status to determine lineup limits
    account_lineups = 0
    max_lineups = 4  # SD default limit
    try:
        if source.sd_username and source.sd_password:
            client = SchedulesDirectClient(source.sd_username, source.sd_password)
            client.authenticate()
            status = client.get_status()
            account_lineups = len(status.get("lineups", []))
            account_info = status.get("account", {})
            max_lineups = account_info.get("maxLineups", 4)
    except Exception as e:
        logger.warning(f"Could not get SD account status: {e}")

    return jsonify(
        {
            "lineups": [
                {
                    "id": lineup.id,
                    "lineup_id": lineup.lineup_id,
                    "name": lineup.name,
                    "location": lineup.location,
                    "lineup_type": lineup.lineup_type,
                    "transport": lineup.transport,
                    "channel_count": lineup.channel_count,
                    "last_sync": lineup.last_sync.isoformat() if lineup.last_sync else None,
                }
                for lineup in lineups
            ],
            "account_lineups": account_lineups,
            "max_lineups": max_lineups,
        }
    )


@epg_bp.route("/api/epg/sd/lineups", methods=["POST"])
@handle_errors(return_json=True, default_message="Error adding SD lineup")
def add_sd_lineup():
    """Add a Schedules Direct lineup to an EPG source

    Request body:
        source_id: EPG source ID
        lineup_id: SD lineup ID (e.g., "USA-NY12345-X")
        name: Optional display name
        location: Optional location
        lineup_type: Optional type (Cable, Satellite, OTA)
    """
    data = request.json

    if not data.get("source_id") or not data.get("lineup_id"):
        return jsonify({"error": "source_id and lineup_id are required"}), 400

    source = EpgSource.query.get_or_404(data["source_id"])

    if source.source_type != "schedules_direct":
        return jsonify({"error": "Source is not a Schedules Direct source"}), 400

    # Check if lineup already exists in our database
    existing = SdLineup.query.filter_by(epg_source_id=source.id, lineup_id=data["lineup_id"]).first()

    if existing:
        return jsonify({"error": "Lineup already added to this source"}), 409

    # Check SD account lineup limit before adding
    try:
        if source.sd_username and source.sd_password:
            client = SchedulesDirectClient(source.sd_username, source.sd_password)
            client.authenticate()
            status = client.get_status()
            account_lineups = status.get("lineups", [])
            account_info = status.get("account", {})
            max_lineups = account_info.get("maxLineups", 4)

            # Check if lineup is already on the SD account
            account_lineup_ids = [lineup.get("lineup") for lineup in account_lineups]
            if data["lineup_id"] not in account_lineup_ids:
                # Need to add to SD account - check limit
                if len(account_lineups) >= max_lineups:
                    return (
                        jsonify(
                            {
                                "error": f"Schedules Direct account limit reached ({max_lineups} lineups). "
                                "Please remove a lineup before adding a new one.",
                                "limit_reached": True,
                                "current_count": len(account_lineups),
                                "max_lineups": max_lineups,
                            }
                        ),
                        400,
                    )
    except SchedulesDirectError as e:
        logger.warning(f"Could not check SD account limit: {e}")
        # Continue anyway - the add_lineup call will fail if at limit

    # Create lineup record
    lineup = SdLineup(
        epg_source_id=source.id,
        lineup_id=data["lineup_id"],
        name=data.get("name"),
        location=data.get("location"),
        lineup_type=data.get("lineup_type"),
        transport=data.get("transport"),
    )

    db.session.add(lineup)
    db.session.commit()

    # Optionally add to SD account and sync channels
    if request.args.get("sync", "false").lower() == "true":
        try:
            sync_result = sync_sd_lineup_impl(source, lineup)
            return jsonify(
                {
                    "success": True,
                    "lineup_id": lineup.id,
                    "message": f"Lineup added and synced ({sync_result['channels_synced']} channels)",
                    "sync_result": sync_result,
                }
            )
        except SchedulesDirectError as e:
            return jsonify(
                {
                    "success": True,
                    "lineup_id": lineup.id,
                    "message": "Lineup added but sync failed",
                    "sync_error": str(e),
                }
            )

    return (
        jsonify(
            {
                "success": True,
                "lineup_id": lineup.id,
                "message": "Lineup added successfully",
            }
        ),
        201,
    )


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing SD lineup")
def sync_sd_lineup(lineup_id):
    """Sync channels from a Schedules Direct lineup"""
    lineup = SdLineup.query.get_or_404(lineup_id)
    source = lineup.source

    if not source.sd_username or not source.sd_password:
        return jsonify({"error": "Source does not have SD credentials configured"}), 400

    try:
        result = sync_sd_lineup_impl(source, lineup)
        return jsonify(
            {
                "success": True,
                "message": f"Synced {result['channels_synced']} channels",
                **result,
            }
        )
    except SchedulesDirectError as e:
        return jsonify({"error": str(e), "code": e.code}), 400


def sync_sd_lineup_impl(source: EpgSource, lineup: SdLineup) -> dict:
    """Implementation of SD lineup sync"""
    from datetime import datetime

    client = SchedulesDirectClient(source.sd_username, source.sd_password)
    client.authenticate()

    # First, try to add the lineup to the SD account (if not already added)
    # This is required before we can fetch channel data
    try:
        client.add_lineup(lineup.lineup_id)
        logger.info(f"Added lineup {lineup.lineup_id} to SD account")
    except SchedulesDirectError as e:
        # Code 2100 = DUPLICATE_LINEUP means it's already added, which is fine
        if e.code != 2100:
            logger.warning(f"Could not add lineup to SD account: {e}")
            # Re-raise if it's a more serious error
            if e.code not in (2100, 2102):  # 2102 = UNKNOWN_LINEUP (might work anyway)
                raise

    # Get channels from SD
    channels = client.get_lineup_channels(lineup.lineup_id)

    channels_synced = 0
    channels_updated = 0

    for ch in channels:
        # Find or create station record
        station = SdStation.query.filter_by(lineup_id=lineup.id, station_id=ch["stationID"]).first()

        logo_url = ch.get("logo", {}).get("url") if ch.get("logo") else None
        broadcast_lang = json.dumps(ch.get("broadcastLanguage", []))

        if station:
            # Update existing
            station.channel_number = ch.get("channel")
            station.callsign = ch.get("callsign")
            station.name = ch.get("name")
            station.affiliate = ch.get("affiliate")
            station.broadcast_language = broadcast_lang
            station.logo_url = logo_url
            channels_updated += 1
        else:
            # Create new
            station = SdStation(
                lineup_id=lineup.id,
                station_id=ch["stationID"],
                channel_number=ch.get("channel"),
                callsign=ch.get("callsign"),
                name=ch.get("name"),
                affiliate=ch.get("affiliate"),
                broadcast_language=broadcast_lang,
                logo_url=logo_url,
            )
            db.session.add(station)
            channels_synced += 1

    # Update lineup stats
    lineup.channel_count = len(channels)
    lineup.last_sync = datetime.utcnow()

    db.session.commit()

    return {
        "channels_synced": channels_synced,
        "channels_updated": channels_updated,
        "total_channels": len(channels),
    }


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error removing SD lineup")
def remove_sd_lineup(lineup_id):
    """Remove a Schedules Direct lineup"""
    lineup = SdLineup.query.get_or_404(lineup_id)

    # Delete associated stations first (cascade should handle this, but being explicit)
    SdStation.query.filter_by(lineup_id=lineup_id).delete()

    db.session.delete(lineup)
    db.session.commit()

    return jsonify({"success": True, "message": "Lineup removed successfully"})


@epg_bp.route("/api/epg/sd/lineups/<int:lineup_id>/stations", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching SD stations")
def get_sd_lineup_stations(lineup_id):
    """Get stations in a Schedules Direct lineup

    Query parameters:
        search: Optional search term for name/callsign
    """
    lineup = SdLineup.query.get_or_404(lineup_id)

    search = request.args.get("search", "").strip()

    query = SdStation.query.filter_by(lineup_id=lineup_id)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                SdStation.callsign.ilike(search_term),
                SdStation.name.ilike(search_term),
            )
        )

    stations = query.order_by(SdStation.channel_number, SdStation.callsign).all()

    return jsonify(
        {
            "lineup_id": lineup.lineup_id,
            "lineup_name": lineup.name,
            "count": len(stations),
            "stations": [
                {
                    "id": s.id,
                    "station_id": s.station_id,
                    "channel_number": s.channel_number,
                    "callsign": s.callsign,
                    "name": s.name,
                    "affiliate": s.affiliate,
                    "logo_url": s.logo_url,
                }
                for s in stations
            ],
        }
    )


@epg_bp.route("/api/epg/sd/match/<int:account_id>", methods=["POST"])
@handle_errors(return_json=True, default_message="Error matching SD stations to channels")
def match_sd_stations(account_id):
    """Match Schedules Direct stations to IPTV channels

    This uses callsign and station name matching to find corresponding
    IPTV channels. It also handles XMLTV-style IDs (e.g., "ESPN.us" -> "ESPN").

    Request body:
        source_id: EPG source ID (required)
        lineup_id: SD lineup ID (optional - if not provided, uses all lineups)
        match_mode: 'exact', 'fuzzy', or 'all' (default: 'all')
        min_confidence: Minimum fuzzy match confidence (default: 0.8)
    """
    import re
    from difflib import SequenceMatcher

    from models import Channel

    def extract_callsign_from_xmltv_id(xmltv_id: str) -> str:
        """
        Extract callsign from XMLTV-style channel IDs.

        Examples:
            "ESPN.us" -> "ESPN"
            "AntennaTV.us" -> "AntennaTV"
            "I10021.json.schedulesdirect.org" -> "10021"
            "CNN" -> "CNN"
        """
        if not xmltv_id:
            return ""

        # Common patterns for XMLTV IDs:
        # 1. CALLSIGN.country (e.g., "ESPN.us", "BBC1.uk")
        # 2. I{station_id}.json.schedulesdirect.org (SD format)
        # 3. Just the callsign

        # Pattern: I{digits}.json.schedulesdirect.org
        sd_match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", xmltv_id, re.IGNORECASE)
        if sd_match:
            return sd_match.group(1)

        # Pattern: CALLSIGN.tld or CALLSIGN.country
        dot_match = re.match(r"^([A-Za-z0-9]+(?:[A-Za-z0-9-]*[A-Za-z0-9])?)\..*$", xmltv_id)
        if dot_match:
            return dot_match.group(1)

        return xmltv_id

    Account.query.get_or_404(account_id)
    data = request.json or {}

    source_id = data.get("source_id")
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400

    _source = EpgSource.query.get_or_404(source_id)  # noqa: F841 (validates source exists)
    lineup_id = data.get("lineup_id")
    match_mode = data.get("match_mode", "all")
    min_confidence = float(data.get("min_confidence", 0.8))

    # Get stations to match
    station_query = SdStation.query.join(SdLineup).filter(SdLineup.epg_source_id == source_id)
    if lineup_id:
        station_query = station_query.filter(SdStation.lineup_id == lineup_id)
    stations = station_query.all()

    # Get channels for this account
    channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

    # Build channel lookup structures
    # Include both exact name and extracted callsign from XMLTV ID
    channel_by_name_lower = {}
    channel_by_epg_id = {}
    channel_by_epg_callsign = {}  # Extracted callsign from XMLTV ID
    all_channels = []

    for ch in channels:
        name_lower = (ch.cleaned_name or ch.name).lower()
        channel_by_name_lower[name_lower] = ch

        if ch.epg_channel_id:
            epg_id_lower = ch.epg_channel_id.lower()
            channel_by_epg_id[epg_id_lower] = ch

            # Extract callsign from XMLTV-style ID
            extracted = extract_callsign_from_xmltv_id(ch.epg_channel_id)
            if extracted:
                channel_by_epg_callsign[extracted.lower()] = ch

        all_channels.append(
            {
                "channel": ch,
                "name_lower": name_lower,
                "name": ch.cleaned_name or ch.name,
                "epg_id": ch.epg_channel_id,
            }
        )

    matches = []
    unmatched_stations = []
    unmatched_channels = set(ch.id for ch in channels)

    for station in stations:
        match_found = False
        best_match = None
        best_confidence = 0
        match_type = None

        callsign = (station.callsign or "").strip()
        station_name = (station.name or "").strip()
        station_id = station.station_id  # Numeric SD station ID

        # Strategy 1: Exact callsign match against channel name
        if match_mode in ("exact", "all"):
            if callsign:
                callsign_lower = callsign.lower()

                # Check against channel names
                if callsign_lower in channel_by_name_lower:
                    best_match = channel_by_name_lower[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_name"
                    match_found = True

                # Check against EPG IDs (exact)
                elif callsign_lower in channel_by_epg_id:
                    best_match = channel_by_epg_id[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_epg_id"
                    match_found = True

                # Check against extracted callsigns from XMLTV IDs
                elif callsign_lower in channel_by_epg_callsign:
                    best_match = channel_by_epg_callsign[callsign_lower]
                    best_confidence = 1.0
                    match_type = "exact_callsign_to_xmltv"
                    match_found = True

        # Strategy 2: Match SD station ID to XMLTV ID containing it
        if not match_found and match_mode in ("exact", "all"):
            if station_id:
                # Check if any channel's XMLTV ID contains this station ID
                # e.g., "I10021.json.schedulesdirect.org" contains "10021"
                for ch_data in all_channels:
                    if ch_data["epg_id"] and station_id in ch_data["epg_id"]:
                        best_match = ch_data["channel"]
                        best_confidence = 1.0
                        match_type = "exact_station_id_in_xmltv"
                        match_found = True
                        break

        # Strategy 3: Exact station name match
        if not match_found and match_mode in ("exact", "all"):
            if station_name:
                name_lower = station_name.lower()
                if name_lower in channel_by_name_lower:
                    best_match = channel_by_name_lower[name_lower]
                    best_confidence = 1.0
                    match_type = "exact_name"
                    match_found = True

        # Strategy 4: Fuzzy matching
        if not match_found and match_mode in ("fuzzy", "all"):
            # Try fuzzy match against all channels
            search_terms = [callsign, station_name]
            search_terms = [t for t in search_terms if t]

            for term in search_terms:
                term_lower = term.lower()
                for ch_data in all_channels:
                    # Match against channel name
                    ratio = SequenceMatcher(None, term_lower, ch_data["name_lower"]).ratio()
                    if ratio >= min_confidence and ratio > best_confidence:
                        best_match = ch_data["channel"]
                        best_confidence = ratio
                        match_type = "fuzzy_name"
                        match_found = True

                    # Also match against extracted XMLTV callsign
                    if ch_data["epg_id"]:
                        extracted = extract_callsign_from_xmltv_id(ch_data["epg_id"])
                        if extracted:
                            ratio = SequenceMatcher(None, term_lower, extracted.lower()).ratio()
                            if ratio >= min_confidence and ratio > best_confidence:
                                best_match = ch_data["channel"]
                                best_confidence = ratio
                                match_type = "fuzzy_xmltv"
                                match_found = True

        if match_found and best_match:
            matches.append(
                {
                    "station_id": station.id,
                    "sd_station_id": station.station_id,
                    "station_callsign": station.callsign,
                    "station_name": station.name,
                    "channel_id": best_match.id,
                    "channel_name": best_match.cleaned_name or best_match.name,
                    "channel_epg_id": best_match.epg_channel_id,
                    "confidence": round(best_confidence, 3),
                    "match_type": match_type,
                }
            )
            unmatched_channels.discard(best_match.id)
        else:
            unmatched_stations.append(
                {
                    "station_id": station.id,
                    "sd_station_id": station.station_id,
                    "station_callsign": station.callsign,
                    "station_name": station.name,
                    "channel_number": station.channel_number,
                }
            )

    return jsonify(
        {
            "account_id": account_id,
            "source_id": source_id,
            "stats": {
                "total_stations": len(stations),
                "matched": len(matches),
                "unmatched_stations": len(unmatched_stations),
                "unmatched_channels": len(unmatched_channels),
            },
            "matches": matches,
            "unmatched_stations": unmatched_stations[:100],  # Limit for response size
        }
    )


@epg_bp.route("/api/epg/sd/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error checking SD status")
def get_sd_status():
    """Get Schedules Direct system status (no auth required)"""
    from services.schedules_direct import SchedulesDirectClient

    client = SchedulesDirectClient("", "")
    status = client.get_system_status()

    return jsonify(status)


# ============================================================================
# API Routes - XMLTV Grabbers
# ============================================================================


@epg_bp.route("/api/xmltv/grabbers", methods=["GET"])
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


@epg_bp.route("/api/xmltv/grabbers/<string:grabber_name>", methods=["GET"])
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


@epg_bp.route("/api/xmltv/grabbers/<string:grabber_name>/channels", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting grabber channels")
def get_xmltv_grabber_channels(grabber_name):
    """Get available channels from an XMLTV grabber"""
    from services.xmltv_grabber_service import XmltvGrabberService

    config_name = request.args.get("config_name")

    success, channels, error = XmltvGrabberService.get_grabber_channels(grabber_name, config_name)

    if not success:
        return jsonify({"error": error}), 500

    return jsonify({"channels": channels, "count": len(channels)})


@epg_bp.route("/api/xmltv/grabbers/<string:grabber_name>/test", methods=["POST"])
@handle_errors(return_json=True, default_message="Error testing grabber")
def test_xmltv_grabber(grabber_name):
    """Test an XMLTV grabber configuration"""
    from services.xmltv_grabber_service import XmltvGrabberService

    data = request.json or {}
    config_name = data.get("config_name")

    result = XmltvGrabberService.test_grabber(grabber_name, config_name)

    return jsonify(result)


@epg_bp.route("/api/xmltv/configs", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting grabber configs")
def get_xmltv_configs():
    """Get list of saved grabber configurations"""
    from services.xmltv_grabber_service import XmltvGrabberService

    grabber_name = request.args.get("grabber_name")

    configs = XmltvGrabberService.list_grabber_configs(grabber_name)

    return jsonify({"configs": configs, "count": len(configs)})


@epg_bp.route("/api/xmltv/configs/<string:config_name>", methods=["POST"])
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


@epg_bp.route("/api/xmltv/configs/<string:config_name>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting grabber config")
def delete_xmltv_config(config_name):
    """Delete a grabber configuration"""
    from services.xmltv_grabber_service import XmltvGrabberService

    success, message = XmltvGrabberService.delete_grabber_config(config_name)

    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 404
