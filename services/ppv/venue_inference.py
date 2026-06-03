"""Detect neutral-site / tournament titles where home-team TZ inference must be skipped."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from services.ppv.extraction import MatchupInfo

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "neutral_site_heuristics.json"


@dataclass
class VenueInferenceMode:
    mode: str  # team_home | metadata_only | low_confidence_fallback
    confidence: float
    reason: str


def validate_neutral_site_heuristics(path: Optional[Path] = None) -> tuple[bool, str]:
    """
    Validate neutral-site heuristics JSON exists and parses as an object.

    Returns (ok, message). Call at startup; tests may point ``path`` at fixtures.
    """
    config_path = path or _CONFIG_PATH
    if not config_path.is_file():
        return False, f"neutral site heuristics file missing: {config_path}"

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid neutral site heuristics JSON: {exc}"

    if not isinstance(data, dict):
        return False, "neutral site heuristics must be a JSON object"

    return True, "ok"


@lru_cache(maxsize=1)
def _load_heuristics() -> dict:
    ok, message = validate_neutral_site_heuristics()
    if not ok:
        logger.error("Neutral site heuristics invalid: %s", message)
        return {}

    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def clear_heuristics_cache() -> None:
    """Clear cached heuristics (for tests)."""
    _load_heuristics.cache_clear()


def _text_has_keyword(text: str, keywords: list) -> Optional[str]:
    lower = text.lower()
    for kw in keywords:
        if kw in lower:
            return kw
    return None


def _text_matches_regex(text: str, patterns: list) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def _both_national_teams(comp1: str, comp2: str, national_teams: list) -> bool:
    nset = {n.lower() for n in national_teams}
    return comp1.strip().lower() in nset and comp2.strip().lower() in nset


def detect_venue_inference_mode(
    channel_name: str,
    *,
    matchup: Optional["MatchupInfo"] = None,
    league_name: Optional[str] = None,
    sport: Optional[str] = None,
) -> VenueInferenceMode:
    """Tiered detection for metadata-only matching (skip home-team TZ)."""
    cfg = _load_heuristics()
    text = channel_name or ""
    lower = text.lower()

    # Tier 1 — high precision keywords
    hit = _text_has_keyword(lower, cfg.get("tier1_keywords", []))
    if hit:
        return VenueInferenceMode("metadata_only", 1.0, f"keyword:{hit.replace(' ', '_')}")

    hit = _text_matches_regex(text, cfg.get("tier1_regex", []))
    if hit:
        return VenueInferenceMode("metadata_only", 0.95, f"pattern:{hit[:40]}")

    for bowl in cfg.get("bowl_game_names", []):
        if bowl in lower:
            return VenueInferenceMode("metadata_only", 0.95, f"bowl:{bowl.replace(' ', '_')}")

    if matchup and matchup.away_team and matchup.home_team:
        if _both_national_teams(matchup.away_team, matchup.home_team, cfg.get("national_teams", [])):
            return VenueInferenceMode("metadata_only", 1.0, "national_teams")

    # Tier 2 — likely metadata_only
    hit = _text_has_keyword(lower, cfg.get("tier2_keywords", []))
    if hit:
        return VenueInferenceMode("metadata_only", 0.7, f"tier2:{hit.replace(' ', '_')}")

    if league_name:
        league_lower = league_name.lower()
        for lg in cfg.get("metadata_only_leagues", []):
            if lg in league_lower:
                return VenueInferenceMode("metadata_only", 0.7, f"league:{lg.replace(' ', '_')}")

    # Conference Final / Semi-Final — NOT neutral (explicit exception)
    if re.search(r"\bconference\s+(final|semi)", lower):
        return VenueInferenceMode("team_home", 0.85, "conference_round")

    if matchup and matchup.ordering_rule not in ("metadata_only", "unknown"):
        return VenueInferenceMode("team_home", matchup.ordering_confidence, matchup.ordering_rule)

    return VenueInferenceMode("team_home", 0.5, "default_regional")
