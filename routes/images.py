"""
Image caching proxy routes

Serves prefetched icons only. Icons are registered and fetched during
provider channel sync and EPG sync — not on arbitrary client requests.
"""

import logging

from flask import Blueprint, Response, jsonify, request

from error_handling import handle_errors
from services.datetime_utils import serialize_utc_iso
from services.image_cache_service import get_image_cache

logger = logging.getLogger(__name__)

# Create blueprint
images_bp = Blueprint("images", __name__)


@images_bp.route("/icon/<url_hash>")
@handle_errors(return_json=False, default_message="Error serving cached image")
def serve_cached_icon(url_hash):
    """Serve a prefetched icon by URL hash.

    Only icons fetched during provider/EPG sync are available. This route
    never initiates outbound HTTP requests (SSRF-safe).
    """
    from models import CachedImage

    if not url_hash or len(url_hash) != 64 or not all(c in "0123456789abcdef" for c in url_hash.lower()):
        return Response("Invalid image hash", status=400)

    cache = get_image_cache()
    cached = CachedImage.query.filter_by(url_hash=url_hash, status="cached").first()
    if not cached:
        return Response("Image not found", status=404)

    result = cache.get_cached_image(cached.original_url)
    if not result:
        return Response("Image not found", status=404)

    image_data, content_type = result
    return Response(
        image_data,
        mimetype=content_type,
        headers={
            "Cache-Control": "public, max-age=604800",
            "X-Cache": "HIT",
        },
    )


@images_bp.route("/api/image-cache/stats", methods=["GET"])
def get_cache_stats():
    """Get image cache statistics."""
    cache = get_image_cache()
    return jsonify(cache.get_stats())


@images_bp.route("/api/image-cache/cleanup", methods=["POST"])
@handle_errors(return_json=True, default_message="Error cleaning up cache")
def cleanup_cache():
    """Clean up cache entries.

    Query parameters:
    - delete_files: "true" to also delete files from disk (default: true)
    - status: Clean entries with specific status (e.g., "error", "failed")
    - all: "true" to clear all cache entries
    """
    delete_files = request.args.get("delete_files", "true").lower() == "true"
    status_filter = request.args.get("status")
    clear_all = request.args.get("all", "false").lower() == "true"

    cache = get_image_cache()

    if clear_all:
        count = cache.clear_all(delete_files=delete_files)
        message = f"Cleared {count} cache entries"
    elif status_filter:
        count = cache.cleanup_by_status(status_filter, delete_files=delete_files)
        message = f"Cleaned up {count} entries with status '{status_filter}'"
    else:
        count = cache.cleanup_expired(delete_files=delete_files)
        message = f"Cleaned up {count} expired cache entries"

    return jsonify(
        {
            "success": True,
            "removed_count": count,
            "message": message,
        }
    )


@images_bp.route("/api/image-cache/entries", methods=["GET"])
def list_cache_entries():
    """List cached images with pagination.

    Query parameters:
    - status: Filter by status (cached, error, expired)
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    from models import CachedImage

    status = request.args.get("status")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    query = CachedImage.query

    if status:
        query = query.filter_by(status=status)

    total = query.count()
    entries = query.order_by(CachedImage.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "entries": [
                {
                    "id": e.id,
                    "url_hash": e.url_hash,
                    "original_url": e.original_url[:100] + "..." if len(e.original_url) > 100 else e.original_url,
                    "content_type": e.content_type,
                    "file_size": e.file_size,
                    "status": e.status,
                    "hit_count": e.hit_count,
                    "fetch_count": e.fetch_count,
                    "fetched_at": serialize_utc_iso(e.fetched_at),
                    "expires_at": serialize_utc_iso(e.expires_at),
                    "last_accessed_at": serialize_utc_iso(e.last_accessed_at),
                }
                for e in entries
            ],
        }
    )


@images_bp.route("/api/image-cache/entries/<int:entry_id>", methods=["DELETE"])
@handle_errors(return_json=True, default_message="Error deleting cache entry")
def delete_cache_entry(entry_id):
    """Delete a specific cache entry."""
    from models import CachedImage, db

    cached = db.get_or_404(CachedImage, entry_id)
    cache = get_image_cache()

    if cached.file_path:
        file_path = cache.cache_dir / cached.file_path
        if file_path.exists():
            file_path.unlink()

    db.session.delete(cached)
    db.session.commit()

    return jsonify({"success": True, "message": "Cache entry deleted"})
