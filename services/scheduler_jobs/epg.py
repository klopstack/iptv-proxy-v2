"""EPG source sync delegation (global metadata updated by orchestrator)."""

import logging
from typing import Callable

from flask import Flask

from services.epg_sync_orchestrator import SYNC_KEY_LAST_EPG_SYNC, EpgSyncOrchestrator

logger = logging.getLogger(__name__)


def run_epg_source_sync(
    app: Flask,
    interval_hours: int,
    *,
    touch_heartbeat: Callable[[], None],
    record_success: Callable[[str], None],
    record_failure: Callable[[str, str], None],
) -> None:
    try:
        touch_heartbeat()
        result = EpgSyncOrchestrator(app).sync_due_sources(interval_hours, parallel=True)
        touch_heartbeat()
        total_sources = result.get("total_sources", 0)
        if total_sources == 0:
            return
        logger.info(
            "EPG sync pass complete: %s/%s succeeded (%s skipped)",
            result.get("sources_synced", 0),
            total_sources,
            result.get("sources_skipped", 0),
        )
        if result.get("success"):
            record_success(SYNC_KEY_LAST_EPG_SYNC)
        else:
            error_message = f"EPG sync: {result.get('sources_synced', 0)}/{total_sources} sources succeeded"
            for entry in result.get("results") or []:
                if not entry.get("success") and entry.get("message"):
                    error_message = str(entry["message"])
                    break
            record_failure(SYNC_KEY_LAST_EPG_SYNC, error_message)
    except Exception as e:
        logger.error("Error in EPG source sync: %s", e)
        record_failure(SYNC_KEY_LAST_EPG_SYNC, str(e))
