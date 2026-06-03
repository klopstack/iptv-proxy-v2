"""Select preferred broadcast-language feeds for PPV event groups."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from models import Channel, ChannelTag, EventChannelLink, Tag, db
from services.quality_service import QualityService

logger = logging.getLogger(__name__)

VALID_FALLBACKS = frozenset({"unknown", "hide", "show_all"})
DEFAULT_PREFERRED_LANGUAGES = ["en"]
UNKNOWN_LANGS = frozenset({"und", "unknown"})


def parse_preferred_languages(value: Any) -> List[str]:
    """Parse JSON text, comma-separated string, or list into normalized ISO 639-1 codes."""
    if value is None:
        return list(DEFAULT_PREFERRED_LANGUAGES)

    if isinstance(value, list):
        langs = [str(item).strip().lower() for item in value if str(item).strip()]
        return langs or list(DEFAULT_PREFERRED_LANGUAGES)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return list(DEFAULT_PREFERRED_LANGUAGES)
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parse_preferred_languages(parsed)
            except json.JSONDecodeError:
                pass
        langs = [part.strip().lower() for part in stripped.split(",") if part.strip()]
        return langs or list(DEFAULT_PREFERRED_LANGUAGES)

    return list(DEFAULT_PREFERRED_LANGUAGES)


def normalize_language_fallback(value: Optional[str]) -> str:
    fallback = (value or "unknown").strip().lower()
    if fallback not in VALID_FALLBACKS:
        return "unknown"
    return fallback


def _normalize_lang(lang: Optional[str]) -> str:
    if not lang:
        return "und"
    normalized = lang.strip().lower()
    return normalized or "und"


def _preference_score(lang: Optional[str], preferred_languages: Sequence[str], fallback: str) -> int:
    """Lower score is better. Unknown langs scored per fallback mode."""
    normalized = _normalize_lang(lang)

    if normalized not in UNKNOWN_LANGS:
        try:
            return preferred_languages.index(normalized)
        except ValueError:
            return len(preferred_languages) + 10

    if fallback == "unknown":
        return len(preferred_languages)
    if fallback == "hide":
        return len(preferred_languages) + 100
    return len(preferred_languages) + 50


def _load_event_links(channels: List[Channel]) -> Dict[int, Tuple[int, float]]:
    """Map channel_id -> (event_id, match_confidence)."""
    if not channels:
        return {}

    channel_ids = [ch.id for ch in channels]
    rows = (
        db.session.query(
            EventChannelLink.channel_id,
            EventChannelLink.event_id,
            EventChannelLink.match_confidence,
        )
        .filter(EventChannelLink.channel_id.in_(channel_ids))
        .all()
    )
    return {channel_id: (event_id, match_confidence or 0.0) for channel_id, event_id, match_confidence in rows}


def _load_channel_tags(channels: List[Channel]) -> Dict[int, List[str]]:
    if not channels:
        return {}

    result: Dict[int, List[str]] = {ch.id: [] for ch in channels}
    account_ids = list({ch.account_id for ch in channels})
    stream_ids = [ch.stream_id for ch in channels]

    rows = (
        db.session.query(ChannelTag.account_id, ChannelTag.stream_id, Tag.name)
        .join(Tag, Tag.id == ChannelTag.tag_id)
        .filter(
            ChannelTag.account_id.in_(account_ids),
            ChannelTag.stream_id.in_(stream_ids),
        )
        .all()
    )
    ch_by_key = {(ch.account_id, ch.stream_id): ch.id for ch in channels}
    for account_id, stream_id, tag_name in rows:
        ch_id = ch_by_key.get((account_id, stream_id))
        if ch_id is not None:
            result[ch_id].append(tag_name)
    return result


def _quality_score(channel: Channel, tags_map: Dict[int, List[str]]) -> int:
    health = None
    if channel.health_status:
        health = {
            "status": channel.health_status.status,
            "successful_checks": channel.health_status.successful_checks or 0,
            "total_checks": channel.health_status.total_checks or 0,
        }
    return QualityService.get_quality_score_with_health(tags_map.get(channel.id, []), health)


def _rank_channel(
    channel: Channel,
    *,
    preferred_languages: Sequence[str],
    fallback: str,
    event_links: Dict[int, Tuple[int, float]],
    tags_map: Dict[int, List[str]],
) -> Tuple[int, float, int, str]:
    """Sort key tuple: lower is better for first element."""
    lang_score = _preference_score(channel.broadcast_language, preferred_languages, fallback)
    _, match_confidence = event_links.get(channel.id, (None, 0.0))
    quality = _quality_score(channel, tags_map)
    stream_id = channel.stream_id or ""
    return (lang_score, -match_confidence, -quality, stream_id)


def select_preferred_channels(
    channels: List[Channel],
    preferred_languages: List[str],
    fallback: str = "unknown",
) -> List[Channel]:
    """
    Keep one feed per PPV event group based on language preference.

    Ungrouped channels (no event link, or sole feed) pass through unchanged.
    When all feeds are non-preferred, keep the highest match_confidence feed.
    When fallback is show_all, skip event-group filtering entirely.
    """
    if not channels:
        return []

    fallback = normalize_language_fallback(fallback)
    preferred = [lang.strip().lower() for lang in preferred_languages if lang.strip()]
    if not preferred:
        preferred = list(DEFAULT_PREFERRED_LANGUAGES)

    if fallback == "show_all":
        return channels

    event_links = _load_event_links(channels)
    tags_map = _load_channel_tags(channels)

    by_event: Dict[int, List[Channel]] = defaultdict(list)
    ungrouped: List[Channel] = []

    for channel in channels:
        link = event_links.get(channel.id)
        if link is None:
            ungrouped.append(channel)
            continue
        event_id, _ = link
        by_event[event_id].append(channel)

    winners: Set[int] = set()
    for _event_id, group in by_event.items():
        if len(group) == 1:
            winners.add(group[0].id)
            continue

        ranked = sorted(
            group,
            key=lambda ch: _rank_channel(
                ch,
                preferred_languages=preferred,
                fallback=fallback,
                event_links=event_links,
                tags_map=tags_map,
            ),
        )
        winners.add(ranked[0].id)

    winner_ids = winners | {ch.id for ch in ungrouped}
    return [ch for ch in channels if ch.id in winner_ids]


def apply_language_preference(
    channels: List[Channel],
    preferred_languages: Optional[Union[str, List[str]]] = None,
    language_fallback: str = "unknown",
) -> List[Channel]:
    """Apply language preference filtering when preferred_languages is configured."""
    parsed = parse_preferred_languages(preferred_languages)
    return select_preferred_channels(channels, parsed, normalize_language_fallback(language_fallback))
