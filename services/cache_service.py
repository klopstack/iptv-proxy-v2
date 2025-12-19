"""
Cache service for storing API responses
"""

import time
import logging

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
        return time.time() > entry['expires_at']
    
    def get_cached_streams(self, account_id):
        """Get cached streams for account"""
        key = self._cache_key(account_id, 'streams')
        if key in self.cache and not self._is_expired(self.cache[key]):
            logger.debug(f"Cache hit for streams: {key}")
            return self.cache[key]['data']
        return None
    
    def cache_streams(self, account_id, streams, ttl=None):
        """Cache streams for account"""
        key = self._cache_key(account_id, 'streams')
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            'data': streams,
            'expires_at': time.time() + ttl
        }
        logger.debug(f"Cached streams for {key}: {len(streams)} items")
    
    def get_cached_categories(self, account_id):
        """Get cached categories for account"""
        key = self._cache_key(account_id, 'categories')
        if key in self.cache and not self._is_expired(self.cache[key]):
            logger.debug(f"Cache hit for categories: {key}")
            return self.cache[key]['data']
        return None
    
    def cache_categories(self, account_id, categories, ttl=None):
        """Cache categories for account"""
        key = self._cache_key(account_id, 'categories')
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            'data': categories,
            'expires_at': time.time() + ttl
        }
        logger.debug(f"Cached categories for {key}: {len(categories)} items")
    
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
