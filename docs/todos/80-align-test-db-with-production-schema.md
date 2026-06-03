# Align test database with production schema

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Production boot: `create_all()` → `run_migrations()` (`entrypoint.sh`). Default pytest fixture (`tests/conftest.py`) uses **`create_all()` only** — most tests never run migrations.

**Concrete gap:** Composite index `ix_channel_ppv_queue` exists only via migration `2026_05_31_add_ppv_enrichment_queue_index.py`, not in `Channel.__table_args__`. Orchestrator hot path filters/orders on these columns; tests pass without the index.

**Related:** `run_migrations()` returns success if DB file does not exist (skips all migrations). `flask init-db` runs only `create_all()`.

**README drift:** P4 TODO docs 35–39 marked ✅ but files are missing from `docs/todos/`.

## Affected files

- `tests/conftest.py`
- `models/channel.py` — add index to model OR run migrations in fixture
- `migrations/2026_05_31_add_ppv_enrichment_queue_index.py`
- `tests/test_schema_parity.py`, `tests/test_migrations.py`
- `run_migrations.py`, `docs/todos/README.md`

## Proposed solution

**Option A:** Add `ix_channel_ppv_queue` to `Channel.__table_args__` so `create_all()` matches production.

**Option B:** Run `run_migrations()` in pytest `app` fixture (slower but complete).

**Also:**
1. Expand `test_schema_parity.py`: index inventory, FK spot checks
2. Restore or remove broken README links for TODOs 35–39
3. Document `init-db` must be followed by migrations in DEVELOPER_GUIDE

## Acceptance criteria

- [ ] Default test DB has same indexes as post-migration production DB
- [ ] Schema parity test covers PPV queue index
- [ ] README links resolve or are marked archived

## Test plan

- `test_schema_parity.py` asserts `ix_channel_ppv_queue` exists
- Full suite still passes with chosen fixture approach

## Dependencies

- See `docs/architecture/schema-lifecycle-and-test-parity.md`
