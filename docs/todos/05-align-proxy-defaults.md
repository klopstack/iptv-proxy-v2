# TODO 05: Align M3U Proxy Defaults

**Priority:** P1  
**Status:** ⬜ Not started  
**Estimated scope:** Small (behavior change + docs)

---

## Problem

Default stream proxy behavior differs between single-account and config playlists:

| Route | Default `proxy` | Code |
|-------|-----------------|------|
| `/playlist/<account_id>.m3u` | **ON** (`true`) | `request.args.get("proxy", "true")` |
| `/playlist/config/<slug>.m3u` | **OFF** | `request.args.get("proxy", "")` → empty ≠ `"true"` |

Single-account users get proxied streams by default (needed for multi-credential accounts). Config playlist users get direct provider URLs unless they explicitly pass `?proxy=true`.

Both paths auto-enable proxy when an account has multiple credentials — but only after the default is evaluated, so config playlists still default off for single-credential accounts.

---

## Goal

Consistent default proxy behavior across all M3U generation endpoints.

---

## Options (pick one)

### Option A: Default ON everywhere (recommended)

Match single-account behavior — proxy by default for all M3U outputs:

```python
use_proxy = request.args.get("proxy", "true").lower() == "true"
```

In `_generate_playlist_from_config`.

**Pros:** Safer for multi-credential setups; consistent with accounts page links.  
**Cons:** Config playlist users who wanted direct URLs must pass `?proxy=false`.

### Option B: Default OFF everywhere

Change single-account to default off:

```python
use_proxy = request.args.get("proxy", "false").lower() == "true"
```

**Pros:** Direct URLs reduce proxy load.  
**Cons:** Breaks existing TiviMate setups that rely on default proxied URLs from accounts page.

### Option C: Explicit default with setting

Add a `Settings` key `default_proxy_playlists=true` used by both routes.

**Pros:** User-configurable.  
**Cons:** More complexity; probably overkill.

---

## Recommended: Option A

Update `_generate_playlist_from_config`:

```python
use_proxy = request.args.get("proxy", "true").lower() == "true"
```

Keep auto-enable for multi-credential accounts as additional OR logic.

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | `_generate_playlist_from_config` default |
| `tests/test_playlist_generation.py` | Update tests expecting direct URLs by default |
| `tests/test_playlists_routes.py` | Same |
| `docs/TIVIMATE.md` | Document `proxy` query param if not already |

---

## Acceptance criteria

- [ ] Config M3U defaults to proxied stream URLs (same as account M3U)
- [ ] `?proxy=false` disables proxy on both route types
- [ ] Multi-credential auto-proxy logic unchanged
- [ ] Accounts page M3U links still work without query params
- [ ] Tests updated to reflect new default

---

## Test plan

```bash
venv/bin/pytest tests/test_playlist_generation.py tests/test_playlists_routes.py -v -k playlist --no-cov
```

Verify generated M3U contains `/stream/` URLs without explicit `?proxy=true` on config route.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
