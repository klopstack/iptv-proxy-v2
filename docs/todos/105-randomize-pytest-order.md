# Randomize pytest test order (order-dependent failure detection)

**Status:** ✅ Done  
**Priority:** P2  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9 follow-up (after **Z** / TODO 100)  
**Dependencies:** [100](./100-parallelize-pytest-xdist.md) (pytest-xdist), [86](./86-web-smoke-tests-and-pytest-consolidation.md) (conftest consolidation)

## Summary

Enable pytest test-order randomization locally and in CI to surface order-dependent failures before they flake under `pytest-xdist` (`-n auto`).

## Problem

Tests pass in a fixed discovery order but fail under parallel execution or a different order because of shared state (SQLite files, module globals, incompletely reset mocks). PR #44 (TODO 103) CI fixes exposed several isolation issues that fixed-order serial runs did not catch.

## Proposed solution

Use **pytest-randomly** (works with xdist; seed logged on every run and on failure):

1. Add `pytest-randomly` to `requirements-dev.txt`.
2. Rely on plugin auto-registration (no separate `pytest.ini`; config stays in `pyproject.toml` / Makefile as today).
3. `make test` / `make test-fast` / CI `make test` inherit random order via venv install (parallel `-n auto` unchanged).
4. Document reproduction: `--randomly-seed=<value>` from failure output; optional `--randomly-dont-reset-seed` while debugging.

## Affected files

- `requirements-dev.txt`
- `pyproject.toml` (optional note in pytest section)
- `docs/DEVELOPER_GUIDE.md`
- `docs/todos/README.md`, `docs/todos/ROADMAP.md`

## Acceptance criteria

- [x] Random order enabled by default via `make test` / `make test-fast` and CI
- [x] Failed run prints seed / `--randomly-seed` repro command (plugin default)
- [x] `DEVELOPER_GUIDE` documents reproducing order-dependent flakes
- [x] CI green (no new order-deps found in `make test-fast`: 2752 passed)

## Test plan

```bash
make install
make test-fast                    # full suite, random + parallel
# On failure, copy seed from output:
venv/bin/pytest tests/ -q --no-cov -n auto --randomly-seed=<seed>
```

## Completion

- **PR:** _(link added on push)_
- Added `pytest-randomly==3.16.0`; plugin auto-enables on install (works with `-n auto`).
- `make test-fast`: 2752 passed, ~63s; seed logged (`Using --randomly-seed=…`).
- No order-dependent failures required fixes in this pass.
