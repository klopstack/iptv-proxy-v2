"""Generic SofaScore HTTP client with cache and rate limiting."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from services.ppv.calendar_providers.sofascore.constants import (
    CACHE_TTL_SECONDS,
    MIN_REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT,
    SCHEDULED_EVENTS_URL,
)
from services.ppv.constants import REPLAY_CALENDAR_DAYS_BACK
from services.thesportsdb_calendar_scraper import (
    MAX_API_SUPPLEMENT_DAYS_AHEAD,
    MAX_API_SUPPLEMENT_DAYS_BACK,
    CalendarEvent,
)

logger = logging.getLogger(__name__)

_sofascore_cache: Dict[str, Tuple[List[CalendarEvent], float]] = {}
_last_request_time = 0.0


def is_date_in_window(date_str: str, *, replay: bool = False) -> bool:
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    delta = (target - today).days
    if replay:
        return -REPLAY_CALENDAR_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD
    return -MAX_API_SUPPLEMENT_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD


def is_date_in_replay_window(date_str: str) -> bool:
    """Return True when date is within replay archive lookback (400d default)."""
    return is_date_in_window(date_str, replay=True)


def rate_limit() -> None:
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    wait = MIN_REQUEST_INTERVAL_SECONDS - elapsed
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.25))
    _last_request_time = time.time()


def http_get(
    url: str,
    *,
    timeout: int,
    headers: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
):
    """HTTP GET with Chrome TLS fingerprint via curl_cffi; falls back to requests."""
    hdrs = headers or {}
    if session is not None:
        return session.get(url, timeout=timeout, headers=hdrs)
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.get(url, timeout=timeout, headers=hdrs, impersonate="chrome")
    except ImportError:
        return requests.get(url, timeout=timeout, headers=hdrs)


def fetch_scheduled_events_http(
    sport_slug: str,
    date_str: str,
    *,
    session: Optional[requests.Session] = None,
    replay: bool = False,
) -> dict:
    """Fetch raw SofaScore scheduled-events JSON (no feature-flag gate)."""
    if not is_date_in_window(date_str, replay=replay):
        return {"events": []}

    url = SCHEDULED_EVENTS_URL.format(sport=sport_slug, date_str=date_str)
    rate_limit()
    try:
        response = http_get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "iptv-proxy-v2/1.0"},
            session=session,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("SofaScore scheduled-events fetch failed for %s %s: %s", sport_slug, date_str, exc)
        return {"events": []}


def get_cached_events(cache_key: str) -> Optional[List[CalendarEvent]]:
    if cache_key not in _sofascore_cache:
        return None
    cached_events, cached_at = _sofascore_cache[cache_key]
    if time.time() - cached_at >= CACHE_TTL_SECONDS:
        return None
    return list(cached_events)


def store_cached_events(cache_key: str, events: List[CalendarEvent]) -> None:
    _sofascore_cache[cache_key] = (events, time.time())


def clear_cache() -> None:
    _sofascore_cache.clear()


def cache_stats() -> Dict[str, Any]:
    return {
        "cache_entries": len(_sofascore_cache),
        "cached_events": sum(len(events) for events, _ in _sofascore_cache.values()),
    }


def cached_slug_event_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cache_key, (events, _) in _sofascore_cache.items():
        if not cache_key.startswith("sofascore-"):
            continue
        slug = cache_key.removeprefix("sofascore-").split(":", 1)[0]
        counts[slug] = counts.get(slug, 0) + len(events)
    return counts
