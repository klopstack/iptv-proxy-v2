# Frontend helper deduplication and ESM migration plan

**Status:** 🟡 Phase 1 complete (PR #33); phases 2–3 tabs 1–3 ✅ [99](./99-esm-tab-migration-and-eslint.md); tabs 4–6 remain  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Legacy frontend has significant duplication untested by Vitest:

| Duplicated helper | Copies |
|-------------------|--------|
| `escapeHtml` | `utils.js`, `epg_common.js`, `match_rules_common.js`, `epg_sources.js`, inline |
| `loadAccounts()` + option building | 3+ legacy files |
| Datetime parse/format | `base.html` inline, `lib/epg_datetime.js` (tested), page-specific copies |

**Coverage gap:** ~20 legacy JS modules loaded by `epg_management.html` (877–714 LOC each) have zero Vitest coverage. ESLint runs on `lib/` + `pages/` only — legacy bundles excluded.

`templates/epg_management.html`: 1407 lines, 17 script tags — fragile load order.

## Affected files

- `static/js/epg_*.js`, `static/js/match_rules_*.js`
- `static/js/lib/`, `static/js/pages/`
- `templates/base.html`, `templates/epg_management.html`
- `docs/FRONTEND_JS.md`, `vitest.config.mjs`

## Proposed solution

**Phase 1 — Dedup without migration:** ✅ PR T
- Single `escapeHtml` in `lib/escape_html.js`; legacy pages via `base_bootstrap.js` / `epg_management_bootstrap.js`
- Shared `lib/account_select.js` for EPG management account fetch/populate
- `base.html` datetime via `epg_datetime.js` + `base_bootstrap.js`

**Phase 2 — Migrate epg_management tabs to ESM `pages/` modules** (one tab per PR)

**Phase 3 — Extend ESLint to migrated code only**

### Phase 2 tab migration order (priority)

| Order | Tab / area | Legacy bundle(s) | Notes |
|-------|------------|------------------|-------|
| 1 | EPG Sources | `epg_sources.js` | Sync progress already in `lib/`; good first ESM page module |
| 2 | Channel mappings | `epg_mappings.js`, `epg_manual_mapping.js` | Heavy `innerHTML`; pairs with TODO 83 |
| 3 | Match rules — rulesets & rules | `match_rules_rulesets.js`, `match_rules_rules.js` | Shares helpers already on `window` |
| 4 | Match rules — exclusions & name mappings | `match_rules_exclusions.js`, `match_rules_name_mappings.js` | |
| 5 | EPG channels / preview / XMLTV / Schedules Direct | `epg_channels.js`, `epg_preview.js`, `epg_xmltv.js`, `epg_schedules_direct.js` | |
| 6 | Reference data | `match_rules_reference.js` | Lowest churn |

### Template inline `escapeHtml` (Phase 2+)

Per-page inline copies remain in `index.html`, `ppv.html`, `stations.html`, etc. Consolidate when each page gets a `pages/*_bootstrap.js`.

## Acceptance criteria

- [x] One canonical `escapeHtml` used by migrated call sites (lib + window bridge; legacy EPG/match-rules deduped)
- [x] `base.html` datetime uses tested module (`parseUtcTimestamp` / `formatUtcTimestamp` via `base_bootstrap.js`)
- [x] Migration plan documented with tab priority order (above)

## Test plan

- [x] Existing Vitest suite passes
- [x] Tests for new shared modules: `escape_html.test.js`, `account_select.test.js`, `formatUtcTimestamp` / `parseUtcTimestamp` in `epg_common.test.js`

## Dependencies

- TODO 83 (XSS) should use shared escapeHtml — Phase 1 provides canonical `lib/escape_html.js`; PR S can fix call sites without redefining the helper
- See `docs/architecture/frontend-architecture-debt.md`

## Completion

- **PR #33 (Wave 6T):** Phase 1 — `lib/escape_html.js`, `lib/account_select.js`, `base_bootstrap.js`, bootstrap load-order fix, dedupe in `epg_common.js`, `match_rules_common.js`, `epg_sources.js`, `epg_sync_progress.js`

## Wave 9 continuation

Phases 2–3 (ESM tab migration + ESLint): [99-esm-tab-migration-and-eslint.md](./99-esm-tab-migration-and-eslint.md) — PR batch **Y**
