# Frontend JavaScript conventions

This app mixes legacy inline/classic scripts in Jinja templates with newer ES modules under `static/js/`. Use the patterns below when adding or changing UI JavaScript.

## Directory layout

| Role | Location | How it is loaded |
|------|----------|------------------|
| Reusable helpers and API clients | `static/js/lib/*.js` | ES module (`import` / `export`) |
| Page bootstrap (attach libs to `window`) | `static/js/pages/{page}_bootstrap.js` | `<script type="module" src="{{ url_for('static', filename='js/pages/…') }}">` |
| Full page logic (preferred for new work) | `static/js/pages/*.js` or top-level `static/js/*_page.js` | module `src` only |
| EPG management tab modules (ESM) | `static/js/pages/epg_*_page.js`, `static/js/pages/match_rules_*_page.js` | `<script type="module">` after `epg_management_bootstrap.js` |
| Legacy EPG / match-rules bundles | `static/js/epg_common.js` only | classic `<script src>` (shared state + modals) |

## Page bootstrap pattern

Templates that still use large inline `<script>` blocks should **not** use inline `import` statements. ESLint’s HTML pipeline treats inline scripts as classic scripts (`sourceType: 'script'`), so inline `import`/`export` fails unless the block is disabled entirely.

Instead:

1. Add a small bootstrap module in `static/js/pages/` that imports from `lib/` and assigns to `window` for legacy callers.
2. Load it with `url_for`:

```html
<script type="module" src="{{ url_for('static', filename='js/pages/accounts_bootstrap.js') }}"></script>
<script>
  // classic inline script; use window.AccountApi, etc.
</script>
```

3. Initialize page logic in `DOMContentLoaded` (or use `defer` on the inline script) so `window.*` bridges from the module bootstrap are available before use.

Examples: `accounts_bootstrap.js`, `ppv_bootstrap.js`, `settings_bootstrap.js`, `epg_management_bootstrap.js`.

## Shared bridges

- **`escapeHtml`** — canonical implementation in `static/js/lib/escape_html.js`. Re-exported from `utils.js` for ESM pages. Exposed on `window` via `pages/base_bootstrap.js` (all admin pages) and `pages/epg_management_bootstrap.js` (legacy EPG/match-rules bundles). Legacy classic scripts must not define local copies; use the global after the bootstrap module runs.
- **`parseUtcTimestamp` / `formatUtcTimestamp`** — implemented in `static/js/lib/epg_datetime.js`, exposed on `window` by `base_bootstrap.js` for inline template scripts (replaces former inline helpers in `base.html`).
- **`AccountSelect`** (`fetchAccounts`, `populateAccountSelect`, `populateAccountSelects`) in `static/js/lib/account_select.js` — exposed on `window` by `epg_management_bootstrap.js` for legacy EPG/match-rules `loadAccounts()` call sites.
- **`installEpgSyncProgressOnWindow()`** in `static/js/lib/install_epg_sync_progress.js` — used by Settings and EPG Management to expose `window.EpgSyncProgress`.

Load order for EPG management (`epg_management.html`):

1. `mpegts.min.js`, `epg_common.js` (shared state, modals, `window.EpgManagementState` bridge)
2. `epg_management_bootstrap.js` (lib helpers on `window` for inline HTML and legacy bridges)
3. ESM tab modules in dependency order:
   - `epg_sources_page.js`, `epg_mappings_page.js`, `epg_manual_mapping_page.js`
   - `match_rules_common_page.js`, `match_rules_rulesets_page.js`, `match_rules_rules_page.js`
   - `match_rules_exclusions_page.js`, `match_rules_name_mappings_page.js`, `match_rules_reference_page.js`
   - `epg_channels_page.js`, `epg_xmltv_page.js`, `epg_schedules_direct_page.js`, `epg_preview_page.js`
4. Inline init (`DOMContentLoaded`)

Migrated tab modules import from `static/js/lib/` and assign handlers to `window` for inline HTML `onclick` and the template init block. Bootstrap modules run before `DOMContentLoaded`.

## Linting

- **HTML templates:** `eslint templates/**/*.html` (structure via `@html-eslint`, inline classic scripts via `eslint-plugin-html`).
- **ES modules:** `eslint static/js/lib static/js/pages` with `sourceType: 'module'`.
- **Do not** add `eslint-disable-next-script` for module imports; use external bootstrap files instead.
- ESM tab modules under `static/js/pages/*_page.js` are linted with `sourceType: 'module'`.
- Legacy non-module bundle remaining on EPG management: `epg_common.js` only.

## Escaping API data in `innerHTML`

Legacy admin scripts build HTML with template literals. **Any string from the API** (account/channel/tag names, EPG titles, error messages, URLs in attributes) must be escaped before interpolation:

- Prefer **`textContent`** or **`document.createElement('option')`** for simple text (account `<select>` options, tag dropdown rows).
- Otherwise use **`escapeHtml()`** from `static/js/utils.js` (ES modules) or the same helper in `epg_common.js` / `templates/base.html` (classic globals on EPG pages).
- For values passed into **`onclick="fn('…')"`** attributes, also use **`escapeJsSingleQuoted()`** from `epg_common.js` so quotes and backslashes cannot break out of the JS literal.

Static markup (spinners, icons, fixed labels) does not need escaping. Do not run `escapeHtml` over strings that intentionally contain HTML markup.

## Tests

Pure helpers in `static/js/lib/` and URL builders are covered by Vitest in `static/js/__tests__/`. Run `npm test`. `escapeHtml` edge cases (`<script>`, quotes) are in `utils.test.js`.

## Future direction

- Move remaining large inline template scripts into `static/js/pages/*.js` (see Preview Channels).
- Convert legacy globals to direct `import` and remove `window.*` bridges when a page is fully modular.
