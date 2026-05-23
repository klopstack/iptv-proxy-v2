# TODO 34: Post-Cleanup Simplifications

**Priority:** P3  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (after TODOs 22–33)

---

## Problem

Several simplifications are **unsafe until** backward-compat shims, test duplication, and semantic ambiguities are resolved. This document tracks **final consolidation** work once the second-pass audit items land.

---

## Goal

Reduce layers, lines, and conceptual overhead after TODOs 22–33 complete.

---

## Simplification items

### 1. Shrink or remove `EpgService` facade class

**Current:** `services/epg/facade.py` (~432 lines) delegates to submodules.

**After TODO 23:** Replace with exports in `services/epg/__init__.py`:

```python
from services.epg.generation import generate_epg_for_channels
from services.epg.facade import EpgService  # optional alias, deprecated
```

**Target:** New code imports functions directly; `EpgService` class deleted or 20-line alias.

---

### 2. Simplify `FilterService.apply_filters_to_channels`

**After TODO 27:** If Option A chosen (live filters only):

- Remove `is_visible` pre-filter step
- `compute_visibility_for_account` becomes optional admin cache, not playlist gate
- Delete duplicate PPV placeholder pattern list

**Estimated reduction:** ~30 lines + clearer model.

---

### 3. Collapse Xtream channel helpers

**After TODO 29:** `routes/xtream.py` should call CQS exclusively:

```python
channels = ChannelQueryService.channels_for_account(account_id)
# not: get_channels_for_account → internal filter → ppv
```

Remove unused imports of `FilterService`, `PPVVisibilityService` from xtream routes.

---

### 4. Trim `vulture_whitelist.py`

**After TODOs 23, 28:** Remove whitelists for:
- Deleted shim modules
- `PlaylistConfigUpdateSchema` (now used)
- Decorator-registered routes that stabilize

**Target:** <150 lines; document remaining entries.

---

### 5. Clean `pyproject.toml` coverage omit list

Remove entries for scripts that no longer exist (e.g., orphaned root test files mentioned in old coverage config).

Verify omit list matches actual repo layout.

---

### 6. Consolidate PPV test file names

**After TODO 23:** Single test module per PPV submodule:

```
tests/ppv/
  test_visibility.py
  test_epg.py
  test_enrichment.py
  test_matching.py
```

Delete redundant `test_ppv_visibility.py` vs `test_ppv_visibility_service.py` overlap if both exist.

---

### 7. Optional: Preview via single CQS method

**After TODO 17 ✅ + 29:** Add if preview routes still duplicate SQL:

```python
ChannelQueryService.preview_for_account(
    account_id, search=, category=, tags=, offset=, limit=
)
```

Deletes parallel query building in `routes/accounts.py` and `routes/api.py`.

---

### 8. Integer ID config routes sunset

**After TODO 28 (slug column):** Document deprecation timeline for:
- `/playlist/config/<int:id>.m3u`
- `/epg/config/<int:id>.xml`

Eventually redirect to slug URLs only.

---

## Dependencies

**Blocked until:**

| Simplification | Requires |
|----------------|----------|
| EpgService shrink | TODO 23, 25 |
| FilterService simplify | TODO 27 |
| Xtream cleanup | TODO 29 |
| vulture trim | TODO 23, 28 |
| PPV test consolidate | TODO 23, 25 |
| Preview CQS method | TODO 29 (optional) |
| ID route sunset | TODO 28 |

---

## Acceptance criteria

- [ ] Each item above either completed or explicitly deferred with reason
- [ ] Net reduction ≥500 lines across services/routes (excluding tests)
- [ ] Full suite passes; coverage ≥75%
- [ ] DEVELOPER_GUIDE updated with simplified import patterns

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
venv/bin/pytest tests/ --cov=. --cov-report=term-missing | tail -5
```

---

## Recommended order within this todo

1. vulture + pyproject cleanup (low risk)
2. Xtream + FilterService simplification
3. EpgService facade shrink
4. Preview CQS method (if still needed)
5. ID route sunset (product decision)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
