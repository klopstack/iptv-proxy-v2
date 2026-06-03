# Data migration tooling: SQLite → PostgreSQL export and import

**Status:** ⬜ Open  
**Priority:** P1  
**Track:** Database Migration — Series B (Switchover)

## Problem

Moving from SQLite to PostgreSQL requires transferring all existing data. The SQLite file cannot be handed to PostgreSQL directly. The migration must handle:

- **Type coercions**: SQLite stores `BOOLEAN` as 0/1 integers; PostgreSQL expects `true`/`false`. SQLite `DATETIME` is stored as ISO-8601 strings (without timezone); PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` accepts them but timezone-aware columns (`TIMESTAMP WITH TIME ZONE`) require explicit UTC tagging.
- **`TEXT`-as-JSON columns**: Under the new schema (after TODO 112), these will be `db.JSON`. If the PostgreSQL schema uses `JSONB`, the import tool must validate JSON before insertion or PostgreSQL will reject malformed values.
- **Sequences / auto-increment**: PostgreSQL uses sequences (`SERIAL` or `GENERATED ALWAYS AS IDENTITY`) for auto-increment PKs. After bulk-loading rows, sequences must be reset to `max(id) + 1` or the first `INSERT` after import will collide.
- **Scale**: The largest tables (`epg_programs`, `epg_channels`, `fcc_facilities`) can have hundreds of thousands of rows. The tool must handle bulk loading efficiently.
- **Referential integrity during load**: FK constraints on PostgreSQL are enforced in real time unless deferred. The load order must respect FK dependency order, or FK checks must be deferred during import.

## Current state

No data migration tooling exists. The codebase is SQLite-only.

## Proposed solution

Two approaches should be evaluated and one chosen based on data size and operational comfort:

### Option A — pgloader (recommended for large datasets)

[pgloader](https://pgloader.io/) is a purpose-built tool for migrating SQLite databases to PostgreSQL. It handles type coercions automatically and streams data via PostgreSQL's `COPY` protocol for bulk efficiency.

Basic pgloader command file:

```
LOAD DATABASE
     FROM sqlite:///app/data/iptv_proxy.db
     INTO postgresql://iptv:changeme@localhost/iptv_proxy

WITH include drop, create tables, create indexes, reset sequences

SET work_mem to '128 MB', maintenance_work_mem to '512 MB'

CAST
  type integer when (= 0 precision) to boolean using integer-to-boolean,
  column epg_programs.categories to jsonb using remove-null-blanks,
  column epg_sources.sync_progress to jsonb using remove-null-blanks,
  column epg_channels.display_names_json to jsonb using remove-null-blanks,
  column epg_channels.matched_channels_json to jsonb using remove-null-blanks

EXCLUDING TABLE NAMES MATCHING 'schema_migrations'
;
```

pgloader advantages:
- Handles SQLite `NULL` / `""` → PostgreSQL `NULL` semantics
- Resets sequences automatically (`reset sequences`)
- Streams data — does not require loading entire dataset into memory
- Can be run as a dry-run (`--dry-run`) for pre-flight validation

pgloader risk: The `CAST` rules for `boolean` columns must be verified against every `db.Boolean` column in the schema (currently stored as 0/1 in SQLite). Listing all boolean columns explicitly in the cast rules is safer than relying on the `type integer when (= 0 precision) to boolean` heuristic, which can misfire on non-boolean integer columns.

### Option B — SQLAlchemy-based Python dump/load script

A Python script that:
1. Reads all rows from SQLite via SQLAlchemy ORM (or Core `select *`).
2. Writes them to PostgreSQL via bulk `INSERT` statements (using `executemany` or `insert().values()`).
3. Resets PostgreSQL sequences after each table.

```python
# Pseudocode
from sqlalchemy import create_engine, MetaData, Table, select, insert, text

src = create_engine("sqlite:///data/iptv_proxy.db")
dst = create_engine("postgresql://iptv:changeme@localhost/iptv_proxy")

metadata = MetaData()
metadata.reflect(src)

LOAD_ORDER = [  # FK dependency order
    "accounts", "credentials", "categories", "channels", "tags",
    "channel_tags", "epg_sources", "epg_channels", "epg_programs",
    ...
]

with dst.begin() as conn:
    conn.execute(text("SET session_replication_role = 'replica'"))  # disable FK checks
    for table_name in LOAD_ORDER:
        table = metadata.tables[table_name]
        rows = src.execute(select(table)).fetchall()
        if rows:
            conn.execute(insert(table), [dict(r) for r in rows])
    conn.execute(text("SET session_replication_role = 'origin'"))  # re-enable FKs

# Reset sequences
with dst.begin() as conn:
    for table_name in LOAD_ORDER:
        conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE(MAX(id), 1)) FROM {table_name}"))
```

Python script advantages:
- Full control over type coercions in Python
- Easier to add validation logic (e.g., check JSON validity before insert)
- No external tool dependency

Python script disadvantages:
- Slower for large tables (does not use `COPY` protocol)
- Must handle `NULL` / empty string differences manually
- Must handle `db.Boolean` 0/1 → Python `bool` → PostgreSQL coercion

### Recommended approach

Use **pgloader** for the initial migration (speed, reliability, automatic sequence reset) with a Python validation script to compare row counts and spot-check values afterwards. The Python dump/load approach is a useful fallback if pgloader is not available in the target environment.

### Validation script

After migration, a validation script should:
1. Count rows in every table in both SQLite and PostgreSQL — counts must match.
2. Sample 100 random rows from large tables and compare field values.
3. Check that all PostgreSQL sequences are > `max(id)` for each table.
4. Run `SELECT 1` from every FK-constrained column to verify FK integrity.

```bash
python scripts/pg_migration_validate.py \
  --src sqlite:///data/iptv_proxy.db \
  --dst postgresql://iptv:changeme@localhost/iptv_proxy
```

## Acceptance criteria

- [ ] `scripts/pg_migration_validate.py` exists and can be run against SQLite source + PostgreSQL destination
- [ ] Validation script checks: row counts match per table; no FK violations; sequences reset correctly
- [ ] `scripts/pg_migrate.pgloader` (or equivalent) exists with documented CAST rules for all boolean columns
- [ ] Dry-run of pgloader (or Python script) against a copy of production data completes without error
- [ ] All `db.Boolean` columns are explicitly handled in the migration cast rules or verified to round-trip correctly
- [ ] Migration run time is documented (ballpark for expected production data volume)

## Test plan

```bash
# Dry-run migration against a test copy of production DB
cp data/iptv_proxy.db /tmp/migration_test.db
pgloader --dry-run scripts/pg_migrate.pgloader

# Full test migration against local Docker PostgreSQL
pgloader scripts/pg_migrate.pgloader
python scripts/pg_migration_validate.py \
  --src sqlite:////tmp/migration_test.db \
  --dst postgresql://iptv:iptv@localhost/iptv_proxy

# Verify test suite passes against migrated data
DATABASE_URL=postgresql://iptv:iptv@localhost/iptv_proxy pytest tests/ -m "not sqlite_only"
```

## Affected files

- `scripts/pg_migrate.pgloader` — new pgloader command file
- `scripts/pg_migration_validate.py` — new validation script
- `requirements-tools.txt` or `DEPLOYMENT.md` — document pgloader installation (`brew install pgloader`, `apt-get install pgloader`)
- `docs/DEPLOYMENT.md` — migration run instructions

## Dependencies

- **Depends on** [TODO 115](./115-pg-prep-ci-docker-config.md) — PostgreSQL Docker service and `psycopg2` must be in place.
- **Depends on** [TODO 113](./113-pg-prep-alembic-migration-system.md) — the destination PostgreSQL schema must be created by Alembic before pgloader runs.
- Runs in parallel with [TODO 117](./117-pg-migration-schema-creation.md) (schema creation) but the schema must exist before the data load.

## Risks

- **SQLite `BOOLEAN` as integer**: pgloader's `type integer when (= 0 precision) to boolean` cast applies to ALL integer columns with precision 0, which in SQLite is almost every integer (SQLite does not distinguish integer sizes). **This will incorrectly cast non-boolean integers to boolean.** Always use explicit column-level casts for every `db.Boolean` column instead of type-level casts.
- **`TEXT`-as-JSON with `NULL` values**: Some JSON columns may contain `None` (stored as SQL NULL) or the string `"null"`. PostgreSQL `JSONB` accepts SQL NULL but rejects the string `"null"` only if it is passed as a literal. Validate all JSON columns for `NULL` vs `"null"` vs `""` before migration.
- **Timezone-naive `DATETIME` columns**: All `DateTime` columns store UTC-naive values (e.g., `2026-01-15T12:00:00`). PostgreSQL `TIMESTAMP WITHOUT TIME ZONE` accepts these as-is. Do NOT use `TIMESTAMP WITH TIME ZONE` in the schema unless the application is updated to be timezone-aware throughout.
- **Large `epg_programs` table**: With hundreds of thousands of rows, the `COPY`-based pgloader approach is strongly preferred over row-by-row Python inserts. Budget 5–15 minutes for a large EPG dataset; test against a representative data snapshot.
- **`schema_migrations` table exclusion**: The legacy `schema_migrations` table must be excluded from migration (it is SQLite-only infrastructure). The `alembic_version` table on PostgreSQL will be populated separately by `alembic stamp head`.
