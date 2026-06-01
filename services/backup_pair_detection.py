"""
Auto-detect primary/backup channel pairs for stream proxy failover.
"""

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from models import Category, Channel, ChannelLink, ChannelTag, EventChannelLink, Tag, db
from services.ppv.detection import is_generic_channel_name
from services.ppv.slot_extraction import extract_ppv_slot_number
from services.quality_service import QualityService
from services.stream_fallback_service import LINK_TYPE_BACKUP, invalidate_cache

logger = logging.getLogger(__name__)

# Category suffix markers for backup feeds: ⁽ᴮᴷ⁾, (BK), etc.
BACKUP_CATEGORY_SUFFIX = re.compile(r"\s*[⁽(]?[ᴮB][ᴷK][⁾)]?\s*$", re.IGNORECASE)


def normalize_category_base(category_name: str) -> Tuple[str, bool]:
    """Return (base_name, is_backup_category)."""
    if not category_name:
        return "", False
    stripped = category_name.strip()
    if BACKUP_CATEGORY_SUFFIX.search(stripped):
        base = BACKUP_CATEGORY_SUFFIX.sub("", stripped).strip()
        return base, True
    return stripped, False


def _load_channel_tags(channels: List[Channel]) -> Dict[int, List[str]]:
    """Map channel.id -> tag name list."""
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
    stream_to_id = {(ch.account_id, ch.stream_id): ch.id for ch in channels}
    for acc_id, stream_id, tag_name in rows:
        ch_id = stream_to_id.get((acc_id, stream_id))
        if ch_id is not None:
            result[ch_id].append(tag_name)
    return result


def _channel_quality_score(channel: Channel, tags: List[str]) -> int:
    health = None
    if channel.health_status:
        health = {
            "status": channel.health_status.status,
            "successful_checks": channel.health_status.successful_checks or 0,
            "total_checks": channel.health_status.total_checks or 0,
        }
    return QualityService.get_quality_score_with_health(tags, health)


def _create_backup_link(
    primary: Channel,
    backup: Channel,
    stats: Dict[str, Any],
    *,
    auto_detected: bool = True,
) -> None:
    existing = ChannelLink.query.filter_by(
        channel_id=primary.id,
        link_type=LINK_TYPE_BACKUP,
    ).first()
    if existing:
        stats["links_skipped"] += 1
        return

    dup = ChannelLink.query.filter_by(
        channel_id=primary.id,
        source_channel_id=backup.id,
    ).first()
    if dup:
        if dup.link_type != LINK_TYPE_BACKUP:
            dup.link_type = LINK_TYPE_BACKUP
            dup.time_offset_hours = 0
            dup.auto_detected = auto_detected
            stats["links_updated"] = stats.get("links_updated", 0) + 1
        else:
            stats["links_skipped"] += 1
        return

    link = ChannelLink(
        channel_id=primary.id,
        source_channel_id=backup.id,
        time_offset_hours=0,
        link_type=LINK_TYPE_BACKUP,
        auto_detected=auto_detected,
    )
    db.session.add(link)
    stats["links_created"] += 1
    logger.info(
        "Backup link: primary %s (%s) -> backup %s (%s)",
        primary.name,
        primary.stream_id,
        backup.name,
        backup.stream_id,
    )


def detect_category_mirror_pairs(channels: List[Channel], stats: Dict[str, Any]) -> None:
    """Pair channels in mirrored categories (plain vs BK suffix) by PPV slot."""
    # (account_id, category_base, slot) -> {"primary": ch, "backup": ch}
    groups: Dict[Tuple[int, str, int], Dict[str, Channel]] = defaultdict(dict)

    for ch in channels:
        if not ch.category:
            continue
        cat_name = ch.category.category_name or ch.category.cleaned_name or ""
        base, is_backup_cat = normalize_category_base(cat_name)
        if not base:
            continue
        slot = extract_ppv_slot_number(ch.name or "")
        if slot is None:
            continue

        key = (ch.account_id, base.lower(), slot)
        role = "backup" if is_backup_cat else "primary"
        existing = groups[key].get(role)
        if existing is None:
            groups[key][role] = ch

    for (_acc_id, _base, _slot), pair in groups.items():
        primary = pair.get("primary")
        backup = pair.get("backup")
        if not primary or not backup:
            continue
        if primary.id == backup.id:
            continue
        backup_is_placeholder = is_generic_channel_name(backup.name or "")
        primary_is_placeholder = is_generic_channel_name(primary.name or "")
        if backup_is_placeholder and not primary_is_placeholder:
            continue
        _create_backup_link(primary, backup, stats)


def detect_name_duplicate_pairs(channels: List[Channel], stats: Dict[str, Any]) -> None:
    """Link cleaned-name duplicates where quality/health differs."""
    tags_map = _load_channel_tags(channels)
    grouped: Dict[Tuple[int, str], List[Channel]] = defaultdict(list)

    for ch in channels:
        base = (ch.cleaned_name or ch.name or "").lower().strip()
        if not base:
            continue
        grouped[(ch.account_id, base)].append(ch)

    for (_acc_id, _name), group in grouped.items():
        if len(group) < 2:
            continue
        if any(ChannelLink.query.filter_by(channel_id=ch.id, link_type=LINK_TYPE_BACKUP).first() for ch in group):
            continue

        scored = sorted(
            group,
            key=lambda ch: _channel_quality_score(ch, tags_map.get(ch.id, [])),
            reverse=True,
        )
        primary = scored[0]
        backup = scored[-1]
        if primary.id == backup.id:
            continue
        if primary.stream_id == backup.stream_id:
            continue

        primary_score = _channel_quality_score(primary, tags_map.get(primary.id, []))
        backup_score = _channel_quality_score(backup, tags_map.get(backup.id, []))
        cat_primary = (primary.category.category_name if primary.category else "") or ""
        cat_backup = (backup.category.category_name if backup.category else "") or ""
        if primary_score == backup_score and cat_primary == cat_backup:
            continue

        _create_backup_link(primary, backup, stats)


def detect_event_multi_feed_pairs(channels: List[Channel], stats: Dict[str, Any]) -> None:
    """Link channels sharing the same PPV event (lower priority than category detection)."""
    ch_by_id = {ch.id: ch for ch in channels}
    event_groups: Dict[int, List[Tuple[Channel, EventChannelLink]]] = defaultdict(list)

    links = (
        EventChannelLink.query.join(Channel, EventChannelLink.channel_id == Channel.id)
        .filter(Channel.id.in_(list(ch_by_id.keys())))
        .all()
    )
    for link in links:
        ch = ch_by_id.get(link.channel_id)
        if ch and ch.is_active:
            event_groups[link.event_id].append((ch, link))

    tags_map = _load_channel_tags(channels)

    for _event_id, entries in event_groups.items():
        if len(entries) < 2:
            continue
        active = [(ch, lnk) for ch, lnk in entries if ch.is_active]
        if len(active) < 2:
            continue
        if any(ChannelLink.query.filter_by(channel_id=ch.id, link_type=LINK_TYPE_BACKUP).first() for ch, _ in active):
            continue

        scored = sorted(
            active,
            key=lambda item: _channel_quality_score(item[0], tags_map.get(item[0].id, [])),
            reverse=True,
        )
        primary_ch, _ = scored[0]
        backup_ch, backup_link = scored[-1]
        if primary_ch.id == backup_ch.id:
            continue
        backup_link.feed_type = "alternate"
        _create_backup_link(primary_ch, backup_ch, stats)


def detect_backup_pairs(account_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Auto-detect primary/backup channel links.

    Returns statistics dict compatible with channel link detect API.
    """
    stats: Dict[str, Any] = {
        "links_created": 0,
        "links_skipped": 0,
        "links_updated": 0,
        "channels_processed": 0,
        "errors": [],
    }

    query = (
        db.session.query(Channel)
        .filter(Channel.is_active.is_(True))
        .join(Category, Channel.category_id == Category.id, isouter=True)
    )
    if account_id:
        query = query.filter(Channel.account_id == account_id)
    channels = query.all()
    stats["channels_processed"] = len(channels)

    if not channels:
        return stats

    try:
        detect_category_mirror_pairs(channels, stats)
        detect_name_duplicate_pairs(channels, stats)
        detect_event_multi_feed_pairs(channels, stats)
        db.session.commit()
        invalidate_cache()
    except Exception as e:
        db.session.rollback()
        stats["errors"].append(str(e))
        logger.error("Backup pair detection failed: %s", e)

    logger.info(
        "Backup pair detection: %s created, %s updated, %s skipped",
        stats["links_created"],
        stats.get("links_updated", 0),
        stats["links_skipped"],
    )
    return stats
