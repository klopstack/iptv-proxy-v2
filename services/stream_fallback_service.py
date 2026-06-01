"""
Stream fallback resolution — primary/backup upstream chains for proxy failover.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, List, Literal, Optional, Set, Tuple

from models import Account, Channel, ChannelLink, Settings, db

logger = logging.getLogger(__name__)

LINK_TYPE_BACKUP = "backup"
CACHE_TTL_SECONDS = 60

_source_cache: dict[tuple[int, str], tuple[float, list["StreamSource"]]] = {}


@dataclass(frozen=True)
class StreamSource:
    """One upstream in an ordered failover chain."""

    channel_id: int
    stream_id: str
    role: Literal["primary", "backup"]


def is_fallback_enabled() -> bool:
    return Settings.get("stream_fallback_enabled", "true") != "false"


def invalidate_cache() -> None:
    """Clear in-memory fallback caches (call after link CRUD)."""
    _source_cache.clear()


def build_upstream_url(account: Account, credential: Any, stream_id: str, fmt: str) -> str:
    """Build provider live URL for a stream."""
    return f"https://{account.server}/live/{credential.username}/{credential.password}/{stream_id}.{fmt}"


def _load_backup_link(primary_channel_id: int) -> Optional[ChannelLink]:
    return ChannelLink.query.filter_by(
        channel_id=primary_channel_id,
        link_type=LINK_TYPE_BACKUP,
    ).first()


def resolve_sources(account_id: int, stream_id: str) -> List[StreamSource]:
    """
    Return ordered stream sources for proxy failover.

    Always includes the requested stream as primary; appends backup when linked.
    """
    if not is_fallback_enabled():
        channel = Channel.query.filter_by(account_id=account_id, stream_id=str(stream_id)).first()
        cid = channel.id if channel else 0
        return [StreamSource(channel_id=cid, stream_id=str(stream_id), role="primary")]

    cache_key = (account_id, str(stream_id))
    now = time.time()
    cached = _source_cache.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    channel = Channel.query.filter_by(account_id=account_id, stream_id=str(stream_id)).first()
    if not channel:
        sources = [StreamSource(channel_id=0, stream_id=str(stream_id), role="primary")]
        _source_cache[cache_key] = (now, sources)
        return sources

    sources = [StreamSource(channel_id=channel.id, stream_id=str(channel.stream_id), role="primary")]

    link = _load_backup_link(channel.id)
    if link and link.source_channel:
        backup = link.source_channel
        if backup.is_active and backup.stream_id != channel.stream_id:
            sources.append(
                StreamSource(
                    channel_id=backup.id,
                    stream_id=str(backup.stream_id),
                    role="backup",
                )
            )

    _source_cache[cache_key] = (now, sources)
    return sources


def get_backup_channel_ids() -> Set[int]:
    """Channel IDs used only as backup targets (hidden from client playlists)."""
    if not is_fallback_enabled():
        return set()

    rows = db.session.query(ChannelLink.source_channel_id).filter(ChannelLink.link_type == LINK_TYPE_BACKUP).all()
    return {row[0] for row in rows}


def probe_and_select_upstream(
    account: Account,
    credential: Any,
    sources: List[StreamSource],
    fmt: str,
    user_agent: str,
    tester: Any,
) -> Tuple[List[Tuple[str, str]], int, Optional[str]]:
    """
    Probe sources in order; return (fallback_chain, start_index, error).

    Each chain entry is (stream_id, upstream_url). start_index is the first
    source that passed connectivity probe (or 0 if probing skipped/disabled).
    """
    from services.stream_proxy_service import StreamConnectivityTester

    if tester is None:
        tester = StreamConnectivityTester

    chain: List[Tuple[str, str]] = []
    for source in sources:
        url = build_upstream_url(account, credential, source.stream_id, fmt)
        chain.append((source.stream_id, url))

    if len(chain) <= 1:
        return chain, 0, None

    for idx, (sid, url) in enumerate(chain):
        head_status, _, head_error = tester.test_upstream_head(url, user_agent)
        get_status = None
        get_error = None
        if head_status == 405:
            get_status, _, _, get_error = tester.test_upstream_get(url, user_agent)
        success, error = tester.determine_test_success_and_error(head_status, head_error, get_status, get_error)
        if success:
            if idx > 0:
                logger.info(
                    "Stream fallback: using backup source %s (index %s) for account %s primary %s",
                    sid,
                    idx,
                    account.id,
                    chain[0][0],
                )
            return chain, idx, None
        logger.debug(
            "Stream source probe failed for %s (index %s): %s",
            sid,
            idx,
            error,
        )

    return chain, 0, "All stream sources unavailable"


def source_role_label(index: int) -> str:
    return "primary" if index == 0 else "backup"
