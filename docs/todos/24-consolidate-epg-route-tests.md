# TODO 24: Consolidate Overlapping EPG Route Tests

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Large (test refactor only)

---

## Problem

Three test modules cover the same EPG HTTP surface with **duplicated test classes**:

| File | Lines | Overlapping classes |
|------|-------|---------------------|
| `tests/test_epg_routes.py` | ~1,267 | `TestEpgSources`, `TestEpgMappings`, `TestEpgCoverage` |
| `tests/test_epg_routes_comprehensive.py` | ~459 | `TestEpgSourcesBasic`, `TestEpgMappingsBasic`, `TestEpgCoverage`, `TestSyncSdChannelsHelper`, `TestSchedulesDirectAuth` |
| `tests/test_epg_comprehensive.py` | ~1,007 | `TestEpgSourcesCRUD`, `TestEpgMappings`, `TestEpgCoverage`, `TestSyncSdChannelsHelper`, `TestSchedulesDirectAuth` |

### Symptoms

- Same endpoints tested 2–3× with slightly different fixtures
- Fixture setup duplicated across files (~200+ lines each)
- CI collects **2,156 tests**; EPG route overlap adds minutes without proportional bug detection
- Failures require fixing the same assertion in multiple files
- Naming (`comprehensive`, `Basic`, no suffix) does not indicate unique scope

### What is NOT duplicate (keep)

| Module | Unique value |
|--------|--------------|
| `tests/test_epg_match_rules.py` | Match rules service + FCC patterns (~2,100 lines) |
| `tests/test_epg_generation.py` | EPG generation unit tests |
| `tests/test_epg_programs.py` | Program parsing |
| `tests/test_epg_sync_service.py` | Sync service |
| `tests/test_channel_output_parity.py` | M3U/EPG parity contracts |

---

## Goal

One canonical EPG route test module per **domain area**, with shared fixtures in `conftest.py`, eliminating duplicate HTTP setup.

---

## Proposed solution

### Target structure

```
tests/
  epg/
    __init__.py
    conftest.py              # EPG-specific fixtures (sources, mappings, SD mock)
    test_sources_routes.py   # CRUD for EPG sources
    test_mappings_routes.py  # Channel mapping endpoints
    test_schedules_direct.py # SD auth + sync helpers (merge unique parts)
    test_coverage_routes.py  # Coverage reporting endpoints
```

Or flat naming if subpackage is undesirable:

```
tests/test_epg_sources_routes.py
tests/test_epg_mappings_routes.py
...
```

### Step 1: Inventory unique assertions

For each duplicate class triple, diff test bodies:

```bash
# Example: list tests in each mappings class
rg "def test_" tests/test_epg_routes.py tests/test_epg_routes_comprehensive.py tests/test_epg_comprehensive.py -n
```

Classify each test:
- **Keep one** — identical behavior
- **Merge** — complementary edge cases → single parametrized test
- **Move** — belongs in service unit test, not route test

### Step 2: Extract shared fixtures

Move to `tests/conftest.py` or `tests/epg/conftest.py`:
- Sample EPG source (provider, SD, XMLTV grabber)
- Account with channels + mappings
- Mock Schedules Direct responses (already partially in `test_schedules_direct.py`)

### Step 3: Delete redundant files

After migration, delete:
- `tests/test_epg_routes_comprehensive.py` (likely fully subsumed)
- Reduce `tests/test_epg_comprehensive.py` to only tests not covered elsewhere, then delete remainder

Keep `tests/test_epg_routes.py` only if renamed to domain split — do not leave empty shell.

### Step 4: Coverage gate check

```bash
venv/bin/pytest tests/ --cov=. --cov-report=term-missing | tail -20
```

Must stay ≥75%. Replace deleted mock-only tests with one meaningful integration test per endpoint if coverage drops.

---

## Dependencies

- **After:** TODO 07 (test DB isolation — stable CI during refactor)
- **Independent of:** TODO 25 (service test split — different files)
- **Related:** TODO 11 (test hygiene patterns)

---

## Files to modify

| File | Action |
|------|--------|
| `tests/test_epg_routes.py` | Split/rename or merge into domain files |
| `tests/test_epg_routes_comprehensive.py` | Delete after merge |
| `tests/test_epg_comprehensive.py` | Delete or reduce to unique tests |
| `tests/conftest.py` | Add shared EPG route fixtures |
| `tests/epg/` (new) | Optional subpackage |

---

## Acceptance criteria

- [ ] No duplicate test class names across EPG route test files
- [ ] Each EPG route blueprint endpoint has ≥1 meaningful test (not mock-only status check)
- [ ] Total test count reduced by ≥15% in EPG route area without coverage drop below 75%
- [ ] Full suite passes: `venv/bin/pytest tests/ -q --no-cov`

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
venv/bin/pytest tests/ --cov=routes/epg --cov-report=term-missing
```

---

## Simplifications unlocked (after completion)

- Faster CI — fewer duplicate HTTP round-trips
- Single place to update when EPG routes change (TODO 31 provider deprecation)
- Easier to add parity-adjacent route tests next to `test_channel_output_parity.py`

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
