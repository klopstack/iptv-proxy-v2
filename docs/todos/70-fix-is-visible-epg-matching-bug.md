# Fix `is_visible` misuse in EPG auto-matching

**Status:** ✅ Done  
**Priority:** P0  
**Audit:** Application-wide audit, June 2026

## Problem

**Critical bug:** EPG match-rules orchestration ignores the return value of live filter evaluation and uses stale cached `is_visible`:

```python
# services/epg/match_rules/orchestrator.py ~198-199
FilterService.apply_filters_to_channels(all_channels, account_id)
channels = [ch for ch in all_channels if ch.is_visible]
```

`FilterService.apply_filters_to_channels()` returns the live-filtered channel list and **does not update** `is_visible`. The `is_visible` column is an admin cache updated during IPTV sync / filter recompute — it can be stale after filter rule changes without a sync.

Same pattern may exist in `routes/epg/channels.py` (~694–695) and `services/ppv/epg.py` boundary.

**Impact:** EPG auto-matching and rematch can include channels that should be hidden or exclude channels that should be visible, until the next full sync.

`ChannelQueryService` applies live filters correctly — this path diverges from the unified channel selection model.

## Affected files

- `services/epg/match_rules/orchestrator.py`
- `routes/epg/channels.py` (verify and fix)
- `services/ppv/epg.py` (verify boundary usage)

## Proposed solution

```python
channels = FilterService.apply_filters_to_channels(all_channels, account_id)
```

Or extract shared helper used by CQS and EPG matching:

```python
def channels_visible_for_account(channels, account_id) -> list[Channel]:
    return FilterService.apply_filters_to_channels(channels, account_id)
```

Add regression test: change filter rule → rematch without sync → correct channel set.

## Acceptance criteria

- [x] EPG matching uses live filter evaluation, not `is_visible` column
- [x] Behavior matches `ChannelQueryService` for same account + filters
- [x] Regression test passes

## Test plan

- Unit test: channel with `is_visible=True` but failing live filter is excluded from matching
- Unit test: channel with `is_visible=False` but passing live filter is included

## Dependencies

- See `docs/architecture/channel-visibility-is-visible.md`
