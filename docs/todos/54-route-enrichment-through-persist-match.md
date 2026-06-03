# Route calendar enrichment writes through `persist_match`

**Status:** ✅ Done (PR #13)  
**Priority:** P0  
**Audit:** PPV audit, June 2026

## Problem

The calendar enrichment path in `PPVCalendarEnrichmentService.enrich_channels` bypasses the persistence layer:

```python
event = self._create_or_update_event(result.calendar_event)
self._link_channel_to_event(channel, event, ...)
channel.ppv_enrichment_status = "matched"
```

Meanwhile, the enhanced fallback path correctly uses `persist_match` / `persist_enhanced_match`, which:

- Applies age validation (`MAX_EVENT_AGE_DAYS`, `MAX_EVENT_FUTURE_DAYS`)
- Sets `ppv_enrichment_status` and clears errors consistently
- Returns structured `(event, created)` tuples

This split means calendar matches can persist events that enhanced matching would reject, and status/error handling diverges.

**Related bug:** `results["events_created"]` increments whenever `create_or_update_event` returns non-None, including **updates** to existing rows — the counter misleads operators.

**Related bug:** `_link_channel_to_event` logs exceptions but does not set `retry_pending` or roll back, leaving channels in an ambiguous state.

## Affected files

- `services/ppv/enrichment.py` — match loop (~lines 237–247), `_link_channel_to_event`
- `services/ppv/persistence.py` — `persist_match`, `create_or_update_event`

## Proposed solution

1. Replace inline create/link/status with `persist_match(channel, calendar_event, confidence, method)`.
2. Extend `persist_match` (or `create_or_update_event`) to return `(event, was_created: bool)` so stats distinguish creates vs updates.
3. On link/persist failure: set `channel.ppv_enrichment_status = "retry_pending"` with error message; roll back or skip commit for that channel.
4. Remove redundant `_create_or_update_event` wrapper if unused elsewhere.

## Acceptance criteria

- [x] Calendar and enhanced paths both use `persist_match`.
- [x] `events_created` counts only new `Event` rows; add `events_updated` if useful.
- [x] Persist failures surface as `retry_pending`, not silent partial state.
- [x] Age-rejected calendar events do not link channels.

## Completion

- PR #13 — https://github.com/klopstack/iptv-proxy-v2/pull/13

## Test plan

- Unit tests in `tests/ppv/test_persistence.py` (see TODO 60).
- Extend `tests/ppv/test_enrichment.py` to assert persist path used and counter semantics.

## Dependencies

- TODO 60 (persistence tests) can land in parallel.
