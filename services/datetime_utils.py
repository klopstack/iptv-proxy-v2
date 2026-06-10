"""Shared datetime serialization helpers for API transport."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_DISPLAY_TIMEZONE = "America/New_York"

# Title timezone tokens -> IANA names (for channel-side matching only)
TITLE_TIMEZONE_MAP = {
    "est": "America/New_York",
    "edt": "America/New_York",
    "et": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "ct": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "utc": "UTC",
    "gmt": "UTC",
    "uk": "Europe/London",
    "bst": "Europe/London",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
}

# Venue country hints for Event.timezone when local/UTC times differ
COUNTRY_TIMEZONE_MAP = {
    "usa": "America/New_York",
    "united states": "America/New_York",
    "england": "Europe/London",
    "united kingdom": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "canada": "America/Toronto",
    "australia": "Australia/Sydney",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "spain": "Europe/Madrid",
    "italy": "Europe/Rome",
    "mexico": "America/Mexico_City",
    "brazil": "America/Sao_Paulo",
    "japan": "Asia/Tokyo",
}

_TITLE_TZ_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(TITLE_TIMEZONE_MAP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def resolve_ppv_rename_timezone(
    *,
    credential_tz: Optional[str] = None,
    account_tz: Optional[str] = None,
) -> Optional[str]:
    """Resolve PPV rename timezone: credential override, then account, then default."""
    if credential_tz and credential_tz.strip():
        return credential_tz.strip()
    if account_tz and account_tz.strip():
        return account_tz.strip()
    return None


def to_display_timezone(
    dt: Optional[datetime],
    tz_name: Optional[str] = None,
) -> Optional[datetime]:
    """Convert a stored UTC datetime to a display timezone.

    Naive datetimes are interpreted as UTC. Invalid timezone names fall back
    to :data:`DEFAULT_DISPLAY_TIMEZONE`.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    name = (tz_name or "").strip() or DEFAULT_DISPLAY_TIMEZONE
    try:
        tz = ZoneInfo(name)
    except Exception:
        tz = ZoneInfo(DEFAULT_DISPLAY_TIMEZONE)

    return dt.astimezone(tz)


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize a datetime to naive UTC for database storage."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_title_timezone(text: str) -> Optional[str]:
    """Extract an IANA timezone from a channel title token (EST, PT, UTC, etc.)."""
    if not text:
        return None
    match = _TITLE_TZ_PATTERN.search(text)
    if not match:
        return None
    return TITLE_TIMEZONE_MAP.get(match.group(1).lower())


def _parse_hms(time_str: str) -> Optional[Tuple[int, int]]:
    """Parse HH:MM or HH:MM:SS into (hour, minute)."""
    if not time_str:
        return None
    parts = time_str.strip().split(":")
    if not parts or not parts[0]:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        return hour, minute
    except ValueError:
        return None


def _timestamp_has_timezone(ts: str) -> bool:
    if ts.endswith("Z"):
        return True
    if len(ts) >= 6 and ts[-6] in "+-" and ":" in ts[-6:]:
        return True
    if len(ts) >= 5 and ts[-5] in "+-" and ":" in ts[-5:]:
        return True
    return False


def _local_datetime_to_naive_utc(
    date_event: str,
    hour: int,
    minute: int,
    tz_name: str,
) -> Optional[datetime]:
    """Combine dateEvent + wall clock in IANA zone, return naive UTC for storage."""
    try:
        year, month, day = map(int, date_event.split("-"))
        tz = ZoneInfo(tz_name)
    except (ValueError, IndexError):
        return None
    try:
        local_dt = datetime(year, month, day, hour, minute, tzinfo=tz)
    except Exception:
        return None
    return to_naive_utc(local_dt)


def infer_thesportsdb_event_timezone(api_data: Dict[str, Any]) -> Optional[str]:
    """Infer display timezone from TheSportsDB local/UTC time fields or venue country/city."""
    from services.ppv.city_timezone_map import iana_for_city

    str_time = (api_data.get("strTime") or "").strip()
    str_time_local = (api_data.get("strTimeLocal") or "").strip()
    city = (api_data.get("strCity") or "").strip()
    country = (api_data.get("strCountry") or "").strip()

    city_tz = iana_for_city(city, country)
    if city_tz:
        return city_tz

    if str_time and str_time_local and str_time != str_time_local:
        country_key = country.lower()
        if country_key in COUNTRY_TIMEZONE_MAP:
            return COUNTRY_TIMEZONE_MAP[country_key]
    country_key = country.lower()
    return COUNTRY_TIMEZONE_MAP.get(country_key)


def parse_thesportsdb_scheduled_at(
    api_data: Dict[str, Any],
) -> Tuple[Optional[datetime], Optional[str]]:
    """Parse canonical start time from TheSportsDB API fields.

    Priority: strTimestamp (with zone) > dateEvent+strTime (UTC wall clock) >
    dateEvent+strTimeLocal (converted via inferred venue IANA zone).

    Returns (naive_utc_datetime, iana_timezone_or_none).
    """
    event_tz = infer_thesportsdb_event_timezone(api_data)
    ts = (api_data.get("strTimestamp") or "").strip()
    date_event = (api_data.get("dateEvent") or "").strip()
    str_time = (api_data.get("strTime") or "").strip()

    if ts and _timestamp_has_timezone(ts):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return to_naive_utc(parsed), event_tz
        except ValueError:
            logger.debug("Failed to parse strTimestamp with timezone: %s", ts)

    if date_event and str_time:
        hms = _parse_hms(str_time)
        if hms:
            try:
                year, month, day = map(int, date_event.split("-"))
                hour, minute = hms
                dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                return to_naive_utc(dt), event_tz
            except (ValueError, IndexError):
                logger.debug("Failed to parse dateEvent+strTime: %s %s", date_event, str_time)

    if ts and "T" in ts and not _timestamp_has_timezone(ts):
        logger.debug(
            "Ignoring naive strTimestamp %s for event %s; strTime/dateEvent preferred",
            ts,
            api_data.get("idEvent"),
        )

    if date_event and not str_time:
        str_time_local = (api_data.get("strTimeLocal") or "").strip()
        if str_time_local and event_tz:
            hms_local = _parse_hms(str_time_local)
            if hms_local:
                hour, minute = hms_local
                scheduled = _local_datetime_to_naive_utc(date_event, hour, minute, event_tz)
                if scheduled is not None:
                    logger.debug(
                        "TheSportsDB event %s: parsed dateEvent+strTimeLocal via %s -> %s UTC",
                        api_data.get("idEvent"),
                        event_tz,
                        scheduled,
                    )
                    return scheduled, event_tz
        logger.debug(
            "TheSportsDB event %s has dateEvent but no parseable UTC/local time; skipping scheduled_at update",
            api_data.get("idEvent"),
        )

    return None, event_tz


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
