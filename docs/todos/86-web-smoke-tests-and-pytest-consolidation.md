# Web UI smoke tests and pytest consolidation

**Status:** ✅ Done (Wave 6 PR U)  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

### Missing web smoke tests

`routes/web.py` serves many admin pages; only index/accounts/filters/preview/rulesets had partial GET 200 coverage. Missing:

`/settings`, `/epg`, `/stations`, `/channel-health`, `/categories`, `/xtream`, `/ppv`

### Duplicate pytest modules/fixtures

- `tests/test_app.py` vs `tests/test_app_routes.py` — overlapping page smoke tests and `sample_account` fixtures
- `tests/test_app.py` vs `tests/test_accounts_routes.py` vs `tests/test_validation.py` — duplicate account-create tests
- `tests/epg/conftest.py` vs `tests/epg_service/conftest.py` — duplicate `test_epg_source` fixtures
- `tests/test_xmltv_grabber.py` vs `tests/epg/test_xmltv_grabber.py` — confusing same basename, different scope
- `tests/test_schedules_direct.py` vs `tests/epg/test_schedules_direct.py` — same issue

### Stale config

- `.flake8` per-file-ignores for removed `migrate_tags.py`, `test_tags.py`
- `tests/test_epg_sync_orchestrator.py` references non-existent `test_epg_sync_integration.py`

## Affected files

- `tests/test_app_routes.py` (extend)
- Consolidate files listed above
- `.flake8`

## Proposed solution

1. Parametrized `test_admin_pages_return_200` for all `web.py` routes
2. Merge duplicate fixtures into root `conftest.py`
3. Deduplicate account tests by concern (CRUD vs validation)
4. Rename confusing duplicate test module basenames
5. Clean `.flake8` stale entries; fix broken test file references

## Acceptance criteria

- [x] All admin HTML pages have GET 200 smoke test
- [x] No duplicate `sample_account` / `test_epg_source` fixtures across packages
- [x] `.flake8` has no references to deleted files

## Test plan

Self-contained.

## Dependencies

None.

## Implementation (Wave 6 PR U)

- Added `ADMIN_PAGES` parametrized smoke test in `tests/test_app_routes.py` covering all 12 `web.py` routes
- Moved `test_epg_source` fixture to root `tests/conftest.py` (`sample_account` already consolidated in PR P)
- Removed duplicate page smoke tests from `tests/test_app.py`; removed `test_create_account` (covered by `tests/test_validation.py`)
- Deleted `tests/epg_service/conftest.py`; removed duplicate `test_epg_source` from `tests/epg/conftest.py`
- Renamed: `test_xmltv_grabber.py` → `test_xmltv_grabber_service.py`, `epg/test_xmltv_grabber.py` → `epg/test_xmltv_grabber_routes.py`, `test_schedules_direct.py` → `test_schedules_direct_client.py`, `epg/test_schedules_direct.py` → `epg/test_schedules_direct_sync.py`
- Cleaned `.flake8` stale per-file-ignores; fixed orchestrator docstring reference to `tests/epg/test_integration.py`
