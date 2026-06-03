# Fix team resolution and validation consistency

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

Three related team-matching issues:

### 1. Risky substring matching in `SportsTeam.resolve_team`

```python
if key in team.name.lower() or team.name.lower() in key:
    return team
```

Short or generic keys (e.g. "United", "City") can match the wrong team when sport filter is absent or broad.

### 2. WNBA missing from `SportsTeam.SPORTS`

`home_timezone_for_team` handles `wnba` via `team_location_registry`, but `SPORTS` constant omits `SPORT_WNBA`. Scheduler refresh jobs and UI enumerations may skip WNBA teams.

### 3. Post-match validation diverges from reverse matcher

`services/ppv/matching/validation.py` (`team_names_match`) uses different normalization than `services/reverse_event_matcher/match_strategy.py` strategies — matches can be accepted by the matcher then rejected (or vice versa) during validation.

## Affected files

- `models/ppv.py` — `SportsTeam.resolve_team`, `SPORTS`, `home_timezone_for_team`
- `services/ppv/matching/validation.py`
- `services/reverse_event_matcher/match_strategy.py`
- `services/scheduler.py` — team refresh jobs

## Proposed solution

1. **resolve_team:** Remove bidirectional substring fallback; rely on exact name + alias table. If substring needed for legacy, gate by `len(key) >= 4` and require sport filter.
2. **WNBA:** Add `SPORT_WNBA = "wnba"` to model constants and `SPORTS` list; verify refresh jobs include it.
3. **Validation:** Share `TextProcessor` / normalization with reverse matcher, or delegate competitor check to matcher confidence + explicit competitor strategy only.

## Acceptance criteria

- [ ] No false-positive team resolution in parametrized edge cases ("United", "City FC").
- [ ] WNBA appears in `SportsTeam.SPORTS` and refresh enumeration.
- [ ] Validation accepts/rejects same pairs as matcher for recorded fixture set.

## Test plan

- Extend `tests/test_team_location_registry.py` / add `tests/ppv/test_sports_team_resolve.py`.
- `tests/ppv/test_matching_validation.py` — align with reverse matcher fixtures.

## Dependencies

- TODO 57 (sport registry) helps WNBA/MiLB consistency.
