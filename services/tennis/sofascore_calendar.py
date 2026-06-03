"""
SofaScore tennis schedule → CalendarEvent mapping (slice 1 — not wired to enrichment).

Public endpoint (no API key):
  https://api.sofascore.com/api/v1/sport/tennis/scheduled-events/{YYYY-MM-DD}

Included status types: notstarted, inprogress, finished.
Excluded: cancelled, postponed, suspended, interrupted (no reliable PPV match window).
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from models.sync import Settings
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED
from services.thesportsdb_calendar_scraper import (
    MAX_API_SUPPLEMENT_DAYS_AHEAD,
    MAX_API_SUPPLEMENT_DAYS_BACK,
    CalendarEvent,
)

logger = logging.getLogger(__name__)

EVENT_SOURCE_SOFASCORE = "sofascore"
CACHE_TTL_SECONDS = 12 * 3600
REQUEST_TIMEOUT = 30
MIN_REQUEST_INTERVAL_SECONDS = 3.0  # ~20 req/min with jitter

SCHEDULED_EVENTS_URL = "https://api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date_str}"

_INCLUDED_STATUS_TYPES = frozenset({"notstarted", "inprogress", "finished"})
_EXCLUDED_STATUS_TYPES = frozenset({"cancelled", "postponed", "suspended", "interrupted", "canceled"})

_sofascore_cache: Dict[str, Tuple[List[CalendarEvent], float]] = {}
_last_request_time = 0.0


def _sofascore_calendar_enabled() -> bool:
    return Settings.get(SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, "false").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


def _is_date_in_window(date_str: str) -> bool:
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    delta = (target - today).days
    return -MAX_API_SUPPLEMENT_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD


def _rate_limit() -> None:
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    wait = MIN_REQUEST_INTERVAL_SECONDS - elapsed
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.25))
    _last_request_time = time.time()


def _parse_start_timestamp(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _team_display_name(team: dict) -> Optional[str]:
    if not isinstance(team, dict):
        return None
    return team.get("name") or team.get("shortName")


def _tournament_label(event: dict) -> str:
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    return unique.get("name") or tournament.get("name") or ""


def scheduled_event_to_calendar_event(event: dict, *, fallback_date: str) -> Optional[CalendarEvent]:
    """Map one SofaScore scheduled event to CalendarEvent."""
    event_id = event.get("id")
    if event_id is None:
        return None

    status = event.get("status") or {}
    status_type = (status.get("type") or "").lower()
    if status_type in _EXCLUDED_STATUS_TYPES:
        return None
    if status_type and status_type not in _INCLUDED_STATUS_TYPES:
        return None

    home_name = _team_display_name(event.get("homeTeam") or {})
    away_name = _team_display_name(event.get("awayTeam") or {})
    if not home_name or not away_name:
        return None

    scheduled = _parse_start_timestamp(event.get("startTimestamp"))
    if scheduled:
        time_utc = scheduled.strftime("%H:%M")
        date_str = scheduled.strftime("%Y-%m-%d")
    else:
        time_utc = ""
        date_str = fallback_date

    if date_str != fallback_date:
        return None

    tournament = _tournament_label(event)
    category = ((event.get("tournament") or {}).get("category") or {}).get("name") or ""
    league_name = tournament
    if category and category not in league_name:
        league_name = f"{tournament} | {category}" if tournament else category

    cal = CalendarEvent(
        event_id=str(event_id),
        event_name=f"{home_name} vs {away_name}",
        league_name=league_name,
        time_utc=time_utc,
        date=date_str,
        home_team=home_name,
        away_team=away_name,
        source=EVENT_SOURCE_SOFASCORE,
        sport="Tennis",
    )
    if scheduled:
        cal._scheduled_at_cached = scheduled.replace(tzinfo=None)
        cal._scheduled_at_computed = True
    return cal


def parse_tennis_scheduled_events(payload: dict, *, date_str: str) -> List[CalendarEvent]:
    """Parse SofaScore scheduled-events JSON into CalendarEvent rows."""
    events: List[CalendarEvent] = []
    for raw in payload.get("events") or []:
        if not isinstance(raw, dict):
            continue
        ev = scheduled_event_to_calendar_event(raw, fallback_date=date_str)
        if ev:
            events.append(ev)
    return events


def fetch_scheduled_events(
    sport: str,
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> dict:
    """Fetch raw SofaScore scheduled-events JSON for a sport and calendar date."""
    if not _sofascore_calendar_enabled():
        return {"events": []}

    if not _is_date_in_window(date_str):
        return {"events": []}

    url = SCHEDULED_EVENTS_URL.format(sport=sport, date_str=date_str)
    _rate_limit()
    http = session or requests
    try:
        response = http.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "iptv-proxy-v2/1.0"},
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("SofaScore scheduled-events fetch failed for %s %s: %s", sport, date_str, exc)
        return {"events": []}


def fetch_tennis_events_for_date(
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> List[CalendarEvent]:
    """Fetch tennis matches for a calendar date. Returns [] when feature flag is off."""
    if not _sofascore_calendar_enabled():
        return []

    if not _is_date_in_window(date_str):
        return []

    cache_key = f"sofascore-tennis:{date_str}"
    if not force_refresh and cache_key in _sofascore_cache:
        cached_events, cached_at = _sofascore_cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return list(cached_events)

    payload = fetch_scheduled_events("tennis", date_str, force_refresh=force_refresh, session=session)
    events = parse_tennis_scheduled_events(payload, date_str=date_str)
    _sofascore_cache[cache_key] = (events, time.time())
    logger.debug("Fetched %d SofaScore tennis events for %s", len(events), date_str)
    return events


def clear_sofascore_tennis_calendar_cache() -> None:
    _sofascore_cache.clear()
