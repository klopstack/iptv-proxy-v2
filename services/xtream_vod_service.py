"""
Upstream VOD catalog passthrough for Xtream Codes output.

When enabled on an account-linked credential, movie categories and titles are
fetched from the provider and returned unchanged (no tag cleaning or filters).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models import Account
from services.image_cache_service import ImageCacheService
from services.iptv_service import get_iptv_service_for_account

logger = logging.getLogger(__name__)


def vod_passthrough_available(*, vod_passthrough: bool, account: Optional[Account], account_id: Optional[int]) -> bool:
    """Return True when upstream VOD passthrough should be used."""
    return bool(vod_passthrough and account is not None and account_id is not None and account.enabled)


def build_vod_upstream_url(account: Account, credential: Any, stream_id: str, ext: str) -> str:
    """Build provider movie URL for a VOD stream."""
    return f"https://{account.server}/movie/{credential.username}/{credential.password}/{stream_id}.{ext}"


def fetch_vod_categories(account: Account) -> List[Dict[str, Any]]:
    """Fetch VOD categories from upstream provider."""
    service = get_iptv_service_for_account(account)
    categories = service.get_vod_categories()
    if not isinstance(categories, list):
        logger.warning("Unexpected VOD categories response type for account %s: %r", account.id, type(categories))
        return []
    return categories


def fetch_vod_streams(account: Account, *, category_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch VOD streams from upstream provider."""
    service = get_iptv_service_for_account(account)
    streams = service.get_vod_streams(category_id=category_id)
    if not isinstance(streams, list):
        logger.warning("Unexpected VOD streams response type for account %s: %r", account.id, type(streams))
        return []
    return streams


def rewrite_vod_stream_icons(streams: List[Dict[str, Any]], *, proxy_base: str) -> List[Dict[str, Any]]:
    """Return a shallow copy of streams with stream_icon proxied when possible."""
    image_cache = ImageCacheService.get_instance()
    rewritten: List[Dict[str, Any]] = []
    for item in streams:
        stream = dict(item)
        icon = stream.get("stream_icon") or stream.get("cover") or ""
        if icon:
            stream["stream_icon"] = image_cache.get_proxy_url(icon, proxy_base)
            if "cover" in stream:
                stream["cover"] = stream["stream_icon"]
        rewritten.append(stream)
    return rewritten
