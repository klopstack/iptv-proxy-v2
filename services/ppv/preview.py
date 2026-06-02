"""PPV enrichment channel preview listing."""

from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from models import Account, Channel, Event, EventChannelLink, db
from services.ppv.channel_matching import infer_unmatched_timezone_debug
from services.ppv.serializers import serialize_linked_event_summary, serialize_utc_iso


def list_ppv_enrichment_channels(
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """List PPV channels with enrichment status and optional linked event."""
    query = Channel.query.filter(Channel.is_ppv == True)  # noqa: E712

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query = query.filter(Channel.ppv_enrichment_status.in_(statuses))

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Channel.name.ilike(term), Channel.cleaned_name.ilike(term)))

    total = query.count()

    status_rows = (
        query.with_entities(Channel.ppv_enrichment_status, func.count(Channel.id))
        .group_by(Channel.ppv_enrichment_status)
        .all()
    )
    by_status: Dict[str, int] = {}
    for row_status, count in status_rows:
        key = row_status or "unset"
        by_status[key] = count

    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    channels = query.order_by(Channel.name.asc()).offset(offset).limit(per_page).all()

    channel_ids = [channel.id for channel in channels]
    links_by_channel: Dict[int, tuple] = {}
    if channel_ids:
        link_rows = (
            db.session.query(EventChannelLink, Event)
            .join(Event, EventChannelLink.event_id == Event.id)
            .filter(EventChannelLink.channel_id.in_(channel_ids))
            .order_by(Event.scheduled_at.desc())
            .all()
        )
        for link, event in link_rows:
            if link.channel_id not in links_by_channel:
                links_by_channel[link.channel_id] = (event, link)

    account_ids = {channel.account_id for channel in channels}
    accounts: Dict[int, Account] = {}
    if account_ids:
        accounts = {acc.id: acc for acc in Account.query.filter(Account.id.in_(account_ids)).all()}

    results: List[Dict[str, Any]] = []
    for channel in channels:
        account = accounts.get(channel.account_id)
        linked = links_by_channel.get(channel.id)
        linked_event = None
        if linked:
            event, link = linked
            linked_event = serialize_linked_event_summary(event, link)

        row = {
            "channel_id": channel.id,
            "channel_name": channel.name,
            "account_id": channel.account_id,
            "account_name": account.name if account else None,
            "ppv_enrichment_status": channel.ppv_enrichment_status,
            "ppv_enrichment_attempts": channel.ppv_enrichment_attempts or 0,
            "ppv_enrichment_error": channel.ppv_enrichment_error,
            "ppv_enrichment_last_attempt": serialize_utc_iso(channel.ppv_enrichment_last_attempt),
            "linked_event": linked_event,
        }
        if channel.ppv_enrichment_status == "no_match":
            row.update(infer_unmatched_timezone_debug(channel))
        results.append(row)

    return {
        "channels": results,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "summary": {
            "total": total,
            "by_status": by_status,
        },
    }
