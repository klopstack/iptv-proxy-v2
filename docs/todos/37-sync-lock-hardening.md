# TODO 37: Sync Lock Hardening

**Priority:** P4  
**Status:** ✅ Done  

---

## Solution

- Atomic `UPDATE ... WHERE sync_in_progress=0` in [`services/sync_service.py`](../../services/sync_service.py)
- `sync_started_at` column + migration
- `recover_stale_sync_locks()` on app startup
- Extended [`tests/test_sync_lock.py`](../../tests/test_sync_lock.py)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
