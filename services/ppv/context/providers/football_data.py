"""
football-data.org context data provider.

Covers the major European soccer leagues and international competitions.
Requires a free API key stored via the provider settings system
(provider: ``football_data``, key: ``api_key``).

API docs: https://www.football-data.org/documentation/quickstart
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

import requests

from services.ppv.context.base import ContextDataProvider, DataType
from services.ppv.context.cache import (
    get_cache,
    make_h2h_key,
    make_standings_key,
)

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_BASE = "https://api.football-data.org/v4"

# Supported league name → football-data competition code
_LEAGUE_CODES: Dict[str, str] = {
    "premier league": "PL",
    "english premier league": "PL",
    "la liga": "PD",
    "spanish la liga": "PD",
    "serie a": "SA",
    "italian serie a": "SA",
    "bundesliga": "BL1",
    "german bundesliga": "BL1",
    "ligue 1": "FL1",
    "french ligue 1": "FL1",
    "champions league": "CL",
    "uefa champions league": "CL",
    "europa league": "EL",
    "world cup": "WC",
    "fifa world cup": "WC",
    "european championship": "EC",
    "uefa european championship": "EC",
    "eredivisie": "DED",
    "dutch eredivisie": "DED",
    "primeira liga": "PPL",
    "portuguese primeira liga": "PPL",
}

_SUPPORTED_LEAGUES: Set[str] = {
    "Premier League", "English Premier League",
    "La Liga", "Spanish La Liga",
    "Serie A", "Italian Serie A",
    "Bundesliga", "German Bundesliga",
    "Ligue 1", "French Ligue 1",
    "Champions League", "UEFA Champions League",
    "Europa League",
    "World Cup", "FIFA World Cup",
    "European Championship", "UEFA European Championship",
    "Eredivisie", "Dutch Eredivisie",
    "Primeira Liga", "Portuguese Primeira Liga",
}


def _league_code(league: str) -> Optional[str]:
    return _LEAGUE_CODES.get(league.lower())


class FootballDataProvider(ContextDataProvider):
    """Context data from football-data.org."""

    name = "football_data"
    supported_sports = {"Soccer"}
    supported_leagues = _SUPPORTED_LEAGUES
    provided_data_types = {DataType.STANDINGS, DataType.HEAD_TO_HEAD}
    priority = 15

    def settings_fields(self):
        return [
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "description": (
                    "API key from football-data.org. "
                    "A free tier key is available at https://www.football-data.org/."
                ),
                "required": True,
            },
        ]

    # ------------------------------------------------------------------
    # Standings
    # ------------------------------------------------------------------

    def get_standings(self, sport: str, league: str, season: Optional[str] = None) -> Optional[dict]:
        api_key = self.get_setting("api_key")
        if not api_key:
            return None

        code = _league_code(league)
        if not code:
            return None

        cache = get_cache()
        cache_key = make_standings_key(self.name, sport, league, season)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{_BASE}/competitions/{code}/standings"
        headers = {"X-Auth-Token": api_key}
        try:
            resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.debug("football-data standings request failed for %s: %s", league, exc)
            return None

        all_teams: Dict[str, dict] = {}
        for table in data.get("standings", []):
            table_type = table.get("type", "")
            for row in table.get("table", []):
                team_name = (row.get("team") or {}).get("name", "").lower()
                if not team_name:
                    continue
                pos = row.get("position")
                played = row.get("playedGames")
                pts = row.get("points")
                won = row.get("won", 0)
                drawn = row.get("draw", 0)
                lost = row.get("lost", 0)
                record = f"{won}W-{drawn}D-{lost}L"
                standing = f"#{pos} ({pts} pts)" if pos is not None else None
                entry = all_teams.setdefault(team_name, {})
                if table_type == "TOTAL" or "record" not in entry:
                    entry["record"] = record
                    entry["standing"] = standing

        result = {"_all_teams": all_teams}
        cache.set(cache_key, result, DataType.STANDINGS)
        return result

    def _get_team_standing(self, sport: str, league: str, team_name: str):
        standings = self.get_standings(sport, league)
        if not standings:
            return None, None
        all_teams = standings.get("_all_teams", {})
        key = team_name.lower()
        entry = all_teams.get(key)
        if not entry:
            for k, v in all_teams.items():
                if key in k or k in key:
                    entry = v
                    break
        if not entry:
            return None, None
        return entry.get("record"), entry.get("standing")

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
        api_key = self.get_setting("api_key")
        if not api_key:
            return None

        # We need a match ID to call /head2head.  Try to find a recent/upcoming match.
        # This is limited without knowing the exact match ID, so we fall back to None.
        # A more complete implementation would search for the match via /matches.
        return None

    # ------------------------------------------------------------------
    # Unimplemented optional methods
    # ------------------------------------------------------------------

    def get_team_form(self, team_name, sport, team_id=None, last_n=5):
        return None

    def get_event_notes(self, home_team, away_team, sport, event_date=None, event_id=None):
        return None
