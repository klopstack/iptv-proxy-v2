# Remove dead routes and dangerous HTTP patterns

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Several route-level cleanup items:

### 1. Dead blueprint

`account_epg_channels_bp` is created in `routes/epg/channels.py` and registered in `app.py` but has **zero routes** — incomplete refactor artifact.

### 2. Duplicate endpoints

- `POST /api/sync/fcc` (`routes/api.py`) vs `POST /api/fcc/facilities/sync` (`routes/stations.py`) — both call `FccFacilityService.full_sync()` with different response shapes
- Three "categories" endpoints with different semantics (`/api/categories`, `/api/accounts/<id>/categories`, `/api/channel-health/categories`)

### 3. Module-level CacheService duplication

Six route modules each instantiate `cache_service = CacheService()` — should be app-scoped.

### 4. routes/__init__.py stub

No centralized `register_routes(app)` — 22+ blueprints imported inline in `app.py`.

## Affected files

- `routes/epg/channels.py`, `app.py`
- `routes/api.py`, `routes/stations.py`
- `routes/accounts.py`, `routes/channel_health.py`
- `routes/filters.py`, `routes/rulesets.py`, `routes/config_transfer.py`, `routes/fcc_match_patterns.py`, `routes/epg/match_rules.py`

## Proposed solution

1. Remove `account_epg_channels_bp` or implement intended account-scoped routes
2. Deprecate one FCC sync endpoint; document canonical path
3. Rename or consolidate category endpoints with explicit `source=` parameter
4. Single app-scoped `CacheService` via factory or `current_app.extensions`
5. Optional: `register_routes(app)` in `routes/__init__.py`

## Acceptance criteria

- [ ] No registered blueprints with zero routes
- [ ] One canonical FCC sync API path documented
- [ ] Category endpoints documented with distinct names/purposes

## Test plan

- Grep for removed endpoint paths; update tests
- App startup test: all registered blueprints have ≥1 route

## Dependencies

- TODO 69 for FCC reset (separate from duplicate sync)
