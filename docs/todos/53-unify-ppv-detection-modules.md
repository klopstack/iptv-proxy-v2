# Unify PPV detection into a single module

**Status:** ⬜ Not started  
**Priority:** P0  
**Audit:** PPV audit, June 2026

## Problem

PPV channel/category/placeholder detection exists in **two parallel modules**:

| Module | Used by |
|--------|---------|
| `services/ppv/detection.py` | `services/ppv/__init__.py` public API |
| `services/epg/ppv.py` | `enrichability.py`, `visibility.py`, `filter_service.py`, `services/epg/__init__.py` |

Both implement `is_ppv_channel`, `is_ppv_category`, and `is_ppv_placeholder_name` with nearly identical logic. Constants are shared via `services/epg/constants.py`, but the duplicate implementations can drift (e.g. logging, normalization).

Additionally, `services/reverse_event_matcher/orchestrator.py` has its own `_is_generic_channel` check that overlaps with `is_generic_channel_name` in `detection.py`.

## Affected files

- `services/ppv/detection.py` — canonical target
- `services/epg/ppv.py` — thin to re-exports or remove
- `services/ppv/enrichability.py`, `services/ppv/visibility.py`
- `services/filter_service.py`
- `services/epg/__init__.py`
- `services/reverse_event_matcher/orchestrator.py`
- `docs/DEVELOPER_GUIDE.md` — examples import legacy path

## Proposed solution

1. Make `services/ppv/detection.py` the **single source of truth** for all PPV detection helpers.
2. Replace `services/epg/ppv.py` body with re-exports from `services.ppv.detection` (keep module temporarily for backward compat) or delete and update all imports.
3. Align reverse matcher generic-channel check with `is_generic_channel_name`.
4. Update docs and developer guide to reference `services.ppv.detection`.

## Acceptance criteria

- [ ] One implementation of each detection function.
- [ ] All callers import from `services.ppv.detection` (or `services.ppv` public API).
- [ ] No behavioral change in existing detection tests.

## Test plan

- Run `tests/ppv/test_visibility.py`, `tests/epg_service/test_epg_ppv.py`, `tests/test_tag_rule_is_ppv.py`.
- Consolidate overlapping tests (see TODO 75).

## Dependencies

None.
