"""
Tests for the CacheService helper
"""
import services.cache_service as cache_service
from services.cache_service import CacheService


def test_cache_streams_and_categories(monkeypatch):
    """Cache entries are returned while TTL is valid."""
    cache = CacheService(default_ttl=30)
    fixed_time = 1_000.0
    monkeypatch.setattr(cache_service.time, "time", lambda: fixed_time)

    cache.cache_streams(1, ["alpha", "beta"])
    cache.cache_categories(1, [{"id": 1, "name": "news"}])

    assert cache.get_cached_streams(1) == ["alpha", "beta"]
    assert cache.get_cached_categories(1) == [{"id": 1, "name": "news"}]


def test_cache_expiration(monkeypatch):
    """Expired cache entries are treated as missing."""
    cache = CacheService(default_ttl=1)
    start_time = 2_000.0

    monkeypatch.setattr(cache_service.time, "time", lambda: start_time)
    cache.cache_streams(2, ["stale"], ttl=1)

    # Still valid at start_time
    assert cache.get_cached_streams(2) == ["stale"]

    # Advance time beyond expiry
    monkeypatch.setattr(cache_service.time, "time", lambda: start_time + 2)
    assert cache.get_cached_streams(2) is None


def test_cache_clear_helpers(monkeypatch):
    """Account-specific and global clears remove the right entries."""
    cache = CacheService(default_ttl=10)
    monkeypatch.setattr(cache_service.time, "time", lambda: 5_000.0)

    cache.cache_streams(1, ["one"])
    cache.cache_categories(1, ["cat-one"])
    cache.cache_streams(2, ["two"])

    cache.clear_account_cache(1)
    assert cache.get_cached_streams(1) is None
    assert cache.get_cached_categories(1) is None
    assert cache.get_cached_streams(2) == ["two"]

    cache.clear_all()
    assert cache.cache == {}
