"""
Cache service for storing API responses
"""

import logging
import time

logger = logging.getLogger(__name__)


class CacheService:
    """Simple in-memory cache with TTL"""

    def __init__(self, default_ttl=3600):
        self.cache = {}
        self.default_ttl = default_ttl

    def _cache_key(self, account_id, data_type):
        """Generate cache key"""
        return f"account_{account_id}_{data_type}"

    def _is_expired(self, entry):
        """Check if cache entry is expired"""
        return time.time() > entry["expires_at"]

    def get_cached_streams(self, account_id):
        """Get cached streams for account"""
        key = self._cache_key(account_id, "streams")
        entry = self.cache.get(key)
        if entry is not None:
            if not self._is_expired(entry):
                logger.debug(f"Cache hit for streams: {key}")
                return entry["data"]
            del self.cache[key]
        return None

    def cache_streams(self, account_id, streams, ttl=None):
        """Cache streams for account"""
        self.purge_expired()
        key = self._cache_key(account_id, "streams")
        ttl = ttl or self.default_ttl
        self.cache[key] = {"data": streams, "expires_at": time.time() + ttl}
        logger.debug(f"Cached streams for {key}: {len(streams)} items")

    def get_cached_categories(self, account_id):
        """Get cached categories for account"""
        key = self._cache_key(account_id, "categories")
        entry = self.cache.get(key)
        if entry is not None:
            if not self._is_expired(entry):
                logger.debug(f"Cache hit for categories: {key}")
                return entry["data"]
            del self.cache[key]
        return None

    def cache_categories(self, account_id, categories, ttl=None):
        """Cache categories for account"""
        self.purge_expired()
        key = self._cache_key(account_id, "categories")
        ttl = ttl or self.default_ttl
        self.cache[key] = {"data": categories, "expires_at": time.time() + ttl}
        logger.debug(f"Cached categories for {key}: {len(categories)} items")

    def purge_expired(self):
        """Remove all expired entries; return the number removed."""
        expired_keys = [key for key, entry in self.cache.items() if self._is_expired(entry)]
        for key in expired_keys:
            del self.cache[key]
        if expired_keys:
            logger.debug(f"Purged {len(expired_keys)} expired cache entries")
        return len(expired_keys)

    def get_stats(self):
        """Return entry counts for observability."""
        total = len(self.cache)
        expired = sum(1 for entry in self.cache.values() if self._is_expired(entry))
        return {
            "total_entries": total,
            "expired_entries": expired,
            "live_entries": total - expired,
        }

    def clear_account_cache(self, account_id):
        """Clear all cache for account"""
        keys_to_remove = [k for k in self.cache.keys() if k.startswith(f"account_{account_id}_")]
        for key in keys_to_remove:
            del self.cache[key]
        logger.info(f"Cleared cache for account {account_id}")

    def clear_all(self):
        """Clear all cache"""
        self.cache.clear()
        logger.info("Cleared all cache")


def init_cache_service(app):
    """Register a single CacheService instance on the Flask app."""
    if "cache_service" not in app.extensions:
        app.extensions["cache_service"] = CacheService()
    return app.extensions["cache_service"]


def get_cache_service():
    """Return the app-scoped CacheService (requires application context)."""
    from flask import current_app

    return current_app.extensions["cache_service"]


class _LazyCacheService:
    """Delegates to app-scoped CacheService; patchable in tests via routes.*.cache_service."""

    def __getattr__(self, name):
        return getattr(get_cache_service(), name)


cache_service = _LazyCacheService()
