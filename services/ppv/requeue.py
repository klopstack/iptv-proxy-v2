"""Bulk re-queue PPV channels for enrichment after matching fixes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import or_

from models import Channel, Settings, db

SETTING_PPV_LAST_DEPLOY_AT = "ppv_last_deploy_at"


def get_deploy_cutoff() -> Optional[datetime]:
    """Return deploy timestamp from settings, or None if unset."""
    raw = Settings.get(SETTING_PPV_LAST_DEPLOY_AT)
    if not raw:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def requeue_ppv_channels(
    *,
    account_id: Optional[int] = None,
    prefix: Optional[str] = None,
    dry_run: bool = False,
    since_last_deploy: bool = False,
    include_skipped: bool = False,
    statuses: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Mark PPV channels as queued for re-enrichment.

    Does not clear EventChannelLink rows (use clear_event_links_for_channels separately).
    Does not reset attempt counters — the next process pass increments them.
    """
    if statuses is None:
        statuses = ["no_match"]
        if include_skipped:
            statuses.append("skipped")

    query = Channel.query.filter(
        Channel.is_ppv.is_(True),
        Channel.ppv_enrichment_status.in_(statuses),
    )
    if account_id is not None:
        query = query.filter_by(account_id=account_id)
    if prefix:
        query = query.filter(Channel.name.ilike(f"{prefix}%"))
    if since_last_deploy:
        deploy_at = get_deploy_cutoff()
        if deploy_at is not None:
            query = query.filter(
                or_(
                    Channel.ppv_enrichment_last_attempt.is_(None),
                    Channel.ppv_enrichment_last_attempt < deploy_at,
                )
            )

    count = query.count()
    if dry_run:
        return {"queued": count, "dry_run": True, "statuses": statuses}

    if count:
        query.update(
            {
                Channel.ppv_enrichment_status: "queued",
                Channel.ppv_enrichment_error: None,
            },
            synchronize_session=False,
        )
        db.session.commit()

    return {"queued": count, "dry_run": False, "statuses": statuses}
