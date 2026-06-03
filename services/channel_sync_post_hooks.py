"""Post-sync side effects decoupled from ChannelSyncService."""

import logging
from typing import Any, Callable, Dict, List, Optional

from models import Channel, Settings

logger = logging.getLogger(__name__)

PostSyncListener = Callable[[int, Dict[str, Any]], None]


class ChannelSyncPostHooks:
    def __init__(self, listeners: Optional[List[PostSyncListener]] = None):
        self._listeners: List[PostSyncListener] = list(listeners or [])

    def register(self, listener: PostSyncListener) -> None:
        self._listeners.append(listener)

    def run(self, account_id: int, stats: Dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(account_id, stats)
            except Exception as e:
                logger.error("Post-sync hook failed: %s", e)
                stats.setdefault("errors", []).append(f"Post-sync hook error: {str(e)}")

    @classmethod
    def noop(cls) -> "ChannelSyncPostHooks":
        return cls(listeners=[])


def _compute_filter_visibility(account_id: int, stats: Dict[str, Any]) -> None:
    from services.filter_service import FilterService

    filter_stats = FilterService.compute_visibility_for_account(account_id)
    stats["channels_visible"] = filter_stats.get("channels_visible", 0)
    stats["channels_hidden"] = filter_stats.get("channels_hidden", 0)
    logger.info(
        "Filter visibility computed: %s visible, %s hidden",
        stats["channels_visible"],
        stats["channels_hidden"],
    )


def _ppv_reenrichment(account_id: int, stats: Dict[str, Any]) -> None:
    requeue_ids = stats.get("ppv_requeue_ids") or []
    if not requeue_ids:
        return
    from flask import current_app, has_app_context

    from services.ppv.enrichment import get_calendar_enrichment_service

    if not has_app_context():
        return
    channels = Channel.query.filter(Channel.id.in_(requeue_ids)).all()
    if not channels:
        return
    logger.info("Re-enriching %s PPV channel(s) after name/event change", len(channels))
    stats["ppv_enrichment"] = get_calendar_enrichment_service(
        current_app._get_current_object()  # type: ignore[attr-defined]
    ).enrich_channels(channels)


def _detect_backup_pairs(account_id: int, stats: Dict[str, Any]) -> None:
    if Settings.get("stream_fallback_auto_detect", "true") == "false":
        return
    from services.backup_pair_detection import detect_backup_pairs

    stats["backup_pair_detection"] = detect_backup_pairs(account_id)


def _detect_channel_languages(account_id: int, stats: Dict[str, Any]) -> None:
    from services.language_detection_service import detect_languages_for_account

    stats["language_detection"] = detect_languages_for_account(account_id)


def _prefetch_icons(account_id: int, stats: Dict[str, Any]) -> None:
    from services.icon_prefetch import prefetch_account_channel_icons

    stats["icon_prefetch"] = prefetch_account_channel_icons(account_id)


def default_post_sync_hooks() -> ChannelSyncPostHooks:
    hooks = ChannelSyncPostHooks()
    hooks.register(_compute_filter_visibility)
    hooks.register(_ppv_reenrichment)
    hooks.register(_detect_channel_languages)
    hooks.register(_detect_backup_pairs)
    hooks.register(_prefetch_icons)
    return hooks


_post_hooks: ChannelSyncPostHooks = default_post_sync_hooks()


def get_channel_sync_post_hooks() -> ChannelSyncPostHooks:
    return _post_hooks


def set_channel_sync_post_hooks(hooks: ChannelSyncPostHooks) -> None:
    global _post_hooks
    _post_hooks = hooks
