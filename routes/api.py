"""
Additional API routes for sync, tags, and cache management
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Category, Channel, ChannelTag, Tag, db
from services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Create blueprint
api_bp = Blueprint("api", __name__)

# Initialize cache service
cache_service = CacheService()

# Store scheduler reference (set by app.py)
_scheduler = None


def set_scheduler(scheduler):
    """Set the scheduler instance for use in API routes"""
    global _scheduler
    _scheduler = scheduler


# ============================================================================
# API Routes - Sync All Accounts
# ============================================================================


@api_bp.route("/api/sync/all", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing all accounts")
def sync_all_accounts():
    """Sync channels for all enabled accounts"""
    from services.sync_service import ChannelSyncService

    results = ChannelSyncService.sync_all_accounts()
    return jsonify({"success": True, "accounts_synced": len(results), "results": results})


# ============================================================================
# API Routes - Categories (Global)
# ============================================================================


@api_bp.route("/api/categories", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching categories")
def get_all_categories():
    """Get all categories across all accounts with channel counts

    Query parameters:
    - account_id (optional): Filter to specific account
    - include_empty (optional): Include categories with no visible channels (default: false)
    - include_epg (optional): Include EPG coverage stats (default: false)
    """
    account_id = request.args.get("account_id", type=int)
    include_empty = request.args.get("include_empty", "false").lower() == "true"
    include_epg = request.args.get("include_epg", "false").lower() == "true"

    # Build query for categories with visible/hidden channel counts
    # Also count channels with provider EPG IDs
    query = (
        db.session.query(
            Category.id,
            Category.category_id,
            Category.category_name,
            Category.account_id,
            Account.name.label("account_name"),
            db.func.sum(
                db.case((db.and_(Channel.is_visible == True, Channel.is_active == True), 1), else_=0)  # noqa: E712
            ).label("visible_count"),
            db.func.sum(
                db.case((db.and_(Channel.is_visible == False, Channel.is_active == True), 1), else_=0)  # noqa: E712
            ).label("hidden_count"),
            db.func.sum(
                db.case(
                    (
                        db.and_(
                            Channel.is_active == True,  # noqa: E712
                            Channel.epg_channel_id.isnot(None),
                            Channel.epg_channel_id != "",
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("with_epg_id_count"),
        )
        .join(Account, Category.account_id == Account.id)
        .outerjoin(
            Channel,
            db.and_(
                Channel.category_id == Category.id,
                Channel.account_id == Category.account_id,
            ),
        )
        .group_by(Category.id, Category.category_id, Category.category_name, Category.account_id, Account.name)
    )

    if account_id:
        Account.query.get_or_404(account_id)  # Validate account exists
        query = query.filter(Category.account_id == account_id)

    if not include_empty:
        # Filter to categories that have at least one visible channel
        query = query.having(
            db.func.sum(
                db.case(
                    (db.and_(Channel.is_visible == True, Channel.is_active == True), 1),  # noqa: E712
                    else_=0,
                )
            )
            > 0  # noqa: W503
        )

    categories = query.order_by(Category.category_name).all()

    # If include_epg is requested, also get EPG mapping counts
    epg_coverage_by_category = {}
    if include_epg:
        from models import ChannelEpgMapping

        # Get all category IDs we're returning
        category_ids = [cat.id for cat in categories]

        if category_ids:
            # Count channels with EPG mappings per category
            epg_counts = (
                db.session.query(
                    Channel.category_id, db.func.count(db.distinct(ChannelEpgMapping.channel_id)).label("mapped_count")
                )
                .join(ChannelEpgMapping, Channel.id == ChannelEpgMapping.channel_id)
                .filter(Channel.category_id.in_(category_ids), Channel.is_active == True)  # noqa: E712
                .group_by(Channel.category_id)
                .all()
            )
            epg_coverage_by_category = {row.category_id: row.mapped_count for row in epg_counts}

    result = []
    for cat in categories:
        cat_data = {
            "id": cat.id,
            "category_id": cat.category_id,
            "category_name": cat.category_name,
            "account_id": cat.account_id,
            "account_name": cat.account_name,
            "visible_count": int(cat.visible_count or 0),
            "hidden_count": int(cat.hidden_count or 0),
            "total_count": int(cat.visible_count or 0) + int(cat.hidden_count or 0),
            "with_epg_id_count": int(cat.with_epg_id_count or 0),
        }

        if include_epg:
            total_active = int(cat.visible_count or 0) + int(cat.hidden_count or 0)
            mapped_count = epg_coverage_by_category.get(cat.id, 0)
            cat_data["epg_mapped_count"] = mapped_count
            cat_data["epg_coverage_percent"] = round((mapped_count / total_active * 100), 1) if total_active > 0 else 0

        result.append(cat_data)

    return jsonify(result)


# ============================================================================
# API Routes - Tags (Global)
# ============================================================================


@api_bp.route("/api/tags", methods=["GET"])
def get_tags():
    """Get all tags with optional account filtering and usage counts

    Query parameters:
    - account_id (optional): Filter tags to specific account
    - with_counts (optional): Include channel counts per tag
    """
    account_id = request.args.get("account_id", type=int)
    with_counts = request.args.get("with_counts", "false").lower() == "true"

    if account_id:
        # Filter tags for specific account
        tags_query = (
            db.session.query(Tag)
            .join(ChannelTag)
            .filter(ChannelTag.account_id == account_id)
            .distinct()
            .order_by(Tag.name)
        )
    else:
        # All tags across all accounts
        tags_query = Tag.query.order_by(Tag.name)

    tags = tags_query.all()

    if with_counts:
        # Build counts for each tag
        result = []
        for tag in tags:
            if account_id:
                count = ChannelTag.query.filter_by(tag_id=tag.id, account_id=account_id).count()
            else:
                count = ChannelTag.query.filter_by(tag_id=tag.id).count()

            result.append(
                {"id": tag.id, "name": tag.name, "created_at": tag.created_at.isoformat(), "channel_count": count}
            )
        return jsonify(result)
    else:
        return jsonify([{"id": t.id, "name": t.name, "created_at": t.created_at.isoformat()} for t in tags])


# ============================================================================
# API Routes - Cache Management
# ============================================================================


@api_bp.route("/api/cache/clear", methods=["POST"])
def clear_all_cache():
    """Clear all caches"""
    cache_service.clear_all()
    return jsonify({"success": True, "message": "All caches cleared"})


@api_bp.route("/api/cache/clear/<int:account_id>", methods=["POST"])
def clear_account_cache(account_id):
    """Clear cache for a specific account"""
    Account.query.get_or_404(account_id)  # Validate account exists
    cache_service.clear_account_cache(account_id)
    return jsonify({"success": True, "message": f"Cache cleared for account {account_id}"})


# ============================================================================
# API Routes - Channel Preview
# ============================================================================


@api_bp.route("/api/channels/preview", methods=["GET"])
@handle_errors(return_json=True, default_message="Error previewing channels")
def preview_channels():
    """Preview channels across all or filtered accounts with pagination

    Query parameters:
    - account_id (optional): Filter to specific account
    - tags (optional): Comma-separated list of tag names to filter by
    - category (optional): Category name to filter by
    - limit (default 50): Number of results to return
    - offset (default 0): Offset for pagination
    """
    account_id = request.args.get("account_id", type=int)
    tags_param = request.args.get("tags", "")
    category_filter = request.args.get("category", "")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Parse tag filter
    filter_tags = [t.strip() for t in tags_param.split(",") if t.strip()] if tags_param else []

    # Build base query
    query = (
        db.session.query(Channel)
        .join(Category, Channel.category_id == Category.id, isouter=True)
        .filter(Channel.is_active, Channel.is_visible)
    )

    # Apply account filter if specified
    if account_id:
        Account.query.get_or_404(account_id)  # Validate account exists
        query = query.filter(Channel.account_id == account_id)

    # Apply category filter if specified
    if category_filter:
        query = query.filter(Category.category_name == category_filter)

    # Apply tag filter if specified
    if filter_tags:
        # Find channels that have at least one of the requested tags
        tag_subquery = (
            db.session.query(ChannelTag.stream_id)
            .join(Tag, ChannelTag.tag_id == Tag.id)
            .filter(Tag.name.in_(filter_tags))
        )
        if account_id:
            tag_subquery = tag_subquery.filter(ChannelTag.account_id == account_id)
        tag_subquery = tag_subquery.distinct()

        query = query.filter(Channel.stream_id.in_(tag_subquery))

    # Get total count
    total = query.count()

    # Get paginated results
    channels = query.order_by(Channel.name).offset(offset).limit(limit).all()

    # Batch-load tags for all channels at once
    stream_ids = [ch.stream_id for ch in channels]
    tag_map = {}
    if stream_ids:
        channel_tags = (
            db.session.query(ChannelTag.stream_id, Tag.name)
            .join(Tag, ChannelTag.tag_id == Tag.id)
            .filter(ChannelTag.stream_id.in_(stream_ids))
        )
        if account_id:
            channel_tags = channel_tags.filter(ChannelTag.account_id == account_id)

        for stream_id, tag_name in channel_tags.all():
            if stream_id not in tag_map:
                tag_map[stream_id] = []
            tag_map[stream_id].append(tag_name)

    # Build response
    result = []
    for ch in channels:
        result.append(
            {
                "id": ch.id,
                "stream_id": ch.stream_id,
                "account_id": ch.account_id,
                "name": ch.name,
                "cleaned_name": ch.cleaned_name,
                "category": ch.category.category_name if ch.category else "Uncategorized",
                "category_id": ch.category_id,
                "icon": ch.stream_icon,
                "is_visible": ch.is_visible,
                "tags": tag_map.get(ch.stream_id, []),
            }
        )

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "showing": len(result),
            "channels": result,
            "has_more": offset + limit < total,
            "filter_tags": filter_tags,
        }
    )


# ============================================================================
# API Routes - Scheduler Management
# ============================================================================


@api_bp.route("/api/scheduler/status", methods=["GET"])
def get_scheduler_status():
    """Get scheduler status and configuration"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    return jsonify(
        {
            "running": _scheduler.running,
            "interval_hours": _scheduler.interval_hours,
            "interval_seconds": _scheduler.interval_seconds,
        }
    )


@api_bp.route("/api/scheduler/restart", methods=["POST"])
def restart_scheduler():
    """Restart scheduler with new interval"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    data = request.get_json() or {}
    new_interval = data.get("interval_hours")

    if new_interval is not None:
        try:
            new_interval = int(new_interval)
            if new_interval < 1 or new_interval > 168:  # 1 hour to 1 week
                return jsonify({"error": "Interval must be between 1 and 168 hours"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid interval value"}), 400

        # Stop and restart with new interval
        _scheduler.stop()
        _scheduler.interval_hours = new_interval
        _scheduler.interval_seconds = new_interval * 3600
        _scheduler.start()

        logger.info(f"Scheduler restarted with new interval: {new_interval} hours")
        return jsonify(
            {
                "success": True,
                "message": f"Scheduler restarted with {new_interval} hour interval",
                "interval_hours": new_interval,
            }
        )
    else:
        # Just restart with current settings
        _scheduler.stop()
        _scheduler.start()
        return jsonify({"success": True, "message": "Scheduler restarted", "interval_hours": _scheduler.interval_hours})


@api_bp.route("/api/scheduler/stop", methods=["POST"])
def stop_scheduler():
    """Stop the scheduler"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    if not _scheduler.running:
        return jsonify({"error": "Scheduler is not running"}), 400

    _scheduler.stop()
    logger.info("Scheduler stopped via API")
    return jsonify({"success": True, "message": "Scheduler stopped"})


@api_bp.route("/api/scheduler/start", methods=["POST"])
def start_scheduler():
    """Start the scheduler"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    if _scheduler.running:
        return jsonify({"error": "Scheduler is already running"}), 400

    _scheduler.start()
    logger.info("Scheduler started via API")
    return jsonify({"success": True, "message": "Scheduler started"})
