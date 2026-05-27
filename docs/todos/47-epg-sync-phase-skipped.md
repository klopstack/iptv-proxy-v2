# TODO 47: Implement or Remove `PHASE_SKIPPED` for EPG Sync

**Priority:** P3  
**Status:** ✅ Done  
**Estimated scope:** Small  

---

## Problem

`services/epg_sync_progress.py` defines:

```python
PHASE_SKIPPED = "skipped"
TERMINAL_PHASES = {PHASE_IDLE, PHASE_COMPLETE, PHASE_ERROR, PHASE_SKIPPED}
```

Nothing in the codebase sets `PHASE_SKIPPED`. Orchestrator and API never return skipped sources in a structured way (see TODO 42 proposed `skipped` count).

### Risk

- Dead constant confuses readers and UI phase switches.
- TODO 42 may introduce skip behavior without a consistent phase name.

---

## Goal

Either **use** `skipped` for intentional non-runs or **remove** it and use `idle` + response metadata only.

---

## Proposed solution

### Option A — Implement (recommended if TODO 42 ships)

When a source is skipped (`sync_in_progress`, disabled, or not due on optional forced bulk):

```python
EpgSyncProgress.set_phase(source_id, PHASE_SKIPPED, message="Already syncing")
```

Ensure `sync_in_progress` is false in terminal skipped state.

Bulk API result:

```json
{"source_id": 3, "success": true, "skipped": true, "message": "In progress elsewhere"}
```

Settings UI: grey badge “skipped”.

### Option B — Remove

- Delete `PHASE_SKIPPED` from constants and `TERMINAL_PHASES`.
- Document skips only in orchestrator `results[]` without DB phase.

---

## Affected files

| File | Change |
|------|--------|
| `services/epg_sync_progress.py` | Keep or remove constant |
| `services/epg_sync_orchestrator.py` | Set phase on skip |
| `templates/settings.html` | Badge for `skipped` |
| `tests/test_epg_sync_progress.py` | Terminal phase test for skipped |

---

## Acceptance criteria

- [ ] No unused `PHASE_*` constants remain without callers.
- [ ] Skipped sources do not appear as `error` or `complete`.
- [ ] Documented in API response schema if implemented.

---

## Test plan

```python
def test_set_phase_skipped_clears_in_progress(app, epg_source):
    EpgSyncProgress.set_phase(epg_source.id, PHASE_SKIPPED, message="busy")
    assert refreshed.sync_in_progress is False
    assert refreshed.sync_phase == PHASE_SKIPPED
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | |
| PR / commit | |
