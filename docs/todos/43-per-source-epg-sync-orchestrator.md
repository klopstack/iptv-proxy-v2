# TODO 43: Route Per-Source EPG Sync Through Orchestrator / Progress

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Medium  

**Related:** [42-epg-bulk-sync-concurrency-guard.md](./42-epg-bulk-sync-concurrency-guard.md), [44-epg-sources-page-progress-ui.md](./44-epg-sources-page-progress-ui.md)

---

## Problem

Bulk sync and scheduler use `EpgSyncOrchestrator`, which drives `EpgSyncProgress` (`sync_phase`, `sync_progress`, `sync_in_progress`).

Per-source sync bypasses this stack:

```python
# routes/epg/sources.py — POST /api/epg/sources/<id>/sync
success, message, stats = EpgSyncService.sync_source(source)
EpgSyncService.update_source_sync_status(source, success, message, stats)
```

### Symptoms

- User syncs one source from **EPG Sources** page; **Settings** progress table stays idle.
- `sync_phase` / `sync_progress` JSON never update for that run.
- Progress polling (`/api/sync/epg/status`) is useless for the most common per-source action.
- Duplicate status update logic (orchestrator already calls `update_source_sync_status`).

Existing route tests in `tests/epg/test_sync_routes.py` mock `EpgSyncService` directly and will need updating.

---

## Goal

Single code path for all EPG sync entry points: orchestrator thread helper or thin wrapper that sets progress + invokes `EpgSyncService.sync_source` with callback.

---

## Proposed solution

### 1. Orchestrator method for single source

```python
def sync_source_by_id(self, source_id: int, *, parallel: bool = False) -> Dict[str, Any]:
    with self.app.app_context():
        source = db.session.get(EpgSource, source_id)
        if not source:
            return {"success": False, "message": "Source not found", ...}
        return self.sync_sources([source], parallel=False)["results"][0]
```

Or call `_sync_source_in_thread(source_id)` directly after acquire lock (TODO 42).

### 2. Update route

```python
from services.epg_sync_orchestrator import EpgSyncOrchestrator
result = EpgSyncOrchestrator(current_app._get_current_object()).sync_source_by_id(source_id)
# map result to existing JSON shape
```

### 3. Deprecate duplicate `update_source_sync_status` in route

Orchestrator already invokes it inside `_sync_source_in_thread`; route should not call twice.

### 4. HTTP semantics

- Return **202** if sync is async in future; today sync is synchronous — keep **200/400** with full result.
- If source skipped due to `sync_in_progress`, return **409** with clear message.

---

## Affected files

| File | Change |
|------|--------|
| `routes/epg/sources.py` | Use orchestrator |
| `services/epg_sync_orchestrator.py` | `sync_source_by_id` (if added) |
| `tests/epg/test_sync_routes.py` | Patch orchestrator; assert progress columns |
| `tests/test_epg_sync_api.py` | Optional route-level test |

---

## Acceptance criteria

- [x] `POST /api/epg/sources/<id>/sync` updates `sync_phase` / `sync_progress` during run.
- [x] Settings progress UI reflects per-source page sync (via `/api/sync/epg/status`).
- [x] No double `update_source_sync_status` commit.
- [x] 404/400 behavior unchanged for missing/disabled sources.
- [x] Participates in TODO 42 lock semantics (409 when in progress; `?force=true` supported).

---

## Test plan

```python
@patch("services.epg_sync_orchestrator.EpgSyncService.sync_source")
def test_per_source_sync_sets_progress(mock_sync, app, client, test_epg_source):
    def sync_with_progress(source, progress=None):
        if progress:
            progress("fetching", message="test")
        return True, "ok", {}
    ...
    response = client.post(f"/api/epg/sources/{id}/sync")
    source = db.session.get(EpgSource, id)
    assert source.sync_phase in ("complete", "fetching", ...)
```

```bash
.venv/bin/pytest tests/epg/test_sync_routes.py tests/test_epg_sync_orchestrator.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | `sync_source_by_id`; route uses orchestrator; tests in `test_sync_routes.py` |
