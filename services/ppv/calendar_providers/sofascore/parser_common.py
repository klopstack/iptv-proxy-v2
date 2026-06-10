"""Shared SofaScore JSON → CalendarEvent helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from services.ppv.calendar_providers.sofascore.constants import _EXCLUDED_STATUS_TYPES, _INCLUDED_STATUS_TYPES
from services.thesportsdb_calendar_scraper import CalendarEvent


def parse_start_timestamp(ts: Optional[int]) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def team_display_name(team: dict) -> Optional[str]:
    if not isinstance(team, dict):
        return None
    return team.get("name") or team.get("shortName")


def tournament_label(event: dict) -> str:
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    return unique.get("name") or tournament.get("name") or ""


def event_status_allowed(event: dict) -> bool:
    status = event.get("status") or {}
    status_type = (status.get("type") or "").lower()
    if status_type in _EXCLUDED_STATUS_TYPES:
        return False
    if status_type and status_type not in _INCLUDED_STATUS_TYPES:
        return False
    return True


def build_calendar_event(
    event: dict,
    *,
    fallback_date: str,
    sport: str,
    strict_date_match: bool = True,
) -> Optional[CalendarEvent]:
    """Map one SofaScore scheduled event to CalendarEvent."""
    from services.ppv.calendar_providers.sofascore.constants import EVENT_SOURCE_SOFASCORE

    event_id = event.get("id")
    if event_id is None or not event_status_allowed(event):
        return None

    home_name = team_display_name(event.get("homeTeam") or {})
    away_name = team_display_name(event.get("awayTeam") or {})
    if not home_name or not away_name:
        return None

    scheduled = parse_start_timestamp(event.get("startTimestamp"))
    if scheduled:
        time_utc = scheduled.strftime("%H:%M")
        date_str = scheduled.strftime("%Y-%m-%d")
    else:
        time_utc = ""
        date_str = fallback_date

    if strict_date_match and date_str != fallback_date:
        return None

    if not strict_date_match:
        date_str = fallback_date

    tournament = tournament_label(event)
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
        sport=sport,
    )
    if scheduled:
        cal._scheduled_at_cached = scheduled.replace(tzinfo=None)
        cal._scheduled_at_computed = True
    return cal
