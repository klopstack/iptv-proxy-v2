"""Prefetch channel icons from known sync sources (provider + EPG).

Icons are only fetched here — never from HTTP client requests — so the
/icon/<hash> route can serve a closed set of registered URLs.
"""

from __future__ import annotations

import logging
from typing import Iterable

from services.image_cache_service import ImageCacheService

logger = logging.getLogger(__name__)


def prefetch_icon_urls(urls: Iterable[str | None]) -> dict[str, int]:
    """Fetch and cache a batch of icon URLs discovered during sync.

    Returns:
        Stats dict with keys: attempted, cached, skipped, failed
    """
    cache = ImageCacheService.get_instance()
    stats = {"attempted": 0, "cached": 0, "skipped": 0, "failed": 0}

    seen: set[str] = set()
    for url in urls:
        if not url or not isinstance(url, str):
            continue
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        stats["attempted"] += 1
        result = cache.prefetch_icon(normalized)
        if result == "cached":
            stats["cached"] += 1
        elif result == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    if stats["attempted"]:
        logger.info(
            "Icon prefetch: attempted=%s cached=%s skipped=%s failed=%s",
            stats["attempted"],
            stats["cached"],
            stats["skipped"],
            stats["failed"],
        )

    return stats


def prefetch_account_channel_icons(account_id: int) -> dict[str, int]:
    """Prefetch stream_icon URLs for active channels on an account."""
    from models import Channel

    urls = [
        row[0]
        for row in Channel.query.with_entities(Channel.stream_icon)
        .filter_by(account_id=account_id, is_active=True)
        .filter(Channel.stream_icon.isnot(None), Channel.stream_icon != "")
        .distinct()
        .all()
    ]
    return prefetch_icon_urls(urls)


def prefetch_epg_source_icons(source_id: int) -> dict[str, int]:
    """Prefetch icon_url values for channels on an EPG source."""
    from models import EpgChannel

    urls = [
        row[0]
        for row in EpgChannel.query.with_entities(EpgChannel.icon_url)
        .filter_by(source_id=source_id)
        .filter(EpgChannel.icon_url.isnot(None), EpgChannel.icon_url != "")
        .distinct()
        .all()
    ]
    return prefetch_icon_urls(urls)
