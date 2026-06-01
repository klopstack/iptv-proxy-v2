"""Resolve sport/league context from PPV channel names and categories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

from services.ppv.extraction import PPVEventExtractor
from services.ppv.slot_extraction import PPV_SLOT_PATTERNS
from services.thesportsdb_calendar_scraper import CalendarEvent

# Sport key -> regex patterns matching TheSportsDB league_name values
SPORT_LEAGUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "mlb": (r"\bMLB\b", r"\bBaseball\b", r"\bWorld Baseball Classic\b"),
    "milb": (r"\bMiLB\b", r"\bMinor League Baseball\b", r"\bTriple-A\b", r"\bDouble-A\b"),
    "nhl": (r"\bNHL\b", r"\bAHL\b", r"\bECHL\b", r"\bIce Hockey\b", r"\bHockey\b"),
    "nba": (r"\bNBA\b", r"\bBasketball\b"),
    "wnba": (r"\bWNBA\b",),
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
    ),
    "ufc": (r"\bUFC\b", r"\bMMA\b", r"\bBellator\b", r"\bPFL\b", r"\bBoxing\b"),
    "tennis": (r"\bTennis\b", r"\bATP\b", r"\bWTA\b", r"\bGrand Slam\b"),
}

# Patterns to detect sport keys from channel name or category text
SPORT_HINT_PATTERNS: dict[str, tuple[str, ...]] = {
    "milb": (r"\bMiLB\b", r"\bMILB\b", r":Milb\s+\d"),
    "mlb": (r"\bMLB\b", r"\bBaseball\b"),
    "nhl": (r"\bNHL\b", r"\bHockey\b", r"\bflohockey\b"),
    "nba": (r"\bNBA\b", r"\bBasketball\b"),
    "wnba": (r"\bWNBA\b",),
    "nfl": (r"\bNFL\b", r"\bAmerican Football\b"),
    "ncaaf": (r"\bNCAA Football\b", r"\bCollege Football\b", r"\bCFB\b"),
    "ncaab": (r"\bNCAA Basketball\b", r"\bCollege Basketball\b", r"\bMarch Madness\b"),
    "mls": (r"\bMLS\b", r"\bMajor League Soccer\b"),
    "soccer": (r"\bSoccer\b", r"\bSOCCER PPV\b", r"\bFootball PPV\b", r"\bPremier League\b", r"\bLa Liga\b"),
    "ufc": (r"\bUFC\b", r"\bMMA\b", r"\bBoxing\b", r"\bBellator\b"),
    "tennis": (r"\bTennis\b", r"\bATP\b", r"\bWTA\b"),
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


@dataclass(frozen=True)
class SportLeagueContext:
    """Sport/league hints extracted from a PPV channel."""

    sport_keys: FrozenSet[str]
    raw_hints: Tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.sport_keys

    @property
    def primary_sport_key(self) -> Optional[str]:
        if not self.sport_keys:
            return None
        # Prefer more specific keys when multiple are present
        priority = ("milb", "mlb", "nhl", "nba", "wnba", "nfl", "ncaaf", "ncaab", "mls", "ufc", "tennis", "soccer")
        for key in priority:
            if key in self.sport_keys:
                return key
        return next(iter(self.sport_keys))


def _compile_league_patterns(sport_keys: FrozenSet[str]) -> Tuple[re.Pattern[str], ...]:
    patterns: list[str] = []
    for key in sport_keys:
        for pattern in SPORT_LEAGUE_PATTERNS.get(key, ()):
            if pattern not in patterns:
                patterns.append(pattern)
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


def resolve_sport_league_context(
    channel_name: str,
    category_name: Optional[str] = None,
) -> SportLeagueContext:
    """Extract sport/league hints from channel name and optional category."""
    sport_keys: set[str] = set()
    raw_hints: list[str] = []

    extractor = PPVEventExtractor()
    inline_sport, _ = extractor.extract_sport(channel_name or "")
    if inline_sport:
        raw_hints.append(inline_sport)
        _add_sport_from_text(inline_sport, sport_keys)

    combined_text = " ".join(part for part in (channel_name, category_name) if isinstance(part, str) and part)
    _add_sports_from_hint_patterns(combined_text, sport_keys, raw_hints)
    _add_sport_from_slot_prefix(channel_name or "", sport_keys, raw_hints)

    if category_name:
        _add_sports_from_hint_patterns(category_name, sport_keys, raw_hints)

    return SportLeagueContext(
        sport_keys=frozenset(sport_keys),
        raw_hints=tuple(raw_hints),
    )


def _add_sport_from_text(text: str, sport_keys: set[str]) -> None:
    _add_sports_from_hint_patterns(text, sport_keys, raw_hints=None)


def _add_sports_from_hint_patterns(
    text: str,
    sport_keys: set[str],
    raw_hints: Optional[list[str]] = None,
) -> None:
    if not text:
        return
    for sport_key, patterns in SPORT_HINT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                sport_keys.add(sport_key)
                if raw_hints is not None and sport_key not in raw_hints:
                    raw_hints.append(sport_key)
                break


def _add_sport_from_slot_prefix(
    channel_name: str,
    sport_keys: set[str],
    raw_hints: list[str],
) -> None:
    for pattern in PPV_SLOT_PATTERNS:
        match = pattern.search(channel_name)
        if not match:
            continue
        prefix = match.group(0)
        for token, sport_key in SLOT_SPORT_MAP.items():
            if token in prefix:
                sport_keys.add(sport_key)
                if sport_key not in raw_hints:
                    raw_hints.append(sport_key)
                return


def event_league_matches_context(event_league: Optional[str], context: SportLeagueContext) -> bool:
    """Return True when event league is compatible with resolved sport context."""
    if context.is_empty:
        return True
    if not event_league:
        return False

    league_patterns = _compile_league_patterns(context.sport_keys)
    return any(p.search(event_league) for p in league_patterns)


def context_for_event(event: CalendarEvent, context: SportLeagueContext) -> bool:
    """Return True when a calendar event matches the sport/league context."""
    return event_league_matches_context(event.league_name, context)


def sport_key_from_league_name(league_name: Optional[str]) -> Optional[str]:
    """Infer a sport key from a TheSportsDB league name."""
    if not league_name:
        return None
    for sport_key, patterns in SPORT_LEAGUE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, league_name, re.IGNORECASE):
                return sport_key
    return None
