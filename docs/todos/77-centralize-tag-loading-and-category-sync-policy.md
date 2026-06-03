# Centralize tag loading and fix N+1 in channel link detection

**Status:** ✅ Done  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Tag batch-loading logic is implemented three times:

- `services/filter_service.py`
- `services/channel_query_service.py` (batch_size 500)
- `services/sync_service.py` — `detect_channel_links` does **per-channel N+1** tag queries inside batches

Also: category sync failure in `ChannelSyncService.sync_account` logs error but leaves `success=True`, so channel sync proceeds with potentially stale categories affecting PPV detection.

## Affected files

- `services/sync_service.py` — `detect_channel_links`, category sync (~170–185)
- `services/filter_service.py`, `services/channel_query_service.py`
- New: `services/channel_tags.py` (optional)

## Proposed solution

1. Centralize tag loading in one module or `ChannelQueryService.load_tags_for_channels`
2. Fix N+1 in `detect_channel_links` to use batch loader
3. Decide category sync policy: fail fast, or set `success=False` and skip downstream steps — document and test

## Acceptance criteria

- [x] `detect_channel_links` uses O(1) tag queries per batch, not per channel
- [x] Category fetch failure policy documented and tested
- [x] Single tag loader used by filter and CQS

## Category sync failure policy

When `get_live_categories()` fails, `sync_account` sets `stats["success"] = False` and
records the error. Channel sync still runs so stream rows can update, but post-sync
steps (deactivation, filter visibility, PPV re-enrichment, backup detection, icon
prefetch) are skipped because they are gated on `stats["success"]`.

## Test plan

- Unit test for `detect_channel_links` with query count assertion
- Update `test_sync_account_categories_error` if policy changes

## Dependencies

None.
