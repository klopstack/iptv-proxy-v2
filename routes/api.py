"""
Additional API routes for sync, tags, and cache management
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Category, Channel, ChannelTag, Tag, db
from services.cache_service import CacheService
from services.channel_query_service import ChannelQueryService
from services.tag_service import TagService

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


@api_bp.route("/api/sync/epg", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing EPG sources")
def sync_all_epg_sources():
    """Sync all enabled EPG sources in parallel with per-source progress."""
    from flask import current_app, request

    from models import EpgSource
    from services.epg_sync_orchestrator import EpgSyncOrchestrator

    force = request.args.get("force", "false").lower() in ("1", "true", "yes")
    sources = EpgSource.query.filter_by(enabled=True).order_by(EpgSource.priority, EpgSource.id).all()
    app = current_app._get_current_object()
    result = EpgSyncOrchestrator(app).sync_sources(sources, parallel=True, force=force)
    return jsonify(result)


@api_bp.route("/api/sync/epg/status", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching EPG sync status")
def get_epg_sync_status():
    """Per-source EPG sync progress for settings UI and monitoring."""
    from flask import current_app

    from models import EpgSource
    from services.epg_sync_orchestrator import EpgSyncOrchestrator, source_needs_sync
    from services.epg_sync_service import get_epg_sync_interval

    app = current_app._get_current_object()
    interval_hours = _scheduler.epg_interval_hours if _scheduler else get_epg_sync_interval()

    sources = EpgSyncOrchestrator(app).list_status()
    for snap in sources:
        source = db.session.get(EpgSource, snap["source_id"])
        snap["due"] = bool(source and source.enabled and source_needs_sync(source, interval_hours))

    return jsonify({"success": True, "interval_hours": interval_hours, "sources": sources})


@api_bp.route("/api/sync/fcc", methods=["POST"])
@handle_errors(return_json=True, default_message="Error syncing FCC data")
def sync_fcc_data():
    """Sync FCC facility data"""
    from services.fcc_facility_service import FccFacilityService

    result = FccFacilityService.full_sync()

    if result.get("success"):
        stats = result.get("stats", {})
        return jsonify(
            {
                "success": True,
                "stats": stats,
                "message": f"{stats.get('added', 0)} added, {stats.get('updated', 0)} updated, {stats.get('total', 0)} total facilities",
            }
        )
    else:
        return jsonify({"success": False, "error": result.get("message", "Unknown error")}), 500


# ============================================================================
# API Routes - Categories (Global)
# ============================================================================


@api_bp.route("/api/categories", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching categories")
def get_all_categories():
    """Get all categories across all accounts with channel counts.

    visible_count / hidden_count use playlist-visible semantics (account filters
    plus PPV visibility), matching M3U/EPG/Xtream output.

    Query parameters:
    - account_id (optional): Filter to specific account
    - include_empty (optional): Include categories with no visible channels (default: false)
    - include_epg (optional): Include EPG coverage stats (default: false)
    - include_ppv (optional): Include PPV categories (default: true)
    """
    account_id = request.args.get("account_id", type=int)
    include_empty = request.args.get("include_empty", "false").lower() == "true"
    include_epg = request.args.get("include_epg", "false").lower() == "true"
    include_ppv = request.args.get("include_ppv", "true").lower() == "true"

    # Get all categories for the account
    query = db.session.query(Category, Account.name.label("account_name")).join(
        Account, Category.account_id == Account.id
    )

    if account_id:
        db.get_or_404(Account, account_id)  # Validate account exists
        query = query.filter(Category.account_id == account_id)

    categories = query.order_by(Category.category_name).all()

    # Get all active channels for this account to apply filters
    channel_query = db.session.query(Channel).filter(Channel.is_active == True)  # noqa: E712
    if account_id:
        channel_query = channel_query.filter(Channel.account_id == account_id)
    all_channels = channel_query.all()

    if account_id:
        playlist_visible_keys = ChannelQueryService.visible_channel_set_for_account(account_id)
    else:
        account_ids = list({ch.account_id for ch in all_channels})
        visible_by_account = ChannelQueryService.visible_channel_sets_by_account(account_ids)
        playlist_visible_keys = set()
        for keys in visible_by_account.values():
            playlist_visible_keys.update(keys)

    # Build channel counts per category
    filtered_stream_ids = playlist_visible_keys
    category_visible_counts = {}
    category_total_counts = {}
    category_epg_counts = {}

    for ch in all_channels:
        cat_id = ch.category_id
        if cat_id:
            # Count total channels
            category_total_counts[cat_id] = category_total_counts.get(cat_id, 0) + 1

            # Count playlist-visible channels
            if (ch.account_id, str(ch.stream_id)) in filtered_stream_ids:
                category_visible_counts[cat_id] = category_visible_counts.get(cat_id, 0) + 1

            # Count channels with EPG IDs
            if ch.epg_channel_id:
                category_epg_counts[cat_id] = category_epg_counts.get(cat_id, 0) + 1

    # If include_epg is requested, also get EPG mapping counts
    epg_mapping_counts = {}
    if include_epg:
        from models import ChannelEpgMapping

        # Get all category IDs we're returning
        category_ids = [cat.Category.id for cat in categories]

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
            epg_mapping_counts = {row.category_id: row.mapped_count for row in epg_counts}

    result = []
    for cat_row in categories:
        cat = cat_row.Category
        account_name = cat_row.account_name

        # Skip PPV categories if not requested (use database column)
        if not include_ppv and cat.is_ppv:
            continue

        visible_count = category_visible_counts.get(cat.id, 0)
        total_count = category_total_counts.get(cat.id, 0)
        hidden_count = total_count - visible_count

        # Skip empty categories if requested
        if not include_empty and visible_count == 0:
            continue

        cat_data = {
            "id": cat.id,
            "category_id": cat.category_id,
            "category_name": cat.category_name,
            "cleaned_name": cat.cleaned_name,
            "account_id": cat.account_id,
            "account_name": account_name,
            "visible_count": visible_count,
            "hidden_count": hidden_count,
            "total_count": total_count,
            "with_epg_id_count": category_epg_counts.get(cat.id, 0),
            "is_ppv": cat.is_ppv or False,
        }

        if include_epg:
            mapped_count = epg_mapping_counts.get(cat.id, 0)
            cat_data["epg_mapped_count"] = mapped_count
            cat_data["epg_coverage_percent"] = round((mapped_count / total_count * 100), 1) if total_count > 0 else 0

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
    db.get_or_404(Account, account_id)  # Validate account exists
    cache_service.clear_account_cache(account_id)
    return jsonify({"success": True, "message": f"Cache cleared for account {account_id}"})


# ============================================================================
# API Routes - EPG Cache Management
# ============================================================================


@api_bp.route("/api/epg-cache/status", methods=["GET"])
def get_epg_cache_status():
    """Get EPG XML cache statistics"""
    from services.epg.cache import get_cache_stats

    stats = get_cache_stats()
    return jsonify(stats)


@api_bp.route("/api/epg-cache/clear", methods=["POST"])
def clear_all_epg_cache():
    """Clear all EPG XML caches"""
    from services.epg.cache import clear_all_cache

    deleted = clear_all_cache()
    return jsonify({"success": True, "message": f"Cleared {deleted} EPG cache files"})


@api_bp.route("/api/epg-cache/source/<int:source_id>", methods=["GET"])
def get_epg_source_cache_info(source_id):
    """Get cache info for a specific EPG source"""
    from models import EpgSource
    from services.epg.cache import get_cache_info, is_cache_valid

    source = db.get_or_404(EpgSource, source_id)
    info = get_cache_info(source_id)

    if info:
        info["source_name"] = source.name
        info["source_type"] = source.source_type
        info["is_valid"] = is_cache_valid(source_id)

    return jsonify({"source_id": source_id, "cached": info is not None, "info": info})


@api_bp.route("/api/epg-cache/source/<int:source_id>", methods=["DELETE"])
def delete_epg_source_cache(source_id):
    """Delete cache for a specific EPG source"""
    from models import EpgSource
    from services.epg.cache import delete_cache

    db.get_or_404(EpgSource, source_id)  # Validate source exists
    success = delete_cache(source_id)
    return jsonify({"success": success, "message": f"EPG cache deleted for source {source_id}"})


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
    # Normalize for case-insensitive matching
    filter_tags = TagService.normalize_filter_tags(filter_tags)

    if account_id:
        db.get_or_404(Account, account_id)

    channels, total = ChannelQueryService.preview_channels_for_scope(
        account_id=account_id,
        category=category_filter,
        filter_tags=filter_tags,
        limit=limit,
        offset=offset,
    )

    # Batch-load tags for all channels at once
    stream_ids = [ch.stream_id for ch in channels]
    tag_map = {}
    if stream_ids:
        channel_tags = (
            db.session.query(ChannelTag.stream_id, Tag.name, ChannelTag.source)
            .join(Tag, ChannelTag.tag_id == Tag.id)
            .filter(ChannelTag.stream_id.in_(stream_ids))
        )
        if account_id:
            channel_tags = channel_tags.filter(ChannelTag.account_id == account_id)

        for stream_id, tag_name, source in channel_tags.all():
            if stream_id not in tag_map:
                tag_map[stream_id] = []
            tag_map[stream_id].append({"name": tag_name, "source": source})

    # Initialize image cache for proxying icons
    from services.image_cache_service import ImageCacheService

    image_cache = ImageCacheService.get_instance()
    proxy_base = f"{request.scheme}://{request.host}"

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
                "icon": image_cache.get_proxy_url(ch.stream_icon, proxy_base) if ch.stream_icon else None,
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
    """Get scheduler status and configuration including separate sync intervals"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    # Use the new detailed status method
    return jsonify(_scheduler.get_status())


@api_bp.route("/api/scheduler/restart", methods=["POST"])
def restart_scheduler():
    """Restart scheduler with new intervals

    Accepts JSON body with optional interval settings:
    - account_interval_hours: IPTV account sync interval (1-168)
    - epg_interval_hours: EPG source sync interval (1-336)
    - fcc_interval_hours: FCC data sync interval (24-672)
    """
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    data = request.get_json() or {}

    # Validate and apply account interval
    if "account_interval_hours" in data:
        try:
            interval = int(data["account_interval_hours"])
            if interval < 1 or interval > 168:  # 1 hour to 1 week
                return jsonify({"error": "Account interval must be between 1 and 168 hours"}), 400
            _scheduler.account_interval_hours = interval
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid account interval value"}), 400

    # Validate and apply EPG interval
    if "epg_interval_hours" in data:
        try:
            interval = int(data["epg_interval_hours"])
            if interval < 1 or interval > 336:  # 1 hour to 2 weeks
                return jsonify({"error": "EPG interval must be between 1 and 336 hours"}), 400
            _scheduler.epg_interval_hours = interval
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid EPG interval value"}), 400

    # Validate and apply FCC interval
    if "fcc_interval_hours" in data:
        try:
            interval = int(data["fcc_interval_hours"])
            if interval < 24 or interval > 672:  # 1 day to 4 weeks
                return jsonify({"error": "FCC interval must be between 24 and 672 hours"}), 400
            _scheduler.fcc_interval_hours = interval
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid FCC interval value"}), 400

    # Restart scheduler
    _scheduler.stop()
    _scheduler.start()

    logger.info(
        f"Scheduler restarted with intervals: "
        f"accounts={_scheduler.account_interval_hours}h, "
        f"epg={_scheduler.epg_interval_hours}h, "
        f"fcc={_scheduler.fcc_interval_hours}h"
    )

    return jsonify(
        {
            "success": True,
            "message": "Scheduler restarted with updated intervals",
            "account_interval_hours": _scheduler.account_interval_hours,
            "epg_interval_hours": _scheduler.epg_interval_hours,
            "fcc_interval_hours": _scheduler.fcc_interval_hours,
        }
    )


@api_bp.route("/api/scheduler/stop", methods=["POST"])
def stop_scheduler():
    """Stop the scheduler"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    if not _scheduler.running and not _scheduler._is_scheduler_alive():
        return jsonify({"error": "Scheduler is not running"}), 400

    _scheduler.stop()
    logger.info("Scheduler stopped via API")
    return jsonify({"success": True, "message": "Scheduler stopped"})


@api_bp.route("/api/scheduler/start", methods=["POST"])
def start_scheduler():
    """Start the scheduler"""
    if _scheduler is None:
        return jsonify({"error": "Scheduler not initialized"}), 500

    if _scheduler.running or _scheduler._is_scheduler_alive():
        return jsonify({"error": "Scheduler is already running"}), 400

    _scheduler.start()
    logger.info("Scheduler started via API")
    return jsonify({"success": True, "message": "Scheduler started"})


# ============================================================================
# API Routes - Dashboard Overview Stats
# ============================================================================


@api_bp.route("/api/overview/stats", methods=["GET"])
@handle_errors(return_json=True, default_message="Error fetching overview stats")
def get_overview_stats():
    """
    Get comprehensive system statistics for dashboard overview.

    Returns stats about:
    - Accounts (total, enabled, synced)
    - Channels (total, visible, hidden, PPV)
    - EPG (sources, programs, coverage)
    - Tags (total, usage)
    - Scheduler (sync status and intervals)
    """
    from models import EpgChannel, EpgProgram, EpgSource, SyncMetadata
    from services.epg.coverage import get_epg_coverage_stats

    stats = {}

    # Account stats
    total_accounts = Account.query.count()
    enabled_accounts = Account.query.filter_by(enabled=True).count()
    synced_accounts = Account.query.filter(Account.last_sync.isnot(None), Account.last_sync_status == "success").count()

    stats["accounts"] = {
        "total": total_accounts,
        "enabled": enabled_accounts,
        "synced": synced_accounts,
        "disabled": total_accounts - enabled_accounts,
    }

    # Channel stats
    total_channels = Channel.query.filter_by(is_active=True).count()
    visible_channels = Channel.query.filter_by(is_active=True, is_visible=True).count()
    ppv_channels = Channel.query.filter_by(is_active=True, is_ppv=True).count()

    stats["channels"] = {
        "total": total_channels,
        "visible": visible_channels,
        "hidden": total_channels - visible_channels,
        "ppv": ppv_channels,
    }

    # Category stats
    total_categories = Category.query.count()
    stats["categories"] = {
        "total": total_categories,
    }

    # Tag stats
    total_tags = Tag.query.count()
    tagged_channels = db.session.query(ChannelTag.stream_id).distinct().count()

    stats["tags"] = {
        "total": total_tags,
        "tagged_channels": tagged_channels,
    }

    # EPG stats
    total_epg_sources = EpgSource.query.count()
    enabled_epg_sources = EpgSource.query.filter_by(enabled=True).count()
    total_epg_channels = EpgChannel.query.count()
    total_epg_programs = EpgProgram.query.count()

    # EPG coverage
    epg_coverage_error = None
    try:
        coverage_stats = get_epg_coverage_stats()
        epg_coverage_pct = coverage_stats.get("coverage_percentage", 0)
        mapped_channels = coverage_stats.get("channels_with_epg", 0)
    except Exception as e:
        logger.warning("Failed to load EPG coverage stats for overview: %s", e, exc_info=True)
        epg_coverage_pct = 0
        mapped_channels = 0
        epg_coverage_error = str(e)

    stats["epg"] = {
        "sources": {
            "total": total_epg_sources,
            "enabled": enabled_epg_sources,
        },
        "channels": total_epg_channels,
        "programs": total_epg_programs,
        "coverage": {
            "percentage": round(epg_coverage_pct, 1),
            "mapped_channels": mapped_channels,
            **({"error": epg_coverage_error} if epg_coverage_error else {}),
        },
    }

    # Scheduler stats
    if _scheduler:
        scheduler_status = _scheduler.get_status()
        stats["scheduler"] = {
            "running": scheduler_status.get("running", False),
            "intervals": {
                "accounts": scheduler_status.get("syncs", {}).get("accounts", {}).get("interval_hours"),
                "epg": scheduler_status.get("syncs", {}).get("epg", {}).get("interval_hours"),
                "fcc": scheduler_status.get("syncs", {}).get("fcc", {}).get("interval_hours"),
            },
            "next_syncs": {
                "accounts": scheduler_status.get("syncs", {}).get("accounts", {}).get("next_sync"),
                "epg": scheduler_status.get("syncs", {}).get("epg", {}).get("next_sync"),
            },
            "last_syncs": {
                "accounts": scheduler_status.get("syncs", {}).get("accounts", {}).get("last_sync"),
                "epg": scheduler_status.get("syncs", {}).get("epg", {}).get("last_sync"),
            },
        }
    else:
        stats["scheduler"] = {"running": False}

    # Sync metadata (additional context)
    try:
        last_account_sync = SyncMetadata.get("last_account_sync")
        last_epg_sync = SyncMetadata.get("last_epg_sync")
        stats["last_full_sync"] = {
            "accounts": last_account_sync,
            "epg": last_epg_sync,
        }
    except Exception as e:
        logger.warning("Failed to load sync metadata for overview stats: %s", e, exc_info=True)
        stats["last_full_sync"] = {
            "accounts": None,
            "epg": None,
            "error": str(e),
        }

    return jsonify(stats)
