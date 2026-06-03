"""MLB team abbreviation resolution for PPV matching (Peacock AWAY at HOME feeds)."""

from __future__ import annotations

import re
from typing import Dict, Optional

# Canonical Peacock / broadcast codes -> TheSportsDB-style team names.
# WSH/WAS: single canonical choice WSN-style codes map to Nationals.
_MLB_ABBREV_FALLBACK: Dict[str, str] = {
    "ARI": "Arizona Diamondbacks",
    "AZ": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CHW": "Chicago White Sox",
    "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "KCR": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "ANA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Oakland Athletics",
    "ATH": "Oakland Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SDP": "San Diego Padres",
    "SF": "San Francisco Giants",
    "SFG": "San Francisco Giants",
    "SEA": "Seattle Mariners",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TBR": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
    "WAS": "Washington Nationals",
    "WSN": "Washington Nationals",
}

_ABBREV_TOKEN = re.compile(r"\b([a-z]{2,3})\b")

_mlb_abbrev_to_name: Optional[Dict[str, str]] = None


def _load_mlb_abbrev_map() -> Dict[str, str]:
    """Build abbrev -> full name map from SportsTeam rows with static fallback."""
    mapping = dict(_MLB_ABBREV_FALLBACK)
    try:
        from models import SportsTeam

        for team in SportsTeam.query.filter_by(sport=SportsTeam.SPORT_MLB).all():
            mapping[team.abbreviation.upper()] = team.name
            for alias in team.get_aliases():
                alias_key = alias.strip().upper()
                if 2 <= len(alias_key) <= 4 and alias_key.isalpha():
                    mapping.setdefault(alias_key, team.name)
    except Exception:
        pass
    return mapping


def get_mlb_abbrev_map() -> Dict[str, str]:
    """Return cached O(1) abbrev -> full name lookup (no live API)."""
    global _mlb_abbrev_to_name
    if _mlb_abbrev_to_name is None:
        _mlb_abbrev_to_name = _load_mlb_abbrev_map()
    return _mlb_abbrev_to_name


def clear_mlb_abbrev_cache() -> None:
    """Clear cached abbrev map (for tests)."""
    global _mlb_abbrev_to_name
    _mlb_abbrev_to_name = None


def resolve_mlb_abbrev(name: str) -> Optional[str]:
    """Resolve a two- or three-letter MLB code to a canonical team name."""
    if not name or not name.strip():
        return None
    key = name.strip().upper()
    if not key.isalpha() or not (2 <= len(key) <= 3):
        return None
    return get_mlb_abbrev_map().get(key)


def extract_mlb_abbrevs_from_text(text: str) -> list[str]:
    """Return lowercase MLB abbrev tokens found in normalized text."""
    if not text:
        return []
    found: list[str] = []
    for token in _ABBREV_TOKEN.findall(text.lower()):
        if resolve_mlb_abbrev(token):
            found.append(token)
    return found


def should_expand_mlb_abbrevs(text: str, *, sport_key: Optional[str] = None) -> bool:
    """True when MLB abbrev expansion should run for this channel text."""
    if sport_key and sport_key != "mlb":
        return False
    if sport_key == "mlb":
        return bool(extract_mlb_abbrevs_from_text(text))
    return len(extract_mlb_abbrevs_from_text(text)) >= 2


def expand_mlb_abbrevs_in_text(text: str, *, sport_key: Optional[str] = None) -> str:
    """
    Replace MLB abbreviation tokens with normalized full team names.

    Expansion applies when sport context is MLB, or when at least two MLB
    abbreviations appear (Peacock PPV pattern). Skipped for explicit non-MLB sport.
    """
    if not text or not should_expand_mlb_abbrevs(text, sport_key=sport_key):
        return text

    abbrev_map = get_mlb_abbrev_map()
    result = text
    tokens = sorted(set(_ABBREV_TOKEN.findall(text.lower())), key=len, reverse=True)
    for token in tokens:
        full_name = abbrev_map.get(token.upper())
        if not full_name:
            continue
        result = re.sub(r"\b" + re.escape(token) + r"\b", full_name.lower(), result)
    return result
