# TODO 25: Refactor EPG Service Monolith and Phase-Era Tests

**Priority:** P2  
**Status:** ✅ Complete  
**Estimated scope:** Large (incremental over multiple PRs)

---

## Problem

### `test_epg_service.py` is unmaintainable

| Metric | Value |
|--------|-------|
| Lines | ~3,424 |
| Test classes | 36 |
| Overlap with | `test_epg_generation.py`, `test_epg_programs.py`, `test_epg_common_helpers.py` |

Many classes test logic now living in `services/epg/parsing.py`, `matching.py`, `generation.py`, etc. The file name implies a monolithic `EpgService` that no longer exists as a single implementation.

### Phase-era test files

Historical restructuring milestones left **misnamed modules**:

| File | Original intent | Current value |
|------|-----------------|---------------|
| `test_phase1_cleaned_names.py` | Cleaned name sync | Still valid — belongs in `test_tag_service` or `test_sync_service` |
| `test_phase2_filter_visibility.py` | Filter + `is_visible` | Valuable — 18 tests including filter CRUD recompute triggers |
| `test_phase4_database_first.py` | No live API fallback | Valid 503/sync guards |

Problems:
- "Phase N" names mean nothing to new contributors
- Duplicate fixtures (`filter_test_account`, `phase4_account`, etc.) vs `conftest.py`
- `test_phase2_filter_visibility.py::test_playlist_uses_is_visible` tests DB flag, not live filter re-application edge case (see TODO 27)

### Other low-signal test modules

| File | Issue |
|------|-------|
| `tests/test_recent_fixes.py` | Named for "issues 20–25"; duplicates tag/sync datetime tests |
| `tests/test_additional_routes.py` | Header: "reach 80% coverage"; mixes account-ruleset tests |
| `tests/test_playlist_generation.py` | Some tests mock deprecated `services.epg.EpgService` paths |

---

## Goal

Split EPG tests by **submodule**, rename phase tests by **domain**, and merge issue-numbered files into canonical locations.

---

## Proposed solution

### Part A: Split `test_epg_service.py` (incremental)

Target mapping:

| Current class prefix | New file |
|---------------------|----------|
| `TestParseXmltv*`, time shifting | `tests/test_epg_parsing.py` (extend existing or create) |
| `TestMatch*`, FCC helpers | `tests/test_epg_matching.py` |
| `TestGenerate*`, XMLTV output | extend `tests/test_epg_generation.py` |
| `TestEpgServiceFacade*` | `tests/test_epg_facade.py` (thin delegation tests only) |

Process per PR:
1. Move one class cluster
2. Run targeted pytest + full suite
3. Delete moved class from monolith
4. Stop when monolith empty → delete file

Dedup rule: if `test_epg_generation.py` already has `TestParseXmltvTime`, **merge** assertions; do not copy.

### Part B: Rename phase tests

| From | To |
|------|-----|
| `test_phase1_cleaned_names.py` | `test_cleaned_names.py` |
| `test_phase2_filter_visibility.py` | `test_filter_visibility.py` |
| `test_phase4_database_first.py` | `test_database_first_outputs.py` |

Move shared fixtures to `conftest.py`.

### Part C: Absorb misc files

| From | To |
|------|-----|
| `test_recent_fixes.py::TestDatetimeTimezoneIssue` | `test_tag_service.py` or `test_sync_service.py` |
| `test_recent_fixes.py` (remainder) | Domain files by subject |
| `test_additional_routes.py` | `test_accounts_routes.py` / `test_rulesets_api.py` |
| Delete `test_additional_routes.py` when empty |

### Part D: Fix playlist generation mocks

Replace patches of monolithic paths with:
- Real EPG generation via `services.epg.generation`
- Or shared fixtures from `test_channel_output_parity.py`

---

## Dependencies

- **After:** TODO 23 (shim removal clarifies import paths)
- **Parallel with:** TODO 24 (route tests — different files)
- **Feeds:** TODO 27 (add filter staleness test to `test_filter_visibility.py`)

---

## Files to modify

| File | Action |
|------|--------|
| `tests/test_epg_service.py` | Incrementally split; delete when empty |
| `tests/test_epg_generation.py` | Absorb generation tests |
| `tests/test_epg_programs.py` | Absorb program tests |
| `tests/test_phase*.py` | Rename + fixture dedup |
| `tests/test_recent_fixes.py` | Merge and delete |
| `tests/test_additional_routes.py` | Merge and delete |
| `tests/conftest.py` | Shared fixtures |

---

## Acceptance criteria

- [x] No file named `test_epg_service.py` (or <200 lines facade-only)
- [x] No files named `test_phase*.py`
- [x] `test_recent_fixes.py` and `test_additional_routes.py` deleted
- [x] No test imports from deleted shim modules
- [x] Full suite passes; coverage ≥75%

---

## Test plan

```bash
# After each incremental move:
venv/bin/pytest tests/test_epg_generation.py tests/test_epg_parsing.py -v --no-cov
venv/bin/pytest tests/ -q --no-cov
venv/bin/pytest tests/ --cov=services/epg --cov-report=term-missing
```

---

## Simplifications unlocked

- Faster navigation: one file per EPG submodule mirrors `services/epg/` layout
- New EPG features get tests colocated with implementation
- Phase/fix naming removed — onboarding reads cleaner test tree

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Split `test_epg_service.py` (3,424 lines) into `tests/epg_service/` (`test_epg_parsing.py`, `test_epg_matching.py`, `test_epg_ppv.py`, `test_epg_facade.py`; 139 tests). Renamed phase files → `test_cleaned_names.py`, `test_database_first_outputs.py` (phase2 already `test_filter_visibility.py`). Merged/deleted `test_recent_fixes.py` and `test_additional_routes.py`. Updated playlist EPG mocks to `services.epg.generation.generate_epg_for_channels`. Full suite: 2087 passed, 78.77% coverage. |
