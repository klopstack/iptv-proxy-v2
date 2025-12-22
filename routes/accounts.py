"""
Account management routes
"""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Category, Channel, ChannelTag, Credential, Filter, Tag, db
from schemas import AccountCreateSchema, AccountUpdateSchema, validate_request_data
from services.cache_service import CacheService
from services.connection_manager import ConnectionManager
from services.iptv_service import IPTVService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
accounts_bp = Blueprint("accounts", __name__)

# Initialize cache service
cache_service = CacheService()


def credential_to_dict(cred):
    """Convert a Credential to a dictionary."""
    return {
        "id": cred.id,
        "username": cred.username,
        "max_connections": cred.max_connections or 1,
        "active_connections": cred.active_connections or 0,
        "status": cred.status,
        "exp_date": cred.exp_date,
        "enabled": cred.enabled,
    }


def get_iptv_service_for_account(account):
    """Create an IPTVService instance for an account using the best available credential."""
    cred = account.get_primary_credential()
    if cred:
        return IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
    # Fallback for legacy accounts
    return IPTVService(account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9")


# ============================================================================
# API Routes - Account CRUD
# ============================================================================


@accounts_bp.route("/api/accounts", methods=["GET"])
def get_accounts():
    """Get all accounts with credential info"""
    accounts = Account.query.all()
    result = []
    for a in accounts:
        account_data = {
            "id": a.id,
            "name": a.name,
            "server": a.server,
            "enabled": a.enabled,
            "credentials": [credential_to_dict(c) for c in a.credentials],
            "total_max_connections": a.get_total_max_connections(),
        }
        # Include legacy username for backward compatibility
        if a.credentials:
            account_data["username"] = a.credentials[0].username
        else:
            account_data["username"] = a.username
        result.append(account_data)
    return jsonify(result)


@accounts_bp.route("/api/accounts", methods=["POST"])
@validate_request_data(AccountCreateSchema)
def create_account():
    """Create new account with initial credential"""
    data = request.validated_data

    account = Account(
        name=data["name"],
        server=data["server"],
        # Store in legacy fields for backward compatibility
        username=data["username"],
        password=data["password"],
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

    return (
        jsonify(
            {
                "id": account.id,
                "name": account.name,
                "server": account.server,
                "username": account.username,
                "user_agent": account.user_agent,
                "enabled": account.enabled,
                "credentials": [credential_to_dict(credential)],
                "total_max_connections": account.get_total_max_connections(),
            }
        ),
        201,
    )


@accounts_bp.route("/api/accounts/<int:account_id>", methods=["PUT"])
@validate_request_data(AccountUpdateSchema)
def update_account(account_id):
    """Update account"""
    account = Account.query.get_or_404(account_id)
    data = request.validated_data

    account.name = data.get("name", account.name)
    account.server = data.get("server", account.server)
    account.username = data.get("username", account.username)
    if "password" in data:
        account.password = data["password"]
    if "user_agent" in data:
        account.user_agent = data["user_agent"]
    account.enabled = data.get("enabled", account.enabled)

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify(
        {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "username": account.username,
            "user_agent": account.user_agent,
            "enabled": account.enabled,
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete account and all associated data"""
    account = Account.query.get_or_404(account_id)

    # Clear cache first
    cache_service.clear_account_cache(account_id)

    # Delete account (cascade will handle filters, channels, credentials, etc.)
    db.session.delete(account)
    db.session.commit()

    return "", 204


@accounts_bp.route("/api/accounts/<int:account_id>/test", methods=["POST"])
def test_account(account_id):
    """Test account connection - tests all credentials and updates their info"""
    account = Account.query.get_or_404(account_id)

    # Get credentials to test
    credentials = account.credentials if account.credentials else []

    # If no credentials, test using legacy fields
    if not credentials and account.username and account.password:
        try:
            service = IPTVService(
                account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
            )
            auth_info = service.authenticate()
            streams = service.get_live_streams()
            categories = service.get_live_categories()

            return jsonify(
                {
                    "success": True,
                    "channels": len(streams),
                    "categories": len(categories),
                    "server_info": {
                        "url": auth_info.get("server_info", {}).get("url", ""),
                        "time": auth_info.get("server_info", {}).get("time_now", ""),
                    },
                    "user_info": {
                        "username": auth_info.get("user_info", {}).get("username", ""),
                        "status": auth_info.get("user_info", {}).get("status", ""),
                        "exp_date": auth_info.get("user_info", {}).get("exp_date", ""),
                        "max_connections": auth_info.get("user_info", {}).get("max_connections", "1"),
                    },
                    "credentials": [],
                    "legacy_mode": True,
                }
            )
        except Exception as e:
            logger.error(f"Error testing account {account_id}: {e}")
            return jsonify({"success": False, "error": str(e)}), 400

    # Test each credential
    credential_results = []
    total_channels = 0
    total_categories = 0
    first_error = None

    for cred in credentials:
        try:
            service = IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
            auth_info = service.authenticate()

            # Get channel/category counts only from first credential (they're the same)
            if not total_channels:
                streams = service.get_live_streams()
                categories = service.get_live_categories()
                total_channels = len(streams)
                total_categories = len(categories)

            # Update credential with info from auth response
            user_info = auth_info.get("user_info", {})
            cred.max_connections = int(user_info.get("max_connections", 1) or 1)
            cred.status = user_info.get("status", "Unknown")
            cred.exp_date = user_info.get("exp_date", "")
            db.session.commit()

            credential_results.append(
                {
                    "id": cred.id,
                    "username": cred.username,
                    "success": True,
                    "status": cred.status,
                    "exp_date": cred.exp_date,
                    "max_connections": cred.max_connections,
                }
            )
        except Exception as e:
            logger.error(f"Error testing credential {cred.id} for account {account_id}: {e}")
            if not first_error:
                first_error = str(e)
            credential_results.append(
                {
                    "id": cred.id,
                    "username": cred.username,
                    "success": False,
                    "error": str(e),
                }
            )

    # Calculate totals
    total_max_connections = sum(c.get("max_connections", 1) for c in credential_results if c.get("success"))

    # If all credentials failed, return error
    if all(not c.get("success") for c in credential_results):
        return (
            jsonify(
                {
                    "success": False,
                    "error": first_error or "All credentials failed",
                    "credentials": credential_results,
                }
            ),
            400,
        )

    return jsonify(
        {
            "success": True,
            "channels": total_channels,
            "categories": total_categories,
            "total_max_connections": total_max_connections,
            "credentials": credential_results,
            "connection_status": ConnectionManager.get_connection_status(account_id),
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>/categories", methods=["GET"])
def get_account_categories(account_id):
    """Get categories for account"""
    account = Account.query.get_or_404(account_id)

    try:
        service = get_iptv_service_for_account(account)
        categories = service.get_live_categories()

        # Cache it
        cache_service.cache_categories(account_id, categories)

        # Trigger tag processing in background if streams are cached
        streams = cache_service.get_cached_streams(account_id)
        if streams:
            try:
                _process_tags_for_account(account_id, streams, categories)
            except Exception as tag_error:
                logger.warning(f"Error auto-processing tags for account {account_id}: {tag_error}")

        return jsonify(categories)
    except Exception as e:
        logger.error(f"Error fetching categories for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 400


def _process_tags_for_account(account_id, streams, categories):
    """Helper function to process tags for an account (internal use)"""
    account = db.session.get(Account, account_id)
    if not account:
        return

    # Build category map
    category_map = {str(c["category_id"]): c["category_name"] for c in categories}

    # Get tag rules for this account
    tag_rules = TagService.get_rules_for_account(account)

    # Clear existing channel tags for this account
    ChannelTag.query.filter_by(account_id=account_id).delete()

    # Process each stream
    for stream in streams:
        stream_id = str(stream.get("stream_id"))
        channel_name = stream.get("name", "")
        category_id = str(stream.get("category_id", ""))
        category_name = category_map.get(category_id, "")

        # Extract tags
        tags, cleaned_name = TagService.extract_tags(channel_name, category_name, tag_rules)

        # Store tags
        for tag_name in tags:
            normalized_tag = TagService.normalize_tag_name(tag_name)

            # Skip empty or too-short tags
            if not normalized_tag or len(normalized_tag) < 2:
                continue

            # Get or create tag
            tag = Tag.query.filter_by(name=normalized_tag).first()
            if not tag:
                tag = Tag(name=normalized_tag)
                db.session.add(tag)
                db.session.flush()

            # Create channel tag association
            channel_tag = ChannelTag(account_id=account_id, stream_id=stream_id, tag_id=tag.id)
            db.session.add(channel_tag)

    db.session.commit()
    logger.info(f"Auto-processed tags for account {account_id}")


@accounts_bp.route("/api/accounts/<int:account_id>/stats", methods=["GET"])
def get_account_stats(account_id):
    """Get statistics for account (uses database if synced, otherwise API)"""
    account = Account.query.get_or_404(account_id)

    # Check if account is synced to database
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()

    if channel_count > 0:
        # Use database stats (fast!)
        category_count = db.session.query(Category.id).filter_by(account_id=account_id).count()

        # Get visible/hidden counts
        visible_count = Channel.query.filter_by(account_id=account_id, is_active=True, is_visible=True).count()
        hidden_count = channel_count - visible_count

        # Get category distribution
        category_counts = {}
        category_data = (
            db.session.query(Category.category_id, db.func.count(Channel.id))
            .join(Channel, Channel.category_id == Category.id)
            .filter(Channel.account_id == account_id, Channel.is_active)
            .group_by(Category.category_id)
            .all()
        )
        for cat_id, count in category_data:
            category_counts[str(cat_id)] = count

        return jsonify(
            {
                "total_channels": channel_count,
                "visible_channels": visible_count,
                "hidden_channels": hidden_count,
                "total_categories": category_count,
                "category_counts": category_counts,
                "using_database": True,
                "synced": True,
                "last_sync": account.updated_at.isoformat() if account.updated_at else None,
            }
        )

    # Fallback to API call if not synced
    try:
        service = get_iptv_service_for_account(account)

        # Get cached or fetch new
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)

        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)

        # Count by category
        category_counts = {}
        for stream in streams:
            cat_id = str(stream.get("category_id", "Unknown"))
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

        return jsonify(
            {
                "total_channels": len(streams),
                "total_categories": len(categories),
                "category_counts": category_counts,
                "using_database": False,
                "synced": False,
                "last_sync": None,
            }
        )
    except Exception as e:
        logger.error(f"Error fetching stats for account {account_id}: {e}")
        return jsonify({"error": str(e)}), 400


@accounts_bp.route("/api/accounts/<int:account_id>/filters", methods=["GET"])
def get_account_filters(account_id):
    """Get filters for a specific account"""
    # Note: Doesn't validate account exists - returns empty list if no account
    filters = Filter.query.filter_by(account_id=account_id).all()
    return jsonify(
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
            "last_sync": last_sync.isoformat() if last_sync else None,
        }
    )


# ============================================================================
# API Routes - Account Tags
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/process-tags", methods=["POST"])
def process_account_tags(account_id):
    """Process tags for an account's channels"""

    account = db.session.get(Account, account_id)

    # Check if channels are synced to database
    db_channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

    if not db_channels:
        return jsonify({"success": False, "error": "Account not synced. Please sync channels first."}), 503

    # Mark start time for this processing run (use utcnow to match model defaults)
    processing_start = datetime.utcnow()

    # Get tag rules for this account
    tag_rules = TagService.get_rules_for_account(account)

    # Build lookup of existing channel tags for efficient updates
    existing_tags = {}
    for ct in ChannelTag.query.filter_by(account_id=account.id).all():
        key = (ct.stream_id, ct.tag_id)
        existing_tags[key] = ct

    # Process each channel
    processed_count = 0
    tag_counts = {}
    tags_created = 0
    tags_updated = 0
    channels_updated = 0

    for channel in db_channels:
        category_name = channel.category.category_name if channel.category else ""

        # Extract tags and cleaned name
        tags, cleaned_name = TagService.extract_tags(channel.name, category_name, tag_rules)

        # Update cleaned name in database if changed
        if channel.cleaned_name != cleaned_name:
            channel.cleaned_name = cleaned_name
            channel.updated_at = processing_start
            channels_updated += 1

        # Store tags
        for tag_name in tags:
            # Normalize tag name
            normalized_tag = TagService.normalize_tag_name(tag_name)

            # Skip empty or too-short tags
            if not normalized_tag or len(normalized_tag) < 2:
                continue

            # Get or create tag
            tag = Tag.query.filter_by(name=normalized_tag).first()
            if not tag:
                tag = Tag(name=normalized_tag)
                db.session.add(tag)
                db.session.flush()  # Get the ID

            # Check if channel tag association exists
            key = (channel.stream_id, tag.id)
            if key in existing_tags:
                # Update existing - mark as fresh
                existing_tags[key].updated_at = processing_start
                tags_updated += 1
            else:
                # Create new channel tag association
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=channel.stream_id,
                    tag_id=tag.id,
                    created_at=processing_start,
                    updated_at=processing_start,
                )
                db.session.add(channel_tag)
                tags_created += 1

            # Count tags
            tag_counts[normalized_tag] = tag_counts.get(normalized_tag, 0) + 1

        processed_count += 1

    # Remove channel tags that weren't updated in this processing run
    stale_tags = ChannelTag.query.filter(ChannelTag.account_id == account.id, ChannelTag.updated_at < processing_start)
    tags_removed = stale_tags.delete()

    db.session.commit()

    # Recompute filter visibility since tags changed
    from services.filter_service import FilterService

    filter_stats = FilterService.compute_visibility_for_account(account.id)

    logger.info(
        f"Processed tags for {processed_count} channels in account {account.id}: "
        f"{tags_created} created, {tags_updated} updated, {tags_removed} removed, "
        f"{channels_updated} channel names cleaned"
    )

    return jsonify(
        {
            "success": True,
            "processed": processed_count,
            "unique_tags": len(tag_counts),
            "tag_counts": tag_counts,
            "tags_created": tags_created,
            "tags_updated": tags_updated,
            "tags_removed": tags_removed,
            "channels_updated": channels_updated,
            "channels_visible": filter_stats.get("channels_visible", 0),
            "channels_hidden": filter_stats.get("channels_hidden", 0),
            "using_database": True,
        }
    )


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

    # Get tags for this channel
    channel_tags = (
        db.session.query(Tag.name)
        .join(ChannelTag, ChannelTag.tag_id == Tag.id)
        .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id == str(stream_id))
        .all()
    )
    tags = [t[0] for t in channel_tags]

    # Build complete channel data
    return jsonify(
        {
            "id": channel.id,
            "account_id": channel.account_id,
            "account_name": account.name,
            "stream_id": channel.stream_id,
            "name": channel.name,
            "cleaned_name": channel.cleaned_name,
            "category": channel.category.category_name if channel.category else "Uncategorized",
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
            "last_seen": channel.last_seen.isoformat() if channel.last_seen else None,
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
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
    - collapse_duplicates: If "true", collapse duplicate channels keeping highest quality

    Returns:
    - JSON with total count, channel data, and using_database flag
    """
    Account.query.get_or_404(account_id)

    # Parse tag filter
    tags_param = request.args.get("tags", "")
    filter_tags = [t.strip() for t in tags_param.split(",") if t.strip()] if tags_param else []

    # Parse category filter
    category_filter = request.args.get("category", "")

    # Parse collapse_duplicates option
    collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

    # Check if account has been synced (database-first approach)
    # Only count ACTIVE channels
    has_synced = (
        db.session.query(Channel.id).filter(Channel.account_id == account_id, Channel.is_active).first() is not None
    )

    if not has_synced:
        return jsonify({"success": False, "error": "Account not synced. Please sync the account first."}), 503

    # Build base query - use pre-computed is_visible
    base_query = (
        db.session.query(Channel)
        .filter(
            Channel.account_id == account_id,
            Channel.is_active,
            Channel.is_visible,  # Use pre-computed filter result
        )
        .join(Category, Channel.category_id == Category.id, isouter=True)
    )

    # Apply category filter if specified
    if category_filter:
        base_query = base_query.filter(Category.category_name == category_filter)

    # Apply tag filter if specified
    if filter_tags:
        # Find channels that have at least one of the requested tags
        tag_subquery = (
            db.session.query(ChannelTag.stream_id)
            .join(Tag, ChannelTag.tag_id == Tag.id)
            .filter(ChannelTag.account_id == account_id, Tag.name.in_(filter_tags))
            .distinct()
        )
        base_query = base_query.filter(Channel.stream_id.in_(tag_subquery))

    base_query = base_query.order_by(Channel.name)

    # Apply pagination
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    if collapse_duplicates:
        # For duplicate collapsing, we need to load ALL matching channels first
        # to properly group and collapse them, then paginate the result
        all_channels = base_query.all()

        # Get ALL channel IDs for batch tag loading
        all_channel_ids = [ch.stream_id for ch in all_channels]

        # Load tags for ALL channels in batches
        tags_map = {}
        batch_size = 500
        for i in range(0, len(all_channel_ids), batch_size):
            batch = all_channel_ids[i : i + batch_size]
            channel_tags_query = (
                db.session.query(ChannelTag.stream_id, Tag.name)
                .join(Tag)
                .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(batch))
            )
            for stream_id, tag_name in channel_tags_query:
                if stream_id not in tags_map:
                    tags_map[stream_id] = []
                tags_map[stream_id].append(tag_name)

        # Build channel dictionaries for collapsing
        channel_dicts = [
            {
                "id": ch.id,
                "stream_id": ch.stream_id,
                "account_id": ch.account_id,
                "name": ch.name,
                "cleaned_name": ch.cleaned_name if ch.cleaned_name is not None else ch.name,
                "category": ch.category.category_name if ch.category else "Uncategorized",
                "category_id": ch.category_id,
                "icon": ch.stream_icon,
                "is_visible": ch.is_visible,
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
        # Standard pagination without collapsing
        # Get total count BEFORE pagination
        total = base_query.count()
        channels = base_query.limit(limit).offset(offset).all()

        # Get channel IDs for batch tag loading
        channel_ids = [ch.stream_id for ch in channels]

        # Load tags for these channels in batch
        channel_tags_query = (
            db.session.query(ChannelTag.stream_id, Tag.name)
            .join(Tag)
            .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(channel_ids))
        )

        # Build tag map
        tags_map = {}
        for stream_id, tag_name in channel_tags_query:
            if stream_id not in tags_map:
                tags_map[stream_id] = []
            tags_map[stream_id].append(tag_name)

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
                        "category": ch.category.category_name if ch.category else "Uncategorized",
                        "category_id": ch.category_id,
                        "icon": ch.stream_icon,
                        "is_visible": ch.is_visible,
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

    if not account.enabled:
        return jsonify({"success": False, "error": "Account is disabled"}), 403

    # Check if account has synced channels
    channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
    if channel_count == 0:
        return jsonify({"success": False, "error": "Account not synced - sync required"}), 503

    data = request.get_json()
    filter_type = data.get("filter_type")
    filter_value = data.get("filter_value", "").strip()

    if not filter_type or not filter_value:
        return jsonify({"success": False, "error": "Missing filter_type or filter_value"}), 400

    # Get all channels for this account
    total_query = Channel.query.filter(Channel.account_id == account_id, Channel.is_active)
    total_count = total_query.count()

    # Build query to match channels
    match_query = total_query

    if filter_type == "category":
        # Match category name
        match_query = match_query.join(Category).filter(Category.category_name.ilike(f"%{filter_value}%"))
    elif filter_type == "channel_name":
        # Match channel name
        match_query = match_query.filter(Channel.name.ilike(f"%{filter_value}%"))
    elif filter_type == "regex":
        # Regex match (SQLite REGEXP)
        import re

        try:
            # Test if regex is valid
            re.compile(filter_value)
            # Note: SQLite doesn't have built-in REGEXP support
            # We'll need to fetch all and filter in Python for regex
            all_channels = total_query.all()
            pattern = re.compile(filter_value, re.IGNORECASE)
            match_count = sum(1 for ch in all_channels if pattern.search(ch.name))
            return jsonify({"success": True, "match_count": match_count, "total_count": total_count})
        except re.error as e:
            return jsonify({"success": False, "error": f"Invalid regex: {str(e)}"}), 400
    elif filter_type == "tag":
        # Match tags
        tags = [t.strip() for t in filter_value.split(",") if t.strip()]
        if not tags:
            return jsonify({"success": False, "error": "No tags specified"}), 400

        # Get channel IDs that have any of these tags
        tagged_streams = (
            db.session.query(ChannelTag.stream_id)
            .join(Tag)
            .filter(ChannelTag.account_id == account_id, Tag.name.in_(tags))
            .distinct()
        )

        match_query = match_query.filter(Channel.stream_id.in_(tagged_streams))
    else:
        return jsonify({"success": False, "error": "Invalid filter_type"}), 400

    match_count = match_query.count() if filter_type != "regex" else match_count

    return jsonify({"success": True, "match_count": match_count, "total_count": total_count})


@accounts_bp.route("/api/tags/cleanup-orphans", methods=["POST"])
@handle_errors()
def cleanup_orphan_tags():
    """
    Delete tags that have no associated channels in any account.
    This cleans up tags that were created but are no longer used.
    """
    # Find tags that have no ChannelTag associations
    orphaned_tags = (
        db.session.query(Tag)
        .outerjoin(ChannelTag, Tag.id == ChannelTag.tag_id)
        .filter(ChannelTag.tag_id.is_(None))
        .all()
    )

    orphan_count = len(orphaned_tags)
    tag_names = [tag.name for tag in orphaned_tags[:100]]  # Sample for display

    # Delete orphaned tags
    for tag in orphaned_tags:
        db.session.delete(tag)

    db.session.commit()

    logger.info(f"Cleaned up {orphan_count} orphaned tags")

    return jsonify(
        {
            "success": True,
            "tags_deleted": orphan_count,
            "sample_tags": tag_names[:20],  # Show first 20 for reference
        }
    )


# ============================================================================
# API Routes - Credential Management
# ============================================================================


@accounts_bp.route("/api/accounts/<int:account_id>/credentials", methods=["GET"])
def get_credentials(account_id):
    """Get all credentials for an account"""
    account = Account.query.get_or_404(account_id)
    return jsonify([credential_to_dict(c) for c in account.credentials])


@accounts_bp.route("/api/accounts/<int:account_id>/credentials", methods=["POST"])
def add_credential(account_id):
    """Add a new credential to an account"""
    account = Account.query.get_or_404(account_id)
    data = request.json

    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    # Check for duplicate username
    existing = Credential.query.filter_by(account_id=account_id, username=data["username"]).first()
    if existing:
        return jsonify({"error": "Credential with this username already exists"}), 400

    credential = Credential(
        account_id=account_id,
        username=data["username"],
        password=data["password"],
        max_connections=data.get("max_connections", 1),
        enabled=data.get("enabled", True),
    )
    db.session.add(credential)
    db.session.commit()

    # Test the new credential to get connection info
    try:
        service = IPTVService(
            account.server, credential.username, credential.password, account.user_agent or "okhttp/3.14.9"
        )
        auth_info = service.authenticate()
        user_info = auth_info.get("user_info", {})

        credential.max_connections = int(user_info.get("max_connections", 1) or 1)
        credential.status = user_info.get("status", "Unknown")
        credential.exp_date = user_info.get("exp_date", "")
        db.session.commit()
    except Exception as e:
        logger.warning(f"Could not verify new credential: {e}")

    return jsonify(credential_to_dict(credential)), 201


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>", methods=["PUT"])
def update_credential(account_id, cred_id):
    """Update a credential"""
    Account.query.get_or_404(account_id)  # Validate account exists
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    data = request.json

    if "username" in data:
        credential.username = data["username"]
    if "password" in data and data["password"]:
        credential.password = data["password"]
    if "enabled" in data:
        credential.enabled = data["enabled"]
    if "max_connections" in data:
        credential.max_connections = data["max_connections"]

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify(credential_to_dict(credential))


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>", methods=["DELETE"])
def delete_credential(account_id, cred_id):
    """Delete a credential"""
    account = Account.query.get_or_404(account_id)
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    # Don't allow deleting the last credential
    if len(account.credentials) <= 1:
        return jsonify({"error": "Cannot delete the last credential"}), 400

    db.session.delete(credential)
    db.session.commit()

    return "", 204


@accounts_bp.route("/api/accounts/<int:account_id>/credentials/<int:cred_id>/test", methods=["POST"])
def test_credential(account_id, cred_id):
    """Test a specific credential and update its info"""
    account = Account.query.get_or_404(account_id)
    credential = Credential.query.filter_by(id=cred_id, account_id=account_id).first_or_404()

    try:
        service = IPTVService(
            account.server, credential.username, credential.password, account.user_agent or "okhttp/3.14.9"
        )
        auth_info = service.authenticate()
        user_info = auth_info.get("user_info", {})

        # Update credential with auth info
        credential.max_connections = int(user_info.get("max_connections", 1) or 1)
        credential.status = user_info.get("status", "Unknown")
        credential.exp_date = user_info.get("exp_date", "")
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "credential": credential_to_dict(credential),
                "user_info": {
                    "username": user_info.get("username", ""),
                    "status": credential.status,
                    "exp_date": credential.exp_date,
                    "max_connections": credential.max_connections,
                },
            }
        )
    except Exception as e:
        logger.error(f"Error testing credential {cred_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@accounts_bp.route("/api/accounts/<int:account_id>/connection-status", methods=["GET"])
def get_account_connection_status(account_id):
    """Get connection status for an account (active streams, available slots)"""
    Account.query.get_or_404(account_id)  # Validate account exists
    return jsonify(ConnectionManager.get_connection_status(account_id))
