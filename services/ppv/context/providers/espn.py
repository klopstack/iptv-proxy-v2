"""
ESPN unofficial API context data provider.

Uses the undocumented but widely-used ESPN public API endpoints:
  https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/...

No authentication is required.  Responses are cached aggressively to avoid
hammering the endpoint (one standings call covers all events in a league).

Sport/league mapping follows ESPN's URL path conventions.  The provider
covers the major North American sports leagues plus WNBA and MLS.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests

from services.ppv.context.base import ContextDataProvider, DataType
from services.ppv.context.cache import get_cache, make_h2h_key, make_notes_key, make_standings_key

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# ESPN sport/league URL path segments.
# Key: normalised sport name (lower) -> (sport_path, league_path)
_ESPN_PATHS: Dict[str, Tuple[str, str]] = {
    "american football": ("football", "nfl"),
    "nfl": ("football", "nfl"),
    "basketball": ("basketball", "nba"),
    "nba": ("basketball", "nba"),
    "wnba": ("basketball", "wnba"),
    "ice hockey": ("hockey", "nhl"),
    "nhl": ("hockey", "nhl"),
    "baseball": ("baseball", "mlb"),
    "mlb": ("baseball", "mlb"),
    "soccer": ("soccer", "usa.1"),  # MLS default; overridden per league
    "mls": ("soccer", "usa.1"),
    "boxing": ("boxing", "boxing"),
    "mma": ("mma", "ufc"),
    "ufc": ("mma", "ufc"),
    "fighting": ("mma", "ufc"),
    "tennis": ("tennis", "atp"),
    "atp": ("tennis", "atp"),
    "wta": ("tennis", "wta"),
}

# League name overrides for ESPN soccer league paths
_ESPN_SOCCER_LEAGUES: Dict[str, str] = {
    "premier league": "eng.1",
    "english premier league": "eng.1",
    "la liga": "esp.1",
    "spanish la liga": "esp.1",
    "serie a": "ita.1",
    "italian serie a": "ita.1",
    "bundesliga": "ger.1",
    "german bundesliga": "ger.1",
    "ligue 1": "fra.1",
    "french ligue 1": "fra.1",
    "champions league": "uefa.champions",
    "uefa champions league": "uefa.champions",
    "europa league": "uefa.europa",
    "mls": "usa.1",
    "major league soccer": "usa.1",
}

_SUPPORTED_SPORTS: Set[str] = {
    "American Football",
    "NFL",
    "Basketball",
    "NBA",
    "WNBA",
    "Ice Hockey",
    "NHL",
    "Baseball",
    "MLB",
    "Soccer",
    "MLS",
    "Boxing",
    "MMA",
    "UFC",
    "Fighting",
    "Tennis",
    "ATP",
    "WTA",
}


def _espn_paths(sport: str, league: str) -> Optional[Tuple[str, str]]:
    """Resolve (sport_path, league_path) for ESPN URL, or None if not mapped."""
    s = sport.lower()
    lg = league.lower()

    # Soccer leagues need special handling
    if s in ("soccer", "football") or "soccer" in s:
        league_path = _ESPN_SOCCER_LEAGUES.get(lg)
        if league_path:
            return ("soccer", league_path)
        return ("soccer", "usa.1")

    paths = _ESPN_PATHS.get(s)
    if not paths:
        # Try partial match
        for key, val in _ESPN_PATHS.items():
            if key in s or s in key:
                paths = val
                break
    return paths


class ESPNProvider(ContextDataProvider):
    """Context data from ESPN's unofficial public API."""

    name = "espn"
    supported_sports = _SUPPORTED_SPORTS
    supported_leagues: Set[str] = set()  # all leagues for supported sports
    provided_data_types = {
        DataType.STANDINGS,
        DataType.HEAD_TO_HEAD,
        DataType.TEAM_FORM,
        DataType.EVENT_NOTES,
        DataType.FIGHTER_RECORD,
    }
    priority = 10  # highest priority

    # ------------------------------------------------------------------
    # Standings
    # ------------------------------------------------------------------

    def get_standings(self, sport: str, league: str, season: Optional[str] = None) -> Optional[dict]:
        cache = get_cache()
        cache_key = make_standings_key(self.name, sport, league, season)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        paths = _espn_paths(sport, league)
        if not paths:
            return None
        sport_path, league_path = paths

        url = f"{_BASE}/{sport_path}/{league_path}/standings"
        try:
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.debug("ESPN standings request failed for %s/%s: %s", sport, league, exc)
            return None

        standings_map = _parse_espn_standings(data)
        result = {"_all_teams": standings_map}
        cache.set(cache_key, result, DataType.STANDINGS)
        return result

    def _get_team_standing(self, sport: str, league: str, team_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (record, standing) for a team from ESPN standings."""
        standings = self.get_standings(sport, league)
        if not standings:
            return None, None
        all_teams = standings.get("_all_teams", {})
        # Try exact match, then partial
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
        cache = get_cache()
        cache_key = make_h2h_key(self.name, sport, home_team, away_team)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        paths = _espn_paths(sport, "")
        if not paths:
            return None
        sport_path, league_path = paths

        # Find team IDs via team search
        home_id = home_team_id or _find_espn_team_id(sport_path, league_path, home_team)
        away_id = away_team_id or _find_espn_team_id(sport_path, league_path, away_team)

        if not home_id or not away_id:
            result: List[str] = []
            cache.set(cache_key, result, DataType.HEAD_TO_HEAD)
            return result

        # Fetch last N head-to-head games from team schedule
        lines = _fetch_h2h_from_schedules(sport_path, league_path, home_id, away_id, home_team, away_team, limit)
        cache.set(cache_key, lines, DataType.HEAD_TO_HEAD)
        return lines

    # ------------------------------------------------------------------
    # Team form
    # ------------------------------------------------------------------

    def get_fighter_record(
        self,
        fighter_name: str,
        sport: str,
        fighter_id: Optional[str] = None,
    ) -> Optional[str]:
        sport_l = sport.lower()
        if sport_l not in ("boxing", "mma", "ufc", "fighting", "wrestling"):
            return None

        cache = get_cache()
        from services.ppv.context.cache import make_form_key

        cache_key = make_form_key(self.name, sport, f"record:{fighter_name}")
        cached = cache.get(cache_key)
        if cached is not None:
            return cached if cached else None

        paths = _espn_paths(sport, "ufc" if sport_l in ("mma", "ufc", "fighting") else sport)
        if not paths:
            return None
        sport_path, league_path = paths

        aid = fighter_id or _find_espn_athlete_id(sport_path, league_path, fighter_name)
        record = _fetch_espn_fighter_record(sport_path, league_path, aid) if aid else None
        cache.set(cache_key, record or "", DataType.FIGHTER_RECORD)
        return record

    def get_team_form(
        self,
        team_name: str,
        sport: str,
        team_id: Optional[str] = None,
        last_n: int = 5,
    ) -> Optional[List[str]]:
        cache = get_cache()
        from services.ppv.context.cache import make_form_key

        cache_key = make_form_key(self.name, sport, team_name)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        paths = _espn_paths(sport, "")
        if not paths:
            return None
        sport_path, league_path = paths

        tid = team_id or _find_espn_team_id(sport_path, league_path, team_name)
        if not tid:
            result: List[str] = []
            cache.set(cache_key, result, DataType.TEAM_FORM)
            return result

        lines = _fetch_team_recent_results(sport_path, league_path, tid, team_name, last_n)
        cache.set(cache_key, lines, DataType.TEAM_FORM)
        return lines

    # ------------------------------------------------------------------
    # Event notes
    # ------------------------------------------------------------------

    def get_event_notes(
        self,
        home_team: str,
        away_team: str,
        sport: str,
        event_date: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Optional[str]:
        cache = get_cache()
        cache_key = make_notes_key(self.name, sport, home_team, away_team, event_date)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        paths = _espn_paths(sport, "")
        if not paths:
            return None
        sport_path, league_path = paths

        # Fetch scoreboard for the event date
        if not event_date:
            return None

        date_compact = event_date.replace("-", "")
        url = f"{_BASE}/{sport_path}/{league_path}/scoreboard?dates={date_compact}"
        try:
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.debug("ESPN scoreboard request failed: %s", exc)
            return None

        notes = _extract_game_notes(data, home_team, away_team)
        cache.set(cache_key, notes or "", DataType.EVENT_NOTES)
        return notes


# ---------------------------------------------------------------------------
# ESPN response parsing helpers
# ---------------------------------------------------------------------------


def _parse_espn_standings(data: dict) -> Dict[str, dict]:
    """Parse ESPN standings response into {team_name_lower: {record, standing}}."""
    result: Dict[str, dict] = {}
    try:
        children = data.get("children") or data.get("standings", {}).get("entries", [])
        # Handle nested group format
        if isinstance(children, list) and children and isinstance(children[0], dict):
            if "standings" in children[0] or "entries" in children[0].get("standings", {}):
                for group in children:
                    sub = group.get("standings", {})
                    entries = sub.get("entries", []) if isinstance(sub, dict) else group.get("entries", [])
                    _parse_entries_into(entries, result)
                return result
        entries = data.get("standings", {}).get("entries", [])
        _parse_entries_into(entries, result)
    except Exception as exc:
        logger.debug("Error parsing ESPN standings: %s", exc)
    return result


def _parse_entries_into(entries: list, result: Dict[str, dict]) -> None:
    for entry in entries:
        team = entry.get("team", {})
        name = (team.get("displayName") or team.get("name") or "").lower()
        if not name:
            continue
        stats = entry.get("stats", [])
        record = None
        standing = None
        for stat in stats:
            n = stat.get("name", "")
            val = stat.get("displayValue") or stat.get("value")
            if n in ("overall", "wins") and record is None:
                record = str(val)
            if n in ("playoffSeed", "rank", "divisionRank") and standing is None:
                display_name = stat.get("abbreviation") or n
                standing = f"{display_name}: {val}"
        result[name] = {"record": record, "standing": standing}


def _find_espn_athlete_id(sport_path: str, league_path: str, athlete_name: str) -> Optional[str]:
    """Search ESPN for an athlete ID by display name."""
    try:
        url = "https://site.web.api.espn.com/apis/common/v3/search" f"?query={quote(athlete_name)}&limit=8&type=player"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        search_lower = athlete_name.lower()
        for item in data.get("items", []):
            if item.get("type") != "player":
                continue
            display = (item.get("displayName") or "").lower()
            if display == search_lower or search_lower in display or display in search_lower:
                return str(item.get("id", ""))
        for item in data.get("items", []):
            if item.get("type") == "player" and item.get("id"):
                return str(item["id"])
    except Exception as exc:
        logger.debug("ESPN athlete search failed for %r: %s", athlete_name, exc)
    return None


def _fetch_espn_fighter_record(sport_path: str, league_path: str, athlete_id: str) -> Optional[str]:
    """Fetch W-L-D style record from ESPN athlete profile."""
    if not athlete_id:
        return None
    try:
        url = f"{_BASE}/{sport_path}/{league_path}/athletes/{athlete_id}"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        record = data.get("record") or {}
        items = record.get("items") or []
        for item in items:
            if (item.get("type") or "").lower() in ("total", "overall"):
                summary = item.get("summary") or item.get("displayValue")
                if summary:
                    return str(summary)
        athlete = data.get("athlete") or data
        for key in ("displayRecord", "recordSummary"):
            if athlete.get(key):
                return str(athlete[key])
        stats = athlete.get("stats") or data.get("stats") or []
        wins = losses = draws = None
        for stat in stats:
            name = (stat.get("name") or stat.get("abbreviation") or "").lower()
            val = stat.get("displayValue") or stat.get("value")
            if name in ("wins", "w"):
                wins = val
            elif name in ("losses", "l"):
                losses = val
            elif name in ("draws", "d"):
                draws = val
        if wins is not None and losses is not None:
            rec = f"{wins}-{losses}"
            if draws not in (None, "0", 0):
                rec = f"{rec}-{draws}"
            return rec
    except Exception as exc:
        logger.debug("ESPN fighter record fetch failed for %s: %s", athlete_id, exc)
    return None


def _find_espn_team_id(sport_path: str, league_path: str, team_name: str) -> Optional[str]:
    """Search for a team ID by name from ESPN teams endpoint."""
    try:
        url = f"{_BASE}/{sport_path}/{league_path}/teams?limit=200"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        sports = data.get("sports", [])
        for sport_obj in sports:
            for league_obj in sport_obj.get("leagues", []):
                for team_obj in league_obj.get("teams", []):
                    team = team_obj.get("team", {})
                    display = (team.get("displayName") or "").lower()
                    short = (team.get("shortDisplayName") or "").lower()
                    abbr = (team.get("abbreviation") or "").lower()
                    search = team_name.lower()
                    if search in (display, short, abbr) or display in search or search in display:
                        return str(team.get("id", ""))
    except Exception as exc:
        logger.debug("ESPN team lookup failed for %r: %s", team_name, exc)
    return None


def _fetch_h2h_from_schedules(
    sport_path: str,
    league_path: str,
    home_id: str,
    away_id: str,
    home_name: str,
    away_name: str,
    limit: int,
) -> List[str]:
    """Fetch recent completed games between two teams from ESPN team schedules."""
    lines: List[str] = []
    try:
        url = f"{_BASE}/{sport_path}/{league_path}/teams/{home_id}/schedule"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        for event in events:
            status = (event.get("status") or {}).get("type", {}).get("completed", False)
            if not status:
                continue
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            competitors = comps[0].get("competitors", [])
            team_ids = [str(c.get("id", "")) for c in competitors]
            if away_id not in team_ids:
                continue
            # Build result line
            date = event.get("date", "")[:10]
            scores = {str(c.get("id")): c.get("score", "?") for c in competitors}
            home_score = scores.get(home_id, "?")
            away_score = scores.get(away_id, "?")
            line = f"{date}: {home_name} {home_score}, {away_name} {away_score}"
            lines.append(line)
            if len(lines) >= limit:
                break
    except Exception as exc:
        logger.debug("ESPN H2H fetch failed: %s", exc)
    return lines


def _fetch_team_recent_results(
    sport_path: str,
    league_path: str,
    team_id: str,
    team_name: str,
    last_n: int,
) -> List[str]:
    """Return last_n completed game results for a team."""
    lines: List[str] = []
    try:
        url = f"{_BASE}/{sport_path}/{league_path}/teams/{team_id}/schedule"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        for event in reversed(events):
            status = (event.get("status") or {}).get("type", {}).get("completed", False)
            if not status:
                continue
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            competitors = comps[0].get("competitors", [])
            our = next((c for c in competitors if str(c.get("id")) == team_id), None)
            opp = next((c for c in competitors if str(c.get("id")) != team_id), None)
            if not our or not opp:
                continue
            result_flag = "W" if our.get("winner") else "L"
            opp_name = (opp.get("team") or {}).get("shortDisplayName") or "Opponent"
            line = f"{result_flag} {our.get('score', '?')}-{opp.get('score', '?')} vs {opp_name}"
            lines.append(line)
            if len(lines) >= last_n:
                break
    except Exception as exc:
        logger.debug("ESPN team form fetch failed: %s", exc)
    return lines


def _extract_game_notes(data: dict, home_team: str, away_team: str) -> Optional[str]:
    """Find and return ESPN notes for a specific game."""
    try:
        events = data.get("events", [])
        home_lower = home_team.lower()
        away_lower = away_team.lower()
        for event in events:
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            competitors = comps[0].get("competitors", [])
            names = [(c.get("team") or {}).get("displayName", "").lower() for c in competitors]
            if not any(home_lower in n or n in home_lower for n in names):
                continue
            if not any(away_lower in n or n in away_lower for n in names):
                continue
            notes = event.get("notes", [])
            for note in notes:
                headline = note.get("headline") or note.get("text") or ""
                if headline:
                    return headline
    except Exception as exc:
        logger.debug("Error extracting ESPN game notes: %s", exc)
    return None
