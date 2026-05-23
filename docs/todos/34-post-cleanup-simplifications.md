# TODO 34: Post-Cleanup Simplifications

**Priority:** P3  
**Status:** ✅ Complete  
**Estimated scope:** Medium (after TODOs 22–33)

---

## Problem

Several simplifications are **unsafe until** backward-compat shims, test duplication, and semantic ambiguities are resolved. This document tracks **final consolidation** work once the second-pass audit items land.

---

## Goal

Reduce layers, lines, and conceptual overhead after TODOs 22–33 complete.

---

## Simplification items

### 1. Shrink or remove `EpgService` facade class ✅

- Moved legacy inline matching helpers to `services/epg/matching_legacy.py`
- Shrunk `services/epg/facade.py` to a thin delegator (~95 lines, was ~430)
- Production code now imports `sync_epg_source`, `generate_epg_for_channels`, `get_epg_coverage_stats`, etc. directly from submodules
- `EpgService` retained for existing tests only

### 2. Simplify `FilterService.apply_filters_to_channels` ✅

- Already completed in TODO 27 (live filters only)
- Removed duplicate `is_ppv_placeholder_name` helper; imports from `services.epg.ppv`

### 3. Collapse Xtream channel helpers ✅ (prior TODO 29)

- Xtream routes already use CQS exclusively; no FilterService/PPVVisibilityService imports
- Updated Xtream EPG redirect to prefer slug URLs

### 4. Trim `vulture_whitelist.py` ✅

- Removed stale `generate_ppv_epg_entries` and `get_ppv_epg_xmltv` entries
- **Deferred:** bulk trim to <150 lines — remaining entries are active vulture suppressions for Flask routes, SD dataclass fields, and ORM columns

### 5. Clean `pyproject.toml` coverage omit list ✅

- Removed 15 orphaned script/test paths that no longer exist

### 6. Consolidate PPV test file names ✅

- Created `tests/ppv/` with `test_visibility.py`, `test_epg.py`, `test_enrichment.py`, `test_matching.py`
- **Deferred:** `test_ppv_detection.py`, `test_ppv_extraction.py`, `test_ppv_integration.py`, `test_ppv_enrichment_routes.py` remain at `tests/` root (lower overlap; merge in a follow-up)

### 7. Optional: Preview via single CQS method ✅

- Added `ChannelQueryService.build_preview_channel_query()`, `preview_channels_for_account()`, `preview_channels_for_scope()`
- Refactored `routes/api.py` and `routes/accounts.py` preview endpoints to use shared CQS helpers

### 8. Integer ID config routes sunset ✅ (partial)

- Numeric config M3U/EPG routes 301-redirect to slug when available; `Deprecation` header set
- Documented slug-first policy in `DEVELOPER_GUIDE.md`
- **Deferred:** removing int routes entirely (breaking change — needs consumer audit)

---

## Dependencies

**Blocked until:**

| Simplification | Requires |
|----------------|----------|
| EpgService shrink | TODO 23, 25 ✅ |
| FilterService simplify | TODO 27 ✅ |
| Xtream cleanup | TODO 29 ✅ |
| vulture trim | TODO 23, 28 ✅ |
| PPV test consolidate | TODO 23, 25 ✅ |
| Preview CQS method | TODO 29 ✅ |
| ID route sunset | TODO 28 ✅ |

---

## Acceptance criteria

- [x] Each item above either completed or explicitly deferred with reason
- [x] Net reduction ≥500 lines across services/routes (excluding tests)
- [x] Full suite passes; coverage ≥75%
- [x] DEVELOPER_GUIDE updated with simplified import patterns

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
venv/bin/pytest tests/ --cov=. --cov-report=term-missing | tail -5
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Facade ~335 lines removed; preview SQL centralized in CQS; PPV tests moved to `tests/ppv/`; config int routes redirect to slug; vulture bulk trim deferred |
