# TODO 12: UI and Navigation Cleanup

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Small–Medium

---

## Problem

Several UI/codepath issues create confusion for developers and users:

| Issue | Location |
|-------|----------|
| Preview page at `/test` | `routes/web.py` — name implies test-only |
| Configurable Patterns has no nav link | `templates/configurable_patterns.html` exists; not in `base.html` nav |
| Debug artifact in repo root | `ppv_analysis_output.txt` |
| Accounts page EPG claim | Says EPG matches M3U — fix wording if TODO 01 not done yet |
| `/test` route function named `test_page` | Confusing in stack traces |

---

## Goal

Clearer navigation, naming, and repo hygiene without changing core functionality.

---

## Proposed changes

### 1. Rename preview route (optional breaking change)

| Current | Proposed |
|---------|----------|
| `/test` | `/preview` or `/channels/preview` |
| `test_page()` | `preview_channels_page()` |
| `templates/test.html` | `templates/preview_channels.html` |

**Migration:** Add redirect from `/test` → `/preview` for bookmarks.

Update links in:
- `templates/base.html` nav
- `templates/categories.html` (links to `/test?account=...`)
- Any docs referencing `/test`

### 2. Add Configurable Patterns to nav

In `templates/base.html`, under EPG section or as sub-item:

```html
<a class="nav-link" href="/configurable-patterns">Configurable Patterns</a>
```

Or add link on FCC Match Patterns page only (lighter touch) — decide based on how often it's used.

### 3. Remove debug artifacts

Delete or gitignore:
- `ppv_analysis_output.txt`
- `reverse_matcher_output.txt` (if present)

Add to `.gitignore`:
```
*_analysis_output.txt
reverse_matcher_output.txt
```

### 4. Update accounts page EPG description

In `templates/accounts.html`, the EPG link tooltip says filtered to M3U channels. After TODO 01, this is accurate. If doing UI cleanup before TODO 01, soften wording to "EPG for account channels" until parity is fixed.

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/web.py` | Route rename + redirect |
| `templates/base.html` | Nav updates |
| `templates/test.html` | Rename or keep with redirect |
| `templates/categories.html` | Update `/test` links |
| `templates/accounts.html` | EPG tooltip (optional) |
| `.gitignore` | Analysis output patterns |

---

## Acceptance criteria

- [ ] Preview page reachable at intuitive URL (`/preview` preferred)
- [ ] Old `/test` URL redirects (if renamed)
- [ ] Configurable Patterns discoverable from nav or FCC page
- [ ] No debug output files in repo root
- [ ] Nav active-state CSS works for renamed route

---

## Test plan

```bash
venv/bin/pytest tests/test_app_routes.py tests/test_web_routes.py -v --no-cov  # if exist
# Manual: click through nav, verify all links work
```

Add route test if missing:
```python
def test_preview_redirect_from_test(client):
    response = client.get("/test", follow_redirects=False)
    assert response.status_code in (301, 302, 200)  # redirect or alias
```

---

## Dependencies

- Accounts EPG tooltip accuracy depends on TODO 01 (optional ordering)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
