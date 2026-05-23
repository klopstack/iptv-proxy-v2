# TODO 21: Remove Dead Channel Selection Code and Orphan Tests

**Priority:** P3  
**Status:** ✅ Done  
**Estimated scope:** Small (cleanup + test migration)

---

## Problem

After `ChannelQueryService` became the selection source of truth, legacy helpers and tests remain:

### Dead route code

| Symbol | File | Status |
|--------|------|--------|
| `_matches_tag_filter()` | `routes/playlists.py` | Defined but **never called** by routes; tag filtering lives in CQS |

### Stale todo index

| Document | Issue |
|----------|-------|
| `01-unify-epg-channel-selection.md` | Marked ⬜ but EPG routes already use CQS (verified post-TODO 08) |
| `02-unify-preview-channel-selection.md` | Marked ⬜ in README but ✅ in document body |

### Orphan / redundant tests

Tests that only exercise dead code or duplicate CQS coverage:

- `tests/test_playlists_routes.py` — `TestMatchesTagFilter` (tests `_matches_tag_filter`)
- `tests/test_coverage_boost.py` — `_matches_tag_filter` tests
- Overlap between `test_playlist_generation.py::test_epg_config_channel_set_matches_m3u` and TODO 08 parity module (keep one canonical location)

Leaving dead code creates false confidence that tag filtering is still maintained in two places.

---

## Goal

Remove unused selection logic from routes. Consolidate tests on `ChannelQueryService` and TODO 08 parity tests. Sync todo index statuses with reality.

---

## Proposed solution

### Step 1: Delete `_matches_tag_filter`

Remove function from `routes/playlists.py`.

### Step 2: Migrate or delete orphan tests

- Move any valuable tag-filter edge cases into `tests/test_channel_query_service.py` (if not already covered by TODO 04 tests)
- Delete `TestMatchesTagFilter` and coverage-boost duplicates

### Step 3: Deduplicate EPG parity tests

Keep config M3U/EPG parity in `tests/test_channel_output_parity.py`; remove redundant assertion from `test_playlist_generation.py` **or** reduce it to a thin re-export comment pointing to parity module.

### Step 4: Update todo 01 completion

Mark TODO 01 ✅ in index and document body with completion date and note that TODO 08 parity tests guard regressions.

---

## Dependencies

- **After:** TODO 08 (parity tests must exist before removing redundant tests)
- Can run in parallel with TODO 11 (test hygiene)

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | Remove `_matches_tag_filter` |
| `tests/test_playlists_routes.py` | Remove dead-code tests |
| `tests/test_coverage_boost.py` | Remove `_matches_tag_filter` tests |
| `tests/test_playlist_generation.py` | Deduplicate vs parity module |
| `docs/todos/01-unify-epg-channel-selection.md` | Mark ✅ complete |
| `docs/todos/README.md` | Sync statuses for 01, 02, 03 |

---

## Acceptance criteria

- [x] `_matches_tag_filter` removed; no references remain
- [x] Tag filter behavior still covered by `test_channel_query_service.py` and/or parity tests
- [x] No reduction in meaningful test coverage (coverage audit in TODO 13 may follow)
- [x] TODO 01 marked complete in index

---

## Test plan

```bash
venv/bin/pytest tests/test_channel_query_service.py tests/test_channel_output_parity.py tests/test_playlists_routes.py -v --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Removed dead `_matches_tag_filter`; migrated tag-filter edge cases to CQS unit tests; deduplicated config EPG/M3U parity test in favor of `test_channel_output_parity.py`. |
