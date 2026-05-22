# TODO 07: Fix Test Database Isolation

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Small (conftest + gitignore)

---

## Problem

Running the test suite against a stale or corrupted database file causes **263 errors**:

```
sqlalchemy.exc.DatabaseError: malformed database schema (Test Account)
```

Observed with `instance/test.db`. With a clean DB, all **2,301 tests pass**.

Contributing factors:
1. `tests/conftest.py` sets `DATABASE_URL=sqlite:///test.db` (relative path → repo root)
2. `.gitignore` ignores `*.db` globally but explicitly lists only `instance/test.db-wal/shm` — inconsistent
3. Leftover `instance/test.db` from older test configs or manual runs can interfere if `DATABASE_URL` is overridden
4. `tests/test_schemas.py` overrides to `sqlite:///:memory:` — import order dependent
5. No CI guard against corrupted test artifacts

---

## Goal

Reliable, isolated test database that cannot be corrupted by stale files or parallel runs.

---

## Proposed solution

### 1. Use absolute temp-file DB per test session (recommended)

In `tests/conftest.py`:

```python
import tempfile
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
```

Or per-function (current approach) but with explicit path:

```python
TEST_DB_PATH = Path(__file__).parent.parent / "instance" / "pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
```

Ensure cleanup in fixture teardown deletes the file even on failure.

### 2. Update `.gitignore`

```gitignore
# Test databases
test.db
test.db-*
instance/pytest.db
instance/test.db
instance/test.db-*
```

Remove redundant partial ignores if `*.db` already covers them (verify `*.db` is present — it is).

### 3. Add pytest hook or Makefile target

```makefile
test-clean:
	rm -f test.db test.db-* instance/test.db instance/test.db-* instance/pytest.db
```

Run before `make test` or document in DEV_SETUP.

### 4. Fix `test_schemas.py` import order

`test_schemas.py` sets `DATABASE_URL` to in-memory **after** conftest may have imported app. Options:
- Remove the override if schemas tests don't need DB
- Move schema-only tests to not import app at all (they only import `schemas`)

Review whether `test_schemas.py` needs Flask app context — if not, remove DB override entirely.

### 5. Document in DEVELOPER_GUIDE

Add troubleshooting section: "If tests fail with malformed database schema, run `make test-clean`."

---

## Files to modify

| File | Changes |
|------|---------|
| `tests/conftest.py` | Explicit DB path + robust cleanup |
| `tests/test_schemas.py` | Remove conflicting DATABASE_URL override if possible |
| `.gitignore` | Explicit test DB paths |
| `Makefile` | Add `test-clean` target |
| `docs/DEVELOPER_GUIDE.md` | Troubleshooting note |

---

## Acceptance criteria

- [x] Fresh clone + `make test` passes without manual DB cleanup
- [x] Corrupt `instance/test.db` present does not break tests
- [x] Each test function gets clean schema (no cross-test pollution)
- [x] No `malformed database schema` errors after 3 consecutive test runs
- [x] `test_schemas.py` does not conflict with conftest DB setup

---

## Test plan

```bash
# Simulate corruption
echo "corrupt" > instance/test.db
make test-clean  # or make test if auto-clean
make test-fast
# Should pass

# Three consecutive runs
for i in 1 2 3; do venv/bin/pytest tests/ -q --no-cov || exit 1; done
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Uses `instance/pytest.db` with engine dispose-before-delete reset; `make test-clean` runs before test targets |
