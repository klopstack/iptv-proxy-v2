"""
Batch loading of channel tag names keyed by account/stream or channel id.

Used by filter visibility, channel query, and sync link detection to avoid
per-channel N+1 queries.
"""

from typing import Dict, List, Set, Tuple

from models import Channel, ChannelTag, Tag, db

DEFAULT_BATCH_SIZE = 500


def load_tag_names_by_stream_keys(
    channels: List[Channel],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[Tuple[int, str], Set[str]]:
    """Map (account_id, stream_id) -> set of tag names."""
    if not channels:
        return {}

    stream_ids = [ch.stream_id for ch in channels]
    account_ids = list({ch.account_id for ch in channels})
    tags_map: Dict[Tuple[int, str], Set[str]] = {}

    for i in range(0, len(stream_ids), batch_size):
        batch = stream_ids[i : i + batch_size]
        rows = (
            db.session.query(ChannelTag.stream_id, ChannelTag.account_id, Tag.name)
            .join(Tag)
            .filter(
                ChannelTag.account_id.in_(account_ids),
                ChannelTag.stream_id.in_(batch),
            )
            .all()
        )
        for stream_id, acc_id, tag_name in rows:
            key = (acc_id, stream_id)
            tags_map.setdefault(key, set()).add(tag_name)

    return tags_map


def load_tag_names_for_account(
    account_id: int,
    channels: List[Channel],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, List[str]]:
    """Map stream_id -> tag names for channels on one account."""
    raw = load_tag_names_by_stream_keys(channels, batch_size=batch_size)
    return {stream_id: list(tags) for (acc_id, stream_id), tags in raw.items() if acc_id == account_id}


def load_tag_names_by_channel_id(
    channels: List[Channel],
    *,
    uppercase: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[int, Set[str]]:
    """Map channel.id -> tag names (optionally uppercased)."""
    if not channels:
        return {}

    stream_keys = load_tag_names_by_stream_keys(channels, batch_size=batch_size)
    id_by_stream = {(ch.account_id, ch.stream_id): ch.id for ch in channels}
    result: Dict[int, Set[str]] = {ch.id: set() for ch in channels}

    for key, tags in stream_keys.items():
        ch_id = id_by_stream.get(key)
        if ch_id is None:
            continue
        if uppercase:
            result[ch_id] = {t.upper() for t in tags}
        else:
            result[ch_id] = set(tags)

    return result
