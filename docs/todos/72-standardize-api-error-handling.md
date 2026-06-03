# Standardize API error handling repo-wide

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

`error_handling.py` provides `@handle_errors`, typed exceptions, and `error_response()` — but adoption is ~30–40% on mutating routes. Completed TODO 33 fixed some silent `except` blocks; most CRUD routes still use ad-hoc patterns:

- `except Exception as e: return jsonify({"error": str(e)}), 500` — leaks internals
- Manual `{ "success": false, "error" }` vs bare `{ "error" }` vs Marshmallow `{ "validation_errors" }`
- `handle_db_error()` defined but never used in routes
- Three parallel validation paths: Marshmallow decorator, `error_handling.ValidationError`, hand-validation

**Worst coverage:** `routes/filters.py` (0/4), `routes/settings.py` (0/8), `routes/fcc_match_patterns.py` (0/42 API routes), `routes/streams.py` (0/12), `routes/ppv_enrichment.py` (manual try/except).

## Affected files

- `error_handling.py`
- `schemas.py` — Marshmallow validation bridge
- All `routes/*.py` JSON blueprints
- `docs/API_REFERENCE.md`

## Proposed solution

1. Apply `@handle_errors(return_json=True)` to all JSON admin blueprints by default
2. Bridge Marshmallow validation errors into unified envelope
3. Replace `str(e)` in 500 responses with generic message in production; log full trace server-side
4. Use `ResourceNotFoundError` instead of mixed `get_or_404` / manual 404 JSON
5. Wire `handle_db_error()` for IntegrityError → 409

Document target envelope in architecture doc (TODO 73).

## Acceptance criteria

- [ ] No route returns raw exception strings in production mode
- [ ] All JSON blueprints use `@handle_errors` or documented exception
- [ ] Marshmallow and manual validation produce same error shape

## Test plan

- Extend `tests/test_error_handling.py` with per-blueprint smoke tests
- Parametrized test: invalid input → consistent JSON shape

## Dependencies

- TODO 73 (response shape standard)
- Extends completed TODO 33
