# TODO 30: Split `EpgMatchRulesService` Monolith

**Priority:** P3  
**Status:** ✅ Done  
**Estimated scope:** Large (multi-PR refactor)

---

## Problem

`services/epg_match_rules_service.py` is **~2,027 lines** — the largest remaining service module after EPG package split.

It mixes unrelated concerns:

| Concern | Examples in file |
|---------|------------------|
| CRUD for match rules / patterns | Pattern dataclasses, DB persistence |
| Channel exclusion logic | `should_exclude_channel`, `hide_channel` |
| FCC facility cache integration | Callsign lookups, city inference |
| Name normalization | Legacy fallback constants |
| Bulk matching orchestration | Account-wide rematch jobs |

`models/epg_match.py` already holds related models, but business logic stayed monolithic.

`tests/test_epg_match_rules.py` mirrors the monolith (~32 test classes) — changes require navigating both huge files.

### Antipattern indicators

- Legacy fallback constants at module top ("used when DB empty")
- Broad `try/except` blocks swallowing errors during FCC lookups
- Route layer (`routes/epg/match_rules.py`) is also large (~1,300 lines) — partial duplicate validation

---

## Goal

Split into focused modules under `services/epg/match_rules/` mirroring the models domain, keeping a thin facade for backward compatibility during migration.

---

## Proposed solution

### Target package layout

```
services/epg/match_rules/
  __init__.py          # Re-export public API
  patterns.py          # Pattern CRUD, dataclasses
  exclusion.py         # should_exclude_channel, hide_channel
  fcc_integration.py   # FCC cache lookups for matching
  normalization.py     # Name cleanup, legacy constants
  orchestrator.py      # Bulk rematch jobs
```

### Migration strategy (same as TODO 15)

1. **Extract** one concern per PR; leave re-export in `epg_match_rules_service.py`
2. **Update** routes to import from submodules
3. **Move** tests to `tests/epg/match_rules/test_*.py` incrementally
4. **Delete** monolith when re-exports unused

### Facade during transition

```python
# services/epg_match_rules_service.py (temporary)
from services.epg.match_rules.exclusion import should_exclude_channel
from services.epg.match_rules.orchestrator import EpgMatchRulesService
```

Remove after TODO 23-style grep confirms zero old imports.

### Route layer follow-up (optional)

Extract JSON serialization helpers from `routes/epg/match_rules.py` into service layer — separate PR.

---

## Dependencies

- **After:** TODO 25 (test split patterns established)
- **Parallel with:** TODO 24 (EPG routes — different layer)
- **Related:** TODO 14 ✅ (models split precedent)

---

## Files to modify

| File | Changes |
|------|---------|
| `services/epg_match_rules_service.py` | Incrementally shrink |
| `services/epg/match_rules/` | New package |
| `routes/epg/match_rules.py` | Update imports |
| `tests/test_epg_match_rules.py` | Split by submodule |
| `docs/DEVELOPER_GUIDE.md` | Document new import paths |

---

## Acceptance criteria

- [x] No single file >600 lines in match rules package
- [x] `EpgMatchRulesService` public API unchanged for routes (behavior parity)
- [x] All `test_epg_match_rules.py` tests pass (possibly relocated)
- [x] Legacy constants documented or moved to DB-only configuration

---

## Test plan

```bash
venv/bin/pytest tests/test_epg_match_rules.py tests/test_fcc_patterns.py -v --no-cov
venv/bin/pytest tests/ -q --no-cov
```

---

## Simplifications unlocked

- FCC integration testable in isolation
- Match rules UI changes touch smaller modules
- Enables future removal of legacy fallback constants when DB always populated

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Split into `services/epg/match_rules/` (patterns, exclusion, normalization, fcc_integration, matching, orchestrator); thin shim at `services/epg_match_rules_service.py` |
