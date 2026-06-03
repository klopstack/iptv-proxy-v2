# Parallelize pytest suite with pytest-xdist (TODO 95)

**Status:** ✅ Done  
**Priority:** P2  
**Parent:** [95-parallelize-pytest-suite.md](./95-parallelize-pytest-suite.md)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **Z**

## Summary

Enable `pytest-xdist` with per-worker SQLite database paths so ~2,650 tests can run in parallel without shared-DB contention. Target ~40–50% wall-time reduction on typical multi-core machines.

## Problem

Serial suite takes ~2.5 minutes with coverage in CI. A spike with `-n auto` ran faster but produced ~1,200 failures because all workers share `instance/pytest.db` (see parent TODO 95 for root cause).

## Affected files

- `tests/conftest.py` — per-worker `TEST_DB_PATH` via `PYTEST_XDIST_WORKER` / `worker_id`
- `requirements-dev.txt` — `pytest-xdist`
- `pyproject.toml`, `Makefile`, `.github/workflows/build.yml`
- `docs/DEVELOPER_GUIDE.md`

## Proposed solution

_(Full spec in [95-parallelize-pytest-suite.md](./95-parallelize-pytest-suite.md).)_

1. Suffix DB path per xdist worker (`pytest_gw0.db`, …).
2. Add `pytest-xdist`; verify `pytest tests/ -n auto --no-cov` matches serial pass count.
3. Configure combined coverage for parallel runs or document serial `make test` for CI until stable.
4. `test-clean` removes `pytest_gw*.db` patterns.

## Acceptance criteria

- [x] `pytest tests/ -n auto --no-cov` passes with same pass count as serial (2728; per-worker DB)
- [x] `make test` uses `-n auto` with combined coverage (pytest-cov xdist)
- [x] `test-clean` removes `pytest_gw*.db` patterns
- [x] DEVELOPER_GUIDE documents parallel vs serial commands
- [x] Before/after timings recorded in implementing PR

## Timings (local, 16 workers)

| Command | Wall time |
|---------|-----------|
| `pytest tests/ -q --no-cov` (serial) | ~128s |
| `pytest tests/ -q --no-cov -n auto` | ~31–39s |
| `make test` (parallel + cov) | ~78–83s |

## Test plan

```bash
make test-clean
venv/bin/pytest tests/ -q --no-cov                    # serial baseline
venv/bin/pytest tests/ -q --no-cov -n auto            # parallel after conftest fix
make test                                             # coverage + CI parity
```

## Dependencies

- [94](./94-speed-up-thesportsdb-tests-no-live-http.md) ✅
- [80](./80-align-test-db-with-production-schema.md) ✅ — re-validate migration fixtures under xdist
- [88](./88-expand-ci-quality-gates.md) ✅ — wire CI once local parallel is stable
- Batch **Z** last in Wave 9 recommended — avoids debugging flakes while route/frontend PRs land

## Completion

- PR: https://github.com/klopstack/iptv-proxy-v2/pull/43
