# Harden PPV enrichment API routes

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

Several route-level issues in `routes/ppv_enrichment.py`:

### 1. Inconsistent error handling

PPV EPG routes use `@handle_errors()`; enrichment routes use manual `try/except` returning raw `str(e)` — inconsistent JSON error shape and potential internal message leakage.

### 2. `include_no_match` memory footgun

Documented in route docstring: when `include_no_match=true`, the handler runs `query.all()` loading **all** matching channels into memory — unsafe on large installs.

### 3. Queue stats silently dropped

In `get_enrichment_status`, orchestrator queue stats are wrapped in bare `except Exception: pass` — failures hide queue depth with no log.

### 4. Hard-coded confidence in orchestrator

`run_enhanced_fallback` uses `result.confidence >= 0.35` instead of `MIN_MATCH_CONFIDENCE` from constants.

## Affected files

- `routes/ppv_enrichment.py`
- `services/ppv/orchestrator.py` — line 236
- `docs/API_REFERENCE.md` (admin auth is proxy-level — see TODO 68)

## Proposed solution

1. Apply `@handle_errors()` to enrichment routes (match `ppv_epg.py` pattern).
2. Replace `include_no_match` bulk load with orchestrator batch API or paginated re-queue; deprecate full-memory path.
3. Log warning on queue stats failure; include `queue_stats_error: true` in JSON when degraded.
4. Import and use `MIN_MATCH_CONFIDENCE`.

## Acceptance criteria

- [ ] All enrichment error responses use consistent JSON shape.
- [ ] No code path loads unbounded channel lists by default.
- [ ] Queue stats failures are logged.
- [ ] Enhanced fallback threshold matches constants module.

## Test plan

- `tests/test_ppv_enrichment_routes.py` — error shape, include_no_match behavior.
- Regression on status endpoint with mocked orchestrator failure.

## Dependencies

None.
