# Replace background detail thread and decouple EPG side effects

**Status:** ⬜ Not started  
**Priority:** P2  
**Audit:** PPV audit, June 2026

## Problem

### Background detail thread

`PPVCalendarEnrichmentService` starts a daemon thread (`_detail_fetch_loop`) that:

- Holds a long-lived Flask `app_context`
- Uses ad hoc `db.session.rollback()` on errors
- Runs LLM enrichment synchronously inside the rate-limited queue (blocks detail fetches on LLM latency)
- Has no graceful shutdown on app teardown

### EPG side effects in enrichment

Every enrichment batch calls `sync_ppv_epg_after_enrichment` and `prune_orphan_ppv_events` inline. Unit tests must patch these to test matching logic — tight coupling between domain matching and EPG infrastructure.

## Affected files

- `services/ppv/enrichment.py` — `_detail_fetch_loop`, `_fetch_event_details`, batch completion hooks
- `services/ppv/cleanup.py`
- `services/scheduler.py` — potential job queue target
- `tests/ppv/test_enrichment.py` — reduce patch surface after refactor

## Proposed solution

1. **Detail fetch:** Move to APScheduler job or RQ task with per-item `app.app_context()` + `db.session.remove()`. Separate LLM enrichment into its own queued job with timeout.
2. **Side effects:** Introduce optional post-enrichment hooks (default listener triggers EPG sync). Tests inject no-op listener.
3. Document threading vs scheduler choice in architecture doc.

## Acceptance criteria

- [ ] No daemon thread holding global session across requests.
- [ ] LLM failure/timeout does not block TheSportsDB detail queue.
- [ ] Enrichment tests can run without patching EPG sync when hook disabled.
- [ ] App shutdown does not leave orphaned threads.

## Test plan

- Test detail job processes queue item with fresh session.
- Test enrichment with null side-effect hook — no EPG service calls.

## Dependencies

- TODO 65 phase 1 (extract DetailFetchWorker).
- See `docs/architecture/ppv-module-boundaries.md`.
