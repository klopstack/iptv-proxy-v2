# TODO 32: Expand Frontend JavaScript Test Coverage

**Priority:** P3  
**Status:** ✅ Complete  
**Estimated scope:** Medium

---

## Problem

TODO 16 established Vitest with **2 test files** for **18 JS modules**:

| Tested | Untested (high complexity) |
|--------|----------------------------|
| `static/js/__tests__/utils.test.js` | `epg_common.js`, `epg_sources.js`, `epg_preview.js` |
| `static/js/__tests__/preview_channels.test.js` | `match_rules_common.js`, `match_rules_reference.js`, `match_rules_name_mappings.js` |

Complex UI logic lives in:
- EPG management (~multi-file workflow)
- Match rules editor (FCC patterns, name mappings)
- Preview channels (partially tested)

### Risk

- Refactors to `static/js/epg_*.js` break admin workflows silently
- Python route tests do not exercise client-side validation or URL building
- ESLint catches syntax only, not behavior

### TODO 16 marked ✅ with minimal scope

The completion note said "minimal coverage" — this todo extends that baseline.

---

## Goal

Extract **pure functions** from complex JS modules and cover them with Vitest; target 50%+ of non-trivial JS logic in unit tests.

---

## Proposed solution

### Phase 1: Inventory extractable functions

Per file, list pure helpers:

| Module | Candidates |
|--------|------------|
| `epg_common.js` | Date formatting, XMLTV id normalization |
| `epg_sources.js` | Source type field visibility toggles |
| `match_rules_common.js` | Pattern validation, priority sorting |
| `match_rules_name_mappings.js` | Mapping key normalization |
| `preview_channels.js` | Remaining untested URL builders |

### Phase 2: Extract without changing behavior

Move functions to bottom of same file with `export` for tests, or split to `static/js/lib/*.js`.

Avoid big-bang template rewrites — incremental extraction.

### Phase 3: Add Vitest files

```
static/js/__tests__/
  epg_common.test.js
  epg_sources.test.js
  match_rules_common.test.js
  preview_channels.test.js  # extend existing
```

### Phase 4: CI

Ensure `.github/workflows/build.yml` runs `npm test` (TODO 16 may have added — verify).

### Phase 5: Provider EPG warning (TODO 31)

If TODO 31 adds client-side deprecation banner, test warning visibility in `epg_sources.test.js`.

---

## Dependencies

- **After:** TODO 16 ✅ (Vitest setup)
- **Related:** TODO 31 (EPG sources UI)
- **Independent of:** backend todos

---

## Files to modify

| File | Changes |
|------|---------|
| `static/js/epg_*.js` | Extract pure functions |
| `static/js/match_rules_*.js` | Extract pure functions |
| `static/js/__tests__/*.test.js` | New tests |
| `package.json` | Ensure test script runs all |
| `.github/workflows/build.yml` | Verify npm test step |

---

## Acceptance criteria

- [x] ≥4 JS test files (double TODO 16 baseline)
- [x] Critical pure functions covered: escapeHtml, preview URL building, match rule validation
- [x] `npm test` passes locally and in CI
- [x] No regression in templates (manual smoke: preview page, EPG management)

---

## Test plan

```bash
npm test
npm run lint
```

---

## Out of scope

- Playwright E2E (Option B from TODO 16)
- Testing inline `<script>` blocks still embedded in templates

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Extracted pure helpers to `static/js/lib/`; 5 Vitest files / 53 tests; EPG lib shim in `epg_management.html` |
