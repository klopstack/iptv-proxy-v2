# PPV misc cleanup: constants, heuristics, providers, context dedup

**Status:** ⬜ Not started  
**Priority:** P3  
**Audit:** PPV audit, June 2026

## Problem

Collection of smaller PPV debt items:

| Issue | Location |
|-------|----------|
| Unused `API_REQUESTS_PER_MINUTE` constant | `enrichment.py` line 63 |
| Magic numbers scattered (0.15/0.2 confidence gaps, 72h/48h tolerances, 31-day far-future) | `enrichment.py`, `timezone_resolution.py`, `enrichability.py` |
| Neutral-site heuristics silently `{}` on load error | `venue_inference.py`, `config/neutral_site_heuristics.json` |
| Failed context provider registration only logs warning | `context/registry.py` |
| Duplicate team name lookup in assembler + 4 providers | `context/assembler.py`, provider modules |
| Stale `extraction.py` module docstring (API-first workflow) | `services/ppv/extraction.py` |
| `city_timezone_map.py` duplicates registry for legacy sports | `services/ppv/city_timezone_map.py` |
| TheSportsDB context provider vs `thesportsdb_service.py` duplicate API paths | context vs service layer |
| ESPN provider (~550 lines) lacks contract tests beyond fighter record | `context/providers/espn.py` |
| `ppv_timezone_analysis.md` "Production run (pending)" section empty | docs |

## Affected files

See table above.

## Proposed solution

1. Remove or wire `API_REQUESTS_PER_MINUTE` to settings default.
2. Move tuning constants to `services/ppv/constants.py` with comments.
3. Validate `neutral_site_heuristics.json` at startup; log error if missing/invalid.
4. Add `providers_failed` list to context registry health / status API.
5. Extract `team_entry_lookup(all_teams, name, team_id)` shared helper.
6. Update extraction module docstring; reference architecture doc.
7. Document `city_timezone_map` as legacy fallback in architecture doc.
8. Run timezone analysis script and fill production section or mark as runbook-only.

## Acceptance criteria

- [ ] No unused constants in enrichment module.
- [ ] Invalid heuristics file produces startup warning (test with bad JSON fixture).
- [ ] Provider registration failures visible in status endpoint.
- [ ] Team lookup helper used by at least assembler + one provider.

## Test plan

- Unit tests for heuristics validation and registry health reporting.
- No regression in existing context tests.

## Dependencies

- TODO 57 (sport registry) for city_timezone_map documentation alignment.
