# PostgreSQL schema creation via Alembic and parity validation

**Status:** ⬜ Open  
**Priority:** P1  
**Track:** Database Migration — Series B (Switchover)

## Problem

Before any data can be migrated, the target PostgreSQL database needs the correct schema. This means:

1. Running `alembic upgrade head` against a fresh PostgreSQL database to generate all ~35 tables with correct column types, constraints, and indexes.
2. Validating that the resulting PostgreSQL schema is semantically equivalent to the SQLite production schema (same tables, columns, FKs, indexes, constraints).
3. Verifying that the application runs correctly against PostgreSQL schema — routes respond, ORM queries work, no dialect errors.

The key risks are dialect differences that SQLAlchemy abstracts for `create_all()` but that may surface differently in the Alembic-generated DDL:

- `INTEGER PRIMARY KEY` → `SERIAL` / `BIGSERIAL` (Alembic handles this via `sa.Integer` with `autoincrement=True`)
- `TEXT`-as-JSON → `JSONB` (must be explicitly specified in Alembic migration for PG columns, or use `db.JSON` which maps to `TEXT` on PG unless overridden)
- `VARCHAR(n)` length constraints (SQLite ignores them; PostgreSQL enforces them)
- Missing `COLLATE` clauses (SQLite defaults to binary; PostgreSQL defaults to locale-aware)
- Index creation syntax differences (`IF NOT EXISTS` is supported in PG 9.5+)
- `UNIQUE` constraints vs `UNIQUE INDEX` (both work; Alembic generates constraints)

## Current state

No PostgreSQL schema exists. The Alembic migration system (TODO 113) must be complete before this item can be worked.

## Proposed solution

### Phase 1 — Generate the Alembic baseline migration with PG-appropriate column types

When the Alembic baseline is generated (TODO 113), it will use the SQLAlchemy model definitions as the source of truth. For PostgreSQL compatibility, review the generated migration for:

- **JSON columns**: Change `sa.Text()` → `sa.JSON()` for the six columns identified in TODO 112. Optionally use `postgresql.JSONB()` for the PG-specific migration.
- **String lengths**: Audit any `VARCHAR(n)` that might be too short for production data. SQLite silently stores strings longer than the declared length; PostgreSQL raises an error. Known risk areas: `display_name` (200 chars), `title` (500 chars), `description` (Text — no limit).
- **Default values**: Ensure Python-callable defaults (`default=lambda: datetime.now(...)`) are expressed in Alembic as `server_default` where possible, or left as application-layer defaults.

### Phase 2 — Create PostgreSQL database and apply Alembic migration

```bash
# Provision PostgreSQL (Docker or managed)
docker compose --profile postgres up -d postgres

# Create database and user (if not created by Docker init)
psql -h localhost -U postgres -c "CREATE USER iptv WITH PASSWORD 'changeme';"
psql -h localhost -U postgres -c "CREATE DATABASE iptv_proxy OWNER iptv;"

# Apply all migrations
DATABASE_URL=postgresql://iptv:changeme@localhost/iptv_proxy flask db upgrade

# Verify alembic_version exists and is at head
DATABASE_URL=postgresql://iptv:changeme@localhost/iptv_proxy alembic current
```

### Phase 3 — Schema parity validation

Compare the PostgreSQL schema against a fully-migrated SQLite database to detect differences:

```python
# scripts/schema_compare.py
from sqlalchemy import create_engine, inspect

sqlite_eng = create_engine("sqlite:///data/iptv_proxy.db")
pg_eng = create_engine("postgresql://iptv:changeme@localhost/iptv_proxy")

sqlite_insp = inspect(sqlite_eng)
pg_insp = inspect(pg_eng)

sqlite_tables = set(sqlite_insp.get_table_names()) - {"schema_migrations"}
pg_tables = set(pg_insp.get_table_names()) - {"alembic_version"}

assert sqlite_tables == pg_tables, f"Table mismatch: {sqlite_tables.symmetric_difference(pg_tables)}"

for table in sorted(sqlite_tables):
    sqlite_cols = {c["name"]: c for c in sqlite_insp.get_columns(table)}
    pg_cols = {c["name"]: c for c in pg_insp.get_columns(table)}
    assert set(sqlite_cols) == set(pg_cols), f"{table}: column mismatch"
    # Check FK count
    sqlite_fks = sqlite_insp.get_foreign_keys(table)
    pg_fks = pg_insp.get_foreign_keys(table)
    assert len(sqlite_fks) == len(pg_fks), f"{table}: FK count mismatch"
```

Known acceptable differences:
- `schema_migrations` (SQLite) vs `alembic_version` (PostgreSQL) — different tracking tables
- Column type representations (`TEXT` in SQLite vs `TEXT` / `VARCHAR(n)` / `JSONB` in PG)
- Default values may differ in representation

### Phase 4 — Smoke-test the application against PostgreSQL

With an empty PostgreSQL database (schema only, no migrated data), run a smoke test sequence:

1. Start the app with `DATABASE_URL=postgresql://...`.
2. Create a test account via POST `/api/accounts`.
3. Verify the account is readable via GET `/api/accounts`.
4. Trigger an EPG sync (or mock it).
5. Verify the dashboard renders (`GET /`).

This confirms SQLAlchemy ORM generates valid PostgreSQL-compatible SQL for the common code paths.

### Phase 5 — Performance baseline

For tables with indexes, verify that PostgreSQL indexes are created and being used:

```sql
-- In psql after schema creation
\d channels      -- verify all expected indexes
EXPLAIN SELECT * FROM channels WHERE account_id = 1 AND is_active = true;
-- Expect: Index Scan, not Seq Scan
```

Document any indexes that are missing from the Alembic migration that exist in the SQLite production schema (possible if they were added via raw SQL in legacy migrations and not reflected in the ORM metadata).

## Acceptance criteria

- [ ] `alembic upgrade head` against fresh PostgreSQL 16 completes without errors
- [ ] `alembic current` shows the latest revision on head
- [ ] `scripts/schema_compare.py` reports zero table/column/FK count mismatches (type differences accepted)
- [ ] App starts successfully with `DATABASE_URL=postgresql://...` and serves `GET /` → 200
- [ ] POST `/api/accounts` creates a row; GET `/api/accounts` returns it
- [ ] All FK constraints are present on PostgreSQL (verified via `information_schema.table_constraints`)
- [ ] All indexes from SQLite schema are present on PostgreSQL (verified via `pg_indexes`)
- [ ] `pytest tests/ -m "not sqlite_only"` passes against the new PostgreSQL schema (empty DB)

## Test plan

```bash
# Schema creation
DATABASE_URL=postgresql://iptv:iptv@localhost/iptv_test flask db upgrade

# Schema comparison
python scripts/schema_compare.py \
  --sqlite sqlite:///data/iptv_proxy.db \
  --pg postgresql://iptv:iptv@localhost/iptv_test

# App smoke test against empty PG schema
DATABASE_URL=postgresql://iptv:iptv@localhost/iptv_test flask run &
curl -s http://localhost:5000/api/accounts   # expect {"data": [], ...}
curl -s -X POST http://localhost:5000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "server": "test.example.com", "username": "u", "password": "p"}'
# Expect: {"success": true, ...}

# Test suite against PG
pytest tests/ -m "not sqlite_only" -x -v
```

## Affected files

- `alembic_migrations/versions/` — baseline migration (from TODO 113), reviewed for PG column types
- `scripts/schema_compare.py` — new validation script
- `scripts/pg_migrate.pgloader` — will reference the PG database created here
- `docs/DEPLOYMENT.md` — PostgreSQL provisioning steps

## Dependencies

- **Blocked by** [TODO 113](./113-pg-prep-alembic-migration-system.md) — Alembic must be in place.
- **Blocked by** [TODO 112](./112-pg-prep-json-column-types.md) — JSON columns must be typed before generating the baseline migration.
- **Enables** [TODO 116](./116-pg-migration-data-export-tooling.md) — data load requires the schema to exist first.
- **Enables** [TODO 118](./118-pg-migration-cutover-procedure.md) — cutover uses this schema as the target.

## Risks

- **`VARCHAR(n)` truncation**: SQLite silently stores `"this is a very long string"` in a `VARCHAR(50)` column. If production data has values longer than the declared column length, PostgreSQL will reject them on INSERT with `value too long for type character varying(50)`. Run `scripts/pg_migration_validate.py` with a length-check mode before cutover.
- **Case-sensitive string comparisons**: PostgreSQL string comparisons are case-sensitive by default (`'ESPN' ≠ 'espn'`). SQLite uses binary comparison too, so behavior should match. However, if any query uses `COLLATE NOCASE` (rare in ORM code), it will fail on PostgreSQL. Search for `COLLATE NOCASE` in the codebase before cutover.
- **`db.Boolean` stored as 0/1 on SQLite**: SQLAlchemy correctly maps `db.Boolean` to `BOOLEAN` on PostgreSQL and handles Python `True`/`False` → PostgreSQL `true`/`false`. No action needed unless the application bypasses the ORM and inserts raw `0`/`1` integers.
- **`DateTime` without timezone**: All `DateTime` columns in the models are timezone-naive (they store UTC without a `+00:00` suffix). PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` is semantically correct here. Do NOT change to `TIMESTAMP WITH TIME ZONE` during this migration unless the application is simultaneously updated to handle timezone-aware datetimes — this is out of scope.
- **Index naming collisions**: Alembic autogenerate uses predictable index names. If any legacy migration created an index with a non-standard name, it may appear as a missing index on the PostgreSQL side. Cross-reference `pg_indexes` against the expected names after `alembic upgrade head`.
