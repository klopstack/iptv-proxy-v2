"""
Image Cache Service

Caches external icon/logo images locally to reduce external API calls
and avoid hitting daily image quotas (e.g., Schedules Direct limits).

Features:
- Content-addressable storage using URL hash
- Configurable cache TTL (default 7 days)
- Automatic cleanup of expired entries
- Graceful degradation (returns original URL on error)
- Thread-safe operations
"""

import hashlib
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CACHE_TTL_DAYS = 7
DEFAULT_CACHE_DIR = "/app/data/image_cache"
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB max
FETCH_TIMEOUT = 10  # seconds
USER_AGENT = "IPTV-Proxy/2.0 (Image Cache)"

# Allowed content types for caching
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}


class ImageCacheService:
    """Service for caching external images locally"""

    _instance: Optional["ImageCacheService"] = None
    _lock = threading.Lock()

    def __init__(self, cache_dir: Optional[str] = None, ttl_days: int = DEFAULT_CACHE_TTL_DAYS):
        """Initialize image cache service.

        Args:
            cache_dir: Directory for cached images (default: /app/data/image_cache)
            ttl_days: Days before cache entries expire (default: 7)
        """
        cache_path = cache_dir or os.getenv("IMAGE_CACHE_DIR") or DEFAULT_CACHE_DIR
        self.cache_dir = Path(cache_path)
        self.ttl_days = ttl_days
        self._ensure_cache_dir()
        self._fetch_lock = threading.Lock()

    @classmethod
    def get_instance(
        cls, cache_dir: Optional[str] = None, ttl_days: int = DEFAULT_CACHE_TTL_DAYS
    ) -> "ImageCacheService":
        """Get singleton instance of the service."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(cache_dir, ttl_days)
        return cls._instance

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Image cache directory: {self.cache_dir}")

    @staticmethod
    def hash_url(url: str) -> str:
        """Generate SHA-256 hash of URL for content-addressable storage."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get_file_path(self, url_hash: str, extension: str = "") -> Path:
        """Get file path for cached image.

        Uses two-level directory structure to avoid too many files in one directory.
        """
        # Use first 2 chars as subdirectory
        subdir = url_hash[:2]
        filename = url_hash + extension
        return self.cache_dir / subdir / filename

    def get_cached_image(self, url: str) -> Optional[Tuple[bytes, str]]:
        """Get cached image data if available and not expired.

        Args:
            url: Original image URL

        Returns:
            Tuple of (image_bytes, content_type) or None if not cached/expired
        """
        from models import CachedImage, db

        url_hash = self.hash_url(url)

        try:
            cached = CachedImage.query.filter_by(url_hash=url_hash, status="cached").first()

            if not cached:
                return None

            # Check if expired
            if cached.expires_at and datetime.utcnow() > cached.expires_at:
                logger.debug(f"Cache expired for {url_hash[:8]}...")
                return None

            # Read from disk
            file_path = self.cache_dir / cached.file_path
            if not file_path.exists():
                logger.warning(f"Cache file missing: {file_path}")
                cached.status = "error"
                cached.error_message = "File missing from disk"
                db.session.commit()
                return None

            # Update access stats
            cached.hit_count += 1
            cached.last_accessed_at = datetime.utcnow()
            db.session.commit()

            return file_path.read_bytes(), cached.content_type or "image/png"

        except Exception as e:
            logger.error(f"Error reading cached image {url_hash[:8]}...: {e}")
            return None

    def cache_image(self, url: str, force_refresh: bool = False) -> Optional[str]:
        """Fetch and cache an image from URL.

        Args:
            url: Image URL to fetch
            force_refresh: Force re-fetch even if cached

        Returns:
            URL hash if successful, None on failure
        """
        from models import CachedImage, db

        if not url or not self._is_valid_url(url):
            return None

        url_hash = self.hash_url(url)

        with self._fetch_lock:
            # Check if already cached (unless forcing refresh)
            if not force_refresh:
                existing = CachedImage.query.filter_by(url_hash=url_hash).first()
                if existing and existing.status == "cached":
                    if not existing.expires_at or datetime.utcnow() < existing.expires_at:
                        return url_hash

            # Fetch image
            try:
                image_data, content_type = self._fetch_image(url)
                if not image_data or not content_type:
                    return None

                # Determine file extension
                extension = self._get_extension(content_type)
                file_path = self.get_file_path(url_hash, extension)

                # Ensure subdirectory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Write to disk
                file_path.write_bytes(image_data)

                # Update database
                expires_at = datetime.utcnow() + timedelta(days=self.ttl_days)
                relative_path = str(file_path.relative_to(self.cache_dir))

                cached = CachedImage.query.filter_by(url_hash=url_hash).first()
                if cached:
                    cached.status = "cached"
                    cached.content_type = content_type
                    cached.file_size = len(image_data)
                    cached.file_path = relative_path
                    cached.fetched_at = datetime.utcnow()
                    cached.expires_at = expires_at
                    cached.fetch_count += 1
                    cached.error_message = None
                else:
                    cached = CachedImage(
                        url_hash=url_hash,
                        original_url=url,
                        content_type=content_type,
                        file_size=len(image_data),
                        file_path=relative_path,
                        status="cached",
                        fetched_at=datetime.utcnow(),
                        expires_at=expires_at,
                        fetch_count=1,
                    )
                    db.session.add(cached)

                db.session.commit()
                logger.debug(f"Cached image {url_hash[:8]}... ({len(image_data)} bytes)")
                return url_hash

            except Exception as e:
                logger.error(f"Error caching image from {url}: {e}")
                # Record error in database
                try:
                    cached = CachedImage.query.filter_by(url_hash=url_hash).first()
                    if cached:
                        cached.status = "error"
                        cached.error_message = str(e)[:500]
                    else:
                        cached = CachedImage(
                            url_hash=url_hash,
                            original_url=url,
                            status="error",
                            error_message=str(e)[:500],
                        )
                        db.session.add(cached)
                    db.session.commit()
                except Exception:
                    pass
                return None

    def _fetch_image(self, url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Fetch image from URL.

        Returns:
            Tuple of (image_bytes, content_type) or (None, None) on failure
        """
        try:
            response = requests.get(
                url,
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                stream=True,
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()

            # Validate content type
            if content_type not in ALLOWED_CONTENT_TYPES:
                # Try to detect from content
                content_type = self._detect_content_type(response.content[:16])
                if content_type not in ALLOWED_CONTENT_TYPES:
                    logger.warning(f"Unsupported content type: {content_type} for {url}")
                    return None, None

            # Check size limit
            content_length = int(response.headers.get("Content-Length", 0))
            if content_length > MAX_IMAGE_SIZE:
                logger.warning(f"Image too large: {content_length} bytes for {url}")
                return None, None

            # Read content with size limit
            image_data = b""
            for chunk in response.iter_content(chunk_size=8192):
                image_data += chunk
                if len(image_data) > MAX_IMAGE_SIZE:
                    logger.warning(f"Image exceeded max size during download: {url}")
                    return None, None

            return image_data, content_type

        except requests.RequestException as e:
            logger.error(f"Failed to fetch image from {url}: {e}")
            return None, None

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for caching."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    def _get_extension(self, content_type: str) -> str:
        """Get file extension from content type."""
        extensions = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
        }
        return extensions.get(content_type, ".img")

    def _detect_content_type(self, header_bytes: bytes) -> str:
        """Detect image type from file header bytes."""
        if header_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        elif header_bytes[:2] == b"\xff\xd8":
            return "image/jpeg"
        elif header_bytes[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        elif header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"WEBP":
            return "image/webp"
        elif header_bytes[:4] == b"\x00\x00\x01\x00":
            return "image/x-icon"
        return "application/octet-stream"

    def get_or_cache(self, url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get image from cache or fetch and cache it.

        Args:
            url: Image URL

        Returns:
            Tuple of (image_bytes, content_type) or (None, None) on failure
        """
        # Try cache first
        result = self.get_cached_image(url)
        if result:
            return result

        # Cache it
        url_hash = self.cache_image(url)
        if url_hash:
            cached_result = self.get_cached_image(url)
            if cached_result:
                return cached_result

        return None, None

    def get_proxy_url(self, original_url: str, base_url: str) -> str:
        """Get proxy URL for an image.

        If caching is enabled and URL is valid, returns a proxy URL.
        Otherwise returns the original URL.

        Args:
            original_url: Original external image URL
            base_url: Base URL of this proxy (e.g., "http://localhost:8000")

        Returns:
            Proxy URL or original URL
        """
        if not original_url or not self._is_valid_url(original_url):
            return original_url or ""

        url_hash = self.hash_url(original_url)
        return f"{base_url.rstrip('/')}/icon/{url_hash}"

    def cleanup_expired(self, delete_files: bool = True) -> int:
        """Clean up expired cache entries.

        Args:
            delete_files: Also delete files from disk

        Returns:
            Number of entries cleaned up
        """
        from models import CachedImage, db

        count = 0
        try:
            expired = CachedImage.query.filter(
                CachedImage.expires_at < datetime.utcnow(), CachedImage.status == "cached"
            ).all()

            for cached in expired:
                if delete_files and cached.file_path:
                    file_path = self.cache_dir / cached.file_path
                    if file_path.exists():
                        file_path.unlink()

                cached.status = "expired"
                count += 1

            db.session.commit()
            logger.info(f"Cleaned up {count} expired cache entries")

        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")

        return count

    def get_stats(self) -> dict:
        """Get cache statistics."""
        from models import CachedImage, db

        try:
            total = CachedImage.query.count()
            cached = CachedImage.query.filter_by(status="cached").count()
            errors = CachedImage.query.filter_by(status="error").count()
            expired = CachedImage.query.filter_by(status="expired").count()

            total_size = db.session.query(db.func.sum(CachedImage.file_size)).filter_by(status="cached").scalar() or 0

            total_hits = db.session.query(db.func.sum(CachedImage.hit_count)).scalar() or 0

            return {
                "total_entries": total,
                "cached": cached,
                "errors": errors,
                "expired": expired,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_hits": total_hits,
                "cache_dir": str(self.cache_dir),
                "ttl_days": self.ttl_days,
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}


# Global instance (lazy initialization)
_image_cache: Optional[ImageCacheService] = None


def get_image_cache() -> ImageCacheService:
    """Get the global image cache service instance."""
    global _image_cache
    if _image_cache is None:
        _image_cache = ImageCacheService.get_instance()
    return _image_cache
