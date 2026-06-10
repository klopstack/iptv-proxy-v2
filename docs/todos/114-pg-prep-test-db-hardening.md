# Harden test DB fixtures and isolation for PostgreSQL compatibility

**Status:** ✅ Complete  
**Priority:** P2  
**Track:** Database Migration — Series A (Preparation)

## Problem

The test suite is tightly coupled to SQLite through multiple layers:

1. **`conftest.py`** hard-codes `DATABASE_URL = sqlite:///...`, uses per-worker SQLite file paths (`pytest_gw0.db`), and cleans up WAL/SHM sidecar files — all SQLite-specific.
2. **`conftest.py` comments** acknowledge "database is locked" SQLite semantics explicitly.
3. **`test_migrations.py`** imports `sqlite3` directly and uses `PRAGMA foreign_key_check`, `PRAGMA table_info`, and `SELECT name FROM sqlite_master` for post-migration assertions.
4. **`test_schema_parity.py`** and **`test_event_composite_unique_migration.py`** make assertions through `sqlite3` introspection in places.
5. **`services/ppv/orchestrator.py`** comment notes "database is locked" (SQLite WAL lock) as a known issue requiring workaround.

None of these files will work transparently against PostgreSQL. Before adding PostgreSQL to CI (TODO 115), the test infrastructure must be abstracted so both backends can be targeted.

## Current state

### `tests/conftest.py`

```python
# Per-worker SQLite path strategy
def _resolve_test_db_path() -> Path:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker and worker != "master":
        return PROJECT_ROOT / "instance" / f"pytest_{worker}.db"
    return PROJECT_ROOT / "instance" / "pytest.db"

TEST_DB_PATH = _resolve_test_db_path()

# SQLite WAL sidecar cleanup
def _cleanup_test_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        db_file = Path(f"{TEST_DB_PATH}{suffix}")
        if db_file.exists():
            db_file.unlink()

# Hard-coded SQLite URL
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
```

The per-file isolation strategy is a workaround for SQLite's lack of proper transactional test isolation — each worker gets its own file to avoid write-lock contention. PostgreSQL supports concurrent transactional isolation via `SAVEPOINT` / `BEGIN`...`ROLLBACK`, which is the standard pytest-sqlalchemy pattern.

### `tests/test_migrations.py`

Uses `sqlite3.connect(path)` and `PRAGMA`-based assertions:
```python
import sqlite3
# ...
conn = sqlite3.connect(path)
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
# ...
fk_conn = sqlite_connect(temp_db)
violations = fk_conn.execute("PRAGMA foreign_key_check").fetchall()
```

## Proposed solution

### 1 — Make `DATABASE_URL` injectable in conftest

Stop hard-coding `sqlite:///...` in `conftest.py`. Instead, read `DATABASE_URL` from the environment and fall back to SQLite only if not set:

```python
import os
from pathlib import Path

_DEFAULT_SQLITE = f"sqlite:///{PROJECT_ROOT}/instance/pytest.db"

def _resolve_test_db_url() -> str:
    url = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE)
    # SQLite per-worker path injection
    if url.startswith("sqlite:///"):
        worker = os.environ.get("PYTEST_XDIST_WORKER")
        if worker and worker != "master":
            base = url.replace("sqlite:///", "")
            url = f"sqlite:///{Path(base).with_suffix('')}_{worker}.db"
    return url

TEST_DB_URL = _resolve_test_db_url()
os.environ["DATABASE_URL"] = TEST_DB_URL
```

This allows CI to pass `DATABASE_URL=postgresql://...` and the test suite will use PostgreSQL instead.

### 2 — Guard SQLite-specific cleanup

WAL/SHM cleanup is only meaningful for SQLite. Guard it:

```python
def _cleanup_test_db() -> None:
    if not TEST_DB_URL.startswith("sqlite:///"):
        return
    path = TEST_DB_URL.replace("sqlite:///", "")
    for suffix in ("", "-wal", "-shm"):
        ...
```

For PostgreSQL, test isolation should use `db.session.rollback()` + `db.drop_all()` / `db.create_all()` (already the pattern for SQLite; the key is removing the file-delete path).

### 3 — Replace PostgreSQL-incompatible patterns in the `app` fixture

The current `app` fixture calls `_db.create_all()` at setup and `_db.drop_all()` at teardown. This works on both SQLite and PostgreSQL when using the ORM path. No change needed here.

The `_db.engine.dispose()` call before `drop_all()` (needed to avoid "database is locked" on SQLite) is harmless on PostgreSQL.

### 4 — Replace `sqlite3` assertions in `test_migrations.py`

Port SQLite-specific assertions to SQLAlchemy `inspect()`:

```python
# Before (SQLite only)
conn = sqlite3.connect(path)
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = {row[0] for row in cursor.fetchall()}

# After (dialect-agnostic)
from sqlalchemy import create_engine, inspect as sa_inspect
engine = create_engine(os.environ["DATABASE_URL"])
tables = set(sa_inspect(engine).get_table_names())
```

For `PRAGMA foreign_key_check` (SQLite FK violation scan), add a `pytest.mark.sqlite_only` marker and skip the check when `DATABASE_URL` is not SQLite. PostgreSQL enforces FK constraints at DML time (not via a separate check pass), so this test has no PG equivalent.

### 5 — Transactional test isolation for PostgreSQL

For PostgreSQL, the per-worker file strategy should be replaced with per-test transaction rollback:

- Wrap each test in a `BEGIN` ... `ROLLBACK` outer transaction using SQLAlchemy's `SAVEPOINT` support.
- The `app` fixture opens a connection, begins a transaction, yields, then rolls back.
- This requires the Flask app's session to be scoped to the test connection (using `db.session = scoped_session(...)` pointed at the test connection).

This is the standard [Flask-SQLAlchemy testing pattern](https://flask.palletsprojects.com/en/2.3.x/testing/) for transactional rollback. It is significantly faster than `drop_all` / `create_all` per test.

Since this is a larger refactor, it can be done incrementally: start with injectable `DATABASE_URL` and SQLite cleanup guards, then add transactional isolation in a follow-up.

### 6 — Mark or skip SQLite-only tests

Create a `pytest.ini` / `conftest.py` marker:

```python
# conftest.py
def is_sqlite() -> bool:
    return os.environ.get("DATABASE_URL", "sqlite").startswith("sqlite")

pytest_plugins = []

def pytest_configure(config):
    config.addinivalue_line("markers", "sqlite_only: test requires SQLite backend")
```

Mark tests that use `PRAGMA`, `sqlite_master`, or WAL semantics:

```python
@pytest.mark.sqlite_only
def test_pragma_foreign_key_check(temp_db):
    ...
```

A custom `autouse` fixture can auto-skip these when the backend is not SQLite.

## Acceptance criteria

- [x] `conftest.py` reads `DATABASE_URL` from environment; SQLite is only the default
- [x] Running `DATABASE_URL=postgresql://localhost/test_iptv pytest tests/ -x` does not immediately crash on import or fixture setup
- [x] SQLite per-worker file strategy remains intact when `DATABASE_URL` is SQLite
- [x] WAL/SHM cleanup is guarded to SQLite-only
- [x] `test_migrations.py` SQLite-specific `PRAGMA` and `sqlite_master` assertions are marked `sqlite_only`
- [x] `pytest -m "not sqlite_only"` passes against PostgreSQL (assuming schema exists)
- [x] Existing SQLite test suite shows no regressions

## Completion

- PG-A3 batch — injectable `DATABASE_URL`, `sqlite_only` markers, PG fixture reset ([#72](https://github.com/klopstack/iptv-proxy-v2/pull/72))

## Test plan

```bash
# SQLite (existing behavior)
pytest tests/ -x -v

# PostgreSQL (requires Docker PG from TODO 115)
DATABASE_URL=postgresql://iptv:iptv@localhost:5432/iptv_test pytest tests/ -m "not sqlite_only" -x -v

# Verify sqlite_only skip
DATABASE_URL=postgresql://... pytest tests/test_migrations.py -v
# Expect: sqlite_only tests skipped, not failed
```

## Affected files

- `tests/conftest.py` — `_resolve_test_db_path()` → `_resolve_test_db_url()`, guard WAL cleanup, injectable DATABASE_URL
- `tests/test_migrations.py` — replace `sqlite3` assertions with `sa_inspect`, add `sqlite_only` markers
- `tests/test_schema_parity.py` — review for `sqlite_master` / PRAGMA usage; add markers or port
- `tests/test_event_composite_unique_migration.py` — review for sqlite3 assertions
- `pytest.ini` or `pyproject.toml` — register `sqlite_only` marker
- `DEVELOPER_GUIDE.md` — document `DATABASE_URL` override for running tests against PostgreSQL

## Dependencies

- Depends on [TODO 113](./113-pg-prep-alembic-migration-system.md) — `test_migrations.py` must be updated to reference Alembic revision tracking, not the legacy `schema_migrations` table.
- Should be complete before [TODO 115](./115-pg-prep-ci-and-docker.md) (CI PostgreSQL test job).

## Risks

- **`db.create_all()` vs Alembic on PostgreSQL**: If tests use `db.create_all()` (which they currently do) but production uses `alembic upgrade head`, any model-to-migration drift will be hidden. Long-term, CI should test both `create_all` (unit tests) and `alembic upgrade head` (integration) against PostgreSQL.
- **Transaction isolation on PostgreSQL**: The `db.drop_all()` / `db.create_all()` per-test lifecycle works but is slow with 100+ tests. The transactional rollback approach (phase 2) can be added iteratively without breaking the basic injectable-URL work.
- **`autocommit` mode in `app.py`**: The current SQLite config sets `isolation_level=None` (autocommit) in `connect_args`. This is PostgreSQL-incompatible as a `connect_args` key. On PostgreSQL, connection-level autocommit is set differently. The `app.py` SQLite pragma listener block is already gated on `"sqlite" in DATABASE_URI` — confirm this gate works correctly in tests when `DATABASE_URL` is overridden.
