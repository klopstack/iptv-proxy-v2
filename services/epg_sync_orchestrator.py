"""
Parallel EPG source synchronization with per-source progress reporting.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask
from sqlalchemy import update

from models import EpgSource, SyncMetadata, db
from services.epg_sync_progress import PHASE_COMPLETE, PHASE_ERROR, PHASE_QUEUED, EpgSyncProgress
from services.epg_sync_service import EpgSyncService

logger = logging.getLogger(__name__)

SYNC_KEY_LAST_EPG_SYNC = "last_epg_sync"
DEFAULT_PARALLEL_WORKERS = int(os.getenv("EPG_SYNC_PARALLEL_WORKERS", "3"))
STALE_EPG_SYNC_LOCK_HOURS = int(os.getenv("EPG_SYNC_STALE_LOCK_HOURS", "12"))


def try_acquire_epg_sync_lock(source_id: int, *, force: bool = False) -> bool:
    """
    Atomically claim an EPG source sync lock (safe across workers/threads).

    Returns True if this caller holds the lock.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if force:
        locked = (
            db.session.execute(
                update(EpgSource).where(EpgSource.id == source_id, EpgSource.sync_in_progress.is_(True))
            ).rowcount
            or 0
        ) > 0
        if locked:
            source = db.session.get(EpgSource, source_id)
            logger.warning(
                "EPG sync force=True overriding in-progress lock for source %s (id=%s)",
                source.name if source else "?",
                source_id,
            )
        result = db.session.execute(
            update(EpgSource).where(EpgSource.id == source_id).values(sync_in_progress=True, sync_started_at=now)
        )
    else:
        result = db.session.execute(
            update(EpgSource)
            .where(EpgSource.id == source_id, EpgSource.sync_in_progress.is_(False))
            .values(sync_in_progress=True, sync_started_at=now)
        )
    db.session.commit()
    return (getattr(result, "rowcount", 0) or 0) > 0


def recover_stale_epg_sync_locks(max_age_hours: int = STALE_EPG_SYNC_LOCK_HOURS) -> int:
    """
    Clear sync locks held longer than max_age_hours (e.g. after worker crash).

    Returns:
        Number of sources recovered.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=max_age_hours)
    stale = EpgSource.query.filter(
        EpgSource.sync_in_progress.is_(True),
        db.or_(
            db.and_(EpgSource.sync_started_at.isnot(None), EpgSource.sync_started_at < cutoff),
            db.and_(EpgSource.sync_started_at.is_(None), EpgSource.updated_at < cutoff),
        ),
    ).all()

    for source in stale:
        logger.warning(
            "Recovering stale EPG sync lock for source %s (id=%s, started=%s)",
            source.name,
            source.id,
            source.sync_started_at,
        )
        source.sync_in_progress = False
        source.sync_started_at = None
        source.sync_phase = None
        source.sync_progress = None

    if stale:
        db.session.commit()

    return len(stale)


def source_needs_sync(source: EpgSource, interval_hours: int) -> bool:
    """True if this source has never synced or is past its interval."""
    if source.sync_in_progress:
        return False
    if not source.last_sync:
        return True
    last = source.last_sync
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= last + timedelta(hours=interval_hours)


class EpgSyncOrchestrator:
    """Run EPG syncs across sources in parallel with granular progress."""

    def __init__(self, app: Flask):
        self.app = app

    def list_status(self) -> List[Dict[str, Any]]:
        with self.app.app_context():
            sources = EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all()
            return [EpgSyncProgress.snapshot(s) for s in sources]

    def sync_due_sources(
        self,
        interval_hours: int,
        *,
        parallel: bool = True,
        max_workers: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self.app.app_context():
            sources = [
                s
                for s in EpgSource.query.filter_by(enabled=True).order_by(EpgSource.priority, EpgSource.id).all()
                if source_needs_sync(s, interval_hours)
            ]
        if not sources:
            return {
                "success": True,
                "message": "No EPG sources due for sync",
                "sources_synced": 0,
                "sources_skipped": 0,
                "total_sources": 0,
                "results": [],
            }
        return self.sync_sources(sources, parallel=parallel, max_workers=max_workers)

    def sync_source_by_id(self, source_id: int, *, force: bool = False) -> Dict[str, Any]:
        """Sync one EPG source with progress tracking and lock acquire (TODO 42/43)."""
        with self.app.app_context():
            source = db.session.get(EpgSource, source_id)
            if not source:
                return {
                    "source_id": source_id,
                    "success": False,
                    "not_found": True,
                    "message": "Source not found",
                    "stats": {},
                }

            batch = self.sync_sources([source], parallel=False, force=force)
            results = batch.get("results") or []
            if results:
                return results[0]

            return {
                "source_id": source_id,
                "success": False,
                "message": "No sync result",
                "stats": {},
            }

    def sync_sources(
        self,
        sources: List[EpgSource],
        *,
        parallel: bool = True,
        max_workers: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not sources:
            return {
                "success": True,
                "message": "No sources to sync",
                "sources_synced": 0,
                "sources_skipped": 0,
                "total_sources": 0,
                "results": [],
            }

        with self.app.app_context():
            source_ids, skipped_results = self._acquire_sources_for_sync(sources, force=force)

        if not source_ids:
            return {
                "success": True,
                "message": "All sources skipped (sync in progress)",
                "sources_synced": 0,
                "sources_skipped": len(skipped_results),
                "total_sources": len(skipped_results),
                "results": skipped_results,
            }

        workers = max_workers if max_workers is not None else DEFAULT_PARALLEL_WORKERS
        workers = max(1, min(workers, len(source_ids)))

        logger.info(
            "EPG orchestrator: syncing %s source(s) (%s, workers=%s)",
            len(source_ids),
            "parallel" if parallel and workers > 1 else "sequential",
            workers,
        )

        results: List[Dict[str, Any]] = []

        if parallel and workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._sync_source_in_thread, sid): sid for sid in source_ids}
                for future in as_completed(futures):
                    sid = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("EPG sync failed for source %s: %s", sid, exc)
                        results.append(
                            {
                                "source_id": sid,
                                "success": False,
                                "message": str(exc),
                                "stats": {},
                            }
                        )
        else:
            for sid in source_ids:
                results.append(self._sync_source_in_thread(sid))

        success_count = sum(1 for r in results if r.get("success"))

        with self.app.app_context():
            if success_count > 0:
                SyncMetadata.set(SYNC_KEY_LAST_EPG_SYNC, datetime.now(timezone.utc).isoformat())
            else:
                logger.warning(
                    "EPG sync pass: 0/%s sources succeeded; global last_epg_sync not updated",
                    len(results),
                )

        all_results = skipped_results + results
        return {
            "success": success_count == len(results) if results else True,
            "sources_synced": success_count,
            "sources_skipped": len(skipped_results),
            "total_sources": len(all_results),
            "results": all_results,
        }

    def _acquire_sources_for_sync(
        self, sources: List[EpgSource], *, force: bool = False
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        to_sync: List[int] = []
        skipped: List[Dict[str, Any]] = []

        for source in sources:
            sid = source.id
            if try_acquire_epg_sync_lock(sid, force=force):
                to_sync.append(sid)
                continue

            message = "Sync already in progress"
            # Do not call set_phase here — it would clear sync_in_progress in DB while
            # another worker holds the lock (including stale ORM rows).

            skipped.append(
                {
                    "source_id": sid,
                    "source_name": source.name,
                    "success": True,
                    "skipped": True,
                    "message": message,
                }
            )

        if skipped:
            logger.info(
                "EPG orchestrator: skipped %s source(s) already in progress",
                len(skipped),
            )

        return to_sync, skipped

    def _sync_source_in_thread(self, source_id: int) -> Dict[str, Any]:
        with self.app.app_context():
            source = db.session.get(EpgSource, source_id)
            if not source:
                return {"source_id": source_id, "success": False, "message": "Source not found", "stats": {}}

            name = source.name
            EpgSyncProgress.set_phase(source_id, PHASE_QUEUED, message="Waiting to start")

            def on_progress(phase: str, message: str = "", **counts: Any) -> None:
                EpgSyncProgress.set_phase(source_id, phase, message=message, **counts)

            try:
                success, message, stats = EpgSyncService.sync_source(source, progress=on_progress)
                EpgSyncService.update_source_sync_status(source, success, message, stats)
                EpgSyncProgress.set_phase(
                    source_id,
                    PHASE_COMPLETE if success else PHASE_ERROR,
                    message=message,
                    **{k: stats.get(k) for k in ("programs_added", "programs_updated", "channels_added") if stats},
                )
                result = {
                    "source_id": source_id,
                    "source_name": name,
                    "success": success,
                    "message": message,
                    "stats": stats,
                }
                if stats.get("partial"):
                    result["partial"] = True
                return result
            except Exception as exc:
                db.session.rollback()
                logger.error("Error syncing EPG source %s: %s", name, exc, exc_info=True)
                EpgSyncProgress.set_phase(source_id, PHASE_ERROR, message=str(exc))
                try:
                    source = db.session.get(EpgSource, source_id)
                    if source:
                        source.last_sync_status = "error"
                        source.last_sync_message = str(exc)
                        source.sync_in_progress = False
                        db.session.commit()
                except Exception:
                    db.session.rollback()
                return {
                    "source_id": source_id,
                    "source_name": name,
                    "success": False,
                    "message": str(exc),
                    "stats": {},
                }
