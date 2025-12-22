"""
Image caching proxy routes

Serves cached images to reduce external API calls and avoid
hitting daily image quotas (e.g., Schedules Direct limits).
"""

import logging

from flask import Blueprint, Response, jsonify, request

from error_handling import handle_errors
from services.image_cache_service import get_image_cache

logger = logging.getLogger(__name__)

# Create blueprint
images_bp = Blueprint("images", __name__)


@images_bp.route("/icon/<url_hash>")
@handle_errors(return_json=False, default_message="Error serving cached image")
def serve_cached_icon(url_hash):
    """Serve a cached icon by URL hash.

    If the image is cached, serve it directly.
    If not cached but we have the original URL, fetch and cache it.
    """
    from models import CachedImage

    # Validate hash format (should be 64 hex chars)
    if not url_hash or len(url_hash) != 64 or not all(c in "0123456789abcdef" for c in url_hash.lower()):
        return Response("Invalid image hash", status=400)

    cache = get_image_cache()

    # Look up the original URL from database
    cached = CachedImage.query.filter_by(url_hash=url_hash).first()

    if cached:
        # Try to get from cache
        result = cache.get_cached_image(cached.original_url)
        if result:
            image_data, content_type = result
            return Response(
                image_data,
                mimetype=content_type,
                headers={
                    "Cache-Control": "public, max-age=604800",  # 7 days
                    "X-Cache": "HIT",
                },
            )

        # Not in cache (expired or missing), try to re-fetch
        if cached.original_url:
            url_hash = cache.cache_image(cached.original_url)
            if url_hash:
                result = cache.get_cached_image(cached.original_url)
                if result:
                    image_data, content_type = result
                    return Response(
                        image_data,
                        mimetype=content_type,
                        headers={
                            "Cache-Control": "public, max-age=604800",
                            "X-Cache": "MISS",
                        },
                    )

    # Image not found or couldn't be fetched
    return Response("Image not found", status=404)


@images_bp.route("/icon/fetch", methods=["POST"])
@handle_errors(return_json=True, default_message="Error fetching image")
def fetch_and_cache_icon():
    """Fetch and cache an image from a URL.

    Request body:
    {
        "url": "https://example.com/icon.png"
    }

    Returns:
    {
        "success": true,
        "url_hash": "abc123...",
        "proxy_url": "/icon/abc123..."
    }
    """
    data = request.json or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    cache = get_image_cache()

    url_hash = cache.cache_image(url)
    if url_hash:
        return jsonify(
            {
                "success": True,
                "url_hash": url_hash,
                "proxy_url": f"/icon/{url_hash}",
            }
        )
    else:
        return jsonify({"success": False, "error": "Failed to fetch or cache image"}), 500


@images_bp.route("/api/image-cache/stats", methods=["GET"])
def get_cache_stats():
    """Get image cache statistics."""
    cache = get_image_cache()
    return jsonify(cache.get_stats())


@images_bp.route("/api/image-cache/cleanup", methods=["POST"])
@handle_errors(return_json=True, default_message="Error cleaning up cache")
def cleanup_cache():
    """Clean up expired cache entries.

    Query parameters:
    - delete_files: "true" to also delete files from disk (default: true)
    """
    delete_files = request.args.get("delete_files", "true").lower() == "true"

    cache = get_image_cache()
    count = cache.cleanup_expired(delete_files=delete_files)

    return jsonify(
        {
            "success": True,
            "cleaned_up": count,
            "message": f"Cleaned up {count} expired cache entries",
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
                    "fetched_at": e.fetched_at.isoformat() if e.fetched_at else None,
                    "expires_at": e.expires_at.isoformat() if e.expires_at else None,
                    "last_accessed_at": e.last_accessed_at.isoformat() if e.last_accessed_at else None,
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

    cached = CachedImage.query.get_or_404(entry_id)
    cache = get_image_cache()

    # Delete file if it exists
    if cached.file_path:
        file_path = cache.cache_dir / cached.file_path
        if file_path.exists():
            file_path.unlink()

    db.session.delete(cached)
    db.session.commit()

    return jsonify({"success": True, "message": "Cache entry deleted"})
