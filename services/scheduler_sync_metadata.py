"""Persistent sync timestamps and failure metadata for scheduler jobs."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from models import SyncMetadata
from services.datetime_utils import serialize_utc_iso
from services.scheduler_constants import (
    MAX_SYNC_ERROR_LENGTH,
    SYNC_FAILURE_AT_SUFFIX,
    SYNC_FAILURE_ERROR_SUFFIX,
    SYNC_KEY_LAST_ACCOUNT_SYNC,
)


def get_last_sync_time(key: str) -> Optional[datetime]:
    value = SyncMetadata.get(key)
    if value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


def set_last_sync_time(key: str, when: Optional[datetime] = None) -> None:
    if when is None:
        when = datetime.now(timezone.utc)
    SyncMetadata.set(key, serialize_utc_iso(when))


def failure_at_key(last_sync_key: str) -> str:
    return f"{last_sync_key}{SYNC_FAILURE_AT_SUFFIX}"


def failure_error_key(last_sync_key: str) -> str:
    return f"{last_sync_key}{SYNC_FAILURE_ERROR_SUFFIX}"


def truncate_sync_error(message: str) -> str:
    text = str(message).strip() if message else ""
    if len(text) <= MAX_SYNC_ERROR_LENGTH:
        return text
    return text[: MAX_SYNC_ERROR_LENGTH - 3] + "..."


def record_sync_failure(last_sync_key: str, error: str) -> None:
    now = datetime.now(timezone.utc)
    SyncMetadata.set(failure_at_key(last_sync_key), serialize_utc_iso(now))
    SyncMetadata.set(failure_error_key(last_sync_key), truncate_sync_error(error))


def record_sync_success(last_sync_key: str) -> None:
    SyncMetadata.delete(failure_error_key(last_sync_key))


def get_sync_failure_fields(last_sync_key: str) -> dict:
    failure_at = get_last_sync_time(failure_at_key(last_sync_key))
    error = SyncMetadata.get(failure_error_key(last_sync_key))
    return {
        "last_failure_at": serialize_utc_iso(failure_at),
        "last_error": error or None,
    }


def resolve_last_run_status(last_success: Optional[datetime], last_error: Optional[str]) -> str:
    if last_error:
        return "error"
    if last_success is not None:
        return "success"
    return "unknown"


def default_failure_message(last_sync_key: str) -> str:
    if last_sync_key == SYNC_KEY_LAST_ACCOUNT_SYNC:
        return "One or more enabled accounts failed to sync"
    return "Job returned failure"


def needs_sync(key: str, interval_hours: int) -> bool:
    last_sync = get_last_sync_time(key)
    if last_sync is None:
        return True
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    next_sync = last_sync + timedelta(hours=interval_hours)
    return datetime.now(timezone.utc) >= next_sync
