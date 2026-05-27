# TODO 48: EPG Sync Failure Semantics Tests

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Small  

**Depends on:** [40-epg-sync-last-sync-on-failure.md](./40-epg-sync-last-sync-on-failure.md), [41-epg-sync-global-metadata-on-failure.md](./41-epg-sync-global-metadata-on-failure.md)

---

## Problem

Current EPG sync tests heavily mock `EpgSyncService.sync_source` and do not assert behavior that caused production pain:

| Behavior | Tested today? |
|----------|----------------|
| Failed sync must not advance `last_sync` | No |
| All-failed pass must not update `SyncMetadata.last_epg_sync` | No |
| Partial failure: global metadata policy | No |
| `source_needs_sync` true after failed sync | No |
| `sync_in_progress` cleared on error | Partially (orchestrator error test) |

Without these tests, TODOs 40–41 can regress silently.

---

## Goal

Dedicated test module (or class) encoding failure semantics as contract tests, run in CI with the rest of the EPG suite.

---

## Proposed solution

### New file (recommended)

`tests/test_epg_sync_failure_semantics.py`

### Test cases

```python
class TestUpdateSourceSyncStatusOnFailure:
    def test_failure_does_not_update_last_sync(...)
    def test_failure_sets_error_status_and_message(...)
    def test_failure_clears_sync_in_progress(...)
    def test_success_updates_last_sync(...)

class TestOrchestratorGlobalMetadata:
  @patch EpgSyncService.sync_source
    def test_all_failed_does_not_set_last_epg_sync_metadata(...)
    def test_partial_success_updates_metadata_when_policy_allows(...)

class TestSourceNeedsSyncAfterFailure:
    def test_failed_source_still_due_when_never_synced(...)
    def test_failed_source_not_due_if_interval_not_elapsed_and_last_sync_unchanged(...)
    # After TODO 40 fix: failed run leaves old last_sync → due when interval passed
```

### Fixtures

- Use real `db` + `EpgSource` rows, no HTTP.
- `SyncMetadata` keys cleared per test.

---

## Affected files

| File | Action |
|------|--------|
| `tests/test_epg_sync_failure_semantics.py` | **Create** |
| `tests/test_epg_sync_orchestrator.py` | Move overlapping tests here if duplicated |
| `tests/test_epg_sync_service.py` | Extend `TestUpdateSourceSyncStatus` if kept there instead |

**Avoid duplication:** If failure tests live in `test_epg_sync_failure_semantics.py`, remove redundant assertions from orchestrator tests.

---

## Acceptance criteria

- [x] Tests fail on pre–40/41 code; pass after fixes (implemented after TODO 40–41).
- [x] All cases in table above covered in `tests/test_epg_sync_failure_semantics.py`.
- [x] CI: included in default `pytest tests/` run.

---

## Test plan

```bash
.venv/bin/pytest tests/test_epg_sync_failure_semantics.py -q --no-cov
```

Implement TODO 40 → 41 → run until green.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | `tests/test_epg_sync_failure_semantics.py`; deduped orchestrator + service tests |
