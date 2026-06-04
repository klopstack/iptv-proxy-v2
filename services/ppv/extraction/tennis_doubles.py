"""Parse tennis doubles / wheelchair-doubles competitor sides from IPTV titles."""

from __future__ import annotations

import re
from typing import List, Optional

_INITIAL_RE = re.compile(r"^[A-Za-z]\.?$")
_SURNAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{2,}$")


def _strip_seed_suffix(tokens: List[str]) -> List[str]:
    if tokens and tokens[-1].isdigit():
        return tokens[:-1]
    return tokens


def is_initial_token(token: str) -> bool:
    """Single-letter (optional period) initial, e.g. A, D, T."""
    return bool(_INITIAL_RE.match(token))


def is_surname_token(token: str) -> bool:
    """Surname-like token (≥3 letters); excludes numeric seeds."""
    if token.isdigit():
        return False
    return bool(_SURNAME_RE.match(token))


def looks_like_initials_doubles_tokens(tokens: List[str]) -> bool:
    """True when tokens alternate initial + surname (≥2 pairs)."""
    if len(tokens) < 4 or len(tokens) % 2 != 0:
        return False
    for i in range(0, len(tokens), 2):
        if not is_initial_token(tokens[i]) or not is_surname_token(tokens[i + 1]):
            return False
    return True


def parse_tennis_doubles_side(side: str) -> Optional[List[str]]:
    """
    Parse one side of a doubles channel title into player strings.

    Supports:
    - Initial + surname pairs: ``A Cornet D Hantuchova`` → two players
    - Explicit separators: ``Foo / Bar`` or ``Foo and Bar``
    """
    side = " ".join(side.split()).strip()
    if not side:
        return None

    if " / " in side:
        parts = [p.strip() for p in side.split(" / ")]
        if len(parts) == 2 and all(parts):
            return parts

    and_match = re.search(r"\s+and\s+", side, re.IGNORECASE)
    if and_match:
        parts = [p.strip() for p in re.split(r"\s+and\s+", side, maxsplit=1, flags=re.IGNORECASE)]
        if len(parts) == 2 and all(parts):
            return parts

    tokens = _strip_seed_suffix(side.split())
    if not looks_like_initials_doubles_tokens(tokens):
        return None

    players: List[str] = []
    for i in range(0, len(tokens), 2):
        init, surname = tokens[i], tokens[i + 1]
        players.append(f"{init} {surname}")
    return players


def format_doubles_side(players: List[str]) -> str:
    """Format players for display / loose side-level matching."""
    labels = [player_label(p) for p in players]
    return " / ".join(labels)


def player_label(player: str) -> str:
    """Prefer surname (last token) for matching calendar last names."""
    parts = player.split()
    if len(parts) >= 2 and is_initial_token(parts[0]):
        return parts[-1]
    return player.strip()


def flatten_doubles_players(side1: List[str], side2: List[str]) -> tuple[str, str, str, str]:
    return (
        player_label(side1[0]),
        player_label(side1[1]),
        player_label(side2[0]),
        player_label(side2[1]),
    )
