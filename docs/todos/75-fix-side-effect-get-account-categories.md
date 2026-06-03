# Fix side-effect GET on account categories

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

`GET /api/accounts/<id>/categories` in `routes/accounts.py` (~412–435) triggers:

- Upstream Xtream API call
- Cache write
- Optional tag processing mutation

On a **GET** request. This violates HTTP semantics, causes surprising latency, and loads the upstream provider on every admin page view.

## Affected files

- `routes/accounts.py`
- Admin UI calling this endpoint
- `tests/test_accounts_routes.py`

## Proposed solution

1. **GET** returns cached/DB categories only (fast, idempotent)
2. Add explicit **`POST /api/accounts/<id>/categories/sync`** for upstream refresh + tag processing
3. Update admin UI to call sync explicitly or show "refresh" button

## Acceptance criteria

- [ ] GET does not call upstream IPTV API
- [ ] Sync endpoint documented and tested
- [ ] UI still allows manual category refresh

## Test plan

- GET with mocked upstream: assert zero HTTP calls to provider
- POST sync: assert upstream called and cache updated

## Dependencies

None.
