# TODO 23: Remove Backward-Compatibility Shim Modules

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (delete + grep cleanup)

---

## Problem

TODO 15 migrated all **production** imports to package paths (`services.ppv.visibility`, `services.epg`, etc.) but left **deprecation shim modules** that re-export with `DeprecationWarning`:

| Shim module | Canonical import |
|-------------|------------------|
| `services/epg_service.py` | `services.epg` / `services.epg.facade` |
| `services/ppv_epg_service.py` | `services.ppv.epg` |
| `services/ppv_visibility_service.py` | `services.ppv.visibility` |
| `services/ppv_event_extractor.py` | `services.ppv.extraction` |
| `services/ppv_calendar_enrichment_service.py` | `services.ppv.enrichment` |
| `services/enhanced_ppv_matcher.py` | `services.ppv.matching.enhanced` |
| `models/_core.py` | `models` package / domain modules |

### Why this is debt

- **Zero production imports** remain (`rg` confirms routes/services use package paths)
- Shims inflate file count and confuse grep/code search
- Test files still use **legacy names** (`test_ppv_visibility_service.py`, `test_enhanced_ppv_matcher.py`) though they import canonical paths — naming drift
- `vulture_whitelist.py` whitelists symbols only needed because shims exist

### Related deprecated API surface (same theme)

| Symbol | Location | Status |
|--------|----------|--------|
| `account_xml_cache` param | `services/epg/generation.py`, `services/epg/facade.py` | Ignored at runtime; kept for signature compat |
| `POST /api/epg/match/<account_id>` | `routes/epg/channels.py` | Redirects to `match-with-rules`; no `Deprecation` header |
| `unmapped_only` query param | `routes/epg/channels.py` | Maps to `view_mode=unmapped` |
| Legacy account credentials | `models/account.py`, `ConnectionManager` | **Intentional** — keep until multi-credential migration complete |
| ID-based config routes | `/playlist/config/<int:id>.m3u` | Canonical slug routes exist; ID routes kept for bookmarks |

---

## Goal

Delete unused shim modules and trim deprecated API parameters/endpoints **after** confirming no external consumers. Document sunset for intentional legacy paths (account credentials, ID routes).

---

## Proposed solution

### Phase 1: Verify zero consumers

```bash
rg "from services\.(epg_service|ppv_epg_service|ppv_visibility_service|ppv_event_extractor|ppv_calendar_enrichment|enhanced_ppv_matcher)" --glob "*.py"
rg "from models\._core|import models\._core" --glob "*.py"
rg "account_xml_cache" --glob "*.py"
```

If any hits remain in app code, migrate before deletion.

### Phase 2: Delete shim modules

Remove the six `services/*_service.py` facade files and `models/_core.py`.

Export anything still needed from:
- `services/epg/__init__.py` — re-export `EpgService`, constants
- `models/__init__.py` — already re-exports all models

### Phase 3: Remove `account_xml_cache` parameter

Delete parameter from `generate_epg_for_channels` and `EpgService.generate_epg_for_channels`. Remove `tests/test_epg_generation.py::test_with_account_xml_cache`.

### Phase 4: Deprecated EPG match endpoint

Options (pick one):
- **A:** Return `410 Gone` with JSON pointing to `match-with-rules`
- **B:** Keep redirect but add `Deprecation: true` and `Link` headers
- **C:** Remove endpoint after grep confirms no UI/JS callers

Search `static/js/` and templates for `/api/epg/match/` (without `-with-rules`).

### Phase 5: Rename misnamed test files (optional same PR)

| Current | Suggested |
|---------|-----------|
| `test_ppv_visibility_service.py` | `test_ppv_visibility.py` (merge with existing?) |
| `test_enhanced_ppv_matcher.py` | merge into `tests/test_ppv_matching/` |
| `test_ppv_epg_service.py` | `test_ppv_epg.py` |
| `test_ppv_event_extractor.py` | `test_ppv_extraction.py` |
| `test_ppv_calendar_enrichment_service.py` | merge into enrichment route tests |

Avoid duplicate files — consolidate if two files test the same module.

### Phase 6: Trim `vulture_whitelist.py`

Remove whitelist entries for deleted shims.

---

## Dependencies

- **After:** TODO 22 (docs synced)
- **Before:** TODO 34 (post-cleanup simplifications)
- **Independent of:** legacy account credentials (do not remove)

---

## Files to modify

| File | Changes |
|------|---------|
| `services/epg_service.py` | Delete |
| `services/ppv_*.py` (5 facade files) | Delete |
| `models/_core.py` | Delete |
| `services/epg/generation.py` | Remove `account_xml_cache` |
| `services/epg/facade.py` | Remove `account_xml_cache` |
| `routes/epg/channels.py` | Sunset deprecated match endpoint |
| `tests/test_epg_generation.py` | Remove deprecated param test |
| `tests/test_*` (PPV named files) | Rename/consolidate |
| `vulture_whitelist.py` | Trim |
| `docs/DEVELOPER_GUIDE.md` | Remove shim import examples |

---

## Acceptance criteria

- [ ] Six facade shim modules deleted; tests pass importing only package paths
- [ ] `models/_core.py` deleted; no import errors
- [ ] `account_xml_cache` removed from signatures and docs
- [ ] Deprecated EPG match endpoint handled (headers, removal, or documented sunset)
- [ ] Legacy account credential path still works (existing `test_connection_manager.py` passes)
- [ ] `rg` shows zero imports of deleted modules

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
rg "epg_service import|ppv_visibility_service|models\._core|account_xml_cache" routes/ services/ tests/
npm run lint  # if JS callers changed
```

---

## Out of scope

- Removing legacy username/password fields on `Account` model
- Removing integer ID playlist/EPG routes (document only; separate product decision)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
