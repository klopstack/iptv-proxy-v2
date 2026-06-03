# Extract shared route serializers and CRUD patterns

**Status:** ⬜ Not started  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Repeated CRUD patterns across route files:

- `_serialize_*` helpers duplicated in `fcc_match_patterns.py`, `epg/match_rules.py`, `config_transfer.py`, `rulesets.py`
- Config export re-serializes the same entities again
- ~8 entity types in FCC patterns alone with identical GET list / GET one / POST / PUT / DELETE structure
- EPG source write routes use manual validation instead of Marshmallow schemas (`routes/epg/sources.py`)
- Credential routes in `accounts.py` skip `@validate_request_data`

## Affected files

- `routes/fcc_match_patterns.py`, `routes/epg/match_rules.py`, `routes/config_transfer.py`, `routes/rulesets.py`
- `routes/epg/sources.py`, `routes/accounts.py`
- `schemas.py`

## Proposed solution

1. Shared serializers module: `services/serializers/` or extend `schemas.py` with `to_dict()` helpers
2. Marshmallow schemas for EPG source create/update and credential create/update
3. Optional generic resource helper for simple pattern tables (FCC entities)

## Acceptance criteria

- [ ] Config export and FCC routes share serialization for same entity types
- [ ] EPG source POST/PUT use schema validation
- [ ] Credential routes use schema validation

## Test plan

- Existing CRUD tests pass
- Schema validation tests for new schemas

## Dependencies

- Supports TODO 78 phase 3–4
