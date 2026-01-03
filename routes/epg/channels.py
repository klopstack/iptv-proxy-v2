"""
EPG channel management routes - channels, matching, and mappings
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from services.epg_match_rules_service import EpgMatchRulesService
from services.epg_service import EpgService
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
    - search: Optional text search
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    source_id = request.args.get("source_id", type=int)
    search = request.args.get("search", "")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    if source_id:
        EpgSource.query.get_or_404(source_id)
        query = EpgChannel.query.filter_by(source_id=source_id)
    else:
        query = EpgChannel.query

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
    """Get EPG mappings with optional filtering

    Query parameters:
    - account_id: Filter by account
    - category_id: Filter by category (internal DB id)
    - epg_source_id: Filter by EPG source (only affects 'mapped' view_mode)
    - view_mode: 'all', 'mapped', or 'unmapped' (default: 'all')
    - unmapped_only: (deprecated) Show only unmapped channels if true
    - show_filtered: Include channels that are filtered out (default: false)
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

        # Filter by EPG source if specified
        if epg_source_id:
            query = query.join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id).filter(
                EpgChannel.source_id == epg_source_id
            )

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
