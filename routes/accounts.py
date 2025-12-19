"""
Account management routes
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Category, Channel, ChannelTag, Filter, Tag, db
from schemas import AccountCreateSchema, AccountUpdateSchema, validate_request_data
from services.cache_service import CacheService
from services.iptv_service import IPTVService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
accounts_bp = Blueprint("accounts", __name__)

# Initialize cache service
cache_service = CacheService()


# ============================================================================
# API Routes - Account CRUD
# ============================================================================


@accounts_bp.route("/api/accounts", methods=["GET"])
def get_accounts():
    """Get all accounts"""
    accounts = Account.query.all()
    return jsonify(
        [
            {
                "id": a.id,
                "name": a.name,
                "server": a.server,
                "username": a.username,
                "enabled": a.enabled,
            }
            for a in accounts
        ]
    )


@accounts_bp.route("/api/accounts", methods=["POST"])
@validate_request_data(AccountCreateSchema)
def create_account():
    """Create new account"""
    data = request.validated_data

    account = Account(
        name=data["name"],
        server=data["server"],
        username=data["username"],
        password=data["password"],
        enabled=data.get("enabled", True),
    )

    db.session.add(account)
    db.session.commit()

    return (
        jsonify(
            {
                "id": account.id,
                "name": account.name,
                "server": account.server,
                "username": account.username,
                "enabled": account.enabled,
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
    account.enabled = data.get("enabled", account.enabled)

    db.session.commit()
    cache_service.clear_account_cache(account_id)

    return jsonify(
        {
            "id": account.id,
            "name": account.name,
            "server": account.server,
            "username": account.username,
            "enabled": account.enabled,
        }
    )


@accounts_bp.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def delete_account(account_id):
    """Delete account and all associated data"""
    account = Account.query.get_or_404(account_id)

    # Clear cache first
    cache_service.clear_account_cache(account_id)

    # Delete account (cascade will handle filters, channels, etc.)
    db.session.delete(account)
    db.session.commit()

    return "", 204


@accounts_bp.route("/api/accounts/<int:account_id>/test", methods=["POST"])
def test_account(account_id):
    """Test account connection"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)
        auth_info = service.authenticate()

        return jsonify(
            {
                "success": True,
                "server_info": {
                    "url": auth_info.get("server_info", {}).get("url", ""),
                    "time": auth_info.get("server_info", {}).get("time_now", ""),
                },
                "user_info": {
                    "username": auth_info.get("user_info", {}).get("username", ""),
                    "status": auth_info.get("user_info", {}).get("status", ""),
                    "exp_date": auth_info.get("user_info", {}).get("exp_date", ""),
                    "max_connections": auth_info.get("user_info", {}).get("max_connections", ""),
                },
            }
        )
    except Exception as e:
        logger.error(f"Error testing account {account_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@accounts_bp.route("/api/accounts/<int:account_id>/categories", methods=["GET"])
def get_account_categories(account_id):
    """Get categories for account"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)
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
    account = Account.query.get(account_id)
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
    """Get statistics for account"""
    account = Account.query.get_or_404(account_id)

    try:
        service = IPTVService(account.server, account.username, account.password)

        # Get cached or fetch new
        streams = cache_service.get_cached_streams(account_id)
        if not streams:
            streams = service.get_live_streams()
            cache_service.cache_streams(account_id, streams)

        categories = cache_service.get_cached_categories(account_id)
        if not categories:
            categories = service.get_live_categories()
            cache_service.cache_categories(account_id, categories)

        # Auto-process tags when stats are fetched
        try:
            _process_tags_for_account(account_id, streams, categories)
        except Exception as tag_error:
            logger.warning(f"Error auto-processing tags for account {account_id}: {tag_error}")

        # Count by category
        category_counts = {}
        for stream in streams:
            cat_id = str(stream.get("category_id", "Unknown"))
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

        return jsonify(
            {"total_channels": len(streams), "total_categories": len(categories), "category_counts": category_counts}
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

    account = Account.query.get(account_id)
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
    from datetime import datetime

    account = Account.query.get_or_404(account_id)

    # Check if channels are synced to database
    db_channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

    if not db_channels:
        return jsonify({"success": False, "error": "Account not synced. Please sync channels first."}), 503

    # Mark start time for this processing run
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

    Returns:
    - JSON with total count, channel data, and using_database flag
    """
    Account.query.get_or_404(account_id)

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
        .order_by(Channel.name)
    )

    # Get total count BEFORE pagination
    total = base_query.count()

    # Apply pagination
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    channels = base_query.limit(limit).offset(offset).all()

    return jsonify(
        {
            "total": total,
            "channels": [
                {
                    "id": ch.id,
                    "stream_id": ch.stream_id,
                    "name": ch.name,
                    "cleaned_name": ch.cleaned_name if ch.cleaned_name is not None else ch.name,
                    "category_id": ch.category_id,
                    "is_visible": ch.is_visible,
                }
                for ch in channels
            ],
            "using_database": True,
        }
    )
