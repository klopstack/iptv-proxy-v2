# Migrate overview stats API to data_response envelope

**Status:** ✅ Done  
**Priority:** P2  
**Deferred from:** [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) — [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)  
**Related:** [73-standardize-api-response-shapes.md](./73-standardize-api-response-shapes.md) ✅

## Problem

`GET /api/dashboard/summary` returns the standardized `{ "data": ... }` envelope via `data_response()` ([TODO 73](./73-standardize-api-response-shapes.md)). `GET /api/overview/stats` still returns a **legacy unwrapped** body from `jsonify(stats)`.

Gaps:

1. **Contract inconsistency** — new dashboard code uses `unwrapData()` / `apiUnwrapData`, which tolerates both shapes, but API consumers and docs should not rely on dual behavior forever.
2. **Smoke checklist mismatch** — `docs/SMOKE_TEST_POST_MERGE.md` §7 expects overview stats `{ data: ... }`, which is not true until this migration ([109](./109-update-smoke-test-dashboard-checks.md) coordinates doc updates).
3. **Contract test ambiguity** — `api_data()` in tests accepts either wrapped or raw payload, masking the inconsistency.

## Current state

| Piece | Behavior |
|-------|----------|
| `routes/api.py` — `get_overview_stats()` | `return jsonify(stats)` |
| `static/js/pages/dashboard_page.js` | `unwrapData(await response.json())` on deferred load |
| `tests/test_api_contract.py` | `test_overview_stats_data_envelope` uses `api_data()` (passes with or without wrapper) |
| `tests/test_dashboard_summary.py` | `TestOverviewStatsCoverageFix` uses `payload.get("data", payload)` |

## Proposed solution

1. Change `get_overview_stats()` to `return data_response(stats)` (same pattern as `get_dashboard_summary`).
2. Update contract tests to require `"data"` key and reject bare dict at top level.
3. Grep admin JS for `/api/overview/stats` — confirm `unwrapData` / `apiUnwrapData` still work; remove any dead dual-path handling if safe.
4. Update `docs/API_REFERENCE.md` — `GET /api/overview/stats` example shows `data` envelope.
5. Coordinate [109](./109-update-smoke-test-dashboard-checks.md) so smoke checklist matches shipped behavior.

## Affected files

- `routes/api.py` — `get_overview_stats`
- `tests/test_api_contract.py`, `tests/test_dashboard_summary.py`, any overview stats route tests
- `static/js/pages/dashboard_page.js` — verify only
- `docs/API_REFERENCE.md`
- `docs/SMOKE_TEST_POST_MERGE.md` (via TODO 109)

## Acceptance criteria

- [x] `GET /api/overview/stats` returns `{ "data": { "accounts", "channels", ... } }` on success
- [x] Contract test fails if `data` key is missing
- [x] Deferred dashboard overview cards still render on `/`
- [x] `docs/API_REFERENCE.md` documents the wrapped shape
- [x] No breaking change for external consumers without a note in PR / CHANGELOG (if any exist)

## Test plan

```bash
pytest tests/test_api_contract.py -k overview -q --no-cov
pytest tests/test_dashboard_summary.py::TestOverviewStatsCoverageFix -q --no-cov
make test-fast

# Manual: / — deferred overview cards (accounts, EPG, tags) appear after Tier-1 summary
```

## Dependencies

- [73-standardize-api-response-shapes.md](./73-standardize-api-response-shapes.md) ✅ — envelope convention
- [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) ✅ — dashboard still calls overview stats in deferred section ([PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48))
- [109-update-smoke-test-dashboard-checks.md](./109-update-smoke-test-dashboard-checks.md) — update smoke doc after envelope ships (or in same PR)

## References

- `routes/api.py` — `get_overview_stats`, `get_dashboard_summary`
- `api_responses.data_response`
- `docs/architecture/api-contract-errors-and-responses.md`
