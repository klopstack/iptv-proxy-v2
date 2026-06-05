# Replace bespoke SQLite migration runner with Alembic

**Status:** ✅ Complete (PR #67)  
**Priority:** P1  
**Track:** Database Migration — Series A (Preparation)

## Problem

The project uses a hand-rolled migration system (`run_migrations.py` + `migrations/*.py`) where every migration file opens a raw `sqlite3` connection and executes SQLite-specific DDL. This system is architecturally incompatible with PostgreSQL:

- All 31 migration files use `import sqlite3` and `sqlite3.connect(db_path)`.
- Introspection uses `PRAGMA table_info(...)` and `SELECT name FROM sqlite_master WHERE type='table'` — both SQLite-only.
- DDL uses `INTEGER PRIMARY KEY AUTOINCREMENT` (SQLite dialect), not the portable `SERIAL` / `GENERATED ALWAYS AS IDENTITY` that PostgreSQL expects (though SQLAlchemy abstracts this via `db.Integer, primary_key=True`).
- The `schema_migrations` tracking table is managed by custom Python code rather than a standard tool.
- `_sqlite_fk_repair.py` modifies `sqlite_master` directly — impossible on PostgreSQL.

Alembic is the standard migration tool for SQLAlchemy projects. It supports multiple backends, generates diffs from model metadata, tracks applied revisions in a standard `alembic_version` table, and integrates with Flask-Migrate for CLI access.

## Current state

```
run_migrations.py          # Custom runner (sqlite3-only)
migrations/
  2024_01_add_indexes.py   # sqlite3-based
  ...                      # 30 more sqlite3-based files
  _sqlite_fk_repair.py     # sqlite_master hack
```

No `alembic.ini`, no `migrations/env.py`, no `migrations/versions/` directory exists.

## Proposed solution

### Phase 1 — Install and initialize Alembic alongside the existing system

Add `alembic` and `flask-migrate` to `requirements.txt`. Initialize Alembic in a new directory to avoid clobbering the existing `migrations/` folder:

```bash
# Use a separate directory during transition
flask db init --directory alembic_migrations
# or
alembic init alembic_migrations
```

Configure `alembic_migrations/env.py` to:
- Import the Flask app and `db.metadata` from `models`
- Read `DATABASE_URL` from the environment (same env var the app uses)
- Enable `compare_type=True` and `render_as_batch=True` for SQLite batch-alter support

### Phase 2 — Generate initial "baseline" migration from current model state

The recommended approach for an existing production database is:

1. Create a baseline migration that reflects the **current model state** but marks it as the initial revision.
2. On existing databases that are already fully migrated via the old system, stamp the baseline revision (`alembic stamp head`) without running DDL.
3. On brand-new databases (PostgreSQL), run `alembic upgrade head` to create all tables.

```bash
# Generate baseline from current SQLAlchemy models
alembic revision --autogenerate -m "baseline_from_current_models"
# Review generated file — expect ~35 tables
```

The baseline migration replaces all 31 legacy migration files for new databases. Existing SQLite databases get stamped.

### Phase 3 — Archive legacy migration files

Move `migrations/*.py` and `run_migrations.py` to `migrations/legacy_sqlite/` with a README explaining they are inert historical artifacts that were replaced by Alembic. Keep them for forensic reference but exclude from any automated tooling.

Do NOT delete them until the PostgreSQL migration (TODO 118) has been verified in production — the legacy files are the only documentation of what each schema change did.

### Phase 4 — Update Flask CLI and app startup

Replace the `run_migrations.py` call in Docker entrypoint / startup scripts with `flask db upgrade` (via Flask-Migrate) or `alembic upgrade head`.

Update `app.py` startup hook (if any) that invokes migration runner.

Add `flask db` commands to `DEVELOPER_GUIDE.md` and `DEPLOYMENT.md`.

### Phase 5 — Handle `schema_migrations` vs `alembic_version` coexistence

Production databases will have both `schema_migrations` (legacy) and `alembic_version` (new) tables. The legacy table should be left in place to avoid confusion; document that it is superseded. Add a comment in `alembic_migrations/env.py` noting the legacy table exists for historical tracking only.

### Phase 6 — Migrate `render_as_batch` mode for SQLite ALTER TABLE

SQLite does not support `ALTER TABLE ... DROP COLUMN` or `ALTER TABLE ... ALTER COLUMN TYPE` natively. Alembic's `render_as_batch=True` (in `env.py`) enables the batch migration strategy (table-copy-and-rename) for SQLite compatibility. Ensure this is set for the SQLite codepath and disabled/unset for PostgreSQL.

## Acceptance criteria

- [ ] `alembic.ini` and `alembic_migrations/` directory exist and are committed
- [ ] `alembic upgrade head` from a fresh database creates all ~35 tables with correct schema (tested on SQLite)
- [ ] Existing SQLite production database can be stamped with `alembic stamp head` without DDL errors
- [ ] `alembic revision --autogenerate` after stamping produces an empty migration (model and DB match)
- [ ] Legacy `migrations/` files moved to `migrations/legacy_sqlite/` with explanatory README
- [ ] `run_migrations.py` replaced by `flask db upgrade` in Docker entrypoint and startup documentation
- [ ] CI passes with Alembic-based setup (SQLite path)
- [ ] `flask db upgrade` and `flask db downgrade` are documented in `DEVELOPER_GUIDE.md`

## Test plan

```bash
# Verify Alembic upgrade creates correct schema on fresh SQLite
rm -f /tmp/test_alembic.db
DATABASE_URL=sqlite:////tmp/test_alembic.db flask db upgrade
DATABASE_URL=sqlite:////tmp/test_alembic.db python -c "
from sqlalchemy import create_engine, inspect
eng = create_engine('sqlite:////tmp/test_alembic.db')
tables = inspect(eng).get_table_names()
assert 'accounts' in tables
assert 'channels' in tables
assert 'alembic_version' in tables
print('OK:', sorted(tables))
"

# Verify autogenerate produces empty diff after stamping
DATABASE_URL=sqlite:////tmp/test_alembic.db alembic revision --autogenerate -m "verify_empty"
# Review generated file — should contain no ops

# Full test suite still passes
pytest tests/ -x
```

## Affected files

- `requirements.txt` — add `alembic`, `flask-migrate`
- `alembic.ini` — new (Alembic config)
- `alembic_migrations/` — new directory with `env.py`, `script.py.mako`, `versions/`
- `run_migrations.py` — archived to `migrations/legacy_sqlite/`
- `migrations/` (all files) — moved to `migrations/legacy_sqlite/`
- `Dockerfile` / entrypoint script — update startup command
- `DEVELOPER_GUIDE.md`, `DEPLOYMENT.md` — update migration instructions
- `tests/test_migrations.py` — extend to test Alembic path; port dialect-agnostic assertions

## Dependencies

- **Depends on** [TODO 111](./111-pg-prep-raw-sqlite3-audit.md) — `fcc_pattern_reset.py` must not call into legacy migration files before they are archived.
- **Should follow** [TODO 112](./112-pg-prep-json-column-types.md) — model column types should be finalized before the baseline Alembic migration is generated (avoids an immediate follow-up migration to change column types).
- **Enables** all of Series B (TODOs 116–120) — PostgreSQL cannot be targeted until a standard migration tool is in place.

## Risks

- **`render_as_batch` vs native PostgreSQL**: Alembic's batch mode is a SQLite workaround. PostgreSQL supports `ALTER TABLE` natively, so batch mode must be disabled for PG autogenerate and `env.py` must branch on dialect. Test on both.
- **Baseline migration completeness**: `--autogenerate` depends on the SQLAlchemy model metadata matching reality. If any table was added via raw `sqlite3` DDL outside the ORM (e.g., in some migration file), it may not appear in `db.metadata` and will be omitted from the baseline. Run `alembic check` against a migrated SQLite DB before stamping production.
- **`schema_migrations` table**: Alembic's introspection ignores unknown tables, but `--autogenerate` will want to create a `alembic_version` table that may not exist yet. Stamp with `alembic stamp head` on existing databases before running `alembic upgrade`.
- **30+ migration files to replace**: The baseline approach means new installs skip all legacy file execution. Verify the baseline migration produces the same schema as a fully-migrated legacy database by comparing `PRAGMA table_info` / `information_schema` outputs.
- **Sorting/ordering**: The existing custom runner discovers files alphabetically. Two legacy files share the `2024_12_` prefix causing ordering ambiguity. Verify the alphabetical sort (which the legacy runner also uses) applied the correct DDL order when generating the baseline.
