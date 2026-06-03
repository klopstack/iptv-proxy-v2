# ESM tab migration and ESLint (TODO 85 phases 2–3)

**Status:** ✅ Complete (tabs 1–3 + ESLint)  
**Priority:** P2  
**Parent:** [85-frontend-deduplication-and-esm-migration.md](./85-frontend-deduplication-and-esm-migration.md) (phase 1 ✅ PR #33)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **Y**

## Summary

Migrate `epg_management.html` tabs from legacy script bundles to ESM `static/js/pages/` modules (one tab per PR where needed), then extend ESLint coverage to migrated code.

## Problem

Phase 1 deduplicated `escapeHtml`, account select, and datetime helpers (PR #33). ~20 legacy JS modules (877–714 LOC each) still load via 17 script tags with fragile order and zero Vitest coverage. ESLint runs on `lib/` + `pages/` only — legacy bundles excluded.

## Affected files

- `templates/epg_management.html`
- `static/js/epg_*.js`, `static/js/match_rules_*.js` (retire incrementally)
- `static/js/pages/`, `static/js/lib/`
- `vitest.config.mjs`, ESLint config
- `docs/FRONTEND_JS.md`

## Proposed solution

Follow tab migration order from TODO 85 (phase 2):

| Order | Tab / area | Legacy bundle(s) |
|-------|------------|------------------|
| 1 | EPG Sources | `epg_sources.js` |
| 2 | Channel mappings | `epg_mappings.js`, `epg_manual_mapping.js` |
| 3 | Match rules — rulesets & rules | `match_rules_rulesets.js`, `match_rules_rules.js` |
| 4 | Match rules — exclusions & name mappings | `match_rules_exclusions.js`, `match_rules_name_mappings.js` |
| 5 | EPG channels / preview / XMLTV / Schedules Direct | `epg_channels.js`, etc. |
| 6 | Reference data | `match_rules_reference.js` |

**Phase 3:** Extend ESLint to `pages/` and migrated modules; fix violations in touched files.

Consolidate per-page inline `escapeHtml` in other templates when each page gets a `pages/*_bootstrap.js`.

## Acceptance criteria

- [x] At least tabs 1–3 migrated to ESM `pages/` modules with Vitest coverage for new modules
- [x] Legacy script tags removed for migrated tabs; load order documented in `FRONTEND_JS.md`
- [x] ESLint passes on migrated `pages/` code (config updated if needed)
- [x] Existing Vitest suite green; no admin UI regressions on migrated tabs

## Test plan

```bash
npm run test          # Vitest
npm run lint          # ESLint after phase 3
# Manual smoke: EPG management tabs 1–3
```

## Dependencies

- [85](./85-frontend-deduplication-and-esm-migration.md) phase 1 ✅ — `lib/escape_html.js`, bootstrap loaders
- [83](./83-xss-audit-legacy-frontend.md) ✅ — escaping patterns for `innerHTML` during tab 2 migration
- [32](./32-expand-frontend-js-tests.md) ✅ — Vitest baseline
- Independent of Wave 9 route splits; can run parallel to batch **W**/**X** if separate contributor

## Completion

- **PR #40:** https://github.com/klopstack/iptv-proxy-v2/pull/40
- Migrated: `epg_sources_page.js`, `epg_mappings_page.js`, `epg_manual_mapping_page.js`, `match_rules_rulesets_page.js`, `match_rules_rules_page.js`
- New lib helpers: `epg_dom_utils.js`, `epg_mappings_helpers.js`, `match_rules_rulesets_helpers.js`; `window.EpgManagementState` bridge in `epg_common.js`
