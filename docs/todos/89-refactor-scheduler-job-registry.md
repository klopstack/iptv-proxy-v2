# Refactor scheduler into job registry (architecture)

**Status:** ✅ Done  
**Priority:** P3  
**Audit:** Application-wide audit, June 2026  
**PR:** Wave 4 PR N (#25)

## Problem

`SyncScheduler` (~676 lines) was a god object owning unrelated scheduled jobs:

- Account IPTV sync, EPG sync delegation, FCC sync
- PPV prefetch/enrichment/time refresh
- Sportsipy/MiLB/TSDB team refresh
- EPG program cleanup, health check cleanup
- Heartbeat, interval persistence, status API

Each `_check_and_sync` tick ran a long **sequential** chain — one slow EPG source blocks PPV/FCC/cleanup for that tick.

Dead code: `_apply_fcc_enrichment` defined but never called.

Unused: `ChannelSyncService.sync_account(..., force=...)` parameter never read.

## Solution (implemented)

1. **`services/scheduler_registry.py`** — `JobDefinition` dataclass and `build_scheduled_jobs()` with `{ key, interval, run, advance_timestamp_on_success }`.
2. **`services/scheduler_jobs/`** — PPV, sportsipy, FCC, accounts, EPG, cleanup, health job modules.
3. **`services/scheduler_sync_metadata.py`** — last-sync timestamps and failure metadata (TODO 71 semantics).
4. **`services/scheduler_constants.py`** — interval keys and defaults.
5. **`services/scheduler.py`** — coordinator (~363 lines): registry loop, heartbeat, status API.
6. Removed `_apply_fcc_enrichment` and unused `sync_account(..., force=...)`.

Parallel job execution remains future work (not in scope).

## Acceptance criteria

- [x] `scheduler.py` coordinator < 400 lines
- [x] Each job registered declaratively
- [x] Timestamp advance only on success (TODO 71)
- [x] Dead code removed

## Test plan

- [x] Existing scheduler tests pass (`tests/test_scheduler_service.py`, `tests/test_api_scheduler.py`)
- [x] `TestSchedulerJobRegistry` — status keys, unique metadata keys, callable runners

## Dependencies

- TODO 71 (timestamp semantics) ✅
- TODO 91 (failure metadata) ✅
- See `docs/architecture/scheduler-and-sync-orchestration.md`
