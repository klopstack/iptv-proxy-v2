# TODO 11: Test Hygiene

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Medium

---

## Problem

### 26 skipped legacy tests

Tests marked skip for removed APIs — they add noise and false sense of coverage:

```
tests/test_epg_comprehensive.py     — Legacy /api/epg/ppv/* routes (4)
tests/test_epg_routes_comprehensive.py — same (2)
tests/test_epg_service.py           — Legacy get_ppv_epg_xmltv (4)
tests/test_epg_service.py           — Legacy update_ppv_channel_visibility (8)
tests/test_ppv_visibility.py        — Legacy is_visible mutation (5)
tests/test_ppv_visibility.py        — Legacy name-based PPV EPG (3)
```

Replacements exist in `tests/test_ppv_integration.py`.

### Duplicate fixtures

~18 test files define their own `test_account` fixture instead of using shared `conftest.py` fixtures.

### Commented-out tests

`tests/test_playlist_generation.py` has disabled slug/disabled-config tests — either fix or delete.

---

## Goal

Leaner test suite: remove dead tests, consolidate fixtures, restore or delete commented tests.

---

## Proposed solution

### Phase 1: Delete skipped legacy tests

Remove skipped test **functions** entirely (not just the skip decorator). Verify replacement coverage in:
- `tests/test_ppv_integration.py`
- `tests/test_ppv_epg_service.py`
- `tests/test_ppv_visibility_service.py`

### Phase 2: Consolidate fixtures in conftest.py

Add to `tests/conftest.py`:

```python
@pytest.fixture
def test_account(app):
    """Standard enabled account with credentials."""
    ...

@pytest.fixture
def test_account_with_channels(app, test_account, test_category):
    ...
```

Remove duplicate definitions from individual test files **incrementally** (one file per commit to ease review).

Files with duplicate `test_account` (from audit):
- `test_xtream.py`, `test_coverage_boost.py`, `test_routes_coverage.py`, `test_accounts_routes.py`, etc.

**Note:** Some fixtures have file-specific variations (e.g. `test_xtream.py` yields ORM object vs ID). Standardize on one pattern — prefer yielding IDs or using factory functions.

### Phase 3: Commented-out tests

In `test_playlist_generation.py`:
- Restore tests if still valid after TODO 05 proxy default change
- Or delete commented blocks with note in commit message

---

## Files to modify

| File | Action |
|------|--------|
| `tests/test_epg_comprehensive.py` | Remove 4 skipped tests |
| `tests/test_epg_routes_comprehensive.py` | Remove 2 skipped tests |
| `tests/test_epg_service.py` | Remove 12 skipped tests |
| `tests/test_ppv_visibility.py` | Remove 8 skipped tests |
| `tests/conftest.py` | Add shared fixtures |
| Various test files | Remove duplicate fixtures |
| `tests/test_playlist_generation.py` | Restore or delete commented tests |

---

## Acceptance criteria

- [x] Zero `@pytest.mark.skip` for "Legacy" removed APIs
- [x] `pytest --collect-only` shows ~26 fewer tests (or replaced with active tests)
- [x] All remaining tests pass
- [x] At least 5 major test files use conftest `test_account`
- [x] No large blocks of commented-out test code remain

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
venv/bin/pytest tests/ --collect-only -q | tail -1  # compare test count
```

---

## Out of scope

- Coverage test audit (TODO 13)
- Parity tests (TODO 08)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Removed 26 skipped legacy PPV tests; added shared `test_account`, `test_category`, and `test_account_with_channels` fixtures to conftest; deduplicated fixtures in 7 test files; deleted commented slug/disabled-config tests (slug support not yet implemented). 2340 tests collected, all passing. |
