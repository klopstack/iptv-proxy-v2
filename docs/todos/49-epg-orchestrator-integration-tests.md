# TODO 49: EPG Orchestrator Integration Test Coverage

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Medium  

**Related:** [43-per-source-epg-sync-orchestrator.md](./43-per-source-epg-sync-orchestrator.md), `tests/test_epg_sync_programs_streaming.py`

---

## Problem

`tests/test_epg_sync_orchestrator.py` patches `EpgSyncService.sync_source` everywhere. That validates threading, progress persistence, and result aggregation but **not**:

- Progress callback wiring through real `sync_xmltv_url_source` → `sync_programs_for_source`
- `update_source_sync_status` + `EpgSyncProgress` interaction on real code paths
- Small XMLTV fixture end-to-end through orchestrator (1 source, sequential)

### Gaps vs production

| Scenario | Coverage |
|----------|----------|
| Mocked orchestrator unit tests | ✅ Extensive |
| Real service + mocked HTTP/XML | ❌ |
| Per-source route + progress columns | ❌ (TODO 43) |
| `sync_due_sources` vs scheduler duplicate filter | ❌ |
| `get_status()["epg_sources"]` with real scheduler | ❌ (only API smoke test) |

---

## Goal

A thin **integration** layer: orchestrator + real `EpgSyncService` + mocked network/disk, proving progress columns and stats without hitting external URLs.

---

## Proposed solution

### File

`tests/test_epg_sync_integration.py` (or `tests/epg/test_sync_integration.py`)

### Pattern

```python
@patch("requests.get")
@patch("services.epg_sync_service.save_to_cache")
def test_orchestrator_xmltv_url_sets_progress_phases(mock_cache, mock_get, app, db):
    mock_get.return_value.content = SMALL_XMLTV_FIXTURE
    mock_get.return_value.raise_for_status = lambda: None
    source = _create_xmltv_source(db)
    result = EpgSyncOrchestrator(app).sync_sources([source], parallel=False)
    assert result["sources_synced"] == 1
    refreshed = db.session.get(EpgSource, source.id)
    assert refreshed.sync_phase == "complete"
    assert json.loads(refreshed.sync_progress)["programs_added"] >= 0
```

### Cases to include

1. **XMLTV URL happy path** — mocked `requests.get`, real parse + program sync.
2. **Provider happy path** — mock `IPTVService.get_xmltv`.
3. **Orchestrator error** — mock raises; assert `sync_phase == error` and DB state.
4. **`list_status` / `due` flag** — with `source_needs_sync` after success vs failure (pairs with TODO 48).
5. **Scheduler `get_status().epg_sources`** — real `SyncScheduler.get_status()` in app context, no mock orchestrator.

### Out of scope

- Multi-worker ThreadPoolExecutor stress tests (keep mocked in unit file).
- Live EPGShare-scale files (use existing streaming unit tests).

---

## Affected files

| File | Action |
|------|--------|
| `tests/test_epg_sync_integration.py` | Create |
| `tests/test_epg_sync_orchestrator.py` | Keep unit tests; link to integration file in module docstring |
| `tests/conftest.py` | Shared small XMLTV bytes fixture if not already in `test_epg_programs.py` |

---

## Acceptance criteria

- [x] At least one test runs orchestrator without patching `sync_source`.
- [x] Progress phases observed in DB for that test.
- [x] Runtime < 5s for integration module (keep fixtures small).
- [x] Documented in `tests/test_epg_sync_orchestrator.py` header: “see test_epg_sync_integration.py for e2e”.

---

## Test plan

```bash
.venv/bin/pytest tests/test_epg_sync_integration.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | tests/test_epg_sync_integration.py |
