"""
Additional API routes for sync, tags, and cache management
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import Account, Channel, ChannelTag, Tag, db
from services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Create blueprint
api_bp = Blueprint("api", __name__)

# Initialize cache service
cache_service = CacheService()


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

            result.append({"id": tag.id, "name": tag.name, "created_at": tag.created_at.isoformat(), "channel_count": count})
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
    - limit (default 50): Number of results to return
    - offset (default 0): Offset for pagination
    """
    account_id = request.args.get("account_id", type=int)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Build base query
    query = db.session.query(Channel).filter(Channel.is_active == True, Channel.is_visible == True)

    # Apply account filter if specified
    if account_id:
        Account.query.get_or_404(account_id)  # Validate account exists
        query = query.filter(Channel.account_id == account_id)

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
                "category_id": ch.category_id,
                "is_visible": ch.is_visible,
                "tags": tag_map.get(ch.stream_id, []),
            }
        )

    return jsonify({"total": total, "offset": offset, "limit": limit, "showing": len(result), "channels": result, "has_more": offset + limit < total})
