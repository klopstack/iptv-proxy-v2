"""PPV virtual category ordering for Xtream and M3U output."""

from datetime import datetime, timezone

from models import Account, db
from services.ppv.visibility import PPVVisibilityService

PPV_LIVE_CATEGORY_ID = "-10"
PPV_REPLAY_CATEGORY_ID = "-11"
PPV_HISTORICAL_CATEGORY_ID = "-12"
PPV_UNMATCHED_LIVE_CATEGORY_ID = "-13"

_GROUPED_PPV_CATEGORY_IDS = (
    PPV_LIVE_CATEGORY_ID,
    PPV_REPLAY_CATEGORY_ID,
    PPV_HISTORICAL_CATEGORY_ID,
    PPV_UNMATCHED_LIVE_CATEGORY_ID,
)


def _as_utc_aware(dt):
    """Normalize datetimes to timezone-aware UTC for safe comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ppv_group_services(channels, account=None):
    """Return per-account PPV grouping services for accounts using Live/Replay mode."""
    if account:
        if getattr(account, "ppv_visibility", None) == PPVVisibilityService.GROUP_LIVE_REPLAY:
            return {account.id: PPVVisibilityService(account)}
        return {}

    account_ids = sorted({ch.account_id for ch in channels if ch.is_ppv})
    if not account_ids:
        return {}

    accounts = Account.query.filter(Account.id.in_(account_ids)).all()
    return {
        acc.id: PPVVisibilityService(acc)
        for acc in accounts
        if getattr(acc, "ppv_visibility", None) == PPVVisibilityService.GROUP_LIVE_REPLAY
    }


def build_ppv_grouping(channels, account=None):
    """Map channel IDs to virtual Live/Replay/Historical PPV categories and linked events."""
    services = _ppv_group_services(channels, account=account)
    grouped = {}
    for channel in channels:
        service = services.get(channel.account_id)
        if not service:
            continue
        if not service.should_show_channel(channel):
            continue
        classification = service.classify_live_replay_channel(channel)
        if classification == PPVVisibilityService.PPV_GROUP_LIVE:
            grouped[channel.id] = {
                "category_id": PPV_LIVE_CATEGORY_ID,
                "event": service.get_linked_event(channel),
            }
        elif classification == PPVVisibilityService.PPV_GROUP_REPLAY:
            grouped[channel.id] = {
                "category_id": PPV_REPLAY_CATEGORY_ID,
                "event": service.get_linked_event(channel),
            }
        elif classification == PPVVisibilityService.PPV_GROUP_HISTORICAL:
            grouped[channel.id] = {
                "category_id": PPV_HISTORICAL_CATEGORY_ID,
                "event": service.get_linked_event(channel),
            }
        elif classification == PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE:
            grouped[channel.id] = {
                "category_id": PPV_UNMATCHED_LIVE_CATEGORY_ID,
                "event": None,
                "scheduled_at": service.unmatched_live_scheduled_at(channel),
            }
    return grouped


def sort_grouped_ppv_channels(channels, grouped_ppv, category_id):
    """Sort PPV Live by soonest first; Replay/Historical by most recent first."""
    reverse = category_id in (PPV_REPLAY_CATEGORY_ID, PPV_HISTORICAL_CATEGORY_ID)
    fallback = datetime.max.replace(tzinfo=timezone.utc) if not reverse else datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(channel):
        group_data = grouped_ppv.get(channel.id, {})
        event = group_data.get("event")
        if event and event.scheduled_at:
            scheduled_at = _as_utc_aware(event.scheduled_at)
        elif group_data.get("scheduled_at"):
            scheduled_at = _as_utc_aware(group_data["scheduled_at"])
        else:
            scheduled_at = fallback
        return scheduled_at

    return sorted(channels, key=sort_key, reverse=reverse)


def reorder_grouped_ppv_in_channel_list(channels, grouped_ppv):
    """Fix relative order of grouped PPV channels without moving non-PPV channels."""
    if not grouped_ppv:
        return channels

    buckets = {cat_id: [] for cat_id in _GROUPED_PPV_CATEGORY_IDS}
    for ch in channels:
        cat = grouped_ppv.get(ch.id, {}).get("category_id")
        if cat in buckets:
            buckets[cat].append(ch)

    sorted_buckets = {
        cat_id: sort_grouped_ppv_channels(chs, grouped_ppv, cat_id) for cat_id, chs in buckets.items() if chs
    }
    if not sorted_buckets:
        return channels

    iterators = {cat_id: iter(sorted_chs) for cat_id, sorted_chs in sorted_buckets.items()}

    result = []
    for ch in channels:
        cat = grouped_ppv.get(ch.id, {}).get("category_id")
        if cat in iterators:
            result.append(next(iterators[cat]))
        else:
            result.append(ch)
    return result
