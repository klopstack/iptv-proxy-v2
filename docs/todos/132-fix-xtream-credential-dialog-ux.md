# Fix Xtream credential dialog: account dropdown and timezone select

**Status:** ✅ Done  
**Priority:** P1 (user-visible — blocks creating account-linked Xtream credentials)  
**Reported:** June 2026

## Problem

On **`/xtream`**, the **Add Credential** / **Edit Credential** modal has two UX issues:

1. **Select Account stays on “Loading accounts…”** — opening the dialog never populates the account dropdown; only the placeholder option is shown (even when accounts exist elsewhere in the admin UI).
2. **PPV Rename Timezone is a free-text field** — operators must type an IANA timezone manually (with a datalist hint). It should be a **`<select>`** like **Language Fallback**, with a clear “use account default” empty option.

Both issues affect the same modal (`#addCredentialModal` in `templates/xtream.html`).

### Root cause (account dropdown)

[TODO 73](./73-standardize-api-response-shapes.md) migrated `GET /api/accounts` to the standard `{ "data": [...] }` envelope (`routes/accounts.py` → `data_response(...)`). Most admin pages unwrap with `apiUnwrapData()` (defined in `templates/base.html`) or `static/js/lib/account_select.js`.

`templates/xtream.html` **`loadAccounts()`** still treats the JSON body as a bare array:

```javascript
.then(data => {
    accounts = data;
    accounts.map(acc => ...)  // TypeError when data is { data: [...] }
})
```

The `.catch` only logs to the console, so the initial `<option>Loading accounts...</option>` is never replaced.

**Playlist config dropdown** is unaffected today — `GET /api/playlist-configs` still returns a raw array (`routes/playlists.py`).

### Root cause (timezone field)

The modal uses `<input type="text" list="xtream-timezone-options">` plus a static `<datalist>`. That allows invalid values and is inconsistent with the adjacent **Language Fallback** `<select>`. Backend validation (`_validate_ppv_rename_timezone` in `routes/xtream.py`) rejects invalid IANA names, but the UI should constrain input up front.

## Current state

| Area | Behavior |
|------|----------|
| `loadAccounts()` | No envelope unwrap; silent failure |
| `loadPlaylistConfigs()` | Works (raw array API) |
| Timezone UI | Text + datalist (10 hardcoded zones) |
| Peer pages | `filters.html`, `accounts.html`, `ppv.html` use `apiUnwrapData` for accounts |
| Shared helper | `static/js/lib/account_select.js` — `fetchAccounts()` + `populateAccountSelect()` |

## Proposed solution

### A. Fix account (and harden playlist) loading

**Minimal fix (inline):**

1. In `loadAccounts()`, use `apiUnwrapData(response, await response.json())` (or async/await + unwrap) before `.map`.
2. On failure or non-array payload, replace select contents with an error option / small alert (match `filters.html` pattern — do not leave “Loading…” forever).
3. Optionally reload accounts when the modal opens (`shown.bs.modal`) so late-added accounts appear without a full page refresh.

**Preferred fix (align with TODO 85):**

1. Extract modal logic to `static/js/pages/xtream_page.js` (ESM).
2. Reuse `fetchAccounts()` / `populateAccountSelect()` from `account_select.js`.
3. Add a Vitest case mirroring `static/js/__tests__/account_api.test.js` for envelope unwrap.

### B. Replace timezone text input with `<select>`

1. Replace `#credential-ppv-rename-timezone` input + `#xtream-timezone-options` datalist with:

   ```html
   <select class="form-select" id="credential-ppv-rename-timezone">
     <option value="">Use account default</option>
     <!-- same IANA zones as current datalist -->
   </select>
   ```

2. Keep the same option set as today (or centralize in a shared constant if extracting JS module — do not expand scope to full `zoneinfo` list unless product asks).
3. **Edit flow:** set `select.value = cred.ppv_rename_timezone || ''`.
4. **Save flow:** unchanged — empty string → `null` (credential override cleared; account default applies per `resolve_ppv_rename_timezone`).

### Out of scope (optional follow-up)

- Migrating `ppv.html` account timezone inputs to `<select>` (same datalist pattern — separate item if desired).
- Wrapping `GET /api/playlist-configs` / `GET /api/xtream-credentials` in `data_response` (API contract consistency — not required for this fix).

## Affected files

- `templates/xtream.html` — modal markup + inline script (or slim template if ESM extract)
- `static/js/lib/account_select.js` — reuse (no change required if import-only)
- `static/js/pages/xtream_page.js` — **new**, if extracting inline script
- `tests/test_api_contract.py` — optional regression note (accounts envelope already covered)
- `tests/test_ppv_rename_format.py` — `TestXtreamCredentialPpvRenameTimezone` (API unchanged; manual/UI only unless ESM tests added)
- `docs/SMOKE_TEST_POST_MERGE.md` — extend § Playlists / Xtream with account dropdown + timezone select checks

## Acceptance criteria

- [x] **Add Credential** modal: **Select Account** lists all accounts by name (same set as `/accounts` or `/filters`).
- [x] If account fetch fails, user sees an error state — not perpetual “Loading accounts…”.
- [x] **PPV Rename Timezone** is a `<select>` with “Use account default” + known IANA options; no free-text input.
- [x] Creating/editing a credential with account source + timezone override persists correctly (`ppv_rename_timezone` round-trip).
- [x] Clearing timezone (empty select) saves `null` and uses account default at playlist render time.
- [x] No console `TypeError` on `/xtream` page load when accounts API returns `{ data: [...] }`.

## Test plan

```bash
pytest tests/test_ppv_rename_format.py::TestXtreamCredentialPpvRenameTimezone -q --no-cov
pytest tests/test_api_contract.py::TestApiContractAccounts -q --no-cov
npm test  # if xtream_page.js or account_select reuse tests added

# Manual
# 1. Open /xtream → Add Credential → confirm account names in Select Account
# 2. Pick account + America/Chicago timezone → save → reload page → edit → values restored
# 3. Set timezone back to "Use account default" → save → credential row/API shows null override
# 4. DevTools: no errors from loadAccounts on page load
```

## Dependencies

- [73-standardize-api-response-shapes.md](./73-standardize-api-response-shapes.md) ✅ — accounts list envelope (regression source)
- [85-frontend-deduplication-and-esm-migration.md](./85-frontend-deduplication-and-esm-migration.md) ✅ — `account_select.js` helper available

## References

- `templates/xtream.html` — `loadAccounts()`, modal fields
- `routes/accounts.py` — `GET /api/accounts` → `data_response`
- `routes/xtream.py` — `_validate_ppv_rename_timezone`, credential CRUD
- `services/datetime_utils.py` — `resolve_ppv_rename_timezone`, `DEFAULT_DISPLAY_TIMEZONE`
- `templates/filters.html` — reference `loadAccounts()` + error handling pattern

## Completion

- PR: _pending_
