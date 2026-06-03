# XSS audit and hardening of legacy frontend JavaScript

**Status:** ✅ Done (Wave 6 PR S)  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Legacy admin JS uses `innerHTML` with API data in multiple places — stored/reflected XSS risk if a provider returns malicious channel names, tag names, or error messages:

| File | Issue |
|------|-------|
| `static/js/preview_channels_page.js` | Injects `account.name` unescaped |
| `static/js/epg_manual_mapping.js` | Injects `data.error` unescaped |
| `static/js/epg_sources.js` | Similar patterns |
| `templates/base.html` | `TagSelector` uses `innerHTML` for `tag.name` |

Tested ESM helpers in `static/js/lib/` and `utils.js` have `escapeHtml`, but legacy bundles duplicate their own implementations and often skip escaping.

## Affected files

- Listed above + grep for `innerHTML` across `static/js/` and `templates/`

## Proposed solution

1. Audit all `innerHTML` assignments with API-sourced strings
2. Use `textContent`, DOM APIs, or shared `escapeHtml` from `utils.js`
3. For error messages from API, escape before display
4. Add ESLint rule or grep check in CI for dangerous patterns (optional)

## Acceptance criteria

- [x] No unescaped provider/account/tag/error strings in innerHTML
- [x] TagSelector renders tag names safely
- [x] Document pattern in `docs/FRONTEND_JS.md`

## Test plan

- Vitest tests for escapeHtml edge cases (`<script>`, quotes)
- Manual smoke: channel name with `<` in preview page

## Dependencies

- TODO 84 (shared escapeHtml) reduces duplication long-term

## Implementation notes (PR S)

- `TagSelector` in `base.html`: DOM APIs for search dropdown; `escapeHtml` for selected badges/`data-tag-name`.
- Legacy EPG bundles (`epg_sources`, `epg_mappings`, `epg_manual_mapping`, `epg_channels`, `epg_xmltv`, `epg_schedules_direct`): API strings escaped; account/source `<option>` lists use `textContent`.
- `preview_channels_page.js`: account options via DOM; channel rows/errors escaped.
- `epg_common.js`: `escapeJsSingleQuoted()` for safe `onclick` string literals.
