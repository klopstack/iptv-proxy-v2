# Standardize API success response shapes

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

API clients cannot rely on a consistent response envelope:

| Pattern | Examples |
|---------|----------|
| Raw array | `GET /api/filters`, `GET /api/accounts` |
| `{ "success": true, ... }` | Many mutating routes |
| Unwrapped object | Scheduler status |
| Empty 204 | Some deletes |
| `{ "message": "..." }` | Other deletes |
| Plain dict (no jsonify) | `routes/streams.py` |

Documented format in `API_REFERENCE.md` (`{ "error", "code", "details" }`) does not match implementation; symbolic error codes are unused.

## Affected files

- Widespread `routes/*.py`
- `docs/API_REFERENCE.md`
- Frontend JS expecting mixed shapes

## Proposed solution

Pick one convention (recommendation):

**Reads:** return resource or `{ "data": ... }` consistently  
**Writes:** `{ "success": true, "data": ... }` or REST-style resource body  
**Errors:** unified via TODO 72  
**Deletes:** 204 No Content OR `{ "success": true }` — pick one

Migrate high-traffic endpoints first; document breaking changes for any external API consumers.

## Acceptance criteria

- [ ] API_REFERENCE documents actual envelope with examples per resource type
- [ ] New endpoints follow chosen convention
- [ ] Top 5 blueprints migrated (accounts, settings, epg/sources, filters, api)

## Test plan

- Contract tests for response shape on representative endpoints
- Update frontend fetch handlers if envelope changes

## Dependencies

- TODO 72
- See `docs/architecture/api-contract-errors-and-responses.md`
