"""
Deprecated shim — import from ``services.ppv.calendar_providers.sofascore`` instead.

Retained for one release so existing imports keep working without behavior change.
"""

from services.ppv.calendar_providers.sofascore import *  # noqa: F401,F403
from services.ppv.calendar_providers.sofascore import (
    EVENT_SOURCE_SOFASCORE,
    MIN_REQUEST_INTERVAL_SECONDS,
    clear_sofascore_football_calendar_cache,
    clear_sofascore_tennis_calendar_cache,
    fetch_football_events_for_date,
    fetch_scheduled_events,
    fetch_tennis_events_for_date,
    get_sofascore_calendar_stats,
    parse_football_scheduled_events,
    parse_tennis_scheduled_events,
    scheduled_event_to_calendar_event,
)
from services.ppv.calendar_providers.sofascore.client import http_get as _http_get
from services.ppv.calendar_providers.sofascore.client import fetch_scheduled_events_http as _fetch_scheduled_events_http

__all__ = [
    "EVENT_SOURCE_SOFASCORE",
    "MIN_REQUEST_INTERVAL_SECONDS",
    "_fetch_scheduled_events_http",
    "_http_get",
    "clear_sofascore_football_calendar_cache",
    "clear_sofascore_tennis_calendar_cache",
    "fetch_football_events_for_date",
    "fetch_scheduled_events",
    "fetch_tennis_events_for_date",
    "get_sofascore_calendar_stats",
    "parse_football_scheduled_events",
    "parse_tennis_scheduled_events",
    "scheduled_event_to_calendar_event",
]
