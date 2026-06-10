"""SofaScore football scheduled-events parser."""

from __future__ import annotations

from typing import List

from services.ppv.calendar_providers.sofascore.parser_common import build_calendar_event
from services.thesportsdb_calendar_scraper import CalendarEvent


def parse_football_scheduled_events(payload: dict, *, date_str: str) -> List[CalendarEvent]:
    events: List[CalendarEvent] = []
    for raw in payload.get("events") or []:
        if not isinstance(raw, dict):
            continue
        ev = build_calendar_event(raw, fallback_date=date_str, sport="Soccer", strict_date_match=False)
        if ev:
            events.append(ev)
    return events
