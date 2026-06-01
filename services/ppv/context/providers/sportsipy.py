"""
sportsipy context data provider.

Uses the existing ``SportsipyService`` to pull team schedules and form data
from Sports Reference pages.  Covers NFL, NBA, NHL, MLB and is especially
useful for college sports and minor leagues where ESPN coverage is thin.

Results are cached aggressively (24-hour TTL) because Sports Reference
scraping is slow and rate-limited.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from services.ppv.context.base import ContextDataProvider, DataType
from services.ppv.context.cache import get_cache, make_form_key, make_h2h_key

logger = logging.getLogger(__name__)

_SUPPORTED_SPORTS: Set[str] = {
    "American Football", "NFL",
    "Basketball", "NBA",
    "Ice Hockey", "NHL",
    "Baseball", "MLB",
    "NCAAF", "NCAAB",
    "MiLB",
}

# Map normalised sport name → sportsipy key used by SportsipyService
_SPORT_KEY: Dict[str, str] = {
    "american football": "nfl",
    "nfl": "nfl",
    "basketball": "nba",
    "nba": "nba",
    "ice hockey": "nhl",
    "nhl": "nhl",
    "baseball": "mlb",
    "mlb": "mlb",
    "ncaaf": "nfl",   # best available in sportsipy
    "ncaab": "nba",
    "milb": "mlb",
}


def _sport_key(sport: str) -> Optional[str]:
    return _SPORT_KEY.get(sport.lower())


class SportsipyContextProvider(ContextDataProvider):
    """Context data from Sports Reference via sportsipy."""

    name = "sportsipy"
    supported_sports = _SUPPORTED_SPORTS
    supported_leagues: Set[str] = set()  # all leagues for supported sports
    provided_data_types = {DataType.TEAM_FORM, DataType.HEAD_TO_HEAD}
    priority = 50

    def _get_service(self):
        from services.sportsipy_service import get_sportsipy_service
        svc = get_sportsipy_service()
        if not svc.is_available():
            return None
        return svc

    # ------------------------------------------------------------------
    # Team form
    # ------------------------------------------------------------------

    def get_team_form(
        self,
        team_name: str,
        sport: str,
        team_id: Optional[str] = None,
        last_n: int = 5,
    ) -> Optional[List[str]]:
        svc = self._get_service()
        if svc is None:
            return None

        key = _sport_key(sport)
        if not key:
            return None

        # Resolve abbreviation if not given
        abbrev = team_id or _find_abbreviation(svc, team_name, sport)
        if not abbrev:
            return None

        cache = get_cache()
        cache_key = make_form_key(self.name, sport, team_name)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            schedule = svc.get_team_schedule(abbrev, key)
        except Exception as exc:
            logger.debug("sportsipy team schedule failed for %s: %s", team_name, exc)
            return None

        lines: List[str] = []
        # Walk schedule in reverse to get most recent completed games first
        for ev in reversed(schedule):
            if not ev.result:
                continue
            result_str = ev.result
            opp = ev.away_team if ev.home_team == abbrev else ev.home_team
            date_str = ""
            if ev.date:
                try:
                    if isinstance(ev.date, datetime):
                        date_str = ev.date.strftime("%Y-%m-%d")
                    else:
                        date_str = str(ev.date)[:10]
                except Exception:
                    pass
            lines.append(f"{result_str} vs {opp} ({date_str})" if date_str else f"{result_str} vs {opp}")
            if len(lines) >= last_n:
                break

        cache.set(cache_key, lines, DataType.TEAM_FORM)
        return lines

    # ------------------------------------------------------------------
    # Head-to-head
    # ------------------------------------------------------------------

    def get_head_to_head(
        self,
        home_team: str,
        away_team: str,
        sport: str,
        home_team_id: Optional[str] = None,
        away_team_id: Optional[str] = None,
        limit: int = 5,
    ) -> Optional[List[str]]:
        svc = self._get_service()
        if svc is None:
            return None

        key = _sport_key(sport)
        if not key:
            return None

        home_abbrev = home_team_id or _find_abbreviation(svc, home_team, sport)
        if not home_abbrev:
            return None

        cache = get_cache()
        cache_key = make_h2h_key(self.name, sport, home_team, away_team)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        away_abbrev = away_team_id or _find_abbreviation(svc, away_team, sport)

        lines: List[str] = []
        try:
            schedule = svc.get_team_schedule(home_abbrev, key)
            for ev in reversed(schedule):
                if not ev.result:
                    continue
                opp = ev.away_team if ev.home_team == home_abbrev else ev.home_team
                opp_lower = opp.lower()
                if not (
                    (away_abbrev and opp.upper() == away_abbrev.upper())
                    or away_team.lower() in opp_lower
                    or opp_lower in away_team.lower()
                ):
                    continue
                date_str = ""
                if ev.date:
                    try:
                        date_str = (
                            ev.date.strftime("%Y-%m-%d")
                            if isinstance(ev.date, datetime)
                            else str(ev.date)[:10]
                        )
                    except Exception:
                        pass
                line = f"{date_str}: {ev.result}" if date_str else ev.result
                lines.append(line)
                if len(lines) >= limit:
                    break
        except Exception as exc:
            logger.debug("sportsipy H2H failed for %s vs %s: %s", home_team, away_team, exc)

        cache.set(cache_key, lines, DataType.HEAD_TO_HEAD)
        return lines

    # ------------------------------------------------------------------
    # Unimplemented optional methods
    # ------------------------------------------------------------------

    def get_standings(self, sport, league, season=None):
        return None

    def get_event_notes(self, home_team, away_team, sport, event_date=None, event_id=None):
        return None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_abbreviation(svc, team_name: str, sport: str) -> Optional[str]:
    """Try to resolve a display name to a team abbreviation via svc patterns."""
    try:
        # SportsipyService has extract_teams / detect_sport utilities but the
        # simplest path for a single name is to look up the in-memory team data.
        if hasattr(svc, "_team_data") and svc._team_data:
            for _sport, teams in svc._team_data.items():
                for abbrev, meta in teams.items():
                    aliases = meta.get("aliases") or []
                    display = meta.get("name") or ""
                    check = [a.lower() for a in aliases] + [display.lower()]
                    if team_name.lower() in check or any(team_name.lower() in c for c in check):
                        return abbrev
    except Exception as exc:
        logger.debug("Sportsipy abbreviation lookup failed for %r: %s", team_name, exc)
    return None
