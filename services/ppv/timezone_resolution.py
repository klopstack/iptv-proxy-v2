"""PPV channel timezone resolution for pre-match calendar matching."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Set
from zoneinfo import ZoneInfo

from services.datetime_utils import parse_title_timezone
from services.ppv.city_timezone_map import iana_for_team_city
from services.ppv.extraction import MatchupInfo, PPVEventExtractor
from services.ppv.venue_inference import VenueInferenceMode, detect_venue_inference_mode

logger = logging.getLogger(__name__)

from services.ppv.constants import COUNTRY_PREFIX_TZ, PROVIDER_SUFFIX_TZ, US_STYLE_REGION_CODES


@dataclass
class ChannelTimezoneResolution:
    timezone: str
    confidence: float
    source: str
    venue_mode: Optional[VenueInferenceMode] = None


def extract_country_prefix(channel_name: str) -> Optional[str]:
    """Capture XX: country prefix from channel or category name."""
    return PPVEventExtractor.extract_country_prefix(channel_name)


def local_channel_datetime_to_utc(naive: datetime, resolution: ChannelTimezoneResolution) -> datetime:
    """Convert naive channel wall-clock to naive UTC using resolved IANA zone."""
    from services.datetime_utils import to_naive_utc

    tz = ZoneInfo(resolution.timezone)
    localized = naive.replace(tzinfo=tz)
    return to_naive_utc(localized)


def resolve_channel_timezone(
    channel_name: str,
    *,
    category_name: Optional[str] = None,
    country_tags: Optional[Set[str]] = None,
    sport: Optional[str] = None,
    league_name: Optional[str] = None,
    competitors: Optional[tuple[str, str]] = None,
    matchup: Optional[MatchupInfo] = None,
) -> ChannelTimezoneResolution:
    """Resolve IANA timezone for pre-match channel title datetime conversion."""
    extractor = PPVEventExtractor()

    if matchup is None and competitors:
        matchup = extractor.extract_matchup(channel_name)

    venue_mode = detect_venue_inference_mode(
        channel_name,
        matchup=matchup,
        league_name=league_name,
        sport=sport,
    )

    # Explicit title token (highest priority)
    token_tz = parse_title_timezone(channel_name)
    if token_tz:
        return ChannelTimezoneResolution(token_tz, 0.95, "title_token", venue_mode)

    # Parenthetical ISO datetime — provider-supplied UTC (WNBA/NBA feeds)
    if PPVEventExtractor.has_iso_paren_utc_datetime(channel_name):
        return ChannelTimezoneResolution("UTC", 0.95, "iso_paren_utc", venue_mode)

    # Provider suffix (e.g. ":Viaplay SE", ":Telia FI") before generic fallbacks
    provider_tz = _provider_suffix_timezone(channel_name)
    if provider_tz:
        return provider_tz

    # metadata_only: skip home venue; use prefix/tags only
    if venue_mode.mode == "metadata_only":
        prefix = extract_country_prefix(channel_name) or (
            extract_country_prefix(category_name) if category_name else None
        )
        if prefix and prefix.upper() in COUNTRY_PREFIX_TZ:
            code = prefix.upper()
            return ChannelTimezoneResolution(COUNTRY_PREFIX_TZ[code], 0.4, "metadata_only_prefix", venue_mode)
        if country_tags:
            for tag in sorted(country_tags):
                code = tag.upper()
                if code in COUNTRY_PREFIX_TZ:
                    return ChannelTimezoneResolution(COUNTRY_PREFIX_TZ[code], 0.35, "metadata_only_tag", venue_mode)
        return ChannelTimezoneResolution("UTC", 0.2, "metadata_only_fallback", venue_mode)

    # Home venue via SportsTeam (US multi-zone)
    if matchup and matchup.home_team and venue_mode.mode == "team_home":
        home_tz = _home_team_timezone(matchup.home_team, sport)
        if home_tz:
            conf = min(0.9, venue_mode.confidence + 0.05)
            return ChannelTimezoneResolution(home_tz, conf, "home_venue_sports_team", venue_mode)

    # Title country prefix
    prefix = extract_country_prefix(channel_name) or (extract_country_prefix(category_name) if category_name else None)
    if prefix:
        code = prefix.upper()
        if code in COUNTRY_PREFIX_TZ:
            return ChannelTimezoneResolution(COUNTRY_PREFIX_TZ[code], 0.85, "name_prefix", venue_mode)
        if code in US_STYLE_REGION_CODES:
            # Multi-zone US/CA/JP without home team — low confidence Eastern/Central fallback
            return ChannelTimezoneResolution("America/New_York", 0.3, "multi_zone_prefix_fallback", venue_mode)

    # Channel country tags
    if country_tags:
        for tag in sorted(country_tags):
            code = tag.upper()
            if code in COUNTRY_PREFIX_TZ:
                return ChannelTimezoneResolution(COUNTRY_PREFIX_TZ[code], 0.8, "channel_tag", venue_mode)

    # Category prefix
    if category_name:
        cat_prefix = extract_country_prefix(category_name)
        if cat_prefix and cat_prefix.upper() in COUNTRY_PREFIX_TZ:
            return ChannelTimezoneResolution(COUNTRY_PREFIX_TZ[cat_prefix.upper()], 0.75, "category_prefix", venue_mode)

    return ChannelTimezoneResolution("America/New_York", 0.25, "fallback", venue_mode)


def _provider_suffix_timezone(channel_name: str) -> Optional[ChannelTimezoneResolution]:
    for pattern, tz, source in PROVIDER_SUFFIX_TZ:
        if pattern.search(channel_name):
            return ChannelTimezoneResolution(tz, 0.85, source, None)
    return None


def _home_team_timezone(home_team: str, sport: Optional[str]) -> Optional[str]:
    try:
        from models.ppv import SportsTeam

        sport_key = _sport_to_team_key(sport)
        if sport_key:
            tz = SportsTeam.home_timezone_for_team(home_team, sport_key)
            if tz:
                return tz
        return iana_for_team_city(home_team)
    except Exception:
        return iana_for_team_city(home_team)


def _sport_to_team_key(sport: Optional[str]) -> Optional[str]:
    if not sport:
        return None
    s = sport.lower()
    mapping = {
        "baseball": "mlb",
        "mlb": "mlb",
        "basketball": "nba",
        "nba": "nba",
        "ice hockey": "nhl",
        "hockey": "nhl",
        "nhl": "nhl",
        "american football": "nfl",
        "nfl": "nfl",
        "ncaa football": "ncaaf",
        "college football": "ncaaf",
        "soccer": "fb",
        "football": "fb",
    }
    for key, val in mapping.items():
        if key in s:
            return val
    return None


def resolve_channel_datetime_utc(
    channel_name: str,
    naive_dt: datetime,
    *,
    category_name: Optional[str] = None,
    country_tags: Optional[Set[str]] = None,
    sport: Optional[str] = None,
    league_name: Optional[str] = None,
    extraction: Optional[dict] = None,
) -> tuple[datetime, ChannelTimezoneResolution]:
    """Convert extracted naive channel datetime to UTC for matching."""
    ext = extraction or PPVEventExtractor().extract_all(channel_name)
    competitors = ext.get("competitors")
    matchup = ext.get("matchup")
    resolution = resolve_channel_timezone(
        channel_name,
        category_name=category_name,
        country_tags=country_tags,
        sport=sport or ext.get("sport"),
        league_name=league_name,
        competitors=competitors,
        matchup=matchup,
    )
    return local_channel_datetime_to_utc(naive_dt, resolution), resolution


def calendar_date_key_for_channel(
    naive_dt: datetime,
    resolution: ChannelTimezoneResolution,
) -> str:
    """UTC calendar date (YYYY-MM-DD) for grouping channel fetches."""
    utc_dt = local_channel_datetime_to_utc(naive_dt, resolution)
    return utc_dt.strftime("%Y-%m-%d")


def metadata_only_date_tolerance_hours(venue_mode: Optional[VenueInferenceMode]) -> int:
    """Wider MatchFilter tolerance for neutral-site / tournament titles."""
    if venue_mode and venue_mode.mode == "metadata_only":
        return 72
    return 48
