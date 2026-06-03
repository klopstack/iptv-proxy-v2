# Fix scheduler sync success and timestamp semantics

**Status:** ✅ Done  
**Priority:** P0  
**Audit:** Application-wide audit, June 2026

## Problem

Two related scheduler bugs:

### 1. Account sync always marked success

`SyncScheduler._sync_accounts()` sets `account.last_sync_status = "success"` after `ChannelSyncService.sync_account()` returns, even when `stats["success"]` is `False` (e.g. channel fetch failure). Operators see green status with partial/missing data.

### 2. Job timestamps advance on failure

`_check_and_sync()` calls `_set_last_sync_time()` unconditionally after `_sync_accounts`, `_sync_fcc_data`, PPV jobs, cleanup jobs, etc. Failed runs still reset the interval clock, delaying retry for hours.

Per-source EPG sync was fixed (TODOs 40–41) to not advance `last_sync` on failure; scheduler-level jobs were not aligned.

## Affected files

- `services/scheduler.py` — `_sync_accounts` (~407–421), `_check_and_sync` (~327–391)

## Proposed solution

1. Set `account.last_sync_status` from `stats["success"]` and error count
2. Only call `_set_last_sync_time(key)` when the corresponding job completes successfully
3. Optionally track per-job failure metadata in `SyncMetadata` for status API

Mirror the pattern already used in `EpgSyncOrchestrator`.

## Acceptance criteria

- [x] Partial channel sync marks account as error (or partial — document semantics)
- [x] Failed FCC/PPV/cleanup run does not advance `_set_last_sync_time`
- [ ] Scheduler status API reflects last failure → [91-scheduler-status-api-failure-metadata.md](./91-scheduler-status-api-failure-metadata.md)

## Test plan

- Unit test: mock `sync_account` returning `success=False` → account status is not "success"
- Unit test: mock failing FCC sync → `SYNC_KEY_LAST_FCC_SYNC` unchanged

## Dependencies

None.
