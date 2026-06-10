"""SofaScore ice-hockey scheduled-events parser (AHL, OHL, QMJHL, ECHL, WHL)."""

from __future__ import annotations

from typing import List

from services.ppv.calendar_providers.sofascore.parser_common import tournament_label
from services.ppv.calendar_providers.sofascore.parser_team import parse_team_scheduled_events
from services.ppv.sport_registry import sofascore_hockey_league_label, sofascore_hockey_sport_label
from services.thesportsdb_calendar_scraper import CalendarEvent


def _league_label(raw: dict) -> str:
    tournament = tournament_label(raw)
    return sofascore_hockey_league_label(tournament)


def parse_ice_hockey_scheduled_events(payload: dict, *, date_str: str) -> List[CalendarEvent]:
    return parse_team_scheduled_events(
        payload,
        date_str=date_str,
        sport_key="nhl",
        sport_label=sofascore_hockey_sport_label(),
        league_resolver=_league_label,
        strict_date_match=False,
    )
