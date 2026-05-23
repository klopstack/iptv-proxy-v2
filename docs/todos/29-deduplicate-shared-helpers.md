# TODO 29: Deduplicate Shared Route and Service Helpers

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Small–medium

---

## Problem

Post-restructuring, several **small duplications** remain that increase drift risk without adding clarity.

### Duplicate `get_iptv_service_for_account`

Identical helper defined in two modules:

| File | Lines | Used by |
|------|-------|---------|
| `routes/accounts.py` | ~41+ | Account sync, connection test routes |
| `services/sync_service.py` | ~64+ | `ChannelSyncService.sync_account` |

Both implement legacy credential fallback identically. A fix in one may not reach the other.

### Xtream route indirection

`routes/xtream.py` imports both `ChannelQueryService` and `FilterService` / `PPVVisibilityService` directly in some code paths while also calling CQS wrappers — partial migration from pre-CQS era.

Thin wrappers like `get_channels_for_account` duplicate CQS entry points.

### Proxy base URL helpers

`routes/playlists.py` defines `get_proxy_base_url()` wrapping `services/url_service.get_proxy_base_url` — minor but repeated pattern across route files.

### `routes/epg/sources.py` test export

Comment: "Export helper function for tests (for backward compatibility)" — helper may belong in service layer only.

---

## Goal

Single canonical helper per concern; routes become thin HTTP adapters.

---

## Proposed solution

### Step 1: Centralize IPTV service factory

Add to `services/iptv_service.py`:

```python
def get_iptv_service_for_account(account: Account) -> IPTVService:
    """Build IPTVService from account credentials (multi-cred or legacy)."""
    ...
```

Update:
- `routes/accounts.py` — import from service
- `services/sync_service.py` — import from service
- `tests/test_accounts_routes.py` — patch `services.iptv_service.get_iptv_service_for_account`

### Step 2: Xtream cleanup audit

For each function in `routes/xtream.py`:
- If it only calls CQS → inline at call site or delete wrapper
- If it adds Xtream-specific formatting → keep, document

Target: no direct `FilterService` / `PPVVisibilityService` imports unless Xtream-specific.

### Step 3: URL helpers

Use `services/url_service.get_proxy_base_url` directly in playlists routes; delete local wrapper if trivial.

### Step 4: EPG sources test helper

Move exported helper from `routes/epg/sources.py` to `services/epg/sources.py` or test utility module; update tests.

---

## Dependencies

- **After:** TODO 17 ✅ (CQS preview pattern established)
- **Independent of:** TODO 28
- **Enables:** TODO 34 (thinner route layer)

---

## Files to modify

| File | Changes |
|------|---------|
| `services/iptv_service.py` | Add `get_iptv_service_for_account` |
| `routes/accounts.py` | Remove duplicate; import service |
| `services/sync_service.py` | Remove duplicate; import service |
| `routes/xtream.py` | Remove redundant filter/PPV calls |
| `routes/playlists.py` | Drop proxy URL wrapper if redundant |
| `routes/epg/sources.py` | Move test helper to service |
| `tests/test_accounts_routes.py` | Update patch paths |

---

## Acceptance criteria

- [x] Exactly one definition of `get_iptv_service_for_account` in codebase
- [x] `rg "def get_iptv_service_for_account"` returns one hit
- [x] Xtream routes import FilterService/PPVVisibilityService only if justified in comment
- [x] Full test suite passes

---

## Test plan

```bash
venv/bin/pytest tests/test_accounts_routes.py tests/test_sync_service.py tests/test_xtream.py -v --no-cov
rg "def get_iptv_service_for_account"
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Centralized `get_iptv_service_for_account` in `services/iptv_service.py`; removed unused FilterService/PPVVisibilityService imports and dead wrappers from `routes/xtream.py`; dropped proxy URL wrappers in xtream/playlists; moved `sync_sd_channels_to_epg` to `services/epg/sources.py`. |
