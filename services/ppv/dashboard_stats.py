"""Lightweight PPV counts for the main dashboard summary."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import exists, not_

from models import Channel, Event, EventChannelLink, db
from services.ppv.orchestrator import PPVEnrichmentOrchestrator


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _upcoming_ppv_events_query(now: datetime, hours: int):
    future = now + timedelta(hours=hours)
    return db.session.query(Event).filter(
        Event.is_ppv.is_(True),
        Event.scheduled_at >= now,
        Event.scheduled_at <= future,
    )


def build_dashboard_ppv_stats() -> Dict[str, Any]:
    """
    Cheap aggregate PPV metrics for GET /api/dashboard/summary.

    Uses indexed COUNT queries only — no event serialization or enrichment work.
    """
    now = _utc_now_naive()

    ppv_channels = Channel.query.filter(
        Channel.is_active.is_(True),
        Channel.is_ppv.is_(True),
    ).count()

    upcoming_24h = _upcoming_ppv_events_query(now, 24).count()
    upcoming_48h = _upcoming_ppv_events_query(now, 48).count()

    link_exists = exists().where(EventChannelLink.event_id == Event.id)
    upcoming_without_channels = _upcoming_ppv_events_query(now, 48).filter(not_(link_exists)).count()

    channel_links = db.session.query(EventChannelLink).count()

    no_match_count = Channel.query.filter(
        Channel.is_active.is_(True),
        Channel.is_ppv.is_(True),
        Channel.ppv_enrichment_status == "no_match",
    ).count()

    enriched_since = now - timedelta(hours=24)
    recently_enriched = Channel.query.filter(
        Channel.is_active.is_(True),
        Channel.is_ppv.is_(True),
        Channel.ppv_enrichment_status.in_(["matched", "enriched"]),
        Channel.ppv_enrichment_last_attempt >= enriched_since,
    ).count()

    queue_stats = PPVEnrichmentOrchestrator.get_queue_stats()
    enrichment_enabled = PPVEnrichmentOrchestrator.is_enabled()

    queued_count = queue_stats.get("queued_count", 0)
    hot_queued_count = queue_stats.get("hot_queued_count", 0)

    has_issues = upcoming_without_channels > 0 or no_match_count > 0 or (queued_count > 0 and not enrichment_enabled)

    return {
        "ppv_channels": ppv_channels,
        "events": {
            "upcoming_24h": upcoming_24h,
            "upcoming_48h": upcoming_48h,
            "without_channels": upcoming_without_channels,
        },
        "channel_links": channel_links,
        "enrichment": {
            "enabled": enrichment_enabled,
            "queued_count": queued_count,
            "hot_queued_count": hot_queued_count,
            "no_match_count": no_match_count,
            "recently_enriched_24h": recently_enriched,
        },
        "has_issues": has_issues,
    }
