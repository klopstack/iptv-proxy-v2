# TODO 40: Do Not Advance `last_sync` on Failed EPG Source Sync

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Small  

**Related:** [41-epg-sync-global-metadata-on-failure.md](./41-epg-sync-global-metadata-on-failure.md), [48-epg-sync-failure-semantics-tests.md](./48-epg-sync-failure-semantics-tests.md)

---

## Problem

`EpgSyncService.update_source_sync_status()` always sets `source.last_sync` to the current time, regardless of whether the sync succeeded:

```python
# services/epg_sync_service.py (current)
source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
source.last_sync_status = "success" if success else "error"
```

`source_needs_sync()` in `services/epg_sync_orchestrator.py` uses `last_sync` plus `epg_interval_hours` to decide if a source is due. After a **failed** sync, the source appears “recently synced” and will not be retried until the full interval elapses.

### Symptoms

- Scheduler skips failed large sources (e.g. EPGShare) for 12+ hours even though data was not updated.
- Settings UI shows a recent `last_sync` timestamp next to `last_sync_status: error`, which is misleading.
- Same pattern may have existed before the orchestrator, but parallel sync and progress UI make the failure mode more visible.

### Affected files

| File | Role |
|------|------|
| `services/epg_sync_service.py` | `update_source_sync_status()` |
| `services/epg_sync_orchestrator.py` | `source_needs_sync()`, calls `update_source_sync_status` |
| `routes/epg/sources.py` | Per-source sync also calls `update_source_sync_status` |
| `templates/settings.html` | Displays `last_sync` / status |

---

## Goal

Only advance `last_sync` when a sync **successfully** completes (channels/programmes committed as intended). Failed runs should update `last_sync_status` / `last_sync_message` without pushing `last_sync` forward.

---

## Proposed solution

### 1. Change `update_source_sync_status`

```python
if success:
    source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
    source.sync_in_progress = False
    if stats:
        source.channel_count = stats.get("channels_added", 0) + stats.get("channels_updated", 0)
else:
    source.sync_in_progress = False  # always clear on terminal failure
    # do NOT touch last_sync
```

Ensure orchestrator error paths (`PHASE_ERROR`, exception handler) also clear `sync_in_progress` consistently (or rely solely on `EpgSyncProgress` terminal phases).

### 2. Audit callers

| Caller | Action |
|--------|--------|
| `EpgSyncOrchestrator._sync_source_in_thread` | No change if `update_source_sync_status` is fixed |
| `routes/epg/sources.py` `sync_epg_source` | Same |
| Any manual `last_sync = now` elsewhere | Grep and align |

### 3. Optional: `last_attempt_at` column

If product wants “last tried” separate from “last success”, add a nullable `last_sync_attempt_at` in a follow-up migration. **Out of scope** unless UI needs both timestamps; document in [44](./44-epg-sources-page-progress-ui.md) if added.

---

## Acceptance criteria

- [x] Failed sync leaves `last_sync` unchanged (null or previous success time).
- [x] Successful sync updates `last_sync` as today.
- [x] `source_needs_sync()` returns `True` for sources that failed on the previous run (assuming interval elapsed or never synced).
- [x] Per-source and bulk orchestrator paths behave the same.
- [x] Existing successful-sync tests still pass; new failure-semantics tests in TODO 48.

---

## Test plan

1. Unit test `update_source_sync_status` failure path: assert `last_sync` unchanged.
2. Orchestrator test: mock `sync_source` returning `(False, ...)`, assert DB `last_sync` unchanged and `source_needs_sync` still true (or due after interval logic).
3. Regression: success path still sets `last_sync`.

```bash
.venv/bin/pytest tests/test_epg_sync_service.py tests/test_epg_sync_orchestrator.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | |
