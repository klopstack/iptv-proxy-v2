# TODO 16: Frontend Tests

**Priority:** P3  
**Status:** ⬜ Not started  
**Estimated scope:** Medium

---

## Problem

- `package.json` scripts: `"test": "echo 'No JS tests yet'"`
- ESLint runs on HTML/JS via `npm run lint` but no automated behavioral tests
- Complex UI logic in inline scripts (e.g. `templates/test.html` ~960 lines) untested
- EPG management split across multiple JS files in `static/js/`

---

## Goal

Minimal frontend test coverage for critical UI logic without full E2E framework overhead.

---

## Options

### Option A: Node unit tests for extracted JS (recommended first step)

Extract pure functions from templates into testable modules:
- `static/js/preview_channels.js` (from test.html)
- `static/js/utils.js` — `escapeHtml`, URL param parsing

Test with **Vitest** or **Jest**:

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest"
}
```

### Option B: Playwright E2E

Full browser tests for critical flows (account sync, preview load). Heavier CI setup.

### Option C: Flask test client only

Continue testing API contracts via Python tests; no JS unit tests. Status quo.

---

## Recommended: Option A (incremental)

### Phase 1: Setup Vitest

```bash
npm install -D vitest jsdom
```

Add `vitest.config.js`, one test file:

```javascript
// static/js/__tests__/utils.test.js
import { escapeHtml } from '../utils.js';

test('escapeHtml escapes special chars', () => {
  expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
});
```

### Phase 2: Extract functions from test.html

Move to `static/js/preview_channels.js`:
- `escapeHtml`
- `buildPreviewUrl(accountId, offset, tags, ...)`
- Tag badge color mapping

### Phase 3: CI integration

Add to `.github/workflows/build.yml`:

```yaml
- run: npm test
```

Or include in `make ci` after `npm install`.

---

## Files to create/modify

| File | Action |
|------|--------|
| `package.json` | Real test script + vitest devDep |
| `vitest.config.js` | **New** |
| `static/js/utils.js` | **New** — shared helpers |
| `static/js/__tests__/*.test.js` | **New** |
| `templates/test.html` | Import extracted JS |
| `Makefile` | Optional `test-js` target |
| `.github/workflows/build.yml` | Run JS tests |

---

## Acceptance criteria

- [ ] `npm test` runs real tests (not echo stub)
- [ ] At least 10 unit tests for extracted pure functions
- [ ] CI runs JS tests on PRs
- [ ] No regression in `npm run lint`

---

## Out of scope

- Full Playwright E2E suite
- Testing mpegts.js player integration
- 100% JS coverage

---

## Test plan

```bash
npm test
npm run lint
make ci  # if integrated
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
