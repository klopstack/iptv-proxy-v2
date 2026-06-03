"""
Account management routes
"""
import logging

from flask import Blueprint, jsonify, request

from api_responses import data_response, success_response
from error_handling import handle_errors
from models import Account, Channel, ChannelTag, Credential, Filter, Tag, db
from schemas import (
    AccountCreateSchema,
    AccountUpdateSchema,
    CredentialCreateSchema,
    CredentialUpdateSchema,
    validate_request_data,
)
from services.account_admin_service import AccountAdminService
from services.account_epg_source_service import (
    find_account_xmltv_epg_source,
    normalize_account_server,
    serialize_account_xmltv_epg_source,
    upsert_account_xmltv_epg_source,
)
from services.cache_service import cache_service
from services.channel_query_service import ChannelQueryService
from services.connection_manager import ConnectionManager
from services.datetime_utils import DEFAULT_DISPLAY_TIMEZONE, serialize_utc_iso
from services.serializers.credentials import serialize_credential
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
accounts_bp = Blueprint("accounts", __name__)


# ============================================================================
# API Routes - Account CRUD
# ============================================================================


@accounts_bp.route("/api/accounts", methods=["GET"])
def get_accounts():
    """Get all accounts with credential info"""
    return data_response(AccountAdminService.list_accounts_data())


@accounts_bp.route("/api/accounts", methods=["POST"])
@validate_request_data(AccountCreateSchema)
def create_account():
    """Create new account with initial credential"""
    data = request.validated_data

    account = Account(
        name=data["name"],
        server=normalize_account_server(data["server"]),
        user_agent=data.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ),
        enabled=data.get("enabled", True),
    )

    db.session.add(account)
    db.session.flush()  # Get the account ID

    # Create initial credential
    credential = Credential(
        account_id=account.id,
        username=data["username"],
        password=data["password"],
        max_connections=1,
        enabled=True,
    )
    db.session.add(credential)
    db.session.commit()

    xmltv_epg_source = None
    if data.get("create_xmltv_epg_source"):
        try:
            source, _created = upsert_account_xmltv_epg_source(account, credential)
            db.session.commit()
            xmltv_epg_source = serialize_account_xmltv_epg_source(source)
        except ValueError as e:
            logger.warning("Could not create XMLTV EPG source for account %s: %s", account.id, e)

    return success_response(
        {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "username": credential.username,
            "user_agent": account.user_agent,
            "enabled": account.enabled,
            "credentials": [serialize_credential(credential)],
            "total_max_connections": account.get_total_max_connections(),
            "xmltv_epg_source": xmltv_epg_source,
        },
        status_code=201,
    )


@accounts_bp.route("/api/accounts/<int:account_id>", methods=["PUT"])
@validate_request_data(AccountUpdateSchema)
def update_account(account_id):
    """Update account"""
    account = Account.query.get_or_404(account_id)
    data = request.validated_data

    account.name = data.get("name", account.name)
    if "server" in data:
        account.server = normalize_account_server(data["server"])
    # Account username/password live on credentials; update the primary credential if requested.
    if account.credentials and ("username" in data or "password" in data):
        cred = account.credentials[0]
        if "username" in data:
            cred.username = data["username"]
        if "password" in data:
            cred.password = data["password"]
    if "user_agent" in data:
        account.user_agent = data["user_agent"]
    account.enabled = data.get("enabled", account.enabled)

    should_update_xmltv = data.get("update_xmltv_epg_source") or data.get("create_xmltv_epg_source")
    cred_fields_changed = "username" in data or "password" in data or "server" in data or "name" in data
    existing_xmltv = find_account_xmltv_epg_source(account_id)

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    xmltv_epg_source = serialize_account_xmltv_epg_source(existing_xmltv)
    if should_update_xmltv or (existing_xmltv and cred_fields_changed):
        try:
            source, _created = upsert_account_xmltv_epg_source(account)
            db.session.commit()
            xmltv_epg_source = serialize_account_xmltv_epg_source(source)
        except ValueError as e:
            logger.warning("Could not update XMLTV EPG source for account %s: %s", account_id, e)

    return success_response(
        {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "username": account.credentials[0].username if account.credentials else None,
            "user_agent": account.user_agent,
            "enabled": account.enabled,
            "xmltv_epg_source": xmltv_epg_source,
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>/ppv-visibility", methods=["PUT"])
def update_ppv_visibility(account_id):
    """Update PPV visibility preference for an account

    Request body:
    {
        "ppv_visibility": "hide_all" | "hide_inactive" | "group_live_replay" | "show_all"
    }
    """
    account = Account.query.get_or_404(account_id)
    data = request.get_json()

    ppv_visibility = data.get("ppv_visibility", "hide_inactive")

    # Validate the value
    from services.ppv.visibility import PPVVisibilityService

    if ppv_visibility not in PPVVisibilityService.VALID_MODES:
        return (
            jsonify({"error": f"Invalid ppv_visibility mode. Must be one of: {PPVVisibilityService.VALID_MODES}"}),
            400,
        )

    account.ppv_visibility = ppv_visibility
    db.session.commit()

    return jsonify({"id": account.id, "ppv_visibility": account.ppv_visibility})


@accounts_bp.route("/api/ppv-visibility-options", methods=["GET"])
def get_ppv_visibility_options():
    """Get available PPV visibility options"""
    from services.ppv.visibility import PPVVisibilityService

    options = PPVVisibilityService.get_visibility_options()
    return jsonify(options)


@accounts_bp.route("/api/accounts/<int:account_id>/ppv-rename-format", methods=["PUT"])
def update_ppv_rename_format(account_id):
    """Update the PPV channel rename format template for an account.

    Request body:
    {
        "ppv_rename_format": "{league} {sport}: {home_team} vs {away_team} - {start_time} {date}",
        "ppv_rename_timezone": "America/New_York"
    }

    Set format to null or empty string to disable.
    Supported tokens: {league}, {sport}, {home_team}, {away_team}, {start_time}, {date}
    {start_time} and {date} are rendered in ppv_rename_timezone (default: America/New_York).
    """
    from zoneinfo import ZoneInfo

    account = Account.query.get_or_404(account_id)
    data = request.get_json() or {}

    if "ppv_rename_format" in data:
        fmt = data.get("ppv_rename_format")
        account.ppv_rename_format = fmt if fmt else None

    if "ppv_rename_timezone" in data:
        tz = (data.get("ppv_rename_timezone") or "").strip()
        if tz:
            try:
                ZoneInfo(tz)
            except Exception:
                return jsonify({"error": f"Invalid timezone: {tz}"}), 400
            account.ppv_rename_timezone = tz
        else:
            account.ppv_rename_timezone = None

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify(
        {
            "id": account.id,
            "ppv_rename_format": account.ppv_rename_format,
            "ppv_rename_timezone": account.ppv_rename_timezone or DEFAULT_DISPLAY_TIMEZONE,
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>/fcc-rename-format", methods=["PUT"])
def update_fcc_rename_format(account_id):
    """Update the FCC-matched channel rename format template for an account.

    Request body:
    {
        "fcc_rename_format": "{network} {callsign} {broadcast_channel} - {market}"
    }

    Set to null or empty string to disable.
    Supported tokens: {network}, {callsign}, {broadcast_channel}, {market}
    """
    account = Account.query.get_or_404(account_id)
    data = request.get_json()

    fmt = data.get("fcc_rename_format")
    account.fcc_rename_format = fmt if fmt else None
    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify({"id": account.id, "fcc_rename_format": account.fcc_rename_format})


@accounts_bp.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete account and all associated data"""
    Account.query.get_or_404(account_id)

    cache_service.clear_account_cache(account_id)

    from services.account_delete_service import AccountDeleteService

    result = AccountDeleteService.delete_account(account_id)
    if not result.get("success"):
        return jsonify(result), 404

    return "", 204


@accounts_bp.route("/api/accounts/<int:account_id>/test", methods=["POST"])
def test_account(account_id):
    """Test account connection - tests all credentials and updates their info"""
    account = Account.query.get_or_404(account_id)
    payload, error, status = AccountAdminService.test_account_connection(account)
    if error:
        return jsonify({"success": False, "error": error}), status
    return jsonify(payload), status


@accounts_bp.route("/api/accounts/<int:account_id>/categories", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching account categories")
def get_account_categories(account_id):
    """Return cached or DB-backed upstream-style category list (idempotent GET).

    For upstream refresh and tag extraction, use POST .../categories/sync.
    Distinct from GET /api/categories (DB browse with counts) and
    GET /api/channel-health/categories (health filter dropdown).
    """
    Account.query.get_or_404(account_id)
    return jsonify(AccountAdminService.get_categories_payload(account_id))


@accounts_bp.route("/api/accounts/<int:account_id>/categories/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing account categories")
def sync_account_categories(account_id):
    """Fetch categories from upstream IPTV, update cache, and process extraction tags."""
    account = Account.query.get_or_404(account_id)
    return jsonify(AccountAdminService.sync_categories(account))


@accounts_bp.route("/api/accounts/<int:account_id>/stats", methods=["GET"])
def get_account_stats(account_id):
    """Get statistics for account (uses database if synced, otherwise API).

    visible_channels / hidden_channels use playlist-visible semantics (account
    filters plus PPV visibility), matching M3U/EPG/Xtream output.
    """
    account = Account.query.get_or_404(account_id)
    stats, error = AccountAdminService.get_account_stats(account)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(stats)


@accounts_bp.route("/api/accounts/<int:account_id>/filters", methods=["GET"])
def get_account_filters(account_id):
    """Get filters for a specific account"""
    # Note: Doesn't validate account exists - returns empty list if no account
    filters = Filter.query.filter_by(account_id=account_id).all()
    return data_response(
        [
            {
                "id": f.id,
                "account_id": f.account_id,
                "name": f.name,
                "filter_type": f.filter_type,
                "filter_action": f.filter_action,
                "filter_value": f.filter_value,
                "enabled": f.enabled,
            }
            for f in filters
        ]
    )


# ============================================================================
# API Routes - Account Sync
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/sync", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing account channels")
def sync_account_channels(account_id):
    """Sync channels for a specific account"""
    from services.sync_service import ChannelSyncService

    Account.query.get_or_404(account_id)  # Validate account exists

    stats = ChannelSyncService.sync_account(account_id)

    # If sync is already in progress, return 409 Conflict
    if not stats.get("success") and "already in progress" in stats.get("error", "").lower():
        return jsonify(stats), 409

    return jsonify(stats)


@accounts_bp.route("/api/accounts/<int:account_id>/sync/status", methods=["GET"])
def get_sync_status(account_id):
    """Get sync status for an account"""
    Account.query.get_or_404(account_id)  # Validate account exists

    # Get channel count and last sync time from database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()

    account = db.session.get(Account, account_id)
    last_sync = account.updated_at if account else None

    return jsonify(
        {
            "account_id": account_id,
            "channel_count": channel_count,
            "last_sync": serialize_utc_iso(last_sync),
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>/recompute-visibility", methods=["POST"])
@handle_errors()
def recompute_visibility(account_id):
    """Manually trigger visibility recomputation for an account

    Recalculates which channels are visible based on the account's enabled filters.
    Useful after changing filters to immediately see the effect without a full sync.
    """
    account = Account.query.get_or_404(account_id)

    if not account.enabled:
        return jsonify({"success": False, "error": "Account is disabled"}), 403

    # Recompute visibility
    from services.filter_service import FilterService

    result = FilterService.compute_visibility_for_account(account_id)

    if not result.get("success"):
        return jsonify({"success": False, "error": result.get("error", "Unknown error")}), 500

    logger.info(
        f"Manual visibility recompute for account {account.name} ({account_id}): "
        f"{result['channels_visible']} visible, {result['channels_hidden']} hidden"
    )

    return jsonify(
        {
            "success": True,
            "account_id": account_id,
            "account_name": account.name,
            "channels_visible": result.get("channels_visible", 0),
            "channels_hidden": result.get("channels_hidden", 0),
        }
    )


# ============================================================================
# API Routes - Account Tags
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/process-tags", methods=["POST"])
def process_account_tags(account_id):
    """Process tags for an account's channels"""

    # Use the service method for tag processing
    result = TagService.process_account_tags(account_id)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        # Return 503 for any condition where processing can't happen
        # (account not found, not synced, etc.)
        status_code = 503 if any(x in error.lower() for x in ["not synced", "not found"]) else 400
        return jsonify({"success": False, "error": error}), status_code

    # Recompute filter visibility since tags changed
    from services.filter_service import FilterService

    filter_stats = FilterService.compute_visibility_for_account(account_id)

    # Add filter visibility to response
    result["channels_visible"] = filter_stats.get("channels_visible", 0)
    result["channels_hidden"] = filter_stats.get("channels_hidden", 0)
    result["using_database"] = True

    return jsonify(result)


@accounts_bp.route("/api/accounts/<int:account_id>/tags", methods=["GET"])
def get_account_tags(account_id):
    """Get all tags for an account's channels"""
    Account.query.get_or_404(account_id)  # Validate account exists

    # Query tags with their channel counts
    from sqlalchemy import func

    results = (
        db.session.query(Tag.id, Tag.name, func.count(ChannelTag.id).label("channel_count"))
        .join(ChannelTag, Tag.id == ChannelTag.tag_id)
        .filter(ChannelTag.account_id == account_id)
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
        .all()
    )

    return jsonify([{"id": r.id, "name": r.name, "channel_count": r.channel_count} for r in results])


@accounts_bp.route("/api/accounts/<int:account_id>/tags/search", methods=["GET"])
def search_account_tags(account_id):
    """Search tags for an account by name (autocomplete endpoint)"""
    Account.query.get_or_404(account_id)  # Validate account exists

    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)

    # Query tags matching the search term
    from sqlalchemy import func

    search_pattern = f"%{query}%" if query else "%"

    results = (
        db.session.query(Tag.id, Tag.name, func.count(ChannelTag.id).label("channel_count"))
        .join(ChannelTag, Tag.id == ChannelTag.tag_id)
        .filter(ChannelTag.account_id == account_id, Tag.name.ilike(search_pattern))
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
        .limit(limit)
        .all()
    )

    return jsonify([{"id": r.id, "name": r.name, "channel_count": r.channel_count} for r in results])


# ============================================================================
# API Routes - Account Rulesets
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/rulesets", methods=["GET"])
def get_account_rulesets(account_id):
    """Get rulesets assigned to an account"""
    from models import AccountRuleSet, RuleSet

    Account.query.get_or_404(account_id)  # Validate account exists

    assignments = (
        db.session.query(RuleSet, AccountRuleSet.priority)
        .join(AccountRuleSet, RuleSet.id == AccountRuleSet.ruleset_id)
        .filter(AccountRuleSet.account_id == account_id)
        .order_by(AccountRuleSet.priority)
        .all()
    )

    return jsonify(
        [
            {
                "id": rs.id,
                "name": rs.name,
                "description": rs.description,
                "is_default": rs.is_default,
                "enabled": rs.enabled,
                "priority": priority,
                "rule_count": len(rs.rules),
            }
            for rs, priority in assignments
        ]
    )


@accounts_bp.route("/api/accounts/<int:account_id>/rulesets", methods=["POST"])
def assign_ruleset_to_account(account_id):
    """Assign a ruleset to an account"""
    from models import AccountRuleSet

    Account.query.get_or_404(account_id)  # Validate account exists
    data = request.json

    ruleset_id = data["ruleset_id"]
    priority = data.get("priority", 100)

    # Check if already assigned
    existing = AccountRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).first()

    if existing:
        # Update priority
        existing.priority = priority
    else:
        # Create new assignment
        assignment = AccountRuleSet(account_id=account_id, ruleset_id=ruleset_id, priority=priority)
        db.session.add(assignment)

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify({"success": True}), 201


@accounts_bp.route("/api/accounts/<int:account_id>/rulesets/<int:ruleset_id>", methods=["DELETE"])
def remove_ruleset_from_account(account_id, ruleset_id):
    """Remove a ruleset assignment from an account"""
    from models import AccountRuleSet

    Account.query.get_or_404(account_id)  # Validate account exists

    AccountRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).delete()

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return "", 204


# ============================================================================
# API Routes - Channel Details
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/channels/<stream_id>", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching channel details")
def get_channel_details(account_id, stream_id):
    """
    Get full details for a specific channel.

    Returns all available information about a channel including:
    - Basic info (name, cleaned_name, category, icon)
    - Stream info (stream_id, stream_type, epg_channel_id)
    - Archive info (tv_archive, tv_archive_duration)
    - Tags associated with the channel
    - Metadata (added date, last_seen, created_at, updated_at)
    """
    account = Account.query.get_or_404(account_id)

    # Get channel by stream_id
    channel = Channel.query.filter_by(account_id=account_id, stream_id=str(stream_id)).first_or_404()

    # Get tags for this channel with source info
    channel_tags = (
        db.session.query(Tag.name, ChannelTag.source)
        .join(ChannelTag, ChannelTag.tag_id == Tag.id)
        .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id == str(stream_id))
        .all()
    )
    tags = [{"name": t[0], "source": t[1]} for t in channel_tags]

    # Build complete channel data
    return jsonify(
        {
            "id": channel.id,
            "account_id": channel.account_id,
            "account_name": account.name,
            "stream_id": channel.stream_id,
            "name": channel.name,
            "cleaned_name": channel.cleaned_name,
            "category": channel.category.cleaned_name or channel.category.category_name
            if channel.category
            else "Uncategorized",
            "category_id": channel.category_id,
            "stream_type": channel.stream_type,
            "stream_icon": channel.stream_icon,
            "epg_channel_id": channel.epg_channel_id,
            "added": channel.added,
            "custom_sid": channel.custom_sid,
            "tv_archive": channel.tv_archive,
            "tv_archive_duration": channel.tv_archive_duration,
            "direct_source": channel.direct_source,
            "is_active": channel.is_active,
            "is_visible": channel.is_visible,
            "tags": tags,
            "last_seen": serialize_utc_iso(channel.last_seen),
            "created_at": serialize_utc_iso(channel.created_at),
            "updated_at": serialize_utc_iso(channel.updated_at),
        }
    )


# ============================================================================
# API Routes - Account Preview
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/preview", methods=["GET"])
@handle_errors(return_json=True, default_message="Error generating preview playlist")
def preview_account_playlist(account_id):
    """
    Preview filtered channels for an account.

    Query Parameters:
    - limit: Number of channels to return (default: 50)
    - offset: Number of channels to skip (default: 0)
    - tags: Comma-separated list of tag names to filter by
    - category: Category name to filter by
    - search: Full-text search term for channel name/cleaned name
    - collapse_duplicates: If "true", collapse duplicate channels keeping highest quality

    Preview applies the same account filters and PPV visibility rules as M3U output.
    Search, category, and tag query params are additional preview-only narrowing filters.

    Returns:
    - JSON with total count, channel data, and using_database flag
    """
    Account.query.get_or_404(account_id)

    # Parse tag filter
    tags_param = request.args.get("tags", "")
    filter_tags = [t.strip() for t in tags_param.split(",") if t.strip()] if tags_param else []
    # Normalize for case-insensitive matching
    filter_tags = TagService.normalize_filter_tags(filter_tags)

    # Parse category filter
    category_filter = request.args.get("category", "")

    # Parse search filter
    search_term = request.args.get("search", "").strip()

    # Parse collapse_duplicates option
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if account has been synced (database-first approach)
    # Only count ACTIVE channels
    has_synced = (
        db.session.query(Channel.id).filter(Channel.account_id == account_id, Channel.is_active).first() is not None
    )

    if not has_synced:
        return jsonify({"success": False, "error": "Account not synced. Please sync the account first."}), 503

    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    base_query = ChannelQueryService.build_preview_channel_query(
        account_id=account_id,
        category=category_filter,
        search=search_term,
        filter_tags=filter_tags,
    )

    if collapse_duplicates:
        # For duplicate collapsing, load all matching channels first.
        all_channels = base_query.all()
        all_channels = ChannelQueryService.channels_for_account_candidates(account_id, all_channels)

        tags_map = ChannelQueryService.load_tags_for_account_channels(account_id, all_channels)

        # Initialize image cache for proxying icons
        from services.image_cache_service import ImageCacheService

        image_cache = ImageCacheService.get_instance()
        proxy_base = f"{request.scheme}://{request.host}"

        # Build channel dictionaries for collapsing
        channel_dicts = [
            {
                "id": ch.id,
                "stream_id": ch.stream_id,
                "account_id": ch.account_id,
                "name": ch.name,
                "cleaned_name": ch.cleaned_name if ch.cleaned_name is not None else ch.name,
                "category": ch.category.cleaned_name or ch.category.category_name if ch.category else "Uncategorized",
                "category_id": ch.category_id,
                "icon": image_cache.get_proxy_url(ch.stream_icon, proxy_base) if ch.stream_icon else None,
                "is_visible": True,
                "playlist_visible": True,
                "tags": tags_map.get(ch.stream_id, []),
            }
            for ch in all_channels
        ]

        # Collapse duplicates
        from services.quality_service import QualityService

        collapsed_channels = QualityService.collapse_duplicates(channel_dicts)

        # Get total after collapsing
        total = len(collapsed_channels)

        # Apply pagination to collapsed results
        paginated_channels = collapsed_channels[offset : offset + limit]

        return jsonify(
            {
                "total": total,
                "showing": len(paginated_channels),
                "has_more": (offset + len(paginated_channels)) < total,
                "channels": paginated_channels,
                "using_database": True,
                "filter_tags": filter_tags,
                "collapse_duplicates": True,
                "duplicates_collapsed": len(all_channels) - total,
            }
        )
    else:
        channels, total = ChannelQueryService.preview_channels_for_account(
            account_id,
            category=category_filter,
            search=search_term,
            filter_tags=filter_tags,
            limit=limit,
            offset=offset,
        )

        tags_map = ChannelQueryService.load_tags_for_account_channels(account_id, channels)

        # Initialize image cache for proxying icons
        from services.image_cache_service import ImageCacheService

        image_cache = ImageCacheService.get_instance()
        proxy_base = f"{request.scheme}://{request.host}"

        return jsonify(
            {
                "total": total,
                "showing": len(channels),
                "has_more": (offset + len(channels)) < total,
                "channels": [
                    {
                        "id": ch.id,
                        "stream_id": ch.stream_id,
                        "account_id": ch.account_id,
                        "name": ch.name,
                        "cleaned_name": ch.cleaned_name if ch.cleaned_name is not None else ch.name,
                        "category": ch.category.cleaned_name or ch.category.category_name
                        if ch.category
                        else "Uncategorized",
                        "category_id": ch.category_id,
                        "icon": image_cache.get_proxy_url(ch.stream_icon, proxy_base) if ch.stream_icon else None,
                        "is_visible": True,  # Legacy field; all channels here are playlist-visible
                        "playlist_visible": True,
                        "tags": tags_map.get(ch.stream_id, []),
                    }
                    for ch in channels
                ],
                "using_database": True,
                "filter_tags": filter_tags,
                "collapse_duplicates": False,
            }
        )


@accounts_bp.route("/api/accounts/<int:account_id>/preview-channels", methods=["POST"])
@handle_errors()
def preview_filter_matches(account_id):
    """
    Preview how many channels would match a filter.
    Used to provide feedback when creating filters.
    """
    account = Account.query.get_or_404(account_id)
    data = request.get_json() or {}
    payload, error, status = AccountAdminService.preview_filter_matches(
        account,
        data.get("filter_type"),
        (data.get("filter_value") or "").strip(),
    )
    if error:
        return jsonify({"success": False, "error": error}), status
    return jsonify(payload)


@accounts_bp.route("/api/tags/cleanup-orphans", methods=["POST"])
@handle_errors()
def cleanup_orphan_tags():
    """
    Delete tags that have no associated channels in any account.
    This cleans up tags that were created but are no longer used.
    """
    return jsonify(AccountAdminService.cleanup_orphan_tags())


# ============================================================================
# API Routes - Credential Management
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/credentials", methods=["GET"])
def get_credentials(account_id):
    """Get all credentials for an account"""
    account = Account.query.get_or_404(account_id)
    return jsonify(AccountAdminService.get_credentials(account))


@accounts_bp.route("/api/accounts/<int:account_id>/credentials", methods=["POST"])
@validate_request_data(CredentialCreateSchema)
def add_credential(account_id):
    """Add a new credential to an account"""
    account = Account.query.get_or_404(account_id)
    data = request.validated_data

    result, error = AccountAdminService.add_credential(account, data)
    if error:
        return jsonify({"error": error}), 400

    return jsonify(result), 201


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>", methods=["PUT"])
@validate_request_data(CredentialUpdateSchema, partial=True)
def update_credential(account_id, cred_id):
    """Update a credential"""
    Account.query.get_or_404(account_id)  # Validate account exists
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    data = request.validated_data
    return jsonify(AccountAdminService.update_credential(account_id, credential, data))


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>", methods=["DELETE"])
def delete_credential(account_id, cred_id):
    """Delete a credential"""
    account = Account.query.get_or_404(account_id)
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    error = AccountAdminService.delete_credential(account, credential)
    if error:
        return jsonify({"error": error}), 400

    return "", 204


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>/test", methods=["POST"])
def test_credential(account_id, cred_id):
    """Test a specific credential and update its info"""
    account = Account.query.get_or_404(account_id)
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    result, error = AccountAdminService.test_credential(account, credential)
    if error:
        return jsonify({"success": False, "error": error}), 400

    return jsonify(result)


@accounts_bp.route("/api/accounts/<int:account_id>/connection-status", methods=["GET"])
def get_account_connection_status(account_id):
    """Get connection status for an account (active streams, available slots)"""
    Account.query.get_or_404(account_id)  # Validate account exists
    return jsonify(ConnectionManager.get_connection_status(account_id))


@accounts_bp.route("/api/accounts/<int:account_id>/xmltv-epg-source", methods=["GET"])
def get_account_xmltv_epg_source(account_id):
    """Get the linked XMLTV EPG source for this account, if configured."""
    Account.query.get_or_404(account_id)
    source = find_account_xmltv_epg_source(account_id)
    return jsonify({"xmltv_epg_source": serialize_account_xmltv_epg_source(source)})


@accounts_bp.route("/api/accounts/<int:account_id>/xmltv-epg-source", methods=["POST"])
@handle_errors(return_json=True, default_message="Error updating account XMLTV EPG source")
def upsert_account_xmltv_epg_source_route(account_id):
    """
    Create or refresh the xmltv_url EPG source for this account.

    Rebuilds the xmltv.php URL from the account server and primary credential.
    Optional query param sync=true runs an EPG sync after upsert.
    """
    account = Account.query.get_or_404(account_id)
    source, created = upsert_account_xmltv_epg_source(account)
    db.session.commit()

    sync_requested = request.args.get("sync", "false").lower() == "true"
    sync_result = None
    if sync_requested:
        from services.epg_sync_service import EpgSyncService

        success, message, stats = EpgSyncService.sync_xmltv_url_source(source)
        EpgSyncService.update_source_sync_status(source, success, message, stats)
        sync_result = {"success": success, "message": message, "stats": stats}

    return jsonify(
        {
            "success": True,
            "created": created,
            "xmltv_epg_source": serialize_account_xmltv_epg_source(source),
            "sync": sync_result,
        }
    )
