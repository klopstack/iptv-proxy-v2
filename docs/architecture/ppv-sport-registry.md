# PPV Sport Registry (proposed)

**Audit:** PPV audit, June 2026  
**Status:** Draft for review

## Problem

Sport identification strings flow through PPV from channel names, extraction hints, calendar events, timezone resolution, and context providers. Each layer maintains its own mapping table with partial overlap and different alias sets.

Adding or fixing a sport (recent examples: **MiLB**, **WNBA**) requires coordinated edits across multiple files — easy to miss one, causing silent wrong timezone or missing EPG context.

---

## Current duplication map

```
Channel name / extraction
        │
        ├── timezone_resolution._sport_to_team_key()
        ├── matching/context.SPORT_*_PATTERNS
        ├── context/providers/sportsipy._SPORT_KEY
        ├── context/providers/espn._ESPN_PATHS
        ├── context/providers/mlb_stats (milb hard-coded)
        ├── context/providers/thesportsdb (league IDs)
        ├── models/ppv.SportsTeam.SPORTS  ← missing wnba
        └── team_location_registry (fb, wnba, milb)
```

---

## Proposed canonical keys

| Key | Description | Primary data source |
|-----|-------------|---------------------|
| `mlb` | Major League Baseball | sportsipy / TSDB |
| `milb` | Minor League Baseball | MLB Stats API |
| `nba` | NBA | sportsipy / TSDB |
| `wnba` | WNBA | team_location_registry |
| `nfl` | NFL | sportsipy |
| `nhl` | NHL | sportsipy |
| `ncaaf` | College football | sportsipy |
| `ncaab` | College basketball | sportsipy |
| `fb` | Soccer / football | registry + football-data |
| `mma` | MMA / UFC | ESPN |
| `nascar` | NASCAR | TSDB |

---

## Proposed module: `services/ppv/sport_registry.py`

```python
@dataclass(frozen=True)
class SportDefinition:
    key: str
    aliases: frozenset[str]          # "basketball", "nba", etc.
    name_patterns: frozenset[str]    # regex or substring hints
    team_source: str                 # sportsipy | registry | mlb_stats | none
    calendar_source: str             # thesportsdb | mlb_stats | both
    context_providers: tuple[str, ...]

def normalize_sport_key(raw: str | None) -> str | None: ...
def sport_for_extraction(extraction: dict) -> str | None: ...
def sport_for_event(event: Event) -> str: ...
```

Consumers replace local dicts with registry lookups.

---

## Migration strategy

1. Inventory all existing mappings (automated test snapshots current behavior).
2. Implement registry with parity to current outputs.
3. Switch one consumer at a time; run full PPV test suite after each.
4. Delete duplicated dicts.
5. Add `SPORT_WNBA` to model (TODO 58).

---

## Related TODOs

- **57** — implement registry
- **58** — WNBA in SportsTeam.SPORTS
- **62** — MiLB integration test validates milb key routing
