# Refactor scheduler into job registry (architecture)

**Status:** ⬜ Not started  
**Priority:** P3  
**Audit:** Application-wide audit, June 2026

## Problem

`SyncScheduler` (~676 lines) is a god object owning unrelated scheduled jobs:

- Account IPTV sync, EPG sync delegation, FCC sync
- PPV prefetch/enrichment/time refresh
- Sportsipy/MiLB/TSDB team refresh
- EPG program cleanup, health check cleanup
- Heartbeat, interval persistence, status API

Each `_check_and_sync` tick runs a long **sequential** chain — one slow EPG source blocks PPV/FCC/cleanup for that tick.

Dead code: `_apply_fcc_enrichment` defined but never called.

Unused: `ChannelSyncService.sync_account(..., force=...)` parameter never read.

## Affected files

- `services/scheduler.py`
- `tests/test_scheduler_service.py`

## Proposed solution

1. Job registry: `{ key, interval_setting, callable, advance_timestamp_on_success }`
2. Move PPV/sportsipy jobs to dedicated modules invoked by registry
3. Remove dead `_apply_fcc_enrichment` or wire it
4. Implement or remove `force` on IPTV sync
5. Consider parallel job execution with isolated app contexts (future)

## Acceptance criteria

- [ ] `scheduler.py` coordinator < 400 lines
- [ ] Each job registered declaratively
- [ ] Timestamp advance only on success (TODO 71)
- [ ] Dead code removed

## Test plan

- Existing scheduler tests pass
- Add test per registered job stub

## Dependencies

- TODO 71 (timestamp semantics)
- See `docs/architecture/scheduler-and-sync-orchestration.md`
