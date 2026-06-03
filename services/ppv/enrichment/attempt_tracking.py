"""Persist per-channel enrichment attempt counters and timestamps."""

from datetime import datetime, timezone

from models import Channel


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _record_enrichment_attempt(channel: Channel) -> None:
    """Increment attempts and set last_attempt in the current session (no commit)."""
    channel.ppv_enrichment_attempts = (channel.ppv_enrichment_attempts or 0) + 1
    channel.ppv_enrichment_last_attempt = _utc_now_naive()
