"""Generic SofaScore multi-sport calendar provider."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from services.ppv.calendar_providers.sofascore import client, registry
from services.ppv.calendar_providers.sofascore.constants import (
    EVENT_SOURCE_SOFASCORE,
    MIN_REQUEST_INTERVAL_SECONDS,
)
from services.ppv.calendar_providers.sofascore.dedup import (
    filter_without_espn_duplicates,
    filter_without_tsdb_duplicates,
)
from services.ppv.calendar_providers.sofascore.parser_football import parse_football_scheduled_events
from services.ppv.calendar_providers.sofascore.parser_tennis import parse_tennis_scheduled_events
from services.ppv.calendar_providers.sofascore.registry import (
    enabled_slugs,
    slug_allowed_for_sport_filter,
    slug_enabled,
)
from services.thesportsdb_calendar_scraper import CalendarEvent

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_SOURCE_SOFASCORE",
    "MIN_REQUEST_INTERVAL_SECONDS",
    "fetch_events_for_slug",
    "fetch_football_events_for_date",
    "fetch_scheduled_events",
    "fetch_tennis_events_for_date",
    "filter_without_espn_duplicates",
    "filter_without_tsdb_duplicates",
    "get_sofascore_calendar_stats",
    "parse_football_scheduled_events",
    "parse_tennis_scheduled_events",
    "scheduled_event_to_calendar_event",
    "clear_sofascore_tennis_calendar_cache",
    "clear_sofascore_football_calendar_cache",
    "enabled_slugs",
]


def scheduled_event_to_calendar_event(event: dict, *, fallback_date: str, sport: str = "Tennis"):
    from services.ppv.calendar_providers.sofascore.parser_common import build_calendar_event

    strict = sport.lower() != "soccer"
    return build_calendar_event(event, fallback_date=fallback_date, sport=sport, strict_date_match=strict)


def fetch_scheduled_events(
    sport_slug: str,
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> dict:
    """Fetch raw JSON when the slug's feature flag is enabled (tennis gate for legacy API)."""
    if sport_slug == "tennis" and not slug_enabled("tennis"):
        return {"events": []}
    return client.fetch_scheduled_events_http(sport_slug, date_str, session=session)


def fetch_events_for_slug(
    slug: str,
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> List[CalendarEvent]:
    """Fetch parsed CalendarEvent rows for one enabled SofaScore slug."""
    config = registry.SLUG_REGISTRY.get(slug)
    if not config or not slug_enabled(slug):
        return []
    if not client.is_date_in_window(date_str):
        return []

    cache_key = f"sofascore-{slug}:{date_str}"
    if not force_refresh:
        cached = client.get_cached_events(cache_key)
        if cached is not None:
            return cached

    payload = client.fetch_scheduled_events_http(slug, date_str, session=session)
    events = config.parser(payload, date_str)
    client.store_cached_events(cache_key, events)
    logger.debug("Fetched %d SofaScore %s events for %s", len(events), slug, date_str)
    return events


def fetch_tennis_events_for_date(
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> List[CalendarEvent]:
    return fetch_events_for_slug("tennis", date_str, force_refresh=force_refresh, session=session)


def fetch_football_events_for_date(
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> List[CalendarEvent]:
    return fetch_events_for_slug("football", date_str, force_refresh=force_refresh, session=session)


def clear_sofascore_tennis_calendar_cache() -> None:
    client.clear_cache()


def clear_sofascore_football_calendar_cache() -> None:
    client.clear_cache()


def get_sofascore_calendar_stats() -> Dict[str, Any]:
    stats = client.cache_stats()
    stats.update(
        {
            "enabled": slug_enabled("tennis"),
            "football_enabled": slug_enabled("football"),
            "enabled_slugs": enabled_slugs(),
        }
    )
    return stats
