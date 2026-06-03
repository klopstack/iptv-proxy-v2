"""Post-enrichment side effects decoupled from calendar matching."""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

PostEnrichmentListener = Callable[[Dict[str, Any]], None]


class EnrichmentPostHooks:
    def __init__(self, listeners: Optional[List[PostEnrichmentListener]] = None):
        self._listeners: List[PostEnrichmentListener] = list(listeners or [])

    def register(self, listener: PostEnrichmentListener) -> None:
        self._listeners.append(listener)

    def run(self, results: Dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                listener(results)
            except Exception as e:
                logger.error("Post-enrichment hook failed: %s", e)
                results.setdefault("errors", 0)
                if isinstance(results.get("errors"), int):
                    results["errors"] = results["errors"] + 1

    @classmethod
    def noop(cls) -> "EnrichmentPostHooks":
        return cls(listeners=[])


def _sync_ppv_epg_after_batch(results: Dict[str, Any]) -> None:
    from services.ppv.cleanup import prune_orphan_ppv_events, sync_ppv_epg_after_enrichment

    matched = results.get("matched", 0)
    if matched > 0:
        try:
            epg_stats = sync_ppv_epg_after_enrichment(matched)
            results.update(epg_stats)
            results["ppv_epg_matched"] = epg_stats.get("epg_mappings", 0)
        except Exception as e:
            logger.error("Failed to auto-create/match PPV EPG source: %s", e)
    else:
        prune_orphan_ppv_events()


def _detect_languages_after_enrichment(results: Dict[str, Any]) -> None:
    matched_channel_ids = results.get("matched_channel_ids") or []
    if not matched_channel_ids:
        return
    from services.language_detection_service import detect_languages_for_channel_ids

    results["language_detection"] = detect_languages_for_channel_ids(matched_channel_ids)


def default_enrichment_post_hooks() -> EnrichmentPostHooks:
    hooks = EnrichmentPostHooks()
    hooks.register(_sync_ppv_epg_after_batch)
    hooks.register(_detect_languages_after_enrichment)
    return hooks


_post_hooks: EnrichmentPostHooks = default_enrichment_post_hooks()


def get_enrichment_post_hooks() -> EnrichmentPostHooks:
    return _post_hooks


def set_enrichment_post_hooks(hooks: EnrichmentPostHooks) -> None:
    global _post_hooks
    _post_hooks = hooks
