"""
TheSportsDB context data provider.

Broad fallback provider covering most sports and leagues.  Uses the existing
``TheSportsDBService`` and ``call_thesportsdb_api`` infrastructure already
present in the application.

Lowest priority (90) — used only when sport-specific providers have no
coverage for a given sport/league combination.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from services.ppv.context.base import ContextDataProvider, DataType
from services.ppv.context.cache import (
    get_cache,
    make_h2h_key,
    make_standings_key,
)

logger = logging.getLogger(__name__)

# League names that TheSportsDB can provide standings for (mapped to league IDs
# in the existing LEAGUE_ID_MAP in thesportsdb_service.py).
_STANDINGS_SUPPORTED_LEAGUES: Set[str] = {
    "English Premier League",
    "English League 1",
    "English League 2",
    "Championship",
    "Spanish La Liga",
    "Spanish Segunda División",
    "Italian Serie A",
    "German Bundesliga",
    "German 2. Bundesliga",
    "French Ligue 1",
    "NFL",
    "NBA",
    "MLB",
    "NHL",
}


class TheSportsDBContextProvider(ContextDataProvider):
    """Broad-fallback context data from TheSportsDB."""

    name = "thesportsdb"
    # Empty sets mean "accept all sports / all leagues"
    supported_sports: Set[str] = set()
    supported_leagues: Set[str] = set()
    provided_data_types = {DataType.HEAD_TO_HEAD, DataType.STANDINGS}
    priority = 90  # lowest priority — last resort fallback

    # ------------------------------------------------------------------
    # Standings (limited to leagues with ID mappings)
    # ------------------------------------------------------------------

    def get_standings(self, sport: str, league: str, season: Optional[str] = None) -> Optional[dict]:
        try:
            from services.thesportsdb_service import LEAGUE_ID_MAP
            from services.thesportsdb_retry import call_thesportsdb_api
            from thesportsdb import tables as tsdb_tables
        except ImportError as exc:
            logger.debug("TheSportsDB import error: %s", exc)
            return None

        league_id = LEAGUE_ID_MAP.get(league)
        if not league_id:
            return None

        cache = get_cache()
        cache_key = make_standings_key(self.name, sport, league, season)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            result = call_thesportsdb_api(tsdb_tables.leagueTable, league_id)
        except Exception as exc:
            logger.debug("TheSportsDB standings failed for %s: %s", league, exc)
            return None

        if not result:
            return None

        table = result.get("table") or []
        all_teams: Dict[str, dict] = {}
        for row in table:
            name = (row.get("strTeam") or "").lower()
            if not name:
                continue
            pos = row.get("intRank") or row.get("intPosition")
            played = row.get("intPlayed")
            won = row.get("intWin") or "?"
            lost = row.get("intLoss") or "?"
            drawn = row.get("intDraw") or "?"
            pts = row.get("intPoints")
            record = f"{won}W-{drawn}D-{lost}L"
            standing = f"#{pos}" if pos else None
            all_teams[name] = {"record": record, "standing": standing}

        payload = {"_all_teams": all_teams}
        cache.set(cache_key, payload, DataType.STANDINGS)
        return payload

    # ------------------------------------------------------------------
    # Head-to-head (requires team IDs known at event enrichment time)
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
        # TheSportsDB H2H endpoint requires numeric team IDs.  If they're not
        # available, skip gracefully.
        if not home_team_id or not away_team_id:
            return None

        try:
            from services.thesportsdb_retry import call_thesportsdb_api
            from thesportsdb import events as tsdb_events
        except ImportError as exc:
            logger.debug("TheSportsDB import error: %s", exc)
            return None

        cache = get_cache()
        cache_key = make_h2h_key(self.name, sport, home_team, away_team)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            result = call_thesportsdb_api(tsdb_events.eventResult, home_team_id)
        except Exception as exc:
            logger.debug("TheSportsDB H2H failed for %s vs %s: %s", home_team, away_team, exc)
            return None

        lines: List[str] = []
        raw_events: List[Dict[str, Any]] = []

        if result:
            raw_events = result.get("results") or result.get("events") or []

        for ev in raw_events[:limit]:
            home = ev.get("strHomeTeam") or "?"
            away = ev.get("strAwayTeam") or "?"
            h_score = ev.get("intHomeScore") or "?"
            a_score = ev.get("intAwayScore") or "?"
            date = (ev.get("dateEvent") or "")[:10]
            # Only include if our two teams are involved
            involved = {home.lower(), away.lower()}
            if home_team.lower() not in involved and away_team.lower() not in involved:
                continue
            lines.append(f"{date}: {home} {h_score}-{a_score} {away}")

        cache.set(cache_key, lines, DataType.HEAD_TO_HEAD)
        return lines

    # ------------------------------------------------------------------
    # Unimplemented optional methods
    # ------------------------------------------------------------------

    def get_team_form(self, team_name, sport, team_id=None, last_n=5):
        return None

    def get_event_notes(self, home_team, away_team, sport, event_date=None, event_id=None):
        return None
