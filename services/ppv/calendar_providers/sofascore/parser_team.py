"""Shared SofaScore team-sport scheduled-events parser."""

from __future__ import annotations

from typing import Callable, List, Optional

from services.ppv.calendar_providers.sofascore.parser_common import build_calendar_event
from services.thesportsdb_calendar_scraper import CalendarEvent


def parse_team_scheduled_events(
    payload: dict,
    *,
    date_str: str,
    sport_key: str,
    sport_label: str,
    league_resolver: Optional[Callable[[dict], str]] = None,
    strict_date_match: bool = True,
) -> List[CalendarEvent]:
    """Parse team-vs-team SofaScore rows into CalendarEvent objects."""
    events: List[CalendarEvent] = []
    for raw in payload.get("events") or []:
        if not isinstance(raw, dict):
            continue
        ev = build_calendar_event(raw, fallback_date=date_str, sport=sport_label, strict_date_match=strict_date_match)
        if not ev:
            continue
        if league_resolver:
            league = league_resolver(raw)
            if league:
                ev.league_name = league
        ev.sport = sport_label
        events.append(ev)
    return events
