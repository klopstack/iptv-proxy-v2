# Speed up TheSportsDB tests and block live HTTP

**Status:** ✅ Done  
**Priority:** P2  
**Audit:** Test runtime review, June 2026  
**PR batch:** Wave 3 **PR I** (with TODO 62)

## Problem

TheSportsDB-related tests are disproportionately slow in CI and locally. A focused run of `tests/test_thesportsdb*.py` takes **~5 minutes** for 148 tests; five tests alone account for **~280 seconds** (~60s each).

### Root cause: stale mocks + real retry loop

`TheSportsDBService` now calls `call_thesportsdb_api(fn, ...)` (see `services/thesportsdb_service.py`), which applies exponential backoff and `time.sleep` on transient failures.

`tests/test_thesportsdb_service.py` still patches SDK entry points such as `services.thesportsdb_service.events.nextLeagueEvents`. That works for happy-path tests that return a dict immediately, but **error-path tests** drive the real retry helper:

| Test | Mock behavior | What actually runs |
|------|---------------|-------------------|
| `test_get_next_league_events_invalid_response_type` | `return_value = None` | `call_thesportsdb_api` treats `None` as retryable → ~4 backoff sleeps |
| `test_get_next_league_events_api_error` | `side_effect = Exception(...)` | Exception path retries with sleeps |
| `test_get_league_season_events_error` | `side_effect = Exception(...)` | Same |
| `test_get_league_info_error` | `side_effect = Exception(...)` | Same |
| `test_get_event_by_id_error` | `side_effect = Exception(...)` | Same |

Those tests are effectively **hammering TheSportsDB** (or waiting on retry timing) instead of asserting service behavior in milliseconds.

`tests/test_thesportsdb_calendar_scraper.py` already patches `services.thesportsdb_retry.call_thesportsdb_api` — the service tests should follow that pattern.

### Secondary risks

- If `THESPORTSDB_API_KEY` is set to a premium key in dev/CI, `try_v2_sdk_call` may hit the live V2 API **before** the patched V1 SDK function runs, even when mocks are applied at the wrong layer.
- No project-wide guard prevents accidental outbound HTTP in unit tests.

## Affected files

- `tests/test_thesportsdb_service.py` (primary — ~20 `@patch` targets on SDK functions)
- `tests/conftest.py` (optional autouse network guard / shared helper)
- `pyproject.toml` (optional `slow` / `network` markers; default deselect in `test-fast`)
- `Makefile` (`test-fast` documentation)
- `docs/DEVELOPER_GUIDE.md` (how to run fast vs integration tests)

Reference fixtures (already exist): `tests/fixtures/thesportsdb/*.json`

## Proposed solution

1. **Patch at the retry boundary**  
   Replace SDK-level patches with `@patch("services.thesportsdb_service.call_thesportsdb_api")` (or a small test helper that sets `side_effect` / `return_value` without sleeping). Calendar scraper tests already use `services.thesportsdb_retry.call_thesportsdb_api` — align service tests with one convention.

2. **Fix the five slow tests first**  
   Error and invalid-response cases should mock `call_thesportsdb_api` to raise or return once, with `@patch("services.thesportsdb_retry.time.sleep")` only if retry behavior itself is under test (see `tests/test_thesportsdb_retry.py`).

3. **Shared fixture for canned API payloads**  
   Load JSON from `tests/fixtures/thesportsdb/` for realistic `events` / `teams` / `leagues` responses instead of large inline dicts where helpful.

4. **Optional: block live HTTP in unit tests**  
   Autouse fixture (e.g. `responses` / `urllib3` connection stub) or pytest plugin that fails if `requests` / SDK calls are not mocked. Mark any intentional live tests with `@pytest.mark.network`.

5. **Measure before/after**  
   Document baseline: `pytest tests/test_thesportsdb*.py --durations=10` should drop from ~5 min to well under 30s for the full TheSportsDB module set.

## Acceptance criteria

- [x] Full `tests/test_thesportsdb*.py` run completes in **under 30s** on a typical dev machine (no intentional live API calls).
- [x] No test in that set performs outbound HTTP to TheSportsDB without `@pytest.mark.network`.
- [x] All `test_thesportsdb_service.py` cases patch `call_thesportsdb_api` (or equivalent) — not bare SDK functions only.
- [x] The five previously ~60s tests each run in **under 1s**.
- [x] `make test-fast` / CI pytest still passes with ≥75% coverage.

## Test plan

```bash
make test-clean
./venv/bin/pytest tests/test_thesportsdb*.py -q --durations=10
make test-fast   # full suite regression
```

Compare slowest durations before and after; attach timings in the PR description.

## Dependencies

- None (standalone test fix).
- Complements [86](./86-web-smoke-tests-and-pytest-consolidation.md) and [88](./88-expand-ci-quality-gates.md); land before expanding CI gates if possible.

## Completion

**June 2026** — Wave 3 PR I (bundled with TODO 62).

- Patched `services.thesportsdb_service.call_thesportsdb_api` in all `test_thesportsdb_service.py` API tests (25 patches).
- Autouse `try_v2_sdk_call` stub in `tests/conftest.py` for `test_thesportsdb*` modules.
- Added `network` pytest marker in `pyproject.toml`.

**Before:** `tests/test_thesportsdb*.py` ~288s (five tests ~60s each).  
**After:** same set **0.18s** (`--no-cov`).

**Follow-up (same PR batch):** additional ~40s suite savings from non-TheSportsDB sleeps:

| Area | Cause | Fix |
|------|-------|-----|
| PPV detail fetcher tests | `queue.get(timeout=5)` on stop | Stop sentinel + 1s idle timeout |
| Scheduler start/stop tests | 30× `sleep(1)` startup loop | Patch `_run` in `TestStartStop` |
| FFmpeg/MediaFlow teardown | `sleep(1)` in cleanup loop | 0.1s poll slices (faster shutdown) |
| MLB retry test | Real backoff sleeps | Patch `time.sleep` |
| Schedules Direct | `_throttle` waited 0.5s | Autouse throttle skip + separate sleep assertion |
