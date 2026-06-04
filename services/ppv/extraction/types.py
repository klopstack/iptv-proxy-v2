"""Shared types for PPV channel name extraction."""

from dataclasses import dataclass
from typing import Literal, Optional, Tuple


@dataclass
class ExtractedCompetitors:
    """Result of competitor extraction from a channel title."""

    side1: str
    side2: str
    format: Literal["singles", "doubles"] = "singles"
    players: Optional[Tuple[str, str, str, str]] = None


@dataclass
class MatchupInfo:
    away_team: Optional[str]
    home_team: Optional[str]
    separator: str
    ordering_rule: str  # us_away_home | eu_home_away | metadata_only | unknown
    ordering_confidence: float
    first_team: Optional[str] = None
    second_team: Optional[str] = None
    format: Literal["singles", "doubles"] = "singles"
    players: Optional[Tuple[str, str, str, str]] = None
