"""
Tag-based output category resolution for M3U group-title and Xtream categories.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from models import Account, Channel, PlaylistConfig

DMA_PREFIX = "DMA:"
CITY_GROUP_PREFIX = "city"
DISPLAY_STRIP_PREFIX_TITLE = "strip_prefix_title"
DISPLAY_AS_TAG = "as_tag"

PRESET_DMA = {
    "enabled": True,
    "prefixes": [DMA_PREFIX],
    "display": DISPLAY_STRIP_PREFIX_TITLE,
}

# Xtream-only parent folder for tag-derived market/local categories (M3U stays flat).
# Negative numeric IDs match Xtream FlexInt expectations (see PPV virtual categories).
XTREAM_LOCAL_CHANNELS_PARENT_ID = "-20"
XTREAM_LOCAL_CHANNELS_PARENT_NAME = "Local Channels"
XTREAM_VIRTUAL_CATEGORY_ID_MIN = -8999
XTREAM_VIRTUAL_CATEGORY_ID_MAX = -1000


@dataclass(frozen=True)
class CategoryTagGrouping:
    enabled: bool
    prefixes: tuple[str, ...]
    display: str


def _normalize_prefix(prefix: str) -> str:
    return prefix.upper() if ":" in prefix else prefix.upper() + ":"


def parse_grouping_config(raw: Union[str, dict, None]) -> Optional[CategoryTagGrouping]:
    """Parse and validate grouping config from JSON text or dict."""
    if raw is None:
        return None

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
    else:
        data = raw

    if not isinstance(data, dict):
        return None

    if not data.get("enabled"):
        return None

    prefixes = data.get("prefixes") or []
    if not prefixes:
        return None

    display = data.get("display") or DISPLAY_STRIP_PREFIX_TITLE
    if display not in (DISPLAY_STRIP_PREFIX_TITLE, DISPLAY_AS_TAG):
        display = DISPLAY_STRIP_PREFIX_TITLE

    normalized = tuple(_normalize_prefix(p) for p in prefixes if p)
    if not normalized:
        return None

    return CategoryTagGrouping(enabled=True, prefixes=normalized, display=display)


def grouping_to_dict(grouping: Optional[CategoryTagGrouping]) -> Optional[dict]:
    """Serialize grouping for API responses."""
    if grouping is None:
        return None
    return {
        "enabled": grouping.enabled,
        "prefixes": list(grouping.prefixes),
        "display": grouping.display,
    }


def grouping_from_db_column(column_value: Union[str, None]) -> Optional[CategoryTagGrouping]:
    """Load grouping from a model Text column."""
    return parse_grouping_config(column_value)


def grouping_needs_fcc_facility(grouping: Optional[CategoryTagGrouping]) -> bool:
    """Whether FCC facility data should be loaded for DMA labels and city fallbacks."""
    return grouping is not None and DMA_PREFIX in grouping.prefixes


def _has_dma_tag(tags: Sequence[str]) -> bool:
    return _find_matching_tag(tags, [DMA_PREFIX]) is not None


def _fcc_city_category_name(
    channel: Channel,
    tags: Sequence[str],
    facility: Any,
    grouping: CategoryTagGrouping,
) -> Optional[str]:
    """City-based category for FCC-matched channels that have no Nielsen DMA."""
    if DMA_PREFIX not in grouping.prefixes:
        return None
    if not channel.fcc_facility_id:
        return None
    if _has_dma_tag(tags):
        return None
    if facility is None:
        return None
    if getattr(facility, "nielsen_dma", None):
        return None

    city = (getattr(facility, "community_city", None) or "").strip()
    if not city:
        return None

    return _title_case_dma(city.replace("_", " "))


def effective_grouping(
    account: Optional[Account],
    playlist_config: Optional[PlaylistConfig] = None,
) -> Optional[CategoryTagGrouping]:
    """Resolve grouping: playlist config override wins when set."""
    if playlist_config is not None and playlist_config.category_tag_grouping:
        config_grouping = parse_grouping_config(playlist_config.category_tag_grouping)
        if config_grouping is not None:
            return config_grouping

    if account is not None and account.category_tag_grouping:
        return parse_grouping_config(account.category_tag_grouping)

    return None


def _provider_category_name(channel: Channel) -> str:
    if channel.category:
        return channel.category.cleaned_name or channel.category.category_name or "Unknown"
    return "Unknown"


def _title_case_dma(value: str) -> str:
    """Title-case a DMA or location string, preserving hyphens."""
    parts = re.split(r"(\s+|-)", value.strip())
    result = []
    for part in parts:
        if part in (" ", "-", ""):
            result.append(part)
        else:
            result.append(part[:1].upper() + part[1:].lower() if len(part) > 1 else part.upper())
    return "".join(result).strip()


def format_tag_value(
    tag: str,
    prefix: str,
    display: str,
    *,
    facility: Any = None,
) -> str:
    """Format a matched tag into a display category name."""
    prefix_upper = prefix.upper()
    tag_upper = tag.upper()

    if prefix_upper == DMA_PREFIX and facility is not None and getattr(facility, "nielsen_dma", None):
        value = facility.nielsen_dma
    elif tag_upper.startswith(prefix_upper):
        value = tag[len(prefix) :]
    else:
        value = tag

    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()

    if display == DISPLAY_AS_TAG:
        return value

    return _title_case_dma(value)


def _find_matching_tag(tags: Sequence[str], prefixes: Sequence[str]) -> Optional[tuple[str, str]]:
    """Return (tag, prefix) for the first prefix match in tag list order."""
    tags_upper = {t.upper(): t for t in tags}
    for prefix in prefixes:
        prefix_upper = prefix.upper()
        for tag_key, original in tags_upper.items():
            if tag_key.startswith(prefix_upper):
                return original, prefix
    return None


def _resolve_grouped_category(
    channel: Channel,
    tags: Sequence[str],
    grouping: CategoryTagGrouping,
    *,
    facility: Any = None,
) -> Optional[tuple[str, str]]:
    """Return (display_name, virtual_id_prefix) when tag/FCC grouping applies."""
    match = _find_matching_tag(tags, grouping.prefixes)
    if match:
        tag, prefix = match
        name = format_tag_value(tag, prefix, grouping.display, facility=facility)
        prefix_slug = prefix.rstrip(":").lower() or "tag"
        return name, prefix_slug

    city_name = _fcc_city_category_name(channel, tags, facility, grouping)
    if city_name:
        return city_name, CITY_GROUP_PREFIX

    return None


def resolve_output_category(
    channel: Channel,
    tags: Sequence[str],
    *,
    account: Optional[Account] = None,
    playlist_config: Optional[PlaylistConfig] = None,
    facility: Any = None,
) -> str:
    """Resolve output category from tags, falling back to provider category."""
    grouping = effective_grouping(account, playlist_config)
    if grouping is None:
        return _provider_category_name(channel)

    grouped = _resolve_grouped_category(channel, tags, grouping, facility=facility)
    if grouped is None:
        return _provider_category_name(channel)

    return grouped[0]


def xtream_local_channels_parent_category() -> dict:
    """Virtual Xtream parent category for nested tag-based groups."""
    return {
        "category_id": XTREAM_LOCAL_CHANNELS_PARENT_ID,
        "category_name": XTREAM_LOCAL_CHANNELS_PARENT_NAME,
        "parent_id": 0,
    }


def virtual_category_id(category_name: str, prefix: str = "") -> str:
    """Stable negative numeric virtual category ID for Xtream API."""
    key = f"{prefix}:{category_name}".lower().strip()
    span = XTREAM_VIRTUAL_CATEGORY_ID_MAX - XTREAM_VIRTUAL_CATEGORY_ID_MIN + 1
    slot = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % span
    return str(XTREAM_VIRTUAL_CATEGORY_ID_MIN + slot)


def is_xtream_virtual_category_id(category_id) -> bool:
    """True for tag-derived Xtream virtual category IDs (not the Local Channels parent)."""
    try:
        value = int(category_id)
    except (TypeError, ValueError):
        return False
    return XTREAM_VIRTUAL_CATEGORY_ID_MIN <= value <= XTREAM_VIRTUAL_CATEGORY_ID_MAX


def build_virtual_category_map(
    channels: List[Channel],
    tags_map: Dict[tuple, List[str]],
    *,
    accounts_by_id: Dict[int, Account],
    playlist_config: Optional[PlaylistConfig] = None,
    facilities_by_channel_id: Optional[Dict[int, Any]] = None,
) -> Dict[int, dict]:
    """
    Map channel.id -> virtual category info for tag-grouped channels.

    Returns dict with keys: category_id, category_name, prefix (only for grouped channels).
    Channels without tag grouping are omitted.
    """
    facilities_by_channel_id = facilities_by_channel_id or {}
    result: Dict[int, dict] = {}

    for channel in channels:
        account = accounts_by_id.get(channel.account_id)
        grouping = effective_grouping(account, playlist_config)
        if grouping is None:
            continue

        tags = tags_map.get((channel.account_id, channel.stream_id), [])
        facility = facilities_by_channel_id.get(channel.id)
        grouped = _resolve_grouped_category(channel, tags, grouping, facility=facility)
        if grouped is None:
            continue

        category_name, id_prefix = grouped
        result[channel.id] = {
            "category_id": virtual_category_id(category_name, id_prefix),
            "category_name": category_name,
            "prefix": id_prefix,
        }

    return result


def serialize_grouping_for_api(column_value: Union[str, None]) -> Optional[dict]:
    """Parse DB column and return API dict (preserves disabled configs)."""
    if column_value is None:
        return None
    if isinstance(column_value, str) and not column_value.strip():
        return None
    try:
        if isinstance(column_value, str):
            data = json.loads(column_value)
        else:
            data = column_value
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def serialize_grouping_for_db(grouping: Optional[dict]) -> Optional[str]:
    """Serialize grouping dict for DB storage."""
    if grouping is None:
        return None
    if not grouping.get("enabled"):
        return json.dumps({"enabled": False})
    return json.dumps(grouping)
