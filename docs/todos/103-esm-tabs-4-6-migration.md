# ESM tab migration — tabs 4–6 and ESLint (TODO 85 phase 3)

**Status:** ✅ Complete (PR pending)  
**Priority:** P2  
**Parent:** [85-frontend-deduplication-and-esm-migration.md](./85-frontend-deduplication-and-esm-migration.md) (phase 2 → [99](./99-esm-tab-migration-and-eslint.md))  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **Y** (follow-on to PR #40)

## Summary

Migrate remaining `epg_management.html` tabs (4–6) from legacy script bundles to ESM `static/js/pages/` modules, retire the corresponding script tags, add Vitest coverage, and extend ESLint to all migrated `pages/` code.

## Problem

[TODO 99](./99-esm-tab-migration-and-eslint.md) / PR #40 completes phase 2 (tabs 1–3). Tabs 4–6 still load via legacy script tags with fragile order and no Vitest coverage. ESLint remains limited to already-migrated `pages/` until the final tab batch lands.

## Affected files

- `templates/epg_management.html`
- ~~`static/js/match_rules_exclusions.js`, `static/js/match_rules_name_mappings.js`~~ → `static/js/pages/match_rules_*_page.js`
- ~~`static/js/epg_channels.js`, `static/js/epg_preview.js`, `static/js/epg_xmltv.js`, `static/js/epg_schedules_direct.js`~~ → `static/js/pages/epg_*_page.js`
- ~~`static/js/match_rules_reference.js`~~ → `static/js/pages/match_rules_reference_page.js`
- ~~`static/js/match_rules_common.js`~~ → `static/js/pages/match_rules_common_page.js`
- `static/js/pages/`, `static/js/lib/`
- `vitest.config.mjs`, ESLint config
- `docs/FRONTEND_JS.md`

## Proposed solution

Follow tab migration order from TODO 85 (phase 3). One tab group per PR where needed.

| Order | Tab / area | Legacy bundle(s) |
|-------|------------|------------------|
| 4 | Match rules — exclusions & name mappings | `match_rules_exclusions.js`, `match_rules_name_mappings.js` |
| 5 | EPG channels / preview / XMLTV / Schedules Direct | `epg_channels.js`, `epg_preview.js`, `epg_xmltv.js`, `epg_schedules_direct.js` |
| 6 | Reference data | `match_rules_reference.js` |

**ESLint (folded from TODO 85 phase 4):** Extend ESLint config to cover all migrated `pages/` modules; fix violations in touched files. Legacy bundles excluded until retired.

Consolidate per-page inline `escapeHtml` in other templates when each page gets a `pages/*_bootstrap.js` (same deferral as TODO 99).

## Acceptance criteria

- [x] Tabs 4–6 migrated to ESM `pages/` modules with Vitest coverage for new modules
- [x] Legacy script tags removed for tabs 4–6; load order documented in `FRONTEND_JS.md`
- [x] ESLint passes on all migrated `pages/` code (config updated if needed)
- [x] Existing Vitest suite green; no admin UI regressions on tabs 4–6

## Test plan

```bash
npm run test          # Vitest — new page modules + regression
npm run lint          # ESLint on migrated pages/
# Manual smoke: EPG management tabs 4–6
#   4 — Match rules exclusions & name mappings (CRUD, filters)
#   5 — EPG channels, preview, XMLTV export, Schedules Direct
#   6 — Reference data tables / lookups
```

## Dependencies

- [99](./99-esm-tab-migration-and-eslint.md) / PR #40 merged first — tabs 1–3 ESM baseline and bootstrap patterns
- [85](./85-frontend-deduplication-and-esm-migration.md) phase 1 ✅ — `lib/escape_html.js`, bootstrap loaders
- [83](./83-xss-audit-legacy-frontend.md) ✅ — escaping patterns for `innerHTML` during tab migrations
- [32](./32-expand-frontend-js-tests.md) ✅ — Vitest baseline
- Independent of Wave 9 route splits; can run parallel to batch **W**/**X** if separate contributor

## Completion

- **PR #44:** https://github.com/klopstack/iptv-proxy-v2/pull/44 — Wave 9 TODO 103; retires 8 legacy bundles; adds `lib/epg_preview_helpers.js`, `lib/epg_channels_helpers.js`, `lib/match_rules_reference_helpers.js`
