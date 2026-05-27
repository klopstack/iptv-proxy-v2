# TODO 50: Fix Stale Scheduler EPG Tests and `run_scheduler` Coverage

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Small  

---

## Problem

### 1. Vacuous scheduler EPG test

`tests/test_scheduler_service.py` patches a **removed** method:

```python
@patch("services.scheduler.SyncScheduler._sync_epg_sources")  # does not exist
def test_trigger_sync_epg(self, mock_sync, scheduler, app):
    assert mock_sync is not None  # always passes
```

Scheduler now uses `_sync_epg_sources_if_due()` and `EpgSyncOrchestrator.sync_sources`.

### 2. No tests for `run_scheduler.py`

Dedicated scheduler process (`entrypoint.sh` → `python run_scheduler.py`) has zero coverage:

- Starts `sync_scheduler` under app context
- Handles SIGTERM/SIGINT
- Respects `DISABLE_SCHEDULER`

### 3. `get_status()["epg_sources"]` not tested on real scheduler

`test_epg_sync_api.py` patches `routes.api._scheduler` with real object but does not assert `due` / snapshot shape deeply. `test_scheduler_service.py::test_get_status_initial` does not assert `epg_sources` key exists.

---

## Goal

Replace false-confidence test with real scheduler EPG behavior tests; add minimal `run_scheduler` smoke test.

---

## Proposed solution

### 1. Replace `test_trigger_sync_epg`

```python
@patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_sources")
def test_sync_epg_sources_if_due_calls_orchestrator(self, mock_sync, scheduler, app):
    with app.app_context():
        # source with last_sync=None → due
        ...
        scheduler._sync_epg_sources_if_due()
        mock_sync.assert_called_once()
```

Add negative case: all sources fresh → `sync_sources` not called.

### 2. Extend `test_get_status_initial`

```python
status = scheduler.get_status()
assert "epg_sources" in status
assert isinstance(status["epg_sources"], list)
```

### 3. `run_scheduler` smoke test

```python
# tests/test_run_scheduler.py
@patch("app.sync_scheduler")
@patch("time.sleep", side_effect=InterruptedError)  # or signal handler
def test_run_scheduler_starts_and_stops(mock_scheduler, ...):
    ...
```

Or subprocess test with `DISABLE_SCHEDULER=true` exits immediately (already in `main()`).

### 4. Delete or repurpose old patch path

Grep for `_sync_epg_sources` across repo; update all references.

```bash
rg "_sync_epg_sources[^_]" tests/
```

---

## Affected files

| File | Change |
|------|--------|
| `tests/test_scheduler_service.py` | Fix EPG tests |
| `tests/test_run_scheduler.py` | **Create** (optional) |
| `tests/test_epg_sync_api.py` | Optional: move scheduler tests here vs scheduler_service |

---

## Acceptance criteria

- [x] No test patches non-existent `_sync_epg_sources`.
- [x] `_sync_epg_sources_if_due` covered with mock orchestrator (positive + negative).
- [x] `get_status()` documents `epg_sources` array contract in test.
- [x] `run_scheduler` main path smoke-tested or explicitly marked `# pragma: no cover` with rationale.

---

## Test plan

```bash
.venv/bin/pytest tests/test_scheduler_service.py tests/test_run_scheduler.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | tests/test_scheduler_service.py, tests/test_run_scheduler.py |
