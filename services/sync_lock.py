"""Shared sync lock primitives for account and EPG source synchronization."""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Type

from sqlalchemy import update

from models import db

logger = logging.getLogger(__name__)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def try_acquire_sync_lock(
    model: Type,
    entity_id: int,
    *,
    force: bool = False,
    entity_label: Optional[str] = None,
    log_entity_type: str = "entity",
    extra_acquire_values: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Atomically claim a sync lock (safe across workers/threads).

    Returns True if this caller holds the lock.
    """
    now = utc_now_naive()
    values: Dict[str, Any] = {"sync_in_progress": True, "sync_started_at": now}
    if extra_acquire_values:
        values.update(extra_acquire_values)

    if force:
        locked = (
            getattr(
                db.session.execute(update(model).where(model.id == entity_id, model.sync_in_progress.is_(True))),
                "rowcount",
                0,
            )
            or 0
        ) > 0
        if locked:
            label = entity_label or "?"
            logger.warning(
                "Sync force=True overriding in-progress lock for %s %s (id=%s)",
                log_entity_type,
                label,
                entity_id,
            )
        result = db.session.execute(update(model).where(model.id == entity_id).values(**values))
    else:
        result = db.session.execute(
            update(model).where(model.id == entity_id, model.sync_in_progress.is_(False)).values(**values)
        )
    db.session.commit()
    return (getattr(result, "rowcount", 0) or 0) > 0


def release_sync_lock(
    model: Type,
    entity_id: int,
    *,
    extra_release_values: Optional[Dict[str, Any]] = None,
) -> None:
    """Clear sync_in_progress and sync_started_at on the entity."""
    entity = db.session.get(model, entity_id)
    if not entity:
        return
    entity.sync_in_progress = False
    entity.sync_started_at = None
    if extra_release_values:
        for key, value in extra_release_values.items():
            setattr(entity, key, value)
    db.session.commit()


def recover_stale_sync_locks(
    model: Type,
    *,
    max_age: timedelta,
    log_entity_type: str,
    name_attr: str = "name",
    extra_recover_values: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Reset sync locks held longer than max_age (e.g. after worker crash).

    Returns:
        Number of entities recovered.
    """
    cutoff = utc_now_naive() - max_age
    stale = model.query.filter(
        model.sync_in_progress.is_(True),
        db.or_(
            db.and_(model.sync_started_at.isnot(None), model.sync_started_at < cutoff),
            db.and_(model.sync_started_at.is_(None), model.updated_at < cutoff),
        ),
    ).all()

    for entity in stale:
        label = getattr(entity, name_attr, None) or entity.id
        logger.warning(
            "Recovering stale sync lock for %s %s (id=%s, started=%s)",
            log_entity_type,
            label,
            entity.id,
            entity.sync_started_at,
        )
        entity.sync_in_progress = False
        entity.sync_started_at = None
        if extra_recover_values:
            for key, value in extra_recover_values.items():
                setattr(entity, key, value)

    if stale:
        db.session.commit()

    return len(stale)


@contextmanager
def sync_lock_context(
    model: Type,
    entity_id: int,
    *,
    not_found_error: str,
    in_progress_error: Callable[[Any], str],
    log_entity_type: str = "entity",
    name_attr: str = "name",
):
    """
    Context manager that acquires a sync lock and releases it on exit.

    Raises:
        ValueError: If entity not found or sync already in progress.
    """
    entity = db.session.get(model, entity_id)
    if not entity:
        raise ValueError(not_found_error)

    if not try_acquire_sync_lock(
        model,
        entity_id,
        entity_label=getattr(entity, name_attr, None),
        log_entity_type=log_entity_type,
    ):
        entity = db.session.get(model, entity_id)
        raise ValueError(in_progress_error(entity))

    entity = db.session.get(model, entity_id)
    label = getattr(entity, name_attr, None) if entity else str(entity_id)
    logger.info("Acquired sync lock for %s %s (ID: %s)", log_entity_type, label, entity_id)

    try:
        yield entity
    finally:
        try:
            release_sync_lock(model, entity_id)
            entity = db.session.get(model, entity_id)
            if entity:
                label = getattr(entity, name_attr, None)
                logger.info("Released sync lock for %s %s (ID: %s)", log_entity_type, label, entity_id)
        except Exception as exc:
            logger.error("Error releasing sync lock for %s %s: %s", log_entity_type, entity_id, exc)
            db.session.rollback()
