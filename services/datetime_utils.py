"""Shared datetime serialization helpers for API transport."""

from datetime import datetime, timezone
from typing import Optional


def serialize_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime as explicit UTC ISO 8601 with Z suffix.

    Naive datetimes are interpreted as UTC to match project storage conventions.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")
