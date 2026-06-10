"""Sportsipy ncaab supplement for Flo replay archive college basketball (TODO 131)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from models.ppv import SportsTeam
from services.ppv.replay_providers import METADATA_KEY_REPLAY_ARCHIVE
from services.thesportsdb_calendar_scraper import CalendarEvent

logger = logging.getLogger(__name__)

EVENT_SOURCE_SPORTSIPY = "sportsipy"
_COLLEGE_BASKETBALL_HINT = re.compile(r"-\s*(Mens|Womens)\s*-", re.IGNORECASE)


def is_college_basketball_replay(channel_name: str, extraction: dict) -> bool:
    """True when Flo-style replay channel is men's/women's college basketball."""
    if not extraction.get(METADATA_KEY_REPLAY_ARCHIVE):
        return False
    return bool(_COLLEGE_BASKETBALL_HINT.search(channel_name or ""))


def _resolve_ncaab_abbrev(team_name: str) -> Optional[str]:
    team = SportsTeam.resolve_team(team_name, sport=SportsTeam.SPORT_NCAAB)
    if team:
        return team.abbreviation
    return None


def _display_name_for_abbrev(abbrev: str) -> str:
    team = SportsTeam.query.filter_by(sport=SportsTeam.SPORT_NCAAB, abbreviation=abbrev).first()
    if team:
        return team.name
    return abbrev


def sportsipy_event_to_calendar_event(
    *,
    event_id: str,
    home_team: str,
    away_team: str,
    date_str: str,
    scheduled_at: Optional[datetime],
    league: str = "NCAA Basketball",
) -> CalendarEvent:
    time_utc = scheduled_at.strftime("%H:%M") if scheduled_at else ""
    cal = CalendarEvent(
        event_id=event_id,
        event_name=f"{home_team} vs {away_team}",
        league_name=league,
        time_utc=time_utc,
        date=date_str,
        home_team=home_team,
        away_team=away_team,
        source=EVENT_SOURCE_SPORTSIPY,
        sport="NCAA Basketball",
    )
    if scheduled_at:
        cal._scheduled_at_cached = scheduled_at.replace(tzinfo=None)
        cal._scheduled_at_computed = True
    return cal


def fetch_ncaab_replay_events(
    channel_name: str,
    extraction: dict,
    date_str: str,
    *,
    schedule_fetcher=None,
) -> List[CalendarEvent]:
    """
    Per-team Sportsipy lookup for DIII/college basketball replay channels.

    Not merged into day-bucket calendar scrape; invoked from match_pipeline when
    SofaScore basketball has no NCAA/DIII coverage (130 spike).
    """
    if not is_college_basketball_replay(channel_name, extraction):
        return []

    competitors = extraction.get("competitors")
    if not competitors or len(competitors) != 2:
        return []

    side1, side2 = competitors[0], competitors[1]
    abbrev1 = _resolve_ncaab_abbrev(side1)
    abbrev2 = _resolve_ncaab_abbrev(side2)
    if not abbrev1:
        logger.debug("Sportsipy ncaab supplement: no abbrev for %r", side1)
        return []

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []

    if schedule_fetcher is None:
        from services.sportsipy_service import get_sportsipy_service

        schedule_fetcher = get_sportsipy_service().get_team_schedule

    schedule = schedule_fetcher(abbrev1, "ncaab", year=target.year)
    if not schedule:
        return []

    results: List[CalendarEvent] = []
    for game in schedule:
        if not game.date or game.date.date() != target.date():
            continue
        if abbrev2:
            opponents = {game.home_team, game.away_team}
            if abbrev2 not in opponents:
                continue
        home_abbrev = game.home_team if game.location == "Home" else game.away_team
        away_abbrev = game.away_team if game.location == "Home" else game.home_team
        home_display = _display_name_for_abbrev(home_abbrev)
        away_display = _display_name_for_abbrev(away_abbrev)
        # Prefer channel competitor strings when they match a side (better matcher overlap)
        home_display, away_display = _align_display_names(
            (side1, side2),
            home_display,
            away_display,
            home_abbrev,
            away_abbrev,
        )
        results.append(
            sportsipy_event_to_calendar_event(
                event_id=game.event_id,
                home_team=home_display,
                away_team=away_display,
                date_str=date_str,
                scheduled_at=game.date,
            )
        )
    return results


def _align_display_names(
    competitors: Tuple[str, str],
    home_display: str,
    away_display: str,
    home_abbrev: str,
    away_abbrev: str,
) -> Tuple[str, str]:
    """Use channel competitor labels when they map to home/away abbrevs."""
    side1, side2 = competitors
    side1_abbrev = _resolve_ncaab_abbrev(side1)
    side2_abbrev = _resolve_ncaab_abbrev(side2)
    if side1_abbrev == home_abbrev:
        home_display = side1
    elif side2_abbrev == home_abbrev:
        home_display = side2
    if side1_abbrev == away_abbrev:
        away_display = side1
    elif side2_abbrev == away_abbrev:
        away_display = side2
    return home_display, away_display
