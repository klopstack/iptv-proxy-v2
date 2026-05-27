# TODO 41: Fix Global `last_epg_sync` Metadata on Partial or Total Failure

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Small  

**Related:** [40-epg-sync-last-sync-on-failure.md](./40-epg-sync-last-sync-on-failure.md), [48-epg-sync-failure-semantics-tests.md](./48-epg-sync-failure-semantics-tests.md)

---

## Problem

After every orchestrator pass, `SyncMetadata` key `last_epg_sync` is set to “now”, even when zero sources succeed:

```python
# services/epg_sync_orchestrator.py (end of sync_sources)
SyncMetadata.set(SYNC_KEY_LAST_EPG_SYNC, datetime.now(timezone.utc).isoformat())
```

Scheduler status (`GET /api/scheduler/status`) exposes this under `syncs.epg.last_sync`. Operators can see “EPG synced recently” while every per-source row shows `error` and programme data is stale.

### Interaction with scheduler loop

- `_sync_epg_sources_if_due()` only runs when at least one source is due.
- Global metadata does not gate the loop, but **misleading status** hides that the last pass failed.
- Combined with TODO 40, per-source `last_sync` on failure makes both global and per-source timestamps wrong.

---

## Goal

Advance global `last_epg_sync` only when the pass **meaningfully succeeded** (define policy below). Status API should reflect reality.

---

## Proposed solution

### Policy options (pick one)

| Policy | Behavior |
|--------|----------|
| **A — All succeeded** | Set metadata only if `success_count == len(results)` |
| **B — Any succeeded** | Set metadata if `success_count > 0` |
| **C — Never on total failure** | Set only if `success_count > 0`; if partial, set with note in logs |

**Recommended:** **C** — update global timestamp only when `success_count > 0`. Log warning when `success_count == 0`.

```python
if success_count > 0:
    SyncMetadata.set(SYNC_KEY_LAST_EPG_SYNC, datetime.now(timezone.utc).isoformat())
else:
    logger.warning("EPG sync pass: 0/%s sources succeeded; global last_epg_sync not updated", len(results))
```

### Optional enhancements

- Store `last_epg_sync_attempt` vs `last_epg_sync_success` keys in `SyncMetadata` (mirrors TODO 40 optional column).
- Include `sources_synced` / `total_sources` in scheduler `get_status()` EPG block for one-glance health.

---

## Affected files

| File | Change |
|------|--------|
| `services/epg_sync_orchestrator.py` | Conditional `SyncMetadata.set` |
| `services/scheduler.py` | Optional richer `syncs.epg` payload |
| `routes/api.py` | Scheduler status consumers |
| `templates/settings.html` | If global EPG sync time shown |

---

## Acceptance criteria

- [x] All-failed pass does **not** update `SyncMetadata` `last_epg_sync`.
- [x] Pass with ≥1 success updates global metadata (policy C: `success_count > 0`).
- [x] Scheduler/API status matches per-source outcomes after a failed night run.
- [x] Tests in `tests/test_epg_sync_orchestrator.py` (`TestOrchestratorGlobalMetadata`).

---

## Test plan

```python
# tests/test_epg_sync_orchestrator.py (or test_epg_sync_failure_semantics.py)
def test_global_last_epg_sync_not_updated_when_all_fail(...):
    mock sync_source -> all False
    assert SyncMetadata.get("last_epg_sync") is previous_value
```

```bash
.venv/bin/pytest tests/test_epg_sync_orchestrator.py -q --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | Policy C in `epg_sync_orchestrator.py`; `TestOrchestratorGlobalMetadata` |
