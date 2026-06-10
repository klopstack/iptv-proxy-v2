"""SofaScore sport slug registry and feature-flag wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from models.sync import Settings
from services.ppv.calendar_providers.sofascore import parser_football, parser_tennis
from services.ppv.constants import SETTING_PPV_SOFASCORE_CALENDAR_ENABLED, SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED
from services.thesportsdb_calendar_scraper import CalendarEvent


@dataclass(frozen=True)
class SofaScoreSlugConfig:
    slug: str
    setting_key: str
    default_enabled: str
    parser: Callable[[dict, str], List[CalendarEvent]]
    sport_filter_tokens: frozenset[str]
    dedup_strategy: str


def _setting_enabled(key: str, *, default: str) -> bool:
    return Settings.get(key, default).lower() in ("true", "1", "yes", "on")


SLUG_REGISTRY: Dict[str, SofaScoreSlugConfig] = {
    "tennis": SofaScoreSlugConfig(
        slug="tennis",
        setting_key=SETTING_PPV_SOFASCORE_CALENDAR_ENABLED,
        default_enabled="false",
        parser=lambda payload, date_str: parser_tennis.parse_tennis_scheduled_events(payload, date_str=date_str),
        sport_filter_tokens=frozenset({"tennis", "", "all"}),
        dedup_strategy="espn_tennis",
    ),
    "football": SofaScoreSlugConfig(
        slug="football",
        setting_key=SETTING_PPV_SOFASCORE_FOOTBALL_ENABLED,
        default_enabled="true",
        parser=lambda payload, date_str: parser_football.parse_football_scheduled_events(payload, date_str=date_str),
        sport_filter_tokens=frozenset({"", "all", "soccer", "football"}),
        dedup_strategy="tsdb_football",
    ),
}


def slug_enabled(slug: str) -> bool:
    config = SLUG_REGISTRY.get(slug)
    if not config:
        return False
    return _setting_enabled(config.setting_key, default=config.default_enabled)


def enabled_slugs() -> List[str]:
    return [slug for slug in SLUG_REGISTRY if slug_enabled(slug)]


def slug_allowed_for_sport_filter(slug: str, sport: str) -> bool:
    config = SLUG_REGISTRY.get(slug)
    if not config:
        return False
    sport_lower = (sport or "").lower()
    return sport_lower in config.sport_filter_tokens or "all" in config.sport_filter_tokens
