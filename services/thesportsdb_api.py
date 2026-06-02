"""TheSportsDB V2 API client and SDK-to-V2 routing.

Premium API keys authenticate via the ``X-API-KEY`` header on V2 endpoints.
Several V1 SDK calls (notably ``lookup_all_teams`` / ``leagueTeams``) return
404 when the key is embedded in the URL path.  This module routes those calls
through V2 and normalizes responses to the V1-shaped dicts existing code expects.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

V2_BASE_URL = "https://www.thesportsdb.com/api/v2/json"
FREE_API_KEYS = frozenset({"", "3", "123", "1"})
USER_AGENT = "iptv-proxy-v2/1.0"


@dataclass(frozen=True)
class V2Route:
    """Maps an SDK function to a V2 path and V1 response list key."""

    path_builder: Callable[..., str]
    list_key: str


def resolve_thesportsdb_api_key() -> str:
    """Return API key from env (build/CI) or app settings."""
    env_key = (os.environ.get("THESPORTSDB_API_KEY") or "").strip()
    if env_key:
        return env_key

    try:
        from models import Settings

        return (Settings.get("ppv_thesportsdb_api_key", "") or "").strip()
    except Exception:
        return ""


def uses_v2_api(api_key: str) -> bool:
    """Premium keys should use V2 header auth instead of V1 path embedding."""
    return api_key not in FREE_API_KEYS


def v2_get(path: str, api_key: str, *, timeout: float = 120.0) -> Optional[Dict[str, Any]]:
    """GET a V2 JSON endpoint with header authentication."""
    url = f"{V2_BASE_URL}/{path.lstrip('/')}"
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"X-API-KEY": api_key, "User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else None


def normalize_v2_to_v1(data: Optional[Dict[str, Any]], list_key: str) -> Dict[str, Any]:
    """Convert a V2 response body to the dict shape the V1 SDK returns."""
    if not data:
        return {list_key: []}

    if "Message" in data and len(data) == 1:
        return {list_key: []}

    if "lookup" in data:
        items = data["lookup"]
        if not isinstance(items, list):
            items = [items] if items else []
        return {list_key: items}

    if "list" in data:
        items = data["list"]
        if not isinstance(items, list):
            items = [items] if items else []
        return {list_key: items}

    if "schedule" in data:
        items = data["schedule"]
        if not isinstance(items, list):
            items = [items] if items else []
        return {list_key: items}

    if "filter" in data:
        items = data["filter"]
        if not isinstance(items, list):
            items = [items] if items else []
        return {"events": items}

    return data


def _events_day_path(day: str, **kwargs: Any) -> str:
    path = f"filter/events/day/{day}"
    params: List[str] = []
    sport = kwargs.get("s")
    league = kwargs.get("l")
    if sport:
        params.append(f"s={quote(str(sport))}")
    if league:
        params.append(f"l={quote(str(league))}")
    if params:
        path = f"{path}?{'&'.join(params)}"
    return path


V2_ROUTES: Dict[Tuple[str, str], V2Route] = {
    ("thesportsdb.teams", "leagueTeams"): V2Route(
        path_builder=lambda league_id: f"list/teams/{league_id}",
        list_key="teams",
    ),
    ("thesportsdb.teams", "teamInfo"): V2Route(
        path_builder=lambda team_id: f"lookup/team/{team_id}",
        list_key="teams",
    ),
    ("thesportsdb.events", "eventInfo"): V2Route(
        path_builder=lambda event_id: f"lookup/event/{event_id}",
        list_key="events",
    ),
    ("thesportsdb.events", "nextLeagueEvents"): V2Route(
        path_builder=lambda league_id: f"schedule/next/league/{league_id}",
        list_key="events",
    ),
    ("thesportsdb.events", "leagueSeasonEvents"): V2Route(
        path_builder=lambda league_id, season: f"schedule/league/{league_id}/{season}",
        list_key="results",
    ),
    ("thesportsdb.events", "eventsDay"): V2Route(
        path_builder=_events_day_path,
        list_key="events",
    ),
    ("thesportsdb.events", "eventResult"): V2Route(
        path_builder=lambda team_id: f"schedule/previous/team/{team_id}",
        list_key="results",
    ),
    ("thesportsdb.leagues", "leagueInfo"): V2Route(
        path_builder=lambda league_id: f"lookup/league/{league_id}",
        list_key="results",
    ),
}


def sdk_route_key(fn: Callable[..., Any]) -> Tuple[str, str]:
    return (getattr(fn, "__module__", ""), getattr(fn, "__name__", ""))


def try_v2_sdk_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """
    If the SDK function has a V2 route and a premium key is configured, call V2.

    Returns None when the caller should fall back to the V1 SDK.
    """
    api_key = resolve_thesportsdb_api_key()
    effective_key = api_key or "3"
    if not uses_v2_api(effective_key):
        return None

    route = V2_ROUTES.get(sdk_route_key(fn))
    if route is None:
        return None

    path = route.path_builder(*args, **kwargs)
    raw = v2_get(path, effective_key)
    return normalize_v2_to_v1(raw, route.list_key)
