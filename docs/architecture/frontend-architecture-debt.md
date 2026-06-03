# Frontend Architecture Debt

**Audit:** Application-wide audit, June 2026  
**Status:** Draft for review

## Two-tier JavaScript codebase

| Tier | Location | Quality |
|------|----------|---------|
| **Modern ESM** | `static/js/lib/`, `static/js/pages/` | Linted, Vitest-covered (~9 test files) |
| **Legacy globals** | `static/js/epg_*.js`, `match_rules_*.js` | Unlinted, untested, duplicated helpers |

`templates/epg_management.html` loads **17 script tags** (~1407 line template) — largest admin UI surface.

## Duplication map

```
utils.js (escapeHtml) ──should replace──► epg_common.js, match_rules_common.js, epg_sources.js
lib/epg_datetime.js ──should replace──► base.html inline parseUtc/formatUtc
lib/account_select.js (proposed) ──should replace──► loadAccounts() x3
```

## Security

Legacy `innerHTML` with API data — XSS risk (TODO 83). TagSelector in `base.html` renders tag names unsafely.

Admin UI has no in-app login page — access is via Traefik + Authentik (see admin-auth doc).

## Testing gaps

| Covered | Not covered |
|---------|-------------|
| lib helpers, partial preview | All epg_*.js, match_rules_*.js, preview_channels_page.js |
| | epg_sync_progress_poll.js (indirect only) |
| | Admin page smoke tests (TODO 86) |

Vitest uses `environment: 'node'`; `jsdom` installed but unused.

## ESLint scope

Runs on `templates/**`, `static/js/lib`, `pages/` — **legacy bundles excluded** (~80% of admin JS LOC).

## Migration strategy (TODO 85)

1. **Dedup helpers** — escapeHtml, datetime, loadAccounts
2. **One tab at a time** — migrate epg_management tabs to ESM `pages/`
3. **Expand ESLint** to migrated code only
4. **Reduce script tags** — single bootstrap per page

## CDN dependencies

Bootstrap/icons from cdn.jsdelivr.net in `base.html` — supply chain / offline consideration.

## Related TODOs

- **83** — XSS audit
- **85** — dedup + migration
- **86** — web smoke tests
- Completed **16**, **32** — partial Vitest expansion; legacy debt remains
