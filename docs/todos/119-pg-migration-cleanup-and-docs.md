# Post-cutover cleanup: remove SQLite code paths and update documentation

**Status:** ⬜ Open  
**Priority:** P3  
**Track:** Database Migration — Series B (Switchover)

## Problem

After a successful PostgreSQL cutover (TODO 118), the codebase will still contain:

1. **SQLite-specific startup code in `app.py`**: The `if "sqlite" in DATABASE_URI` PRAGMA listener block, the SQLite-specific `connect_args`, and comments referencing WAL/lock semantics.
2. **Legacy migration artifacts**: `migrations/legacy_sqlite/` directory, `_sqlite_fk_repair.py`, `run_migrations.py` (archived), and the `schema_migrations` table reference in `test_migrations.py`.
3. **Outdated documentation**: `DEPLOYMENT.md`, `DEVELOPER_GUIDE.md`, and `README.md` will reference SQLite paths, file-based backups, and setup instructions that no longer apply.
4. **Test fixtures still referencing SQLite internals**: WAL cleanup code, `sqlite_only` markers, and per-file isolation strategy (which can now be replaced with transactional rollback).
5. **Docker volume mount for SQLite file**: `./data:/app/data` volume is no longer needed once PostgreSQL is the only backend.

Leaving this code in place creates maintenance burden, confuses new contributors, and risks accidental SQLite-specific code re-emerging via copy-paste.

**This TODO must only be started after:**
- TODO 118 (cutover) is complete and verified in production.
- At least 7 days of stable PostgreSQL operation without rollback.

## Current state

All SQLite-specific code is currently in place (necessary until cutover). See TODOs 111–118 for the full inventory.

## Proposed solution

### 1 — Clean up `app.py`

Remove the `if "sqlite" in DATABASE_URI:` block and the SQLite-specific `connect_args`:

```python
# REMOVE this entire block after PostgreSQL cutover:
if "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        ...

# REMOVE SQLite-specific connect_args from engine options:
# "timeout": 60,
# "check_same_thread": False,
# "isolation_level": None,
```

Keep `pool_pre_ping`, `pool_size`, `max_overflow`, and `pool_timeout` (PostgreSQL connection pool settings).

Update the comment block to document PostgreSQL-specific tuning.

### 2 — Delete legacy SQLite migration artifacts

```bash
# Remove the archived legacy migration directory (keep only Alembic)
rm -rf migrations/legacy_sqlite/

# Remove the archived migration runner
rm run_migrations.py   # or remove from its archived location

# These files were SQLite-only and have no PG equivalent:
rm migrations/_sqlite_fk_repair.py  # if not already deleted in TODO 111
```

The `alembic_migrations/` directory (created in TODO 113) is the only migration system going forward.

### 3 — Simplify `conftest.py`

Remove SQLite-specific test infrastructure:

```python
# REMOVE per-worker SQLite file strategy
# REMOVE WAL sidecar cleanup (_cleanup_test_db)
# REMOVE sqlite:/// default fallback (DATABASE_URL must be set explicitly in CI)
```

Replace with transactional rollback test isolation (the standard Flask-SQLAlchemy testing pattern for PostgreSQL):

```python
@pytest.fixture(scope="function")
def app():
    flask_app = app_module.app
    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        _db.session.begin_nested()     # SAVEPOINT
        yield flask_app
        _db.session.rollback()         # roll back to SAVEPOINT
```

This is faster than `drop_all` / `create_all` per test (no DDL round-trip) and uses proper transaction isolation.

### 4 — Remove `sqlite_only` test markers

Once PostgreSQL is the only backend, `@pytest.mark.sqlite_only` tests that were previously skipped should either:
- Be **ported** to PostgreSQL-equivalent assertions (e.g., `PRAGMA foreign_key_check` → ORM-level FK integrity test).
- Be **deleted** if they tested SQLite-specific behavior that no longer applies (e.g., WAL checkpoint, `writable_schema`).

### 5 — Update Docker Compose

Remove the SQLite data volume and simplify the service definition:

```yaml
# REMOVE after cutover:
volumes:
  - ./data:/app/data   # SQLite file — no longer needed

# Keep (PostgreSQL data volume):
volumes:
  postgres_data: ...
```

If the `./data` directory is used for anything other than the SQLite database file (e.g., cached images, pgloader source files), retain only those mounts and document their purpose.

### 6 — Update documentation

**`DEPLOYMENT.md`**:
- Remove SQLite setup section ("no database setup required")
- Document PostgreSQL as the only supported backend
- Update backup instructions: `pg_dump iptv_proxy > backup.sql` instead of `cp iptv_proxy.db backup.db`
- Update restore instructions: `psql iptv_proxy < backup.sql`
- Add connection string format: `postgresql://user:pass@host:port/dbname`
- Add pool tuning env vars: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`

**`DEVELOPER_GUIDE.md`**:
- Remove "SQLite is the only dependency" claim
- Add PostgreSQL local development setup (Docker Compose one-liner)
- Update test instructions: `DATABASE_URL=postgresql://... pytest tests/`
- Remove `instance/pytest.db` references

**`README.md`**:
- Update "Requirements" section: add PostgreSQL 15+
- Update "Quick Start": include Docker Compose PostgreSQL service step
- Remove SQLite-specific backup instructions

**`migrations/README.md`** (or `alembic_migrations/README.md`):
- Document Alembic workflow: `flask db upgrade`, `flask db revision --autogenerate`, `flask db downgrade`
- Remove all references to legacy SQLite migration runner

### 7 — Archive the SQLite backup

Move the pre-migration SQLite backup to long-term storage (e.g., S3 or an offline drive). Document its location in `docs/DEPLOYMENT.md` under "Database backup history" for audit purposes.

## Acceptance criteria

- [ ] `app.py` contains no `sqlite` string references in engine config or event listeners
- [ ] `migrations/legacy_sqlite/` directory deleted (or confirmed to not exist)
- [ ] `conftest.py` uses transactional rollback isolation; no WAL/SHM cleanup code; no `sqlite:///` default
- [ ] `pytest tests/` passes with `DATABASE_URL=postgresql://...` and all tests (no `sqlite_only` skips)
- [ ] `docker-compose.yml` removes `./data:/app/data` volume (or documents its non-SQLite purpose)
- [ ] `DEPLOYMENT.md` updated for PostgreSQL-only deployment
- [ ] `DEVELOPER_GUIDE.md` updated with PostgreSQL local dev setup
- [ ] `README.md` prerequisites updated
- [ ] `requirements.txt` removes `aiosqlite` if present (SQLite async driver, not needed for PG)

## Test plan

```bash
# Verify no sqlite references remain in core app code
grep -rn "sqlite" app.py models/ services/ routes/ tests/conftest.py \
  --include="*.py" | grep -v "# legacy\|archived\|historical"
# Expect: zero results (or only comments)

# Full test suite with PostgreSQL only
DATABASE_URL=postgresql://iptv:iptv@localhost/iptv_test pytest tests/ -v
# Expect: all tests pass, no skips

# Docker Compose clean start
docker compose down -v
docker compose --profile postgres up -d
# Wait for postgres healthy, then app healthy
curl http://localhost:8000/api/accounts
# Expect: empty list (fresh DB)
flask db upgrade  # apply schema
# App ready for fresh use
```

## Affected files

- `app.py` — remove SQLite pragma listener, SQLite connect_args
- `tests/conftest.py` — transactional rollback isolation, remove WAL cleanup
- `tests/test_migrations.py` — remove `sqlite_only` markers or port assertions
- `tests/test_schema_parity.py` — update for PostgreSQL introspection
- `docker-compose.yml` — remove SQLite data volume
- `requirements.txt` — remove `aiosqlite` if present
- `migrations/legacy_sqlite/` — delete
- `DEPLOYMENT.md`, `DEVELOPER_GUIDE.md`, `README.md`, `migrations/README.md` — update for PostgreSQL
- `services/fcc_pattern_reset.py` — confirm `sqlite_path_from_database_url` deleted (should have been done in TODO 111)

## Dependencies

- **Blocked by** [TODO 118](./118-pg-migration-cutover-procedure.md) — do not start until production cutover is stable for ≥7 days.
- Optionally pairs with [TODO 101](./101-final-documentation-review.md) — documentation review pass can catch remaining SQLite references.

## Risks

- **Cached image storage**: The `./data` volume may be used for more than just the SQLite file. If `CachedImage` model stores local file paths under `./data/images/`, the volume mount removal would break image caching. Audit `models/epg.py` `CachedImage` path fields before removing the volume.
- **Backup habit change**: Operators accustomed to `cp iptv_proxy.db backup.db` (instant, atomic, SQLite-native) may not immediately adopt `pg_dump`. Consider adding a `make backup` target to the Makefile that wraps `pg_dump` with a timestamped filename.
- **Developer onboarding friction**: SQLite required zero setup; PostgreSQL requires Docker or a local install. The Docker Compose one-liner (`docker compose --profile postgres up -d postgres`) should be the documented path to minimize friction.
- **Old SQLite backups**: Pre-migration SQLite backups should NOT be deleted — they may be needed for regulatory / audit purposes or to recover data that was inadvertently not migrated. Keep them in cold storage for at least 90 days post-cutover.
