"""Canonical sport keys and alias resolution for PPV pipeline consumers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

# Sport key -> regex patterns matching TheSportsDB league_name values
SPORT_LEAGUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "mlb": (r"\bMLB\b", r"\bBaseball\b", r"\bWorld Baseball Classic\b"),
    "milb": (
        r"\bMiLB\b",
        r"\bMinor League Baseball\b",
        r"\bTriple-A\b",
        r"\bDouble-A\b",
        r"\bHigh-A\b",
        r"\bSingle-A\b",
    ),
    "nhl": (r"\bNHL\b", r"\bAHL\b", r"\bECHL\b", r"\bIce Hockey\b", r"\bHockey\b"),
    "nba": (r"\bNBA\b", r"\bBasketball\b"),
    "wnba": (r"\bWNBA\b", r"\bWomen's National Basketball\b"),
    "nfl": (r"\bNFL\b", r"\bUFL\b", r"\bAmerican Football\b"),
    "ncaaf": (r"\bNCAA Football\b", r"\bCollege Football\b", r"\bCFB\b", r"\bFBS\b", r"\bFCS\b"),
    "ncaab": (r"\bNCAA Basketball\b", r"\bCollege Basketball\b", r"\bMarch Madness\b", r"\bNCAAB\b"),
    "mls": (r"\bMLS\b", r"\bMajor League Soccer\b"),
    "soccer": (
        r"\bSoccer\b",
        r"\bFootball\b",
        r"\bPremier League\b",
        r"\bLa Liga\b",
        r"\bSerie A\b",
        r"\bBundesliga\b",
        r"\bLigue 1\b",
        r"\bChampions League\b",
        r"\bEuropa League\b",
        r"\bFA Cup\b",
        r"\bCopa\b",
        r"\bLiga\b",
        r"\bDivision\b",
        r"\bSuperliga\b",
        r"\bEredivisie\b",
        r"\bUWCL\b",
        r"\bUEFA Women\b",
    ),
    "nwsl": (r"\bNWSL\b", r"\bNational Women's Soccer League\b"),
    "wsl": (
        r"\bWomen's Super League\b",
        r"\bEnglish Womens Super League\b",
        r"\bBarclays Women\b",
        r"\bWSL\b",
    ),
    "ufc": (r"\bUFC\b", r"\bMMA\b", r"\bBellator\b", r"\bPFL\b", r"\bBoxing\b"),
    "tennis": (
        r"\bTennis\b",
        r"\bATP\b",
        r"\bWTA\b",
        r"\bGrand Slam\b",
        r"\bWimbledon\b",
        r"\bRoland Garros\b",
        r"\bFrench Open\b",
        r"\bUS Open\b",
        r"\bAustralian Open\b",
        r"\bIndian Wells\b",
        r"\bMiami Open\b",
    ),
}

# Patterns to detect sport keys from channel name or category text
SPORT_HINT_PATTERNS: dict[str, tuple[str, ...]] = {
    "milb": (r"\bMiLB\b", r"\bMILB\b", r":Milb\s+\d"),
    "mlb": (r"\bMLB\b", r"\bBaseball\b"),
    "nhl": (r"\bNHL\b", r"\bHockey\b", r"\bflohockey\b"),
    "nba": (r"\bNBA\b", r"\bBasketball\b"),
    "wnba": (r"\bWNBA\b", r"\bWomen's National Basketball\b"),
    "nwsl": (r"\bNWSL\b", r"\bNational Women's Soccer\b"),
    "wsl": (r"\bWSL\b", r"\bWomen's Super League\b", r"\bBarclays Women\b"),
    "nfl": (r"\bNFL\b", r"\bAmerican Football\b"),
    "ncaaf": (r"\bNCAA Football\b", r"\bCollege Football\b", r"\bCFB\b"),
    "ncaab": (r"\bNCAA Basketball\b", r"\bCollege Basketball\b", r"\bMarch Madness\b"),
    "mls": (r"\bMLS\b", r"\bMajor League Soccer\b"),
    "soccer": (r"\bSoccer\b", r"\bSOCCER PPV\b", r"\bFootball PPV\b", r"\bPremier League\b", r"\bLa Liga\b"),
    "ufc": (r"\bUFC\b", r"\bMMA\b", r"\bBoxing\b", r"\bBellator\b"),
    "tennis": (
        r"\bTennis\b",
        r"\bATP\b",
        r"\bWTA\b",
        r"\bWimbledon\b",
        r"\bRoland Garros\b",
        r"\bGrand Slam\b",
    ),
}

# Slot prefix patterns (e.g. "MLB 10 |") -> sport key
SLOT_SPORT_MAP: dict[str, str] = {
    "MLB": "mlb",
    "MILB": "milb",
    "MiLB": "milb",
    "Milb": "milb",
    "NBA": "nba",
    "WNBA": "wnba",
    "NHL": "nhl",
    "NFL": "nfl",
    "UFC": "ufc",
    "MLS": "mls",
    "NCAA": "ncaaf",
}

# Substring aliases for timezone / team-key resolution (order matters — longer first)
_SPORT_ALIAS_TO_KEY: tuple[tuple[str, str], ...] = (
    ("minor league baseball", "milb"),
    ("american football", "nfl"),
    ("ncaa football", "ncaaf"),
    ("college football", "ncaaf"),
    ("ice hockey", "nhl"),
    ("baseball", "mlb"),
    ("basketball", "nba"),
    ("football", "fb"),
    ("soccer", "fb"),
    ("milb", "milb"),
    ("mlb", "mlb"),
    ("wnba", "wnba"),
    ("nba", "nba"),
    ("hockey", "nhl"),
    ("nhl", "nhl"),
    ("nfl", "nfl"),
)

# Exact aliases for sportsipy / ESPN provider lookups
_SPORT_EXACT_ALIASES: dict[str, str] = {
    "american football": "nfl",
    "nfl": "nfl",
    "basketball": "nba",
    "nba": "nba",
    "wnba": "wnba",
    "ice hockey": "nhl",
    "nhl": "nhl",
    "baseball": "mlb",
    "mlb": "mlb",
    "ncaaf": "ncaaf",
    "ncaab": "ncaab",
    "soccer": "soccer",
    "football": "fb",
    "mls": "mls",
    "boxing": "boxing",
    "mma": "mma",
    "ufc": "ufc",
    "fighting": "mma",
    "tennis": "tennis",
    "atp": "atp",
    "wta": "wta",
    "milb": "milb",
}

# ESPN sport/league URL path segments (canonical sport key -> paths)
ESPN_PATHS: Dict[str, Tuple[str, str]] = {
    "nfl": ("football", "nfl"),
    "nba": ("basketball", "nba"),
    "wnba": ("basketball", "wnba"),
    "nhl": ("hockey", "nhl"),
    "mlb": ("baseball", "mlb"),
    "soccer": ("soccer", "usa.1"),
    "fb": ("soccer", "usa.1"),
    "mls": ("soccer", "usa.1"),
    "boxing": ("boxing", "boxing"),
    "mma": ("mma", "ufc"),
    "ufc": ("mma", "ufc"),
    "tennis": ("tennis", "atp"),
    "atp": ("tennis", "atp"),
    "wta": ("tennis", "wta"),
}

ESPN_SOCCER_LEAGUES: Dict[str, str] = {
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

# Sportsipy-supported keys (subset of canonical keys)
SPORTSIPY_SPORT_KEYS: FrozenSet[str] = frozenset({"nfl", "nba", "nhl", "mlb", "ncaaf", "ncaab"})

# Priority when multiple sport keys match channel context
CONTEXT_SPORT_PRIORITY: tuple[str, ...] = (
    "milb",
    "mlb",
    "nhl",
    "nba",
    "wnba",
    "nfl",
    "ncaaf",
    "ncaab",
    "mls",
    "nwsl",
    "wsl",
    "ufc",
    "tennis",
    "soccer",
)

CANONICAL_SPORT_KEYS: FrozenSet[str] = frozenset(
    {
        "mlb",
        "milb",
        "nba",
        "wnba",
        "nfl",
        "nhl",
        "ncaaf",
        "ncaab",
        "fb",
        "soccer",
        "mls",
        "nwsl",
        "wsl",
        "ufc",
        "tennis",
        "mma",
        "nascar",
    }
)


@dataclass(frozen=True)
class SportDefinition:
    key: str
    aliases: frozenset[str]
    team_source: str
    sportsipy_key: Optional[str] = None


def normalize_sport_key(raw: str | None) -> str | None:
    """Map a sport string or hint to a canonical key (timezone / team resolution)."""
    if not raw:
        return None
    s = raw.lower().strip()
    if not s:
        return None
    for alias, key in _SPORT_ALIAS_TO_KEY:
        if alias in s:
            return key
    return None


def normalize_sport_key_exact(raw: str) -> str | None:
    """Map a normalized sport label to a canonical key (exact / provider lookups)."""
    return _SPORT_EXACT_ALIASES.get(raw.lower().strip())


def sportsipy_sport_key(sport: str) -> Optional[str]:
    """Return sportsipy service key for a sport label, or None if unsupported."""
    key = normalize_sport_key_exact(sport) or normalize_sport_key(sport)
    if key and key in SPORTSIPY_SPORT_KEYS:
        return key
    return None


def espn_paths(sport: str, league: str = "") -> Optional[Tuple[str, str]]:
    """Resolve ESPN API (sport_path, league_path) for a sport/league label."""
    s = sport.lower()
    lg = league.lower()

    if s in ("soccer", "football", "fb") or "soccer" in s:
        league_path = ESPN_SOCCER_LEAGUES.get(lg)
        if league_path:
            return ("soccer", league_path)
        return ("soccer", "usa.1")

    key = normalize_sport_key_exact(s) or normalize_sport_key(s)
    if key and key in ESPN_PATHS:
        return ESPN_PATHS[key]

    for alias, canonical in _SPORT_EXACT_ALIASES.items():
        if alias in s or s in alias:
            paths = ESPN_PATHS.get(canonical)
            if paths:
                return paths
    return None


def sport_key_from_league_name(league_name: Optional[str]) -> Optional[str]:
    """Infer a sport key from a TheSportsDB league name."""
    if not league_name:
        return None
    for sport_key, patterns in SPORT_LEAGUE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, league_name, re.IGNORECASE):
                return sport_key
    return None


def primary_sport_key(sport_keys: FrozenSet[str]) -> Optional[str]:
    """Pick the most specific sport key from a set of matched hints."""
    if not sport_keys:
        return None
    for key in CONTEXT_SPORT_PRIORITY:
        if key in sport_keys:
            return key
    return next(iter(sport_keys))


def sport_keys_for_context(channel_name: str, category_name: Optional[str] = None) -> frozenset[str]:
    """Collect sport keys from channel/category text using hint patterns."""
    from services.ppv.extraction import PPVEventExtractor
    from services.ppv.slot_extraction import PPV_SLOT_PATTERNS

    sport_keys: set[str] = set()

    extractor = PPVEventExtractor()
    inline_sport, _ = extractor.extract_sport(channel_name or "")
    if inline_sport:
        key = normalize_sport_key(inline_sport)
        if key:
            sport_keys.add(key)
        for hint_key, patterns in SPORT_HINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, inline_sport, re.IGNORECASE):
                    sport_keys.add(hint_key)
                    break

    combined_text = " ".join(part for part in (channel_name, category_name) if isinstance(part, str) and part)
    for sport_key, patterns in SPORT_HINT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                sport_keys.add(sport_key)
                break

    for slot_pattern in PPV_SLOT_PATTERNS:
        match = slot_pattern.search(channel_name or "")
        if not match:
            continue
        prefix = match.group(0)
        for token, sport_key in SLOT_SPORT_MAP.items():
            if token in prefix:
                sport_keys.add(sport_key)
                return frozenset(sport_keys)

    if category_name:
        for sport_key, patterns in SPORT_HINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, category_name, re.IGNORECASE):
                    sport_keys.add(sport_key)
                    break

    return frozenset(sport_keys)
