"""
ESPN tennis scoreboard → CalendarEvent mapping.

Uses the public ESPN site API (no auth):
  https://site.api.espn.com/apis/site/v2/sports/tennis/{wta|atp}/scoreboard?dates=YYYYMMDD
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from services.thesportsdb_calendar_scraper import (
    MAX_API_SUPPLEMENT_DAYS_AHEAD,
    MAX_API_SUPPLEMENT_DAYS_BACK,
    CalendarEvent,
)

logger = logging.getLogger(__name__)

EVENT_SOURCE_ESPN = "espn"
CACHE_TTL_SECONDS = 3600
REQUEST_TIMEOUT = 30

ESPN_TENNIS_TOURS = ("wta", "atp")
SCOREBOARD_URL_TEMPLATE = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={date_yyyymmdd}"

_espn_cache: Dict[str, Tuple[List[CalendarEvent], float]] = {}


def _is_date_in_espn_window(date_str: str) -> bool:
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    delta = (target - today).days
    return -MAX_API_SUPPLEMENT_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD


def _parse_competition_datetime(raw: Optional[str]) -> Optional[datetime]:
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


def _grouping_display_name(grouping: dict) -> str:
    nested = grouping.get("grouping") or {}
    return nested.get("displayName") or grouping.get("displayName") or ""


def _competitor_side_name(competitor: dict) -> Optional[str]:
    athlete = competitor.get("athlete") or {}
    if athlete.get("displayName"):
        return athlete["displayName"]
    roster = competitor.get("roster") or {}
    if roster.get("displayName"):
        return roster["displayName"]
    athletes = roster.get("athletes") or []
    names: List[str] = []
    for a in athletes:
        if not isinstance(a, dict):
            continue
        display = a.get("displayName")
        if display:
            names.append(str(display))
    if len(names) >= 2:
        return " / ".join(names[:2])
    if names:
        return names[0]
    return None


def competition_to_calendar_event(
    competition: dict,
    *,
    tournament_name: str,
    grouping_name: str,
    tour: str,
    fallback_date: str,
) -> Optional[CalendarEvent]:
    """Map one ESPN tennis competition to CalendarEvent."""
    comp_id = competition.get("id")
    if comp_id is None:
        return None

    competitors = competition.get("competitors") or []
    if len(competitors) < 2:
        return None

    home_name: Optional[str] = None
    away_name: Optional[str] = None
    for comp in competitors:
        side = (comp.get("homeAway") or "").lower()
        name = _competitor_side_name(comp)
        if not name:
            continue
        if side == "home":
            home_name = name
        elif side == "away":
            away_name = name

    if not home_name or not away_name:
        ordered = [_competitor_side_name(c) for c in competitors]
        ordered = [n for n in ordered if n]
        if len(ordered) < 2:
            return None
        away_name, home_name = ordered[0], ordered[1]

    scheduled = _parse_competition_datetime(competition.get("date") or competition.get("startDate"))
    if scheduled:
        time_utc = scheduled.strftime("%H:%M")
        date_str = scheduled.strftime("%Y-%m-%d")
    else:
        time_utc = ""
        date_str = fallback_date

    league_parts = [tournament_name]
    if grouping_name:
        league_parts.append(grouping_name)
    if tour:
        league_parts.append(tour.upper())
    league_name = " | ".join(p for p in league_parts if p)

    event_name = f"{away_name} vs {home_name}"
    event = CalendarEvent(
        event_id=str(comp_id),
        event_name=event_name,
        league_name=league_name,
        time_utc=time_utc,
        date=date_str,
        home_team=home_name,
        away_team=away_name,
        source=EVENT_SOURCE_ESPN,
        sport="Tennis",
    )
    if scheduled:
        event._scheduled_at_cached = scheduled.replace(tzinfo=None)
        event._scheduled_at_computed = True
    return event


def parse_scoreboard_payload(payload: dict, *, tour: str, fallback_date: str) -> List[CalendarEvent]:
    """Parse ESPN tennis scoreboard JSON into CalendarEvent rows for one tour."""
    events: List[CalendarEvent] = []
    for tournament in payload.get("events") or []:
        if not isinstance(tournament, dict):
            continue
        tournament_name = tournament.get("name") or tournament.get("shortName") or ""
        for grouping in tournament.get("groupings") or []:
            if not isinstance(grouping, dict):
                continue
            grouping_name = _grouping_display_name(grouping)
            for competition in grouping.get("competitions") or []:
                if not isinstance(competition, dict):
                    continue
                ev = competition_to_calendar_event(
                    competition,
                    tournament_name=tournament_name,
                    grouping_name=grouping_name,
                    tour=tour,
                    fallback_date=fallback_date,
                )
                if ev and ev.date == fallback_date:
                    events.append(ev)
    return events


def _fetch_scoreboard(tour: str, date_str: str, session: Optional[requests.Session] = None) -> dict:
    yyyymmdd = date_str.replace("-", "")
    url = SCOREBOARD_URL_TEMPLATE.format(tour=tour, date_yyyymmdd=yyyymmdd)
    http = session or requests
    response = http.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_espn_tennis_events_for_date(
    date_str: str,
    *,
    force_refresh: bool = False,
    session: Optional[requests.Session] = None,
) -> List[CalendarEvent]:
    """Fetch WTA and ATP tennis matches for a calendar date."""
    if not _is_date_in_espn_window(date_str):
        return []

    cache_key = f"espn-tennis:{date_str}"
    if not force_refresh and cache_key in _espn_cache:
        cached_events, cached_at = _espn_cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return list(cached_events)

    events: List[CalendarEvent] = []
    try:
        for tour in ESPN_TENNIS_TOURS:
            payload = _fetch_scoreboard(tour, date_str, session=session)
            events.extend(parse_scoreboard_payload(payload, tour=tour, fallback_date=date_str))
    except Exception as exc:
        logger.warning("ESPN tennis scoreboard fetch failed for %s: %s", date_str, exc)
        if cache_key in _espn_cache:
            return list(_espn_cache[cache_key][0])
        return []

    _espn_cache[cache_key] = (events, time.time())
    logger.debug("Fetched %d ESPN tennis events for %s", len(events), date_str)
    return events


def clear_espn_tennis_calendar_cache() -> None:
    _espn_cache.clear()
