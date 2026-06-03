# Consolidate duplicate PPV detection tests

**Status:** ✅ Done ([PR #21](https://github.com/klopstack/iptv-proxy-v2/pull/21))  
**Priority:** P3  
**Audit:** PPV audit, June 2026

## Problem

PPV placeholder/category detection tests overlap significantly:

- `tests/epg_service/test_epg_ppv.py`
- `tests/ppv/test_visibility.py`
- `tests/test_tag_rule_is_ppv.py`

Same pattern lists are duplicated; updating `PPV_PLACEHOLDER_PATTERNS` requires editing multiple files.

Reverse matcher tests live under `tests/test_reverse_event_matcher/` while PPV tests are under `tests/ppv/` — easy to miss when changing PPV matching.

## Affected files

- `tests/epg_service/test_epg_ppv.py`
- `tests/ppv/test_visibility.py`
- `tests/test_tag_rule_is_ppv.py`
- New: `tests/ppv/test_detection.py` (parametrized)

## Proposed solution

1. Create `tests/ppv/test_detection.py` with parametrized cases for all detection helpers.
2. Reduce epg_service tests to import/re-export smoke only.
3. Cross-link reverse matcher integration tests in PPV architecture test plan.

## Acceptance criteria

- [x] Single parametrized source of truth for placeholder/category patterns.
- [x] No duplicate assertion blocks across three files.
- [x] CI runtime for PPV detection tests not increased materially.

## Completion

Implemented in [PR #21](https://github.com/klopstack/iptv-proxy-v2/pull/21): consolidated cases into `tests/ppv/test_detection.py`; `test_epg_ppv.py` reduced to import smoke; placeholder/title tests removed from `test_visibility.py` (visibility-only); cross-links to `tests/test_reverse_event_matcher/`. `test_tag_rule_is_ppv.py` unchanged (tag-rule tests, not detection duplicates).

## Test plan

Run full test suite; compare test count before/after.

## Dependencies

- TODO 53 (unify detection modules) should land first or in same PR.
