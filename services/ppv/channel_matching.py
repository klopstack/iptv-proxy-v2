"""Build timezone and date context for PPV channel → calendar matching."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from models import Channel
from services.ppv.timezone_resolution import (
    ChannelTimezoneResolution,
    calendar_date_key_for_channel,
    local_channel_datetime_to_utc,
    metadata_only_date_tolerance_hours,
    resolve_channel_timezone,
)


def _category_name(channel: Channel) -> Optional[str]:
    category = getattr(channel, "category", None)
    if category is None:
        return None
    name = getattr(category, "category_name", None)
    return name if isinstance(name, str) else None


def load_country_tags_for_channel(channel: Channel) -> Set[str]:
    """Load EPG country tags for a single channel."""
    account_id = getattr(channel, "account_id", None)
    stream_id = getattr(channel, "stream_id", None)
    if account_id is None or stream_id is None:
        return set()
    if not isinstance(account_id, int) or not isinstance(stream_id, str):
        return set()
    from services.epg.fcc.matching import load_country_tags_for_channels

    tags_map = load_country_tags_for_channels(account_id, [channel])
    return tags_map.get(stream_id, set())


def build_matching_context_from_name(
    channel_name: str,
    extraction: Dict[str, Any],
    *,
    category_name: Optional[str] = None,
    country_tags: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Resolve pre-match timezone context from extraction (no Channel required)."""
    tags = country_tags or set()
    naive_dt = extraction.get("date")
    competitors = extraction.get("competitors")
    matchup = extraction.get("matchup")

    resolution = resolve_channel_timezone(
        channel_name,
        category_name=category_name,
        country_tags=tags,
        sport=extraction.get("sport"),
        competitors=competitors,
        matchup=matchup,
    )

    channel_date_utc: Optional[datetime] = None
    channel_date_for_match: Optional[datetime] = None
    calendar_date: Optional[str] = None
    if isinstance(naive_dt, datetime):
        channel_date_utc = local_channel_datetime_to_utc(naive_dt, resolution)
        channel_date_for_match = channel_date_utc.replace(tzinfo=timezone.utc)
        calendar_date = calendar_date_key_for_channel(naive_dt, resolution)

    tolerance = metadata_only_date_tolerance_hours(resolution.venue_mode)

    return {
        "category_name": category_name,
        "country_tags": tags,
        "timezone_resolution": resolution,
        "channel_date_utc": channel_date_utc,
        "channel_date_for_match": channel_date_for_match,
        "calendar_date": calendar_date,
        "date_tolerance_hours": tolerance,
        "metadata_only": resolution.venue_mode.mode == "metadata_only" if resolution.venue_mode else False,
    }


def build_channel_matching_context(
    channel: Channel,
    extraction: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve pre-match timezone, UTC datetime, and calendar day for matching."""
    category_name = _category_name(channel)
    country_tags = load_country_tags_for_channel(channel)
    ctx = build_matching_context_from_name(
        channel.name,
        extraction,
        category_name=category_name,
        country_tags=country_tags,
    )
    return ctx


def infer_unmatched_timezone_debug(
    channel: Channel,
    extraction: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Heuristic timezone fields for no_match preview rows."""
    from services.datetime_utils import serialize_utc_iso
    from services.ppv.extraction import PPVEventExtractor

    ext = extraction or PPVEventExtractor().extract_all(channel.name)
    ctx = build_channel_matching_context(channel, ext)
    resolution: ChannelTimezoneResolution = ctx["timezone_resolution"]
    naive_dt = ext.get("date")
    inferred_utc = None
    if isinstance(naive_dt, datetime):
        inferred_utc = serialize_utc_iso(ctx["channel_date_utc"])

    venue = resolution.venue_mode
    return {
        "inferred_timezone": resolution.timezone,
        "inferred_utc": inferred_utc,
        "timezone_confidence": resolution.confidence,
        "timezone_source": resolution.source,
        "metadata_only": ctx["metadata_only"],
        "ordering_rule": venue.reason if venue else None,
    }
