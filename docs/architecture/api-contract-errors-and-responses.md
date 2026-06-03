# API Contract: Errors and Response Shapes

**Audit:** Application-wide audit, June 2026  
**Status:** Draft for review

## Problem

Clients cannot rely on a single API contract. At least four error formats and three success patterns coexist.

## Observed error formats

```json
{ "error": "message" }
{ "success": false, "error": "message" }
{ "error": "Validation failed", "validation_errors": { "field": ["msg"] } }
{ "error": "message", "code": "SYMBOLIC_CODE" }
```

Documented `{ "error", "code", "details" }` in API_REFERENCE is **aspirational** — symbolic codes unused in routes.

## Observed success formats

| Style | Example endpoints |
|-------|-------------------|
| Raw array/object | `GET /api/filters`, scheduler status |
| Wrapped | `{ "success": true, "data": ... }` |
| 204 empty | Some DELETE |
| Plain Python dict | `routes/streams.py` |

## Validation paths

1. `@validate_request_data` (Marshmallow) — different error shape
2. `error_handling.ValidationError` — almost unused in routes
3. Manual `if not data.get("name")` — inconsistent

## Target contract (proposal)

### Errors (JSON admin routes)

```json
{
  "success": false,
  "error": "Human-readable message",
  "code": "VALIDATION_ERROR",
  "details": { "field": "reason" }
}
```

HTTP status: 400 validation, 404 not found, 409 conflict, 500 internal.

### Success

- **Collection GET:** `{ "data": [...] }` or raw array (pick one — recommend wrapped for consistency)
- **Resource GET:** resource object or `{ "data": {...} }`
- **Mutation:** `{ "success": true, "data": {...} }`
- **DELETE:** 204 No Content

### Exceptions

- Xtream API: `{ "user_info": { "auth": 0 } }` — keep Xtream-compatible
- XMLTV/M3U: non-JSON responses unchanged

## Migration strategy

1. Define contract in API_REFERENCE (this doc → reference)
2. TODO 72: `@handle_errors` everywhere; bridge Marshmallow
3. TODO 73: migrate high-traffic endpoints to success envelope
4. Add contract tests parametrized by blueprint

## Related TODOs

- **72**, **73**, **87**
