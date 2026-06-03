"""Shared types for PPV channel name extraction."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MatchupInfo:
    away_team: Optional[str]
    home_team: Optional[str]
    separator: str
    ordering_rule: str  # us_away_home | eu_home_away | metadata_only | unknown
    ordering_confidence: float
    first_team: Optional[str] = None
    second_team: Optional[str] = None
