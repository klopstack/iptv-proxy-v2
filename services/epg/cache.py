"""
EPG XML Cache Service

Provides filesystem-based caching of EPG XML data to avoid re-fetching
from external sources during EPG generation.

The cache stores raw XMLTV XML (optionally gzipped) keyed by EpgSource ID.
Cache is updated during EPG sync operations.
"""
import gzip
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

# Default cache directory - can be overridden via environment variable
DEFAULT_CACHE_DIR = "/app/data/epg_cache"


def get_cache_dir() -> Path:
    """Get the EPG cache directory, creating it if necessary."""
    cache_dir = Path(os.getenv("EPG_CACHE_DIR", DEFAULT_CACHE_DIR))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cache_path(source_id: int) -> Path:
    """Get the cache file path for an EPG source."""
    return get_cache_dir() / f"epg_source_{source_id}.xml.gz"


def get_cache_meta_path(source_id: int) -> Path:
    """Get the metadata file path for an EPG source cache."""
    return get_cache_dir() / f"epg_source_{source_id}.meta"


def save_to_cache(source_id: int, xml_content: bytes) -> bool:
    """
    Save EPG XML content to cache.

    The content is gzip-compressed for storage efficiency.

    Args:
        source_id: EpgSource ID
        xml_content: Raw XMLTV XML bytes

    Returns:
        True if save was successful, False otherwise
    """
    try:
        cache_path = get_cache_path(source_id)
        meta_path = get_cache_meta_path(source_id)

        # Compress and save
        compressed = gzip.compress(xml_content)
        cache_path.write_bytes(compressed)

        # Save metadata
        content_hash = hashlib.md5(xml_content).hexdigest()
        meta = {
            "source_id": source_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "original_size": len(xml_content),
            "compressed_size": len(compressed),
            "content_hash": content_hash,
        }
        import json

        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info(
            f"Cached EPG for source {source_id}: {len(xml_content)} bytes "
            f"-> {len(compressed)} bytes ({len(compressed) * 100 // len(xml_content)}% compressed)"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to cache EPG for source {source_id}: {e}")
        return False


def load_from_cache(source_id: int) -> Optional[bytes]:
    """
    Load EPG XML content from cache.

    Args:
        source_id: EpgSource ID

    Returns:
        Raw XMLTV XML bytes, or None if not cached or cache read fails
    """
    try:
        cache_path = get_cache_path(source_id)

        if not cache_path.exists():
            logger.debug(f"No cache found for EPG source {source_id}")
            return None

        compressed = cache_path.read_bytes()
        xml_content = gzip.decompress(compressed)

        logger.debug(f"Loaded EPG from cache for source {source_id}: {len(xml_content)} bytes")
        return xml_content

    except Exception as e:
        logger.error(f"Failed to load cached EPG for source {source_id}: {e}")
        return None


def get_cache_info(source_id: int) -> Optional[dict]:
    """
    Get metadata about cached EPG for a source.

    Args:
        source_id: EpgSource ID

    Returns:
        Dict with cache metadata, or None if not cached
    """
    try:
        meta_path = get_cache_meta_path(source_id)

        if not meta_path.exists():
            return None

        import json

        return json.loads(meta_path.read_text())

    except Exception as e:
        logger.error(f"Failed to read cache metadata for source {source_id}: {e}")
        return None


def is_cache_valid(source_id: int, max_age_hours: int = 24) -> bool:
    """
    Check if cached EPG is still valid (not expired).

    Args:
        source_id: EpgSource ID
        max_age_hours: Maximum cache age in hours

    Returns:
        True if cache exists and is not expired
    """
    info = get_cache_info(source_id)
    if not info:
        return False

    try:
        cached_at = datetime.fromisoformat(info["cached_at"])
        age = datetime.now(timezone.utc) - cached_at
        return age.total_seconds() < (max_age_hours * 3600)
    except (ValueError, TypeError, OSError) as e:
        logger.warning("Invalid cache metadata for source %s: %s", source_id, e)
        return False


def delete_cache(source_id: int) -> bool:
    """
    Delete cached EPG for a source.

    Args:
        source_id: EpgSource ID

    Returns:
        True if deletion was successful or cache didn't exist
    """
    try:
        cache_path = get_cache_path(source_id)
        meta_path = get_cache_meta_path(source_id)

        if cache_path.exists():
            cache_path.unlink()
        if meta_path.exists():
            meta_path.unlink()

        logger.info(f"Deleted EPG cache for source {source_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete EPG cache for source {source_id}: {e}")
        return False


def clear_all_cache() -> int:
    """
    Clear all cached EPG data.

    Returns:
        Number of cache files deleted
    """
    try:
        cache_dir = get_cache_dir()
        deleted = 0

        for path in cache_dir.glob("epg_source_*"):
            try:
                path.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete {path}: {e}")

        logger.info(f"Cleared EPG cache: {deleted} files deleted")
        return deleted

    except Exception as e:
        logger.error(f"Failed to clear EPG cache: {e}")
        return 0


def get_cache_stats() -> dict:
    """
    Get statistics about the EPG cache.

    Returns:
        Dict with cache statistics
    """
    try:
        cache_dir = get_cache_dir()

        total_size = 0
        file_count = 0
        oldest = None
        newest = None

        for path in cache_dir.glob("epg_source_*.xml.gz"):
            file_count += 1
            total_size += path.stat().st_size

            meta_path = path.with_suffix("").with_suffix(".meta")
            if meta_path.exists():
                import json

                meta = json.loads(meta_path.read_text())
                cached_at = datetime.fromisoformat(meta.get("cached_at", ""))

                if oldest is None or cached_at < oldest:
                    oldest = cached_at
                if newest is None or cached_at > newest:
                    newest = cached_at

        return {
            "cache_dir": str(cache_dir),
            "file_count": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_cache": serialize_utc_iso(oldest),
            "newest_cache": serialize_utc_iso(newest),
        }

    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {"error": str(e)}
