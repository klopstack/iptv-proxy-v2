# Audit and remove raw `sqlite3` usage in services and migrations

**Status:** ✅ Complete (PR #65)  
**Priority:** P1  
**Track:** Database Migration — Series A (Preparation)

## Problem

The codebase has two classes of raw `sqlite3` usage that are completely opaque to SQLAlchemy and PostgreSQL:

1. **`services/fcc_pattern_reset.py`** — `reset_fcc_patterns_to_defaults()` opens a raw `sqlite3.connect(db_path)` connection to `DROP TABLE IF EXISTS` on the four FCC tables. The helper `sqlite_path_from_database_url()` returns `None` for any non-`sqlite:///` URL, meaning the reset operation silently does nothing (or errors) on PostgreSQL.

2. **`migrations/` (31 files) and `run_migrations.py`** — Every migration file imports `sqlite3` and calls `sqlite3.connect(db_path)` directly. They use SQLite-specific introspection (`SELECT name FROM sqlite_master`, `PRAGMA table_info(...)`) and DDL (`INTEGER PRIMARY KEY AUTOINCREMENT`, `INSERT OR IGNORE`). The `_sqlite_fk_repair.py` module directly writes to `sqlite_master` via `PRAGMA writable_schema=ON`, which is a SQLite-only operation with no PostgreSQL equivalent. This migration system cannot run against PostgreSQL at all.

Until these are replaced, no other migration step is possible.

## Current state

| File | sqlite3 usage | Blocker for PG |
|------|---------------|----------------|
| `services/fcc_pattern_reset.py` | `sqlite3.connect`, `DROP TABLE` via cursor, `sqlite_path_from_database_url()` | Hard — fails silently |
| `run_migrations.py` | `sqlite3.connect`, `PRAGMA foreign_keys`, `INSERT OR IGNORE`, `sqlite_master` | Hard — runner is SQLite-only |
| `migrations/2024_01_add_indexes.py` | `sqlite3.connect`, `sqlite_master` index introspection | Hard |
| `migrations/2024_03_add_channels_categories.py` | `sqlite3.connect`, `INTEGER PRIMARY KEY AUTOINCREMENT` | Hard |
| `migrations/2024_04_add_channel_tag_updated_at.py` | `PRAGMA table_info(channel_tags)`, `AUTOINCREMENT` | Hard |
| `migrations/2024_05_*` through `migrations/2026_06_*` (~28 more files) | Same patterns throughout | Hard |
| `migrations/_sqlite_fk_repair.py` | `PRAGMA writable_schema=ON`, `UPDATE sqlite_master` | Impossible on PG |
| `tests/test_migrations.py` | `sqlite3.connect`, `PRAGMA foreign_key_check`, `sqlite_master` | Breaks with PG test target |

`_sqlite_fk_repair.py` was written specifically to handle a SQLite table-rename quirk. It has no equivalent on PostgreSQL (which handles FK references on `ALTER TABLE RENAME` correctly).

## Proposed solution

This TODO covers the **service-layer** raw sqlite3 removal only. The migration system replacement is tracked separately in [TODO 113](./113-pg-prep-alembic-migration-system.md) since it requires a larger architectural change.

### 1 — Replace `fcc_pattern_reset.py` with SQLAlchemy operations

`reset_fcc_patterns_to_defaults()` currently:
1. Deletes rows via ORM (already dialect-agnostic).
2. Opens a raw `sqlite3` connection to drop the tables (`DROP TABLE IF EXISTS`).
3. Dynamically loads and re-runs the seed migration (which is also sqlite3-only).

Replace step 2 with SQLAlchemy `text("DROP TABLE IF EXISTS ...")` via `db.session.execute()` inside an app context. The `IF EXISTS` clause is standard SQL supported by both SQLite and PostgreSQL.

Replace step 3 with a direct call to the ORM-based seed loader that will be written as part of TODO 113's Alembic data-seed strategy, or extract the seed data from the migration into a standalone Python dict that `reset_fcc_patterns_to_defaults()` re-inserts via the ORM.

Remove `sqlite_path_from_database_url()` entirely; the function only exists to bridge from a `DATABASE_URL` to a filesystem path for `sqlite3.connect()`.

### 2 — Remove `_sqlite_fk_repair.py` usages

`migrations/2026_05_30_fix_stale_foreign_key_references.py` is the only consumer of `_sqlite_fk_repair.py`. This migration exists to fix a one-time SQLite schema corruption from a previous table-rebuild migration. It is a no-op on any database that was not affected by that exact issue. On PostgreSQL it must be replaced by a no-op stub or removed from the migration sequence.

When the migration system is replaced with Alembic (TODO 113), this migration will not be ported forward (it is a historical SQLite repair).

### 3 — Update `test_migrations.py` SQLite-specific assertions

`test_migrations.py` uses `sqlite3.connect()` and `PRAGMA` queries to verify migration results. Tag these assertions with `@pytest.mark.sqlite_only` (or equivalent skip markers) so they are not attempted against a PostgreSQL test target. The PostgreSQL-compatible assertions (table existence, column presence) should be expressed via SQLAlchemy reflection (`inspect(engine).get_table_names()`, `inspect(engine).get_columns(table)`).

## Acceptance criteria

- [ ] `services/fcc_pattern_reset.py` contains zero `import sqlite3` statements
- [ ] `sqlite_path_from_database_url()` is deleted (or unreachable dead code)
- [ ] `reset_fcc_patterns_to_defaults()` works correctly when `DATABASE_URL` is a PostgreSQL URL (manual smoke test or integration test with Docker PG)
- [ ] `_sqlite_fk_repair.py` is either deleted or marked clearly as SQLite-only legacy (not imported from any production code path)
- [ ] `tests/test_migrations.py` SQLite-specific assertions are gated so the test suite does not fail when run against PostgreSQL
- [ ] Existing FCC pattern reset tests still pass against SQLite (no regression)

## Test plan

```bash
# Regression: FCC reset still works on SQLite
pytest tests/ -k fcc_pattern_reset -v

# Migration runner still passes (SQLite)
pytest tests/test_migrations.py -v

# Manual: start app with PostgreSQL DATABASE_URL, call fcc_pattern_reset CLI
# Expect: no sqlite3 import errors, clean success path
```

## Affected files

- `services/fcc_pattern_reset.py` — remove sqlite3 import, remove `sqlite_path_from_database_url`, rewrite step 2 of reset
- `migrations/_sqlite_fk_repair.py` — remove or archive
- `migrations/2026_05_30_fix_stale_foreign_key_references.py` — remove import of `_sqlite_fk_repair`, make no-op for non-SQLite
- `tests/test_migrations.py` — gate SQLite-specific PRAGMA/sqlite_master assertions
- Any route or CLI that currently calls `reset_fcc_patterns_to_defaults(db_path)` with a raw path

## Dependencies

- Must be complete before [TODO 113](./113-pg-prep-alembic-migration-system.md) (Alembic migration system).
- Pairs with [TODO 112](./112-pg-prep-json-column-types.md) (can be done in parallel).
- No dependency on Docker or CI changes.

## Risks

- **FCC seed data**: If the seed migration is still the source of truth for FCC default patterns, extracting it into a standalone seed dict requires care to avoid drift. Consider a single `services/fcc_seed_data.py` module that both the seed migration and the reset service import.
- **`DROP TABLE` in ORM session**: Using `db.session.execute(text(...))` for DDL inside a transactional session can behave differently on PostgreSQL (DDL is transactional) vs SQLite. Wrap in `db.engine.connect()` with `connection.execution_options(autocommit=True)` or use `with db.engine.begin() as conn:` to be explicit.
