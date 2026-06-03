# Parallelize pytest suite (pytest-xdist)

**Status:** ✅ Done — implemented in [100-parallelize-pytest-xdist.md](./100-parallelize-pytest-xdist.md) ([PR #43](https://github.com/klopstack/iptv-proxy-v2/pull/43))  
**Priority:** P2  
**Audit:** Test runtime review, June 2026

## Problem

The suite has **~2,650 tests** and takes **~2.5 minutes** serially with coverage in CI (`make test`; see baseline in [94](./94-speed-up-thesportsdb-tests-no-live-http.md)). [94](./94-speed-up-thesportsdb-tests-no-live-http.md) removed the worst single-thread bottlenecks (live HTTP / retry sleeps); further gains need **multi-process execution**.

A spike with `pytest-xdist` (`-n auto`, no code changes) produced **~1,850 passes and ~1,200 failures/errors in ~68s** — faster wall time, but invalid because workers contend on one database file.

### Root cause: shared SQLite path

`tests/conftest.py` sets a single absolute path for all tests:

```python
TEST_DB_PATH = PROJECT_ROOT / "instance" / "pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
```

The `app` fixture resets that file per test, which is correct **within one worker** but breaks when multiple xdist workers run tests concurrently against the same path (locks, `OperationalError`, `FileNotFoundError` during `_cleanup_test_db`).

Most tests are otherwise good candidates for parallelism: function-scoped fixtures, in-memory-style isolation per test, no shared global mutable app state beyond the DB path.

### Secondary concerns

| Area | Risk | Mitigation |
|------|------|------------|
| Coverage | `pytest-cov` must merge worker reports | `pytest-cov` supports xdist; document `COVERAGE_PROCESS` / combine step |
| `@pytest.mark.migrations` | Temp DB per test; usually fine | Run in `xdist_group` serially if flakiness appears |
| `@pytest.mark.network` / `integration` | Rare; may touch shared resources | Keep default deselect in `test-fast`; optional serial group |
| CI | Single job today | Optional: shard by directory in matrix *after* per-worker DB works locally |

## Affected files

- `tests/conftest.py` — per-worker `TEST_DB_PATH` (use `PYTEST_XDIST_WORKER` / `worker_id` when present)
- `requirements-dev.txt` — add `pytest-xdist`
- `pyproject.toml` — optional default `-n auto` for `test-fast` only; keep `make test` documented for CI until stable
- `Makefile` — `test-parallel` or extend `test-fast` with `-n auto`
- `.github/workflows/build.yml` — enable parallel run once local + CI green
- `docs/DEVELOPER_GUIDE.md` — when to use serial vs parallel

## Proposed solution

1. **Per-worker database path**  
   In `conftest.py`, if xdist worker env is set, suffix the DB file, e.g. `pytest_gw0.db`, `pytest_gw1.db`, and set `DATABASE_URL` before app import (same pattern as today, one path per process).

2. **Add `pytest-xdist`** to dev requirements; verify `make test-fast -n auto` (or new target) passes with **0 failures** vs current serial baseline.

3. **Coverage**  
   Configure combined coverage for parallel runs so `make test` still enforces **≥75%** (may need `pytest --cov` xdist options or a documented two-step combine).

4. **Makefile / CI**  
   - Local: `make test-fast` with `-n auto` for quick feedback.  
   - CI: adopt parallel only after stable on Linux runners (same CPU count variance as dev laptops).

5. **Measure**  
   Record before/after: `pytest tests/ -q --no-cov` and `make test` wall times; target **~40–50%** wall-time reduction with `-n auto` on a typical 8-core machine (diminishing returns from SQLite and fixture setup).

6. **Fallback**  
   If combined coverage under xdist is too brittle, ship **parallel without coverage** for `test-fast` and keep serial `make test` for CI until coverage merge is solved.

## Acceptance criteria

- [ ] `pytest tests/ -n auto --no-cov` passes with the same pass count as serial (no shared-DB flakes).
- [ ] `make test` (with coverage) passes in CI with parallel enabled, or parallel is explicitly limited to `test-fast` with serial `test` documented.
- [ ] Per-worker DB files are cleaned up (`test-clean` removes `pytest_gw*.db` patterns).
- [ ] DEVELOPER_GUIDE documents parallel vs serial commands.
- [ ] Documented speedup: serial vs `-n auto` timings attached to the implementing PR.

## Test plan

```bash
make test-clean
venv/bin/pytest tests/ -q --no-cov                    # serial baseline
venv/bin/pytest tests/ -q --no-cov -n auto            # parallel after conftest fix
make test                                             # coverage + CI parity
```

Re-run the parallel spike that currently fails (shared `pytest.db`) and confirm **0 errors** from DB contention.

## Dependencies

- [94](./94-speed-up-thesportsdb-tests-no-live-http.md) ✅ — removes live HTTP / sleep hotspots (do not parallelize on top of a slow suite).
- [80](./80-align-test-db-with-production-schema.md) — optional; migration fixture changes should be re-validated under xdist.
- [88](./88-expand-ci-quality-gates.md) — natural place to wire CI once local parallel is stable.
- Complements [86](./86-web-smoke-tests-and-pytest-consolidation.md) (fewer redundant tests → faster parallel runs).

## Completion

Implemented in [100-parallelize-pytest-xdist.md](./100-parallelize-pytest-xdist.md) — **PR #43:** https://github.com/klopstack/iptv-proxy-v2/pull/43
