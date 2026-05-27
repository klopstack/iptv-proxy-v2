# TODO 42: EPG Bulk Sync Concurrency and `sync_in_progress` Guard

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Medium  

**Related:** [37-sync-lock-hardening.md](./37-sync-lock-hardening.md) (account sync locks), [43-per-source-epg-sync-orchestrator.md](./43-per-source-epg-sync-orchestrator.md)

---

## Problem

### 1. Manual bulk sync ignores in-progress state

`POST /api/sync/epg` loads **all enabled** sources and calls `sync_sources()` with no check for `sync_in_progress`:

```python
# routes/api.py
sources = EpgSource.query.filter_by(enabled=True).order_by(...).all()
EpgSyncOrchestrator(app).sync_sources(sources, parallel=True)
```

`source_needs_sync()` returns `False` when `sync_in_progress` is true, but that helper is **not** used here.

### 2. Overlap with scheduler

- Dedicated `run_scheduler.py` process and/or gunicorn worker may run `_sync_epg_sources_if_due()` concurrently with a user-triggered bulk sync.
- Two threads can sync the same source: duplicate HTTP fetches, DB contention, corrupted progress columns, SQLite lock pressure.

### 3. No EPG equivalent of account sync lock

TODO 37 added atomic `sync_in_progress` for **accounts** with stale recovery. EPG sources have `sync_in_progress` on `epg_sources` but no atomic acquire before sync starts.

---

## Goal

- Prevent double-sync of the same EPG source across scheduler + API + per-source route.
- Manual “Sync all EPG” should skip or queue sources already in progress (document UX).
- Align with account sync hardening patterns where sensible.

---

## Proposed solution

### Option A — Skip in-progress sources (minimal)

In `EpgSyncOrchestrator.sync_sources()`:

```python
sources = [s for s in sources if not s.sync_in_progress]
```

Return skipped count in result payload; UI shows “skipped (in progress)”.

### Option B — Atomic acquire per source (stronger)

Before `_sync_source_in_thread`:

```sql
UPDATE epg_sources SET sync_in_progress=1, sync_started_at=? 
WHERE id=? AND sync_in_progress=0
```

If rowcount 0, skip or return “already syncing”. Mirror `services/sync_service.py` account pattern.

### Option C — Global EPG sync lock (single flight)

One metadata flag `epg_bulk_sync_in_progress` for entire pass. Simpler but blocks per-source manual sync during bulk run.

**Recommended:** **B** per source + skip list in bulk API response.

### Manual API behavior

| Endpoint | Behavior |
|----------|----------|
| `POST /api/sync/epg` | Sync enabled sources not `sync_in_progress`; optional `?force=true` for admins |
| Scheduler `_sync_epg_sources_if_due` | Already filters due; add in-progress skip |
| `POST /api/epg/sources/<id>/sync` | See TODO 43; must participate in same lock |

### Stale EPG `sync_in_progress` recovery

On app startup (alongside account recovery in TODO 37):

- Clear `sync_in_progress` on sources where `sync_started_at` older than N hours (configurable, default 6–12h).
- Log recovered source IDs.

---

## Affected files

| File | Change |
|------|--------|
| `services/epg_sync_orchestrator.py` | Acquire/skip logic |
| `routes/api.py` | Bulk sync filtering / response shape |
| `services/scheduler.py` | Due sync respects locks |
| `app.py` | Startup stale EPG progress recovery (optional) |
| `services/epg_sync_progress.py` | Ensure terminal phases always clear flag |
| `templates/settings.html` | Show skipped sources |

---

## Acceptance criteria

- [x] Starting bulk sync while scheduler is syncing source X does not run two syncs on X.
- [x] `sync_in_progress` cleared on success, error, and stale recovery.
- [x] API response documents skipped-in-progress sources (`sources_skipped`, `skipped` on results).
- [x] Tests: concurrent acquire returns skip; stale recovery clears flag.

---

## Test plan

- Unit: two threads attempt same `source_id`; only one runs `sync_source`.
- API: mock in-progress source excluded from `sync_sources` call list.
- Optional integration with `ThreadPoolExecutor` + mocked slow sync.

```bash
.venv/bin/pytest tests/test_epg_sync_orchestrator.py tests/test_epg_sync_api.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | Atomic lock in `epg_sync_orchestrator.py`; `tests/test_epg_sync_lock.py` |
