# Expose scheduler job failures in status API

**Status:** ✅ Done  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026  
**Deferred from:** [71-fix-scheduler-sync-status-semantics.md](./71-fix-scheduler-sync-status-semantics.md)

## Problem

TODO 71 fixed runtime semantics: account `last_sync_status` reflects `stats["success"]`, and `_set_last_sync_time()` only runs after successful jobs. Operators still lack a unified view of **which scheduler jobs last failed** and **why**.

Gaps today:

1. **`GET /api/scheduler/status`** (`SyncScheduler.get_status()`) reports `last_sync`, `next_sync`, and `overdue` per sync type, but not last failure time, status, or error summary.
2. **Only four job types** appear in `syncs` (accounts, epg, fcc, ppv_enrichment). Other scheduled jobs (PPV prefetch, PPV time refresh, sportsipy refresh, EPG program cleanup, health-check cleanup) have no status surface.
3. **Per-account failures** are on `Account.last_sync_status` / `last_sync`, but bulk dashboard code (`routes/api.py` sync overview) still counts `last_sync_status == "success"` without surfacing recent errors or partial failures.
4. **No `SyncMetadata` failure keys** — unlike per-source EPG progress (`EpgSyncProgress`), scheduler-level jobs do not persist `last_error` / `last_failure_at` when a run returns `False` or raises.

After a failed FCC or PPV run, the UI can show the job as **overdue** (because `last_sync` did not advance) without explaining that the previous attempt failed vs. never having run.

## Affected files

- `services/scheduler.py` — job helpers and `get_status()`
- `models/sync.py` — `SyncMetadata` (if new key conventions are documented)
- `routes/api.py` — `GET /api/scheduler/status`, sync overview payload
- `static/js/` or admin settings UI — display failure state (if applicable)
- `docs/API_REFERENCE.md` — response shape

## Proposed solution

1. **Define metadata keys** per job, e.g. `last_fcc_sync_failure_at`, `last_fcc_sync_error` (short string or JSON), set on failure; clear or leave historical on success (document retention).
2. **Record failures** in `_check_and_sync` when a job helper returns `False` or catches an exception (mirror EPG orchestrator error fields).
3. **Extend `get_status()`** so each sync entry includes:
   - `last_success_at` (existing `last_sync` semantics, renamed or aliased for clarity)
   - `last_failure_at`
   - `last_error` (truncated message)
   - `last_run_status`: `"success" | "error" | "unknown"`
4. **Register all scheduled jobs** in status output with their interval keys (prefetch, time refresh, sportsipy, cleanups).
5. **Dashboard** — include failed accounts list or count in sync overview; link to account detail where `last_sync_status == "error"`.

Optional: align with TODO 89 job registry so status is driven from a single `JobDefinition` table rather than hand-maintained dicts.

## Acceptance criteria

- [x] Failed scheduler job writes failure metadata without advancing `last_*_sync` timestamp
- [x] `GET /api/scheduler/status` exposes failure fields for each registered job type
- [x] Admin/sync overview surfaces at least one failed job or failed account without reading logs
- [x] API reference documents new fields

## Completion

- **PR:** [#22](https://github.com/klopstack/iptv-proxy-v2/pull/22) (`wave4/pr-k-91-scheduler-failure-metadata`)
- **Policy:** On success, `last_error` is cleared; `last_failure_at` is retained until the next failure overwrites it.

## Test plan

- Unit test: mock job returning `False` → failure metadata set, success timestamp unchanged
- Unit test: `get_status()` includes `last_failure_at` / `last_error` after simulated failure
- Unit test: successful run clears or updates failure fields per documented policy

## Dependencies

- [71-fix-scheduler-sync-status-semantics.md](./71-fix-scheduler-sync-status-semantics.md) ✅ (timestamp and account status semantics)
- Optional: [89-refactor-scheduler-job-registry.md](./89-refactor-scheduler-job-registry.md) (cleaner implementation)

## References

- `docs/architecture/scheduler-and-sync-orchestration.md`
- EPG per-source pattern: `EpgSyncProgress`, TODOs 40–44
