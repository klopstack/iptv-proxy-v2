"""Resolve sport/league context from PPV channel names and categories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

from services.ppv.extraction import PPVEventExtractor
from services.ppv.slot_extraction import PPV_SLOT_PATTERNS
from services.ppv.sport_registry import (
    CONTEXT_SPORT_PRIORITY,
    SLOT_SPORT_MAP,
    SPORT_HINT_PATTERNS,
    SPORT_LEAGUE_PATTERNS,
    primary_sport_key,
    sport_key_from_league_name,
)
from services.thesportsdb_calendar_scraper import CalendarEvent


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
        return primary_sport_key(self.sport_keys)


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


__all__ = [
    "CONTEXT_SPORT_PRIORITY",
    "SLOT_SPORT_MAP",
    "SPORT_HINT_PATTERNS",
    "SPORT_LEAGUE_PATTERNS",
    "SportLeagueContext",
    "context_for_event",
    "event_league_matches_context",
    "resolve_sport_league_context",
    "sport_key_from_league_name",
]
