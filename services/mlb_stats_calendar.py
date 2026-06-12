"""
MiLB schedule → CalendarEvent mapping via MLB Stats API.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from services.mlb_stats_api import MILB_SPORT_IDS, get_mlb_stats_client
from services.thesportsdb_calendar_scraper import (
    MAX_API_SUPPLEMENT_DAYS_AHEAD,
    MAX_API_SUPPLEMENT_DAYS_BACK,
    CalendarEvent,
)

logger = logging.getLogger(__name__)

EVENT_SOURCE_MLB_STATS = "mlb_stats_api"
CACHE_TTL_SECONDS = 3600

_milb_cache: Dict[str, Tuple[List[CalendarEvent], float]] = {}


def _is_date_in_milb_window(date_str: str) -> bool:
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    delta = (target - today).days
    return -MAX_API_SUPPLEMENT_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD


def _parse_game_datetime(game: dict) -> Optional[datetime]:
    raw = game.get("gameDate")
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def game_to_calendar_event(game: dict) -> Optional[CalendarEvent]:
    """Map one MLB Stats API schedule game to CalendarEvent."""
    game_pk = game.get("gamePk")
    if game_pk is None:
        return None

    teams = game.get("teams") or {}
    home = (teams.get("home") or {}).get("team") or {}
    away = (teams.get("away") or {}).get("team") or {}
    home_name = home.get("name") or ""
    away_name = away.get("name") or ""
    if not home_name or not away_name:
        return None

    scheduled = _parse_game_datetime(game)
    official = game.get("officialDate") or ""
    if scheduled:
        time_utc = scheduled.strftime("%H:%M")
        date_str = official or scheduled.strftime("%Y-%m-%d")
    else:
        time_utc = ""
        date_str = official

    level = game.get("_level") or "MiLB"
    league = (game.get("league") or {}).get("name") or ""
    league_name = f"MiLB {level}"
    if league:
        league_name = f"{league_name} | {league}"

    event_name = f"{away_name} vs {home_name}"
    event = CalendarEvent(
        event_id=str(game_pk),
        event_name=event_name,
        league_name=league_name,
        time_utc=time_utc,
        date=date_str,
        home_team=home_name,
        away_team=away_name,
        home_team_id=str(home.get("id")) if home.get("id") is not None else None,
        away_team_id=str(away.get("id")) if away.get("id") is not None else None,
        source=EVENT_SOURCE_MLB_STATS,
        sport="MiLB",
    )
    if scheduled:
        event._scheduled_at_cached = scheduled.replace(tzinfo=None)
        event._scheduled_at_computed = True
    return event


def fetch_milb_events_for_date(
    date_str: str,
    *,
    force_refresh: bool = False,
) -> List[CalendarEvent]:
    """Fetch MiLB games for a date across sportIds 11–14."""
    if not _is_date_in_milb_window(date_str):
        return []

    cache_key = f"milb:{date_str}"
    stale_events: Optional[List[CalendarEvent]] = None
    if not force_refresh and cache_key in _milb_cache:
        cached_events, cached_at = _milb_cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return list(cached_events)
        stale_events = cached_events
        del _milb_cache[cache_key]

    client = get_mlb_stats_client()
    events: List[CalendarEvent] = []
    try:
        games = client.get_milb_schedule_for_date(date_str, sport_ids=MILB_SPORT_IDS)
        for game in games:
            ev = game_to_calendar_event(game)
            if ev:
                events.append(ev)
    except Exception as exc:
        logger.warning("MiLB schedule fetch failed for %s: %s", date_str, exc)
        if stale_events is not None:
            return list(stale_events)
        if cache_key in _milb_cache:
            return list(_milb_cache[cache_key][0])
        return []

    _milb_cache[cache_key] = (events, time.time())
    logger.debug("Fetched %d MiLB events for %s", len(events), date_str)
    return events


def clear_milb_calendar_cache() -> None:
    _milb_cache.clear()
