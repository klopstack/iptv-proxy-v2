# TODO 35: Referential Integrity and Account Delete

**Priority:** P4  
**Status:** ✅ Done  
**Estimated scope:** Medium

---

## Problem

SQLite foreign keys were not enforced. Account delete assumed ORM cascade but only `filters` and `credentials` had relationship cascade.

---

## Solution

- `PRAGMA foreign_keys=ON` in [`app.py`](../../app.py)
- [`services/account_delete_service.py`](../../services/account_delete_service.py) explicit deletion order
- Model FKs aligned with `ondelete="CASCADE"` where migrations specify it
- Tests in [`tests/test_account_delete_service.py`](../../tests/test_account_delete_service.py)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| Notes | Global tags, events, rulesets preserved on account delete |
