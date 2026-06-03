"""Competitor, sport, and matchup extraction from PPV channel names."""

import re
from typing import Optional, Tuple

from services.ppv.constants import US_STYLE_REGION_CODES
from services.ppv.extraction.patterns import (
    BARE_PPV_SLOT_RE,
    COMPETITOR_PATTERN,
    COUNTRY_PREFIX_RE,
    NO_EVENT_PATTERN,
    PROVIDER_SLOT_RE,
    SPORT_PATTERN,
    TOURNAMENT_STRUCTURE_PATTERN,
    TRAILING_TIME_PATTERN,
)
from services.ppv.extraction.types import MatchupInfo


def is_placeholder(channel_name: str) -> bool:
    return bool(re.search(NO_EVENT_PATTERN, channel_name, re.IGNORECASE))


def is_inactive_channel(channel_name: str) -> bool:
    name = channel_name.strip()

    if not name or len(name) < 5:
        return True

    if re.match(r"^\([^)]*\)$", name):
        return True

    if re.match(r"^[:\s\d]+$", name):
        return True

    if re.match(r"^[#*_\s:]+$", name):
        return True

    return False


def extract_sport(channel_name: str) -> Tuple[Optional[str], str]:
    match = re.search(SPORT_PATTERN, channel_name, re.IGNORECASE)
    if not match:
        return None, channel_name

    sport = match.group(0)
    cleaned = channel_name[: match.start()] + channel_name[match.end() :]
    cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return sport, cleaned


def clean_tournament_structure(channel_name: str) -> str:
    cleaned = re.sub(TOURNAMENT_STRUCTURE_PATTERN, "", channel_name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def strip_provider_prefix(name: str) -> str:
    prev = None
    result = name
    while result != prev:
        prev = result
        result = COUNTRY_PREFIX_RE.sub("", result).strip()
        result = PROVIDER_SLOT_RE.sub("", result).strip()
        result = BARE_PPV_SLOT_RE.sub("", result).strip()
    return result


def extract_country_prefix(name: str) -> Optional[str]:
    if not name:
        return None
    m = COUNTRY_PREFIX_RE.match(name.strip())
    if not m:
        return None
    raw = name.strip()[: m.end()].rstrip(": ").upper()
    return raw.rstrip(":")


def detect_separator(cleaned_name: str) -> Optional[str]:
    if re.search(r"\s+vs\.?\s+", cleaned_name, re.IGNORECASE):
        return "vs"
    if re.search(r"\s+x\s+", cleaned_name, re.IGNORECASE):
        return "x"
    if re.search(r"\s+(?:at|@|versus)\.?\s+", cleaned_name, re.IGNORECASE):
        return "@"
    if re.search(r"[A-Z][A-Za-z\s&\'\-]+?\s+-\s+[A-Z][A-Za-z\s&\'\-]+", cleaned_name):
        return "-"
    return None


def clean_team_name(name: str) -> str:
    name = re.sub(TRAILING_TIME_PATTERN, "", name, flags=re.IGNORECASE)
    name = re.sub(r":\w+.*$", "", name)
    name = re.sub(r"^#?\s*\d+\s+", "", name)
    name = re.sub(r"\s+\d+$", "", name)
    name = " ".join(name.split())
    return name.strip()


def is_valid_team_name(name: str) -> bool:
    if len(name) < 2:
        return False

    if re.match(r"^[\d\s]+$", name):
        return False

    if re.match(
        r"^(PPV|HD|ᴴᴰ|ᴿᴬᵂ|RAW|4K|60FPS|Day|Round|Game|Match|Studio|Championship|Bowl|Cup)", name, re.IGNORECASE
    ):
        return False

    if re.match(r"^(Day|Round|Game|Match|Studio)\s*\d+", name, re.IGNORECASE):
        return False

    if re.match(r"^(SD|HD|FHD)$", name) and len(name) <= 3:
        return False

    if re.match(r"(HD|SD|FHD|4K|RAW|PPV)$", name, re.IGNORECASE):
        return False

    return True


def extract_competitors(channel_name: str) -> Optional[Tuple[str, str]]:
    if is_placeholder(channel_name):
        return None

    _, cleaned_name = extract_sport(channel_name)
    cleaned_name = strip_provider_prefix(cleaned_name)
    cleaned_name = clean_tournament_structure(cleaned_name)

    match = re.search(COMPETITOR_PATTERN, cleaned_name, re.IGNORECASE)
    if not match:
        return None

    if match.group(1) is not None:
        comp1 = match.group(1).strip()
        comp2 = match.group(2).strip()
    elif match.group(3) is not None:
        comp1 = match.group(3).strip()
        comp2 = match.group(4).strip()
    elif match.group(5) is not None:
        comp1 = match.group(5).strip()
        comp2 = match.group(6).strip()
    else:
        comp1 = match.group(7).strip()
        comp2 = match.group(8).strip()

    comp1 = clean_team_name(comp1)
    comp2 = clean_team_name(comp2)

    if not is_valid_team_name(comp1) or not is_valid_team_name(comp2):
        return None

    return (comp1, comp2)


def feed_region_code(channel_name: str, category_name: Optional[str] = None) -> Optional[str]:
    prefix = extract_country_prefix(channel_name)
    if prefix:
        return prefix.upper()
    if category_name:
        cat = extract_country_prefix(category_name)
        if cat:
            return cat.upper()
    return None


def extract_matchup(
    channel_name: str,
    *,
    category_name: Optional[str] = None,
) -> Optional[MatchupInfo]:
    from services.ppv.venue_inference import detect_venue_inference_mode

    competitors = extract_competitors(channel_name)
    if not competitors:
        return None

    comp1, comp2 = competitors
    _, cleaned = extract_sport(channel_name)
    cleaned = strip_provider_prefix(cleaned)
    cleaned = clean_tournament_structure(cleaned)
    separator = detect_separator(cleaned) or "vs"

    region = feed_region_code(channel_name, category_name)
    us_style = region in US_STYLE_REGION_CODES if region else False

    draft = MatchupInfo(
        away_team=comp1 if us_style else comp2,
        home_team=comp2 if us_style else comp1,
        separator=separator,
        ordering_rule="us_away_home" if us_style else "eu_home_away",
        ordering_confidence=0.85 if separator in ("@", "at", "versus") else 0.8,
        first_team=comp1,
        second_team=comp2,
    )

    if not region:
        draft = MatchupInfo(
            away_team=comp2,
            home_team=comp1,
            separator=separator,
            ordering_rule="eu_home_away",
            ordering_confidence=0.65,
            first_team=comp1,
            second_team=comp2,
        )

    venue_mode = detect_venue_inference_mode(channel_name, matchup=draft)
    if venue_mode.mode == "metadata_only":
        draft.ordering_rule = "metadata_only"
        draft.ordering_confidence = venue_mode.confidence

    return draft
