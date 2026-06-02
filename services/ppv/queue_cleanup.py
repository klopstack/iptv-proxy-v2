"""Bulk-mark non-enrichable PPV channels as skipped."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import or_

from models import Channel, db
from services.ppv.enrichability import classify_ppv_enrichment, skip_error_message


def cleanup_ppv_queue(*, dry_run: bool = False, account_id: int | None = None) -> dict:
    pending_filter = or_(
        Channel.ppv_enrichment_status.is_(None),
        Channel.ppv_enrichment_status.in_(["queued", "retry_pending"]),
    )
    query = Channel.query.filter(Channel.is_ppv.is_(True), pending_filter)
    if account_id is not None:
        query = query.filter(Channel.account_id == account_id)

    reason_counts: Counter = Counter()
    marked = 0
    enrichable = 0
    commit_batch = 500
    pending_marks = 0

    for channel in query.yield_per(500):
        reason = classify_ppv_enrichment(channel.name)
        if reason is None:
            enrichable += 1
            continue

        reason_counts[reason] += 1
        if dry_run:
            marked += 1
            continue

        channel.ppv_enrichment_status = "skipped"
        channel.ppv_enrichment_error = skip_error_message(reason)
        marked += 1
        pending_marks += 1

        if pending_marks >= commit_batch:
            db.session.commit()
            pending_marks = 0

    if not dry_run and pending_marks:
        db.session.commit()

    return {
        "dry_run": dry_run,
        "marked_skipped": marked,
        "still_enrichable": enrichable,
        "by_reason": dict(reason_counts),
    }
