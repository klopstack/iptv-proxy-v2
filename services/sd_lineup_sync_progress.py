"""Per-lineup Schedules Direct sync progress tracking."""

import json
from datetime import datetime, timezone
from typing import Any, Dict

from models import SdLineup, SdLineupSyncStatus, db

PHASE_IDLE = "idle"
PHASE_QUEUED = "queued"
PHASE_FETCHING = "fetching"
PHASE_CHANNELS = "channels"
PHASE_COMPLETE = "complete"
PHASE_ERROR = "error"

TERMINAL_PHASES = {PHASE_IDLE, PHASE_COMPLETE, PHASE_ERROR}


class SdLineupSyncProgress:
    @staticmethod
    def _get_or_create(lineup_id: int) -> SdLineupSyncStatus | None:
        lineup = db.session.get(SdLineup, lineup_id)
        if not lineup:
            return None
        status = db.session.get(SdLineupSyncStatus, lineup_id)
        if not status:
            status = SdLineupSyncStatus(lineup_id=lineup_id)
            db.session.add(status)
        return status

    @staticmethod
    def set_phase(lineup_id: int, phase: str, message: str = "", **counts: Any) -> None:
        status = SdLineupSyncProgress._get_or_create(lineup_id)
        if not status:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        status.sync_phase = phase
        status.sync_in_progress = phase not in TERMINAL_PHASES
        if phase == PHASE_QUEUED:
            status.sync_started_at = now
        if phase in (PHASE_COMPLETE, PHASE_ERROR):
            status.sync_in_progress = False

        progress = SdLineupSyncProgress._load_progress(status)
        if message:
            progress["message"] = message
        for key, value in counts.items():
            if value is not None:
                progress[key] = value
        progress["updated_at"] = now.isoformat()
        status.sync_progress = json.dumps(progress)

        if phase == PHASE_COMPLETE:
            status.last_sync = now
            status.last_sync_status = "success"
            status.last_sync_message = message or status.last_sync_message
        elif phase == PHASE_ERROR:
            status.last_sync_status = "error"
            status.last_sync_message = message or status.last_sync_message

        db.session.commit()

    @staticmethod
    def merge(lineup_id: int, **counts: Any) -> None:
        status = SdLineupSyncProgress._get_or_create(lineup_id)
        if not status:
            return
        progress = SdLineupSyncProgress._load_progress(status)
        for key, value in counts.items():
            if value is not None:
                progress[key] = value
        progress["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        status.sync_progress = json.dumps(progress)
        db.session.commit()

    @staticmethod
    def reset_idle(lineup_id: int) -> None:
        SdLineupSyncProgress.set_phase(lineup_id, PHASE_IDLE, message="")

    @staticmethod
    def snapshot(lineup: SdLineup) -> Dict[str, Any]:
        status = db.session.get(SdLineupSyncStatus, lineup.id)
        prog = SdLineupSyncProgress._load_progress(status) if status else {}
        return {
            "lineup_id": lineup.id,
            "sd_lineup_id": lineup.lineup_id,
            "name": lineup.name,
            "location": lineup.location,
            "channel_count": lineup.channel_count,
            "sync_in_progress": bool(status.sync_in_progress) if status else False,
            "sync_phase": status.sync_phase if status and status.sync_phase else PHASE_IDLE,
            "sync_started_at": status.sync_started_at.isoformat() if status and status.sync_started_at else None,
            "last_sync": status.last_sync.isoformat() if status and status.last_sync else None,
            "last_sync_status": status.last_sync_status if status else None,
            "last_sync_message": status.last_sync_message if status else None,
            "progress": prog,
        }

    @staticmethod
    def _load_progress(status: SdLineupSyncStatus | None) -> Dict[str, Any]:
        if not status or not status.sync_progress:
            return {}
        try:
            data = json.loads(status.sync_progress)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
