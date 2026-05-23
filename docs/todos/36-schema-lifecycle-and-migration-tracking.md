# TODO 36: Schema Lifecycle and Migration Tracking

**Priority:** P4  
**Status:** ✅ Done  

---

## Solution

- `schema_migrations` table in [`run_migrations.py`](../../run_migrations.py)
- [`migrations/2026_05_21_add_playlist_configs_table.py`](../../migrations/2026_05_21_add_playlist_configs_table.py)
- [`entrypoint.sh`](../../entrypoint.sh) runs `create_all()` then migrations on every boot
- [`tests/test_migrations.py`](../../tests/test_migrations.py)
- [`add_indexes.py`](../../add_indexes.py) deprecated wrapper

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
