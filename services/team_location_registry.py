"""Bundled team/school location registry (non-heuristic lookup)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "data" / "team_locations" / "registry.json"

RegistryIndexes = Tuple[
    Dict[Tuple[str, str], "LocationEntry"],
    Dict[Tuple[str, str], "LocationEntry"],
    Dict[Tuple[str, str], "LocationEntry"],
]


def _registry_lookup_key(sport: str, key: str) -> str:
    if sport.lower() in ("fb", "wnba", "milb"):
        return str(key)
    return str(key).upper()


@dataclass(frozen=True)
class LocationEntry:
    sport: str
    key: str
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    venue_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    iana_timezone: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    thesportsdb_id: Optional[str] = None
    fbref_squad_id: Optional[str] = None
    league: Optional[str] = None
    aliases: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocationEntry":
        sport = str(data["sport"]).lower()
        raw_key = str(data["key"])
        key = _registry_lookup_key(sport, raw_key)
        raw_aliases = data.get("aliases") or []
        aliases = tuple(_normalize_name(a) for a in raw_aliases if a)
        return cls(
            sport=sport,
            key=key,
            name=str(data.get("name") or ""),
            city=data.get("city"),
            state=data.get("state"),
            country=data.get("country"),
            venue_name=data.get("venue_name"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            iana_timezone=data.get("iana_timezone"),
            source=data.get("source"),
            source_url=data.get("source_url"),
            thesportsdb_id=str(data["thesportsdb_id"]) if data.get("thesportsdb_id") else None,
            fbref_squad_id=data.get("fbref_squad_id"),
            league=data.get("league"),
            aliases=aliases,
        )


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().strip().split())


@lru_cache(maxsize=1)
def _load_registry(path: Optional[str] = None) -> RegistryIndexes:
    registry_path = Path(path) if path is not None else Path(DEFAULT_REGISTRY_PATH)
    if not registry_path.exists():
        logger.warning("Team location registry not found at %s", registry_path)
        return {}, {}, {}

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    by_key: Dict[Tuple[str, str], LocationEntry] = {}
    by_name: Dict[Tuple[str, str], LocationEntry] = {}
    by_alias: Dict[Tuple[str, str], LocationEntry] = {}
    for raw in data.get("entries", []):
        try:
            ent = LocationEntry.from_dict(raw)
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping invalid registry entry: %s", exc)
            continue
        by_key[(ent.sport, ent.key)] = ent
        if ent.name:
            by_name[(ent.sport, _normalize_name(ent.name))] = ent
        for alias in ent.aliases:
            if alias:
                by_alias[(ent.sport, alias)] = ent
    return by_key, by_name, by_alias


def clear_registry_cache() -> None:
    _load_registry.cache_clear()


def lookup(sport: str, abbreviation: str, registry_path: Optional[str] = None) -> Optional[LocationEntry]:
    """Look up location by sport and key (sportsipy abbr, college slug, or TheSportsDB idTeam)."""
    if not sport or not abbreviation:
        return None
    by_key, _, _ = _load_registry(registry_path)
    key = _registry_lookup_key(sport.lower(), abbreviation)
    return by_key.get((sport.lower(), key))


def lookup_by_name(sport: str, name: str, registry_path: Optional[str] = None) -> Optional[LocationEntry]:
    """Exact normalized name match only — no prefix heuristics."""
    if not sport or not name:
        return None
    _, by_name, _ = _load_registry(registry_path)
    return by_name.get((sport.lower(), _normalize_name(name)))


def lookup_by_alias(sport: str, alias: str, registry_path: Optional[str] = None) -> Optional[LocationEntry]:
    """Exact normalized alias match from registry aliases[]."""
    if not sport or not alias:
        return None
    _, _, by_alias = _load_registry(registry_path)
    return by_alias.get((sport.lower(), _normalize_name(alias)))


def entries_for_sport(sport: str, registry_path: Optional[str] = None) -> List[LocationEntry]:
    """Return all registry entries for a sport."""
    by_key, _, _ = _load_registry(registry_path)
    sport_l = sport.lower()
    return [ent for (s, _), ent in sorted(by_key.items()) if s == sport_l]


def registry_version(registry_path: Optional[str] = None) -> Optional[str]:
    registry_path_obj = Path(registry_path) if registry_path is not None else Path(DEFAULT_REGISTRY_PATH)
    if not registry_path_obj.exists():
        return None
    data = json.loads(registry_path_obj.read_text(encoding="utf-8"))
    return data.get("version")


def apply_location_to_sports_team(team_row: Any, location: LocationEntry) -> None:
    """Copy registry fields onto a SportsTeam model instance."""
    if location.city:
        team_row.city = location.city
    if location.iana_timezone:
        team_row.iana_timezone = location.iana_timezone
    if location.state:
        team_row.state = location.state
    if location.country:
        team_row.country = location.country
    if location.venue_name:
        team_row.venue_name = location.venue_name
    if location.latitude is not None:
        team_row.latitude = location.latitude
    if location.longitude is not None:
        team_row.longitude = location.longitude
    if location.source:
        team_row.location_source = location.source
