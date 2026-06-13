"""
Process and in-process cache statistics for dashboard observability.

Aggregates cheap, read-only counts from the various singleton caches so the
dashboard can correlate RSS growth with calendar events, IPTV stream payloads,
and active ffmpeg streams. Each collector is isolated so one failing import or
uninitialized singleton never breaks the dashboard summary.
"""

import logging
import os
import resource
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def get_process_rss_bytes() -> Optional[int]:
    """Return resident set size of the current process in bytes, or None."""
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ValueError, OSError):
        return None
    # ru_maxrss is kilobytes on Linux, bytes on macOS.
    if sys.platform == "darwin":
        return int(usage)
    return int(usage) * 1024


def _iptv_cache_stats() -> Dict[str, Any]:
    from services.cache_service import get_cache_service

    return get_cache_service().get_stats()


def _calendar_cache_stats() -> Dict[str, Any]:
    from services.thesportsdb_calendar_scraper import get_calendar_scraper

    stats = get_calendar_scraper().get_cache_stats()
    return {
        "total_entries": stats.get("total_entries", 0),
        "valid_entries": stats.get("valid_entries", 0),
        "expired_entries": stats.get("expired_entries", 0),
        "total_events": stats.get("total_events", 0),
    }


def _reverse_matcher_stats() -> Dict[str, Any]:
    from services.reverse_event_matcher import get_reverse_matcher

    matcher = get_reverse_matcher()
    stats = matcher.get_stats()
    total_events = stats.get("total_events")
    if total_events is None:
        total_events = getattr(matcher, "_last_event_count", 0)
    return {
        "events_loaded": stats.get("events_loaded", False),
        "total_events": total_events,
    }


def _sportsipy_stats() -> Dict[str, Any]:
    from services.sportsipy_service import get_sportsipy_service

    stats = get_sportsipy_service().get_stats()
    return {"cache_size": stats.get("cache_size", 0)}


def _context_cache_stats() -> Dict[str, Any]:
    from services.ppv.context.cache import get_cache

    return get_cache().stats()


def _sofascore_stats() -> Dict[str, Any]:
    from services.ppv.calendar_providers.sofascore import client

    return client.cache_stats()


def _stream_stats() -> Dict[str, Any]:
    """Read existing stream service stats without creating the singleton."""
    import services.mediaflow_stream_service as mediaflow_mod
    import services.transcode_stream_service as transcode_mod

    active_streams = 0
    total_subscribers = 0
    for mod in (mediaflow_mod, transcode_mod):
        service = getattr(mod, "_mediaflow_service", None) or getattr(mod, "_transcode_service", None)
        get_stats = getattr(service, "get_stats", None) if service else None
        if get_stats is None:
            continue
        stats = get_stats()
        active_streams += stats.get("active_streams", 0)
        total_subscribers += stats.get("total_subscribers", 0)
    return {"active_streams": active_streams, "total_subscribers": total_subscribers}


def build_memory_stats() -> Dict[str, Any]:
    """Aggregate process RSS and per-cache entry counts for the dashboard."""
    collectors = {
        "iptv": _iptv_cache_stats,
        "calendar": _calendar_cache_stats,
        "reverse_matcher": _reverse_matcher_stats,
        "sportsipy": _sportsipy_stats,
        "context": _context_cache_stats,
        "sofascore": _sofascore_stats,
        "streams": _stream_stats,
    }
    caches: Dict[str, Any] = {}
    for name, collector in collectors.items():
        try:
            caches[name] = collector()
        except Exception as exc:
            logger.debug("memory stats collector %s failed: %s", name, exc)
            caches[name] = {"error": str(exc)}

    return {
        "process": {"rss_bytes": get_process_rss_bytes(), "pid": os.getpid()},
        "caches": caches,
    }
