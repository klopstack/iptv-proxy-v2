"""Tests for PPV virtual category ordering."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from services.ppv.ordering import (
    PPV_LIVE_CATEGORY_ID,
    PPV_REPLAY_CATEGORY_ID,
    reorder_grouped_ppv_in_channel_list,
    sort_grouped_ppv_channels,
)


def _channel(channel_id, name):
    return SimpleNamespace(id=channel_id, name=name)


def _grouped_ppv(entries):
    """entries: list of (channel_id, category_id, scheduled_at)"""
    grouped = {}
    for channel_id, category_id, scheduled_at in entries:
        grouped[channel_id] = {
            "category_id": category_id,
            "event": SimpleNamespace(scheduled_at=scheduled_at),
        }
    return grouped


class TestSortGroupedPpvChannels:
    def test_live_sorts_soonest_first(self):
        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        ch_soon = _channel(1, "A Soon")
        ch_later = _channel(2, "Z Later")
        grouped = _grouped_ppv(
            [
                (1, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=1)),
                (2, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=6)),
            ]
        )
        result = sort_grouped_ppv_channels([ch_later, ch_soon], grouped, PPV_LIVE_CATEGORY_ID)
        assert [ch.id for ch in result] == [1, 2]

    def test_replay_sorts_most_recent_first(self):
        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        ch_recent = _channel(1, "Recent")
        ch_old = _channel(2, "Old")
        grouped = _grouped_ppv(
            [
                (1, PPV_REPLAY_CATEGORY_ID, now - timedelta(hours=1)),
                (2, PPV_REPLAY_CATEGORY_ID, now - timedelta(hours=5)),
            ]
        )
        result = sort_grouped_ppv_channels([ch_old, ch_recent], grouped, PPV_REPLAY_CATEGORY_ID)
        assert [ch.id for ch in result] == [1, 2]


class TestReorderGroupedPpvInChannelList:
    def test_fixes_relative_order_without_moving_non_ppv(self):
        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        ch_regular = _channel(99, "ESPN")
        ch_soon = _channel(1, "PPV Soon")
        ch_later = _channel(2, "PPV Later")
        # Name order puts later before soon among PPV, with regular channel between
        channels = [ch_later, ch_regular, ch_soon]
        grouped = _grouped_ppv(
            [
                (1, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=1)),
                (2, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=6)),
            ]
        )
        result = reorder_grouped_ppv_in_channel_list(channels, grouped)
        assert [ch.id for ch in result] == [1, 99, 2]
        live_only = [ch for ch in result if ch.id in (1, 2)]
        assert [ch.id for ch in live_only] == [1, 2]

    def test_client_side_category_filter_gets_correct_order(self):
        """Simulate client fetching all streams then filtering by category_id."""
        now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        ch_z_later = _channel(2, "Z Later PPV")
        ch_a_soon = _channel(1, "A Soon PPV")
        ch_m_mid = _channel(3, "M Mid Regular")
        channels = [ch_z_later, ch_m_mid, ch_a_soon]
        grouped = _grouped_ppv(
            [
                (1, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=1)),
                (2, PPV_LIVE_CATEGORY_ID, now + timedelta(hours=6)),
            ]
        )
        reordered = reorder_grouped_ppv_in_channel_list(channels, grouped)
        live_filtered = [ch for ch in reordered if grouped.get(ch.id, {}).get("category_id") == PPV_LIVE_CATEGORY_ID]
        assert [ch.id for ch in live_filtered] == [1, 2]
