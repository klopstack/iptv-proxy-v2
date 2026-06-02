"""
MLB Stats API client (statsapi.mlb.com).

Official public API used by MLB.com — no API key required.
Covers MLB and affiliated MiLB levels via sportId.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Union

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://statsapi.mlb.com/api/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_REQUEST_DELAY = 0.25
MAX_RETRIES = 3

# Affiliated MiLB levels (Triple-A through Single-A)
MILB_SPORT_IDS: tuple[int, ...] = (11, 12, 13, 14)

MILB_SPORT_LABELS: Dict[int, str] = {
    11: "Triple-A",
    12: "Double-A",
    13: "High-A",
    14: "Single-A",
}


class MlbStatsApiError(Exception):
    """Raised when the MLB Stats API returns an error or unexpected payload."""


class MlbStatsApiClient:
    """Thin HTTP client for statsapi.mlb.com."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("MLB_STATS_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.request_delay = request_delay
        self._session = session or requests.Session()
        self._session.headers.setdefault(
            "User-Agent",
            "iptv-proxy-v2/1.0 (+https://github.com/benklop/iptv-proxy-v2)",
        )
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        if self.request_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = self._session.get(url, params=params or {}, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise MlbStatsApiError(f"HTTP {resp.status_code} from {url}")
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise MlbStatsApiError(f"Expected JSON object from {url}")
                return data
            except (requests.RequestException, MlbStatsApiError, ValueError) as exc:
                last_exc = exc
                if attempt + 1 < MAX_RETRIES:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                break
        raise MlbStatsApiError(f"Request failed for {url}: {last_exc}") from last_exc

    def get_sports(self) -> List[Dict[str, Any]]:
        data = self._get("sports")
        return list(data.get("sports") or [])

    def get_teams(
        self,
        sport_id: int,
        season: Optional[Union[int, str]] = None,
    ) -> List[Dict[str, Any]]:
        season = season or date.today().year
        data = self._get("teams", {"sportId": sport_id, "season": season})
        return list(data.get("teams") or [])

    def get_venue(self, venue_id: int) -> Optional[Dict[str, Any]]:
        data = self._get(f"venues/{venue_id}", {"hydrate": "location"})
        venues = data.get("venues") or []
        return venues[0] if venues else None

    def get_schedule(
        self,
        sport_id: int,
        *,
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        season: Optional[Union[int, str]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"sportId": sport_id}
        if date:
            params["date"] = date
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if season:
            params["season"] = season
        return self._get("schedule", params)

    def get_milb_teams(
        self,
        season: Optional[Union[int, str]] = None,
        sport_ids: Sequence[int] = MILB_SPORT_IDS,
    ) -> List[Dict[str, Any]]:
        teams: List[Dict[str, Any]] = []
        for sport_id in sport_ids:
            for team in self.get_teams(sport_id, season=season):
                team = dict(team)
                team["_sport_id"] = sport_id
                team["_level"] = MILB_SPORT_LABELS.get(sport_id, str(sport_id))
                teams.append(team)
        return teams

    def get_milb_schedule_for_date(
        self,
        date_str: str,
        sport_ids: Sequence[int] = MILB_SPORT_IDS,
    ) -> List[Dict[str, Any]]:
        games: List[Dict[str, Any]] = []
        for sport_id in sport_ids:
            data = self.get_schedule(sport_id, date=date_str)
            for day in data.get("dates") or []:
                for game in day.get("games") or []:
                    g = dict(game)
                    g["_sport_id"] = sport_id
                    g["_level"] = MILB_SPORT_LABELS.get(sport_id, str(sport_id))
                    games.append(g)
        return games


_default_client: Optional[MlbStatsApiClient] = None


def get_mlb_stats_client() -> MlbStatsApiClient:
    global _default_client
    if _default_client is None:
        _default_client = MlbStatsApiClient()
    return _default_client
