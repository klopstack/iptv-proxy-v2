"""
EPG channel management routes - channels, matching, mappings, and programs
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Channel, ChannelEpgMapping, EpgChannel, EpgSource, Event, EventChannelLink, db
from services.epg_match_rules_service import EpgMatchRulesService
from services.epg import EpgService
from services.channel_query_service import ChannelQueryService
from services.iptv_service import IPTVService

logger = logging.getLogger(__name__)

# Create blueprints
epg_channels_bp = Blueprint("epg_channels", __name__, url_prefix="/api/epg")
account_epg_channels_bp = Blueprint("account_epg_channels", __name__)


# ============================================================================
# API Routes - EPG Channels
# ============================================================================


@epg_channels_bp.route("/channels", methods=["GET"])
def get_epg_channels():
    """Get list of EPG channels from a source

    Query parameters:
    - source_id: Optional - EPG source to get channels from (if not provided, returns all channels)
    - lineup_id: Optional - Filter by SD lineup (only for Schedules Direct sources)
    - search: Optional text search
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    from models import SdStation

    source_id = request.args.get("source_id", type=int)
    lineup_id = request.args.get("lineup_id", type=int)
    search = request.args.get("search", "")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if source_id:
        EpgSource.query.get_or_404(source_id)
        query = EpgChannel.query.filter_by(source_id=source_id)
    else:
        query = EpgChannel.query

    # Filter by lineup if specified (for Schedules Direct sources)
    if lineup_id:
        # Join with SdStation to filter by lineup
        # For SD sources, EpgChannel.channel_id == SdStation.station_id
        query = query.join(
            SdStation, db.and_(SdStation.station_id == EpgChannel.channel_id, SdStation.lineup_id == lineup_id)
        )

    # Apply search if provided
    if search:
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


@epg_channels_bp.route("/match/<int:account_id>", methods=["POST"])
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


@epg_channels_bp.route("/match-with-rules/<int:account_id>", methods=["POST"])
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


# ============================================================================
# API Routes - EPG Mappings CRUD
# ============================================================================


@epg_channels_bp.route("/mappings", methods=["GET"])
def get_epg_mappings():
    """Get EPG mappings with optional filtering.

    When show_filtered is false and account_id is set, only playlist-visible
    channels are returned (account filters plus PPV visibility), matching M3U output.
    Set show_filtered=true to include all synced channels for admin mapping work.

    Query parameters:
    - account_id: Filter by account
    - category_id: Filter by category (internal DB id)
    - epg_source_id: Filter by EPG source (only affects 'mapped' view_mode)
    - view_mode: 'all', 'mapped', or 'unmapped' (default: 'all')
    - unmapped_only: (deprecated) Show only unmapped channels if true
    - show_filtered: Include channels hidden from playlists (default: false)
    - limit: Max results
    - offset: Pagination offset
    """
    account_id = request.args.get("account_id", type=int)
    category_id = request.args.get("category_id", type=int)
    epg_source_id = request.args.get("epg_source_id", type=int)
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

        if account_id:
            query = query.filter_by(account_id=account_id)

        if category_id:
            query = query.filter_by(category_id=category_id)

        all_channels = query.order_by(Channel.name).all()

        if not show_filtered and account_id:
            channels = ChannelQueryService.channels_for_account_candidates(account_id, all_channels)
        else:
            channels = all_channels

        total = len(channels)
        channels = channels[offset : offset + limit]

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
        # Check if filtering by a PPV events source
        is_ppv_source = False
        if epg_source_id:
            epg_source = db.session.get(EpgSource, epg_source_id)
            is_ppv_source = epg_source and epg_source.source_type == "ppv_events"

        all_mappings = []

        if is_ppv_source:
            # For PPV events, get channels linked via EventChannelLink
            query = (
                db.session.query(EventChannelLink)
                .join(Channel, EventChannelLink.channel_id == Channel.id)
                .join(Event, EventChannelLink.event_id == Event.id)
                .filter(Event.is_ppv == True)  # noqa: E712
            )

            if account_id:
                query = query.filter(Channel.account_id == account_id)

            if category_id:
                query = query.filter(Channel.category_id == category_id)

            event_links = query.all()

            # Build mapping-like objects from event links for consistency with frontend
            for link in event_links:
                if link.channel and link.event:
                    # Create a pseudo-mapping object
                    class PseudoMapping:
                        def __init__(self, link):
                            self.id = f"ppv_{link.id}"
                            self.channel_id = link.channel_id
                            self.channel = link.channel
                            self.epg_channel_id = f"ppv-event-{link.event.external_id}"
                            self.mapping_type = "ppv_event"
                            self.confidence = link.match_confidence or 1.0
                            self.time_offset_hours = 0
                            self.is_override = False
                            # Store event info for display
                            self.event = link.event
                            self.epg_channel = type(
                                "EpgChannel",
                                (),
                                {
                                    "display_name": f"{link.event.home_team_name} vs {link.event.away_team_name}",
                                    "id": None,
                                },
                            )()

                    all_mappings.append(PseudoMapping(link))
        else:
            # Regular EPG mappings
            query = db.session.query(ChannelEpgMapping).join(Channel, ChannelEpgMapping.channel_id == Channel.id)

            # Filter by EPG source if specified
            if epg_source_id:
                query = query.join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id).filter(
                    EpgChannel.source_id == epg_source_id
                )

            if account_id:
                query = query.filter(Channel.account_id == account_id)

            if category_id:
                query = query.filter(Channel.category_id == category_id)

            all_mappings = query.all()

        if not show_filtered and account_id:
            channels = [m.channel for m in all_mappings if m.channel]
            visible_channels = ChannelQueryService.channels_for_account_candidates(
                account_id, channels
            )
            visible_ids = {ch.id for ch in visible_channels}
            mappings = [m for m in all_mappings if m.channel and m.channel.id in visible_ids]
        else:
            mappings = all_mappings

        total = len(mappings)
        mappings = mappings[offset : offset + limit]

        # Get current programs for mapped EPG channels
        from services.epg.programs import get_current_programs_batch

        epg_channel_ids = [
            m.epg_channel_id
            for m in mappings
            if hasattr(m, "epg_channel_id") and m.epg_channel_id and not isinstance(m.epg_channel_id, str)
        ]
        current_programs = get_current_programs_batch(epg_channel_ids) if epg_channel_ids else {}

        def get_current_program(mapping):
            """Get current program info for a mapping."""
            if not hasattr(mapping, "epg_channel_id") or isinstance(mapping.epg_channel_id, str):
                return None
            prog = current_programs.get(mapping.epg_channel_id)
            return prog.to_dict() if prog and hasattr(prog, "to_dict") else prog

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
                        "source_name": m.epg_channel.source.name if m.epg_channel and m.epg_channel.source else None,
                        "mapping_type": m.mapping_type,
                        "confidence": m.confidence,
                        "time_offset_hours": m.time_offset_hours or 0,
                        "is_override": m.is_override,
                        "is_visible": m.channel.is_visible if m.channel else True,
                        "current_program": get_current_program(m),
                    }
                    for m in mappings
                ],
            }
        )
    else:
        # view_mode == "all" - return all channels with mapping info if available
        # Check if filtering by a PPV events source
        is_ppv_source = False
        if epg_source_id:
            epg_source = db.session.get(EpgSource, epg_source_id)
            is_ppv_source = epg_source and epg_source.source_type == "ppv_events"

        query = Channel.query.filter(Channel.is_active == True)  # noqa: E712

        if account_id:
            query = query.filter_by(account_id=account_id)

        if category_id:
            query = query.filter_by(category_id=category_id)

        # If filtering by PPV source, only show channels with PPV event links
        if is_ppv_source:
            ppv_channel_ids = (
                db.session.query(EventChannelLink.channel_id)
                .join(Event, EventChannelLink.event_id == Event.id)
                .filter(Event.is_ppv == True)  # noqa: E712
                .distinct()
            )
            query = query.filter(Channel.id.in_(ppv_channel_ids))

        all_channels = query.order_by(Channel.name).all()

        if not show_filtered and account_id:
            channels = ChannelQueryService.channels_for_account_candidates(account_id, all_channels)
        else:
            channels = all_channels

        total = len(channels)
        channels = channels[offset : offset + limit]

        # Get mappings for these channels
        channel_ids = [c.id for c in channels]
        mappings_by_channel = {}
        ppv_mappings_by_channel = {}

        if channel_ids:
            # Get regular EPG mappings
            if not is_ppv_source or epg_source_id is None:
                # If not filtering by EPG source or not PPV, get regular mappings
                mappings = (
                    db.session.query(ChannelEpgMapping).filter(ChannelEpgMapping.channel_id.in_(channel_ids)).all()
                )
                for m in mappings:
                    # If filtering by specific EPG source, only include matching mappings
                    if epg_source_id and m.epg_channel and m.epg_channel.source_id != epg_source_id:
                        continue
                    mappings_by_channel[m.channel_id] = m

            # Get PPV event links if filtering by PPV source or if no EPG source filter
            if is_ppv_source or epg_source_id is None:
                event_links = (
                    db.session.query(EventChannelLink)
                    .join(Event, EventChannelLink.event_id == Event.id)
                    .filter(EventChannelLink.channel_id.in_(channel_ids), Event.is_ppv == True)  # noqa: E712
                    .all()
                )
                for link in event_links:
                    if link.event:
                        ppv_mappings_by_channel[link.channel_id] = {
                            "id": f"ppv_{link.id}",
                            "epg_channel_id": f"ppv-event-{link.event.external_id}",
                            "epg_display_name": f"{link.event.home_team_name} vs {link.event.away_team_name}",
                            "mapping_type": "ppv_event",
                            "confidence": link.match_confidence or 1.0,
                            "time_offset_hours": 0,
                            "is_override": False,
                        }

        # Get current programs for channels with mappings
        from services.epg.programs import get_current_programs_batch

        epg_channel_ids_for_programs = [m.epg_channel_id for m in mappings_by_channel.values() if m.epg_channel_id]
        current_programs_map = (
            get_current_programs_batch(epg_channel_ids_for_programs) if epg_channel_ids_for_programs else {}
        )

        def get_current_program_for_channel(channel_id):
            """Get current program info for a channel's EPG mapping."""
            if channel_id in mappings_by_channel:
                mapping = mappings_by_channel[channel_id]
                if mapping.epg_channel_id in current_programs_map:
                    prog = current_programs_map[mapping.epg_channel_id]
                    return prog.to_dict() if hasattr(prog, "to_dict") else prog
            return None

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
                        "mapping": (
                            # Prefer PPV mapping if filtering by PPV source, otherwise prefer regular mapping
                            ppv_mappings_by_channel.get(c.id)
                            if is_ppv_source and c.id in ppv_mappings_by_channel
                            else (
                                {
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
                                else ppv_mappings_by_channel.get(c.id)
                            )
                        ),
                        "current_program": get_current_program_for_channel(c.id),
                    }
                    for c in channels
                ],
            }
        )


@epg_channels_bp.route("/mappings", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating EPG mapping")
def create_epg_mapping():
    """Create a manual EPG mapping"""
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


@epg_channels_bp.route("/mappings/<int:mapping_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting EPG mapping")
def delete_epg_mapping(mapping_id):
    """Delete an EPG mapping"""
    mapping = ChannelEpgMapping.query.get_or_404(mapping_id)

    db.session.delete(mapping)
    db.session.commit()

    return jsonify({"success": True, "message": "EPG mapping deleted"})


@epg_channels_bp.route("/mappings/<int:mapping_id>", methods=["PUT"])
@handle_errors(return_json=True, default_message="Error updating EPG mapping")
def update_epg_mapping(mapping_id):
    """Update an existing EPG mapping

    Request body:
    - epg_channel_id: Optional - new EPG channel ID
    - time_offset_hours: Optional - time offset in hours
    """
    mapping = ChannelEpgMapping.query.get_or_404(mapping_id)
    data = request.get_json()

    if "epg_channel_id" in data:
        new_epg_channel_id = data["epg_channel_id"]
        # Verify the new EPG channel exists
        epg_channel = EpgChannel.query.get(new_epg_channel_id)
        if not epg_channel:
            return jsonify({"error": "EPG channel not found"}), 404
        mapping.epg_channel_id = new_epg_channel_id

    if "time_offset_hours" in data:
        mapping.time_offset_hours = data["time_offset_hours"]

    # Update match type to manual since user is editing
    mapping.match_type = "manual"
    mapping.confidence_score = 100

    db.session.commit()

    # Get EPG channel details for response
    epg_channel = EpgChannel.query.get(mapping.epg_channel_id)

    return jsonify(
        {
            "success": True,
            "message": "EPG mapping updated",
            "mapping_id": mapping.id,
            "epg_channel_id": mapping.epg_channel_id,
            "epg_display_name": epg_channel.display_name if epg_channel else None,
            "time_offset_hours": mapping.time_offset_hours,
        }
    )


@epg_channels_bp.route("/mappings/bulk-delete", methods=["POST"])
@handle_errors(return_json=True, default_message="Error deleting EPG mappings")
def bulk_delete_epg_mappings():
    """Delete all EPG mappings for channels in a category

    Request body:
    - account_id: Required - the account ID
    - category_id: Required - the category ID to delete mappings for
    """
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
# API Routes - Provider EPG Source Helper
# ============================================================================


@account_epg_channels_bp.route("/api/accounts/<int:account_id>/epg-source", methods=["POST"])
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
# API Routes - EPG Programs
# ============================================================================


@epg_channels_bp.route("/programs/current", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting current programs")
def get_current_programs():
    """Get currently airing programs for specified EPG channels.

    Query parameters:
    - epg_channel_ids: Comma-separated list of EPG channel IDs
    - source_id: Optional EPG source ID to get all current programs from

    Returns a mapping of epg_channel_id -> program info
    """
    from services.epg.programs import get_current_programs_batch

    epg_channel_ids_param = request.args.get("epg_channel_ids", "")
    source_id = request.args.get("source_id", type=int)

    epg_channel_ids = []

    if epg_channel_ids_param:
        try:
            epg_channel_ids = [int(x.strip()) for x in epg_channel_ids_param.split(",") if x.strip()]
        except ValueError:
            return jsonify({"error": "Invalid epg_channel_ids format"}), 400
    elif source_id:
        # Get all EPG channel IDs for this source
        channels = EpgChannel.query.filter_by(source_id=source_id).all()
        epg_channel_ids = [c.id for c in channels]

    if not epg_channel_ids:
        return jsonify({"programs": {}})

    programs = get_current_programs_batch(epg_channel_ids)

    return jsonify({"programs": {epg_id: prog.to_dict() for epg_id, prog in programs.items()}})


@epg_channels_bp.route("/programs/search", methods=["GET"])
@handle_errors(return_json=True, default_message="Error searching programs")
def search_programs():
    """Search EPG programs by title.

    Query parameters:
    - q: Search query (required)
    - source_id: Optional EPG source ID to limit search
    - current_only: If 'true', only return currently airing programs
    - limit: Max results (default 100)

    Returns list of programs with their EPG channel info.
    Used for matching channels by searching for what's currently playing.
    """
    from services.epg.programs import search_programs_by_title

    query = request.args.get("q", "").strip()
    source_id = request.args.get("source_id", type=int)
    current_only = request.args.get("current_only", "false").lower() == "true"
    limit = request.args.get("limit", 100, type=int)

    if not query:
        return jsonify({"error": "Search query 'q' is required"}), 400

    if len(query) < 2:
        return jsonify({"error": "Search query must be at least 2 characters"}), 400

    results = search_programs_by_title(
        title_query=query,
        source_id=source_id,
        include_current_only=current_only,
        limit=limit,
    )

    return jsonify(
        {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "program": prog.to_dict(),
                    "epg_channel": {
                        "id": epg_channel.id,
                        "source_id": epg_channel.source_id,
                        "channel_id": epg_channel.channel_id,
                        "display_name": epg_channel.display_name,
                        "icon_url": epg_channel.icon_url,
                    },
                }
                for prog, epg_channel in results
            ],
        }
    )


@epg_channels_bp.route("/programs/<int:epg_channel_id>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting programs")
def get_epg_channel_programs(epg_channel_id):
    """Get programs for a specific EPG channel.

    Query parameters:
    - hours: Number of hours to look ahead (default 24)
    - limit: Max programs to return (default 20)
    - include_current: Include currently airing program (default true)

    Returns the current program (if any) and list of upcoming programs.
    """
    from services.epg.programs import get_current_program, get_upcoming_programs

    # Validate EPG channel exists
    EpgChannel.query.get_or_404(epg_channel_id)

    hours = request.args.get("hours", 24, type=int)
    limit = request.args.get("limit", 20, type=int)
    include_current = request.args.get("include_current", "true").lower() == "true"

    result = {
        "epg_channel_id": epg_channel_id,
        "current_program": None,
        "upcoming_programs": [],
    }

    if include_current:
        current = get_current_program(epg_channel_id)
        if current:
            result["current_program"] = current.to_dict()

    upcoming = get_upcoming_programs(epg_channel_id, hours=hours, limit=limit)
    result["upcoming_programs"] = [p.to_dict() for p in upcoming]

    return jsonify(result)


@epg_channels_bp.route("/programs/<int:epg_channel_id>/schedule", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting program schedule")
def get_epg_channel_schedule(epg_channel_id):
    """Get program schedule around a reference time with optional offset.

    This endpoint is useful for displaying the schedule when adjusting
    time offsets in the manual mapping modal, showing what's on before
    and after the "current" program based on the offset.

    Query parameters:
    - offset_hours: Time offset in hours (default 0)
    - hours_before: Hours of past programs to include (default 2)
    - hours_after: Hours of future programs to include (default 4)

    Returns current program, programs_before, and programs_after based on
    the adjusted time (now + offset_hours).
    """
    from services.epg.programs import get_schedule_around_time

    # Validate EPG channel exists
    EpgChannel.query.get_or_404(epg_channel_id)

    offset_hours = request.args.get("offset_hours", 0, type=int)
    hours_before = request.args.get("hours_before", 2, type=int)
    hours_after = request.args.get("hours_after", 4, type=int)

    schedule = get_schedule_around_time(
        epg_channel_id=epg_channel_id,
        offset_hours=offset_hours,
        hours_before=hours_before,
        hours_after=hours_after,
    )

    return jsonify(schedule)


@epg_channels_bp.route("/mappings-with-programs", methods=["GET"])
@handle_errors(return_json=True, default_message="Error getting mappings with programs")
def get_mappings_with_current_programs():
    """Get EPG mappings with current program information.

    When show_filtered is false, only playlist-visible channels are returned
    (account filters plus PPV visibility), matching M3U output.

    Query parameters:
    - account_id: Filter by account (required)
    - category_id: Filter by category
    - view_mode: 'all', 'mapped', or 'unmapped' (default: 'all')
    - show_filtered: Include channels hidden from playlists (default: false)
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    from services.epg.programs import get_current_programs_batch

    account_id = request.args.get("account_id", type=int)
    category_id = request.args.get("category_id", type=int)
    view_mode = request.args.get("view_mode", "all")
    show_filtered = request.args.get("show_filtered", "false").lower() == "true"
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    # Build base query for channels with mappings
    query = (
        db.session.query(Channel, ChannelEpgMapping, EpgChannel)
        .outerjoin(ChannelEpgMapping, Channel.id == ChannelEpgMapping.channel_id)
        .outerjoin(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .filter(Channel.account_id == account_id, Channel.is_active == True)  # noqa: E712
    )

    if category_id:
        query = query.filter(Channel.category_id == category_id)

    if view_mode == "mapped":
        query = query.filter(ChannelEpgMapping.id != None)  # noqa: E711
    elif view_mode == "unmapped":
        query = query.filter(ChannelEpgMapping.id == None)  # noqa: E711

    results = query.order_by(Channel.name).all()

    if not show_filtered:
        channels = [r[0] for r in results]
        visible_channels = ChannelQueryService.channels_for_account_candidates(
            account_id, channels
        )
        visible_ids = {ch.id for ch in visible_channels}
        results = [r for r in results if r[0].id in visible_ids]

    total = len(results)
    results = results[offset : offset + limit]

    # Get current programs for all mapped EPG channels
    epg_channel_ids = [r[2].id for r in results if r[2] is not None]
    current_programs = get_current_programs_batch(epg_channel_ids) if epg_channel_ids else {}

    # Build response
    response_data = []
    for channel, mapping, epg_channel in results:
        item = {
            "channel": {
                "id": channel.id,
                "stream_id": channel.stream_id,
                "name": channel.name,
                "cleaned_name": channel.cleaned_name,
                "category_id": channel.category_id,
                "category_name": channel.category.category_name if channel.category else None,
                "is_visible": channel.is_visible,
                "stream_icon": channel.stream_icon,
            },
            "mapping": None,
            "epg_channel": None,
            "current_program": None,
        }

        if mapping and epg_channel:
            item["mapping"] = {
                "id": mapping.id,
                "mapping_type": mapping.mapping_type,
                "confidence": mapping.confidence,
                "time_offset_hours": mapping.time_offset_hours or 0,
                "is_override": mapping.is_override,
            }
            item["epg_channel"] = {
                "id": epg_channel.id,
                "channel_id": epg_channel.channel_id,
                "display_name": epg_channel.display_name,
                "icon_url": epg_channel.icon_url,
                "source_id": epg_channel.source_id,
            }

            # Add current program if available
            current_prog = current_programs.get(epg_channel.id)
            if current_prog:
                item["current_program"] = current_prog.to_dict()

        response_data.append(item)

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(response_data) < total,
            "view_mode": view_mode,
            "data": response_data,
        }
    )
