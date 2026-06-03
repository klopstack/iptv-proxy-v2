"""
MLB Stats API context provider for MiLB.

Supplies standings-style records from recent schedule leagueRecord fields.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, Optional, Set

from services.mlb_stats_api import MILB_SPORT_IDS, get_mlb_stats_client
from services.ppv.context.base import ContextDataProvider, DataType
from services.ppv.sport_registry import normalize_sport_key

logger = logging.getLogger(__name__)

_SUPPORTED_SPORTS: Set[str] = {"MiLB"}


class MlbStatsContextProvider(ContextDataProvider):
    """Context data from MLB Stats API for affiliated MiLB."""

    name = "mlb_stats"
    supported_sports = _SUPPORTED_SPORTS
    supported_leagues: Set[str] = set()
    provided_data_types = {DataType.STANDINGS, DataType.TEAM_FORM}
    priority = 35

    def covers(self, sport: str, league: str, data_type: DataType) -> bool:
        if data_type not in self.provided_data_types:
            return False
        if sport in self.supported_sports:
            return True
        if normalize_sport_key(sport) == "milb":
            return True
        if league and "milb" in league.lower():
            return True
        return False

    def get_standings(self, sport: str, league: str, season: Optional[str] = None) -> Optional[Dict]:
        records = self._team_records_for_league(league)
        if not records:
            return None
        return {"_all_teams": records}

    def get_team_form(
        self,
        team_name: str,
        sport: str,
        team_id: Optional[str] = None,
        last_n: int = 5,
    ) -> Optional[list]:
        records = self._team_records_for_league("")
        key = (team_id or team_name).lower()
        entry = records.get(key) or records.get(team_name.lower())
        if not entry:
            for name, data in records.items():
                if team_name.lower() in name or name in team_name.lower():
                    entry = data
                    break
        if entry and entry.get("record"):
            return [f"Season: {entry['record']}"]
        return None

    def _team_records_for_league(self, league: str) -> Dict[str, Dict[str, str]]:
        client = get_mlb_stats_client()
        today = date.today().isoformat()
        all_teams: Dict[str, Dict[str, str]] = {}
        try:
            for sport_id in MILB_SPORT_IDS:
                games = client.get_milb_schedule_for_date(today, sport_ids=(sport_id,))
                if not games:
                    yesterday = (date.today() - timedelta(days=1)).isoformat()
                    games = client.get_milb_schedule_for_date(yesterday, sport_ids=(sport_id,))
                for game in games:
                    for side in ("home", "away"):
                        team = (game.get("teams", {}).get(side) or {}).get("team") or {}
                        rec = (game.get("teams", {}).get(side) or {}).get("leagueRecord") or {}
                        name = team.get("name")
                        if not name:
                            continue
                        wins = rec.get("wins")
                        losses = rec.get("losses")
                        if wins is None or losses is None:
                            continue
                        record = f"{wins}-{losses}"
                        all_teams[name.lower()] = {"record": record, "standing": game.get("_level", "")}
                        tid = team.get("id")
                        if tid is not None:
                            all_teams[str(tid).lower()] = {"record": record, "standing": game.get("_level", "")}
        except Exception as exc:
            logger.debug("mlb_stats standings fetch failed: %s", exc)
            return {}
        return all_teams
