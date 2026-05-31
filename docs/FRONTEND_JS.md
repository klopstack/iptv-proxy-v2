# Frontend JavaScript conventions

This app mixes legacy inline/classic scripts in Jinja templates with newer ES modules under `static/js/`. Use the patterns below when adding or changing UI JavaScript.

## Directory layout

| Role | Location | How it is loaded |
|------|----------|------------------|
| Reusable helpers and API clients | `static/js/lib/*.js` | ES module (`import` / `export`) |
| Page bootstrap (attach libs to `window`) | `static/js/pages/{page}_bootstrap.js` | `<script type="module" src="{{ url_for('static', filename='js/pages/…') }}">` |
| Full page logic (preferred for new work) | `static/js/pages/*.js` or top-level `static/js/*_page.js` | module `src` only |
| Legacy EPG / match-rules bundles | `static/js/epg_*.js`, `static/js/match_rules_*.js` | classic `<script src>` (non-module globals) |

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

- **`installEpgSyncProgressOnWindow()`** in `static/js/lib/install_epg_sync_progress.js` — used by Settings and EPG Management to expose `window.EpgSyncProgress`.

## Linting

- **HTML templates:** `eslint templates/**/*.html` (structure via `@html-eslint`, inline classic scripts via `eslint-plugin-html`).
- **ES modules:** `eslint static/js/lib static/js/pages` with `sourceType: 'module'`.
- **Do not** add `eslint-disable-next-script` for module imports; use external bootstrap files instead.
- Legacy non-module bundles (`epg_common.js`, etc.) are not ESLint module targets until migrated.

## Tests

Pure helpers in `static/js/lib/` and URL builders are covered by Vitest in `static/js/__tests__/`. Run `npm test`.

## Future direction

- Move remaining large inline template scripts into `static/js/pages/*.js` (see Preview Channels).
- Convert legacy globals to direct `import` and remove `window.*` bridges when a page is fully modular.
