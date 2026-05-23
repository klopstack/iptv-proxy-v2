# TODO 15: Facade Layer Consolidation

**Priority:** P3  
**Status:** ✅ Done  
**Estimated scope:** Large (incremental)

---

## Problem

The restructuring left **backward-compatibility facade modules** that re-export from new packages:

| Facade | Delegates to |
|--------|-------------|
| `services/epg_service.py` | `services/epg/*` |
| `services/ppv_epg_service.py` | `services/ppv/epg.py` |
| `services/ppv_visibility_service.py` | `services/ppv/visibility.py` |
| `services/ppv_event_extractor.py` | `services/ppv/extraction.py` |
| `services/ppv_calendar_enrichment_service.py` | `services/ppv/enrichment.py` |
| `services/enhanced_ppv_matcher.py` | `services/ppv/matching/enhanced.py` |

This causes:
- Dual import paths (`from services.ppv.visibility import ...` vs `from services.ppv_visibility_service import ...`)
- Large facade files that look like implementations but aren't
- Confusion for new contributors

---

## Goal

Standardize on package imports; deprecate and eventually remove facade files.

---

## Proposed approach

### Phase 1: Inventory imports

```bash
rg "from services\.epg_service import" --glob "*.py"
rg "from services\.ppv_visibility_service import" --glob "*.py"
# etc.
```

### Phase 2: Update consumers

Replace facade imports with direct package imports in:
- `routes/`
- `services/`
- `tests/`

Example:
```python
# Before
from services.ppv_visibility_service import PPVVisibilityService

# After
from services.ppv.visibility import PPVVisibilityService
```

### Phase 3: Add deprecation warnings

In each facade module:

```python
import warnings
warnings.warn(
    "Import from services.ppv.visibility instead",
    DeprecationWarning,
    stacklevel=2,
)
```

### Phase 4: Remove facades

Once grep shows zero internal usage, delete facade files or reduce to 3-line re-exports for one release cycle.

---

## Files to modify

All consumers found in Phase 1 inventory, plus facade files themselves.

Priority order (smallest facades first):
1. `ppv_visibility_service.py` (2 lines)
2. `ppv_event_extractor.py`
3. `enhanced_ppv_matcher.py`
4. `ppv_epg_service.py`
5. `ppv_calendar_enrichment_service.py`
6. `epg_service.py` (largest — `EpgService` class facade)

---

## Acceptance criteria

- [x] Zero facade imports in `routes/` and `services/` (tests may lag one PR)
- [x] DEVELOPER_GUIDE documents canonical import paths
- [x] Facade files removed or marked deprecated with removal version
- [x] Full test suite passes

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
rg "ppv_visibility_service|epg_service import EpgService" routes/ services/
```

---

## Out of scope

- Removing `EpgService` class entirely — may keep as thin alias in `services/epg/__init__.py`

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Migrated routes/services/tests to package imports; EpgService moved to services/epg/facade.py; legacy facade modules kept with DeprecationWarning |
