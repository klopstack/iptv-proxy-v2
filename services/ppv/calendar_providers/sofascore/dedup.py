"""SofaScore dedup strategies keyed by sport slug."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from services.thesportsdb_calendar_scraper import CalendarEvent

logger = logging.getLogger(__name__)


def _tennis_matchup_key(event: CalendarEvent) -> Optional[Tuple[str, str, str]]:
    sport_lower = (event.sport or "").lower()
    if sport_lower != "tennis":
        return None
    if not event.home_team or not event.away_team:
        return None
    pair = tuple(sorted([event.home_team.strip().lower(), event.away_team.strip().lower()]))
    return (event.date, pair[0], pair[1])


def _football_matchup_key(event: CalendarEvent) -> Optional[Tuple[str, str, str]]:
    sport_lower = (event.sport or "").lower()
    if sport_lower not in ("soccer", "football"):
        return None
    if not event.home_team or not event.away_team:
        return None
    pair = tuple(sorted([event.home_team.strip().lower(), event.away_team.strip().lower()]))
    return (event.date, pair[0], pair[1])


def filter_without_espn_duplicates(
    primary_events: List[CalendarEvent],
    sofascore_events: List[CalendarEvent],
) -> List[CalendarEvent]:
    """Keep SofaScore tennis rows that do not duplicate an ESPN (player pair, day) fixture."""
    espn_keys = {key for key in (_tennis_matchup_key(event) for event in primary_events) if key is not None}
    kept: List[CalendarEvent] = []
    for event in sofascore_events:
        key = _tennis_matchup_key(event)
        if key is not None and key in espn_keys:
            logger.debug(
                "Skipping SofaScore tennis duplicate of ESPN: %s vs %s on %s",
                event.home_team,
                event.away_team,
                event.date,
            )
            continue
        kept.append(event)
    return kept


def filter_without_tsdb_duplicates(
    primary_events: List[CalendarEvent],
    sofascore_events: List[CalendarEvent],
) -> List[CalendarEvent]:
    """Keep SofaScore football rows that do not duplicate a TheSportsDB fixture."""
    tsdb_keys = {key for key in (_football_matchup_key(event) for event in primary_events) if key is not None}
    kept: List[CalendarEvent] = []
    for event in sofascore_events:
        key = _football_matchup_key(event)
        if key is not None and key in tsdb_keys:
            logger.debug(
                "Skipping SofaScore football duplicate of TheSportsDB: %s vs %s on %s",
                event.home_team,
                event.away_team,
                event.date,
            )
            continue
        kept.append(event)
    return kept


def _hockey_matchup_key(event: CalendarEvent) -> Optional[Tuple[str, str, str]]:
    sport_lower = (event.sport or "").lower()
    if sport_lower not in ("ice hockey", "hockey", "nhl"):
        return None
    if not event.home_team or not event.away_team:
        return None
    pair = tuple(sorted([event.home_team.strip().lower(), event.away_team.strip().lower()]))
    return (event.date, pair[0], pair[1])


def filter_without_tsdb_hockey_duplicates(
    primary_events: List[CalendarEvent],
    sofascore_events: List[CalendarEvent],
) -> List[CalendarEvent]:
    """Keep SofaScore hockey rows that do not duplicate a TheSportsDB fixture."""
    tsdb_keys = {key for key in (_hockey_matchup_key(event) for event in primary_events) if key is not None}
    kept: List[CalendarEvent] = []
    for event in sofascore_events:
        key = _hockey_matchup_key(event)
        if key is not None and key in tsdb_keys:
            logger.debug(
                "Skipping SofaScore hockey duplicate of TheSportsDB: %s vs %s on %s",
                event.home_team,
                event.away_team,
                event.date,
            )
            continue
        kept.append(event)
    return kept


def dedup_sofascore_events(
    slug: str,
    *,
    primary_events: List[CalendarEvent],
    sofascore_events: List[CalendarEvent],
) -> List[CalendarEvent]:
    if slug == "tennis":
        return filter_without_espn_duplicates(primary_events, sofascore_events)
    if slug == "football":
        return filter_without_tsdb_duplicates(primary_events, sofascore_events)
    if slug == "ice-hockey":
        return filter_without_tsdb_hockey_duplicates(primary_events, sofascore_events)
    return list(sofascore_events)
