# TODO 51: Consolidate Duplicate Bulk EPG Sync API Tests

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Small (test-only)  

**Related:** [24-consolidate-epg-route-tests.md](./24-consolidate-epg-route-tests.md)

---

## Problem

`POST /api/sync/epg` is tested twice with nearly identical structure:

| File | Tests | Unique value |
|------|-------|----------------|
| `tests/test_sync_endpoints.py` | `test_sync_epg_sources`, `test_sync_epg_sources_with_errors` | Disabled source count (3 sources, 2 synced); FCC tests in same class |
| `tests/test_epg_sync_api.py` | `test_post_sync_epg_uses_orchestrator`, `test_post_sync_epg_partial_failure_success_false` | Asserts `parallel=True`; asserts `success: false` on partial failure |

### Duplication symptoms

- Same `@patch("...EpgSyncOrchestrator.sync_sources")` boilerplate twice.
- Same endpoint, same mock return shapes; CI runs both on every suite.
- Future API changes require editing two files (already drifted once on `success` JSON semantics).

### Not duplicate (keep separate)

| File | Scope |
|------|--------|
| `tests/test_epg_sync_api.py` | `GET /api/sync/epg/status`, scheduler integration, migrations |
| `tests/epg/test_sync_routes.py` | Per-source `POST /api/epg/sources/<id>/sync` |
| `tests/test_epg_sync_orchestrator.py` | Service layer, not HTTP |

---

## Goal

Single canonical HTTP test module for bulk EPG sync; `test_sync_endpoints.py` retains only non-EPG sync routes (accounts, FCC).

---

## Proposed solution

### Step 1: Merge into `tests/test_epg_sync_api.py`

Add to `TestEpgSyncApi`:

```python
def test_post_sync_epg_only_enabled_sources(self, ...):
    """From test_sync_endpoints — 2 enabled, 1 disabled."""

def test_post_sync_epg_partial_failure(self, ...):
    """Merged assertions: success false, sources_synced counts, parallel=True."""
```

### Step 2: Remove from `test_sync_endpoints.py`

Delete `test_sync_epg_sources` and `test_sync_epg_sources_with_errors`.

Rename class docstring to “Sync endpoints (accounts, FCC)” if only FCC remains.

### Step 3: Optional shared fixture

```python
# tests/conftest.py or tests/epg_sync_conftest.py
@pytest.fixture
def enabled_epg_sources(db):
    ...
```

### Step 4: Document in module headers

`test_epg_sync_api.py`:

> Canonical tests for `/api/sync/epg` and `/api/sync/epg/status`.

---

## Acceptance criteria

- [x] Exactly one test class/module owns `POST /api/sync/epg` cases.
- [x] All assertions from both old tests preserved (enabled filter, partial failure, parallel flag).
- [x] `pytest tests/test_sync_endpoints.py tests/test_epg_sync_api.py` passes.
- [x] No reduction in line coverage for `routes/api.py` sync_epg handlers.

---

## Test plan

```bash
.venv/bin/pytest tests/test_sync_endpoints.py tests/test_epg_sync_api.py -q --no-cov
rg "sync/epg" tests/  # should hit one primary file
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | tests/test_epg_sync_api.py, tests/test_sync_endpoints.py |
