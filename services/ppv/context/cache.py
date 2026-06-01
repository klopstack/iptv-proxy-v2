"""
Shared result cache for context data providers.

Cache keys are tuples of (provider_name, data_type, *identifiers).
TTLs differ by data type so standings (slow-moving) are cached longer
than event notes (game-day specific).

The cache is in-process only (dict + timestamps).  Because the detail
fetcher already runs in a single background thread, concurrent writes
are rare.  A threading lock is used for safety.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from services.ppv.context.base import DataType

logger = logging.getLogger(__name__)

# TTL in seconds per data type
CACHE_TTL: Dict[DataType, int] = {
    DataType.STANDINGS: 6 * 3600,  # 6 hours
    DataType.HEAD_TO_HEAD: 24 * 3600,  # 24 hours — historical data rarely changes
    DataType.TEAM_FORM: 2 * 3600,  # 2 hours
    DataType.EVENT_NOTES: 30 * 60,  # 30 minutes — game-day context updates
    DataType.FIGHTER_RECORD: 24 * 3600,  # 24 hours
}

DEFAULT_TTL = 3600  # fallback for unknown data types

CacheKey = Tuple  # variable-length tuple


class ContextCache:
    """Thread-safe in-process cache for provider results."""

    def __init__(self) -> None:
        self._store: Dict[CacheKey, Tuple[Any, float]] = {}  # key -> (value, expiry_ts)
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> Optional[Any]:
        """Return cached value or None if missing / expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: CacheKey, value: Any, data_type: Optional[DataType] = None) -> None:
        """Store a value with TTL derived from data_type."""
        ttl = CACHE_TTL.get(data_type, DEFAULT_TTL) if data_type else DEFAULT_TTL
        expiry = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (value, expiry)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, int]:
        """Return simple stats for observability."""
        now = time.monotonic()
        with self._lock:
            total = len(self._store)
            expired = sum(1 for _, exp in self._store.values() if now > exp)
        return {"total_entries": total, "expired_entries": expired, "live_entries": total - expired}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache: Optional[ContextCache] = None


def get_cache() -> ContextCache:
    """Return the global context cache (created on first call)."""
    global _cache
    if _cache is None:
        _cache = ContextCache()
    return _cache


def make_standings_key(provider: str, sport: str, league: str, season: Optional[str] = None) -> CacheKey:
    return (provider, DataType.STANDINGS, sport.lower(), league.lower(), season or "current")


def make_h2h_key(provider: str, sport: str, home: str, away: str) -> CacheKey:
    # Sort team names so (A, B) and (B, A) share the same cache entry
    pair = tuple(sorted([home.lower(), away.lower()]))
    return (provider, DataType.HEAD_TO_HEAD, sport.lower()) + pair


def make_form_key(provider: str, sport: str, team: str) -> CacheKey:
    return (provider, DataType.TEAM_FORM, sport.lower(), team.lower())


def make_notes_key(provider: str, sport: str, home: str, away: str, date: Optional[str] = None) -> CacheKey:
    return (provider, DataType.EVENT_NOTES, sport.lower(), home.lower(), away.lower(), date or "")
