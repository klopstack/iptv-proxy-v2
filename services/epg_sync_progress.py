"""Per-source EPG sync progress tracking."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from models import EpgSource, db
from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

PHASE_IDLE = "idle"
PHASE_QUEUED = "queued"
PHASE_FETCHING = "fetching"
PHASE_CHANNELS = "channels"
PHASE_PROGRAMS = "programs"
PHASE_COMPLETE = "complete"
PHASE_ERROR = "error"
PHASE_SKIPPED = "skipped"

TERMINAL_PHASES = {PHASE_IDLE, PHASE_COMPLETE, PHASE_ERROR, PHASE_SKIPPED}


class EpgSyncProgress:
    """Update EpgSource sync progress fields (per source)."""

    @staticmethod
    def set_phase(source_id: int, phase: str, message: str = "", **counts: Any) -> None:
        source = db.session.get(EpgSource, source_id)
        if not source:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source.sync_phase = phase
        source.sync_in_progress = phase not in TERMINAL_PHASES

        if phase == PHASE_QUEUED:
            source.sync_started_at = now
        elif phase in (PHASE_COMPLETE, PHASE_ERROR, PHASE_SKIPPED):
            source.sync_in_progress = False

        progress = dict(EpgSyncProgress._load_progress(source))
        if message:
            progress["message"] = message
        for key, value in counts.items():
            if value is not None:
                progress[key] = value
        progress["updated_at"] = serialize_utc_iso(now)
        source.sync_progress = progress
        db.session.commit()

    @staticmethod
    def merge(source_id: int, **counts: Any) -> None:
        source = db.session.get(EpgSource, source_id)
        if not source:
            return
        progress = dict(EpgSyncProgress._load_progress(source))
        for key, value in counts.items():
            if value is not None:
                progress[key] = value
        progress["updated_at"] = serialize_utc_iso(datetime.now(timezone.utc).replace(tzinfo=None))
        source.sync_progress = progress
        db.session.commit()

    @staticmethod
    def reset_idle(source_id: int) -> None:
        EpgSyncProgress.set_phase(source_id, PHASE_IDLE, message="")

    @staticmethod
    def snapshot(source: EpgSource) -> Dict[str, Any]:
        progress = EpgSyncProgress._load_progress(source)
        return {
            "source_id": source.id,
            "source_name": source.name,
            "source_type": source.source_type,
            "enabled": source.enabled,
            "sync_in_progress": bool(source.sync_in_progress),
            "sync_phase": source.sync_phase or PHASE_IDLE,
            "sync_started_at": serialize_utc_iso(source.sync_started_at),
            "last_sync": serialize_utc_iso(source.last_sync),
            "last_sync_status": source.last_sync_status,
            "last_sync_message": source.last_sync_message,
            "progress": progress,
        }

    @staticmethod
    def _load_progress(source: EpgSource) -> Dict[str, Any]:
        if not source.sync_progress:
            return {}
        data = source.sync_progress
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
