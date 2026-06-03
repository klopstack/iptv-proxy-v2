# Frontend helper deduplication and ESM migration plan

**Status:** ⬜ Not started  
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

**Phase 1 — Dedup without migration:**
- Single `escapeHtml` export; legacy pages load via existing bootstrap
- Shared `lib/account_select.js`
- Replace `base.html` inline datetime with `epg_datetime.js`

**Phase 2 — Migrate epg_management tabs to ESM `pages/` modules** (one tab per PR)

**Phase 3 — Extend ESLint to migrated code only**

## Acceptance criteria

- [ ] One canonical `escapeHtml` used by migrated call sites
- [ ] `base.html` datetime uses tested module
- [ ] Migration plan documented with tab priority order

## Test plan

- Existing Vitest suite passes
- Add tests for any new shared modules

## Dependencies

- TODO 83 (XSS) should use shared escapeHtml
- See `docs/architecture/frontend-architecture-debt.md`
