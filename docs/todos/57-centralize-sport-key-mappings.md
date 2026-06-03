# Centralize sport-key mapping tables

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

The mapping from extracted sport strings / league hints to internal keys is duplicated across at least four modules with inconsistent coverage:

| Location | Keys handled |
|----------|--------------|
| `services/ppv/timezone_resolution.py` — `_sport_to_team_key` | fb, milb, wnba, mlb, nba, … |
| `services/ppv/matching/context.py` — `SPORT_*_PATTERNS` | Pattern → sport for calendar context |
| `services/ppv/context/providers/sportsipy.py` — `_SPORT_KEY` | sportsipy sport param |
| `services/ppv/context/providers/espn.py` — `_ESPN_PATHS` | ESPN API path segments |

Adding a sport (e.g. WNBA, MiLB) requires touching multiple files; mismatches cause silent wrong timezone or missing context.

## Affected files

- New: `services/ppv/sport_registry.py` (or extend `constants.py`)
- `services/ppv/timezone_resolution.py`
- `services/ppv/matching/context.py`
- `services/ppv/context/providers/sportsipy.py`
- `services/ppv/context/providers/espn.py`
- `services/ppv/context/providers/mlb_stats.py`
- `services/ppv/context/providers/thesportsdb.py`

## Proposed solution

1. Define canonical sport keys (`mlb`, `milb`, `nba`, `wnba`, `nfl`, `nhl`, `fb`, …) in one registry.
2. Each consumer registers aliases / pattern lists against canonical keys.
3. Provide helpers: `normalize_sport_key(str) -> Optional[str]`, `sport_keys_for_context(event) -> list[str]`.
4. Migrate existing tables to import from registry; delete duplicated dicts.

## Acceptance criteria

- [ ] Single module defines canonical sport keys and alias resolution.
- [ ] All four consumer modules use registry helpers.
- [ ] Existing timezone and context tests pass without behavior change.

## Test plan

- `tests/test_ppv_timezone_resolution.py` — no regressions.
- New parametrized test: known sport strings resolve to expected canonical keys.

## Dependencies

- See `docs/architecture/ppv-sport-registry.md`.
