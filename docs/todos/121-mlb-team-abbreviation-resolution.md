# MLB team abbreviation resolution for Peacock PPV feeds

**Status:** ✅ Done  
**Priority:** P1  
**PR:** (pending)
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`)

## Problem

Peacock MLB PPV channels use **three-letter MLB abbreviations** in an `AWAY at HOME` format. The calendar contains full team names, but the reverse matcher fails to link them.

Production verification (2026-06-03):

| Channel name | Matcher result | Calendar event |
|--------------|----------------|----------------|
| `US (Peacock 001) \| Away Feed: BAL at BOS (2026-06-03 18:30:00)` | **No match** | `Boston Red Sox vs Baltimore Orioles` ✓ |
| `US (Peacock 001) \| Baltimore Orioles at Boston Red Sox (2026-06-03 22:45:00)` | **Match, confidence 1.0** | Same event ✓ |

Active production impact: **27 Peacock `no_match` channels** (more in upcoming days as MLB schedule fills). Abbreviation feeds are the default Peacock PPV naming pattern (`MIN at DET`, `NYY at TOR`, `STL at NYM`, etc.).

### Gap vs existing work

- [58](./58-fix-team-resolution-and-validation.md) fixed substring false positives and aligned validation with the matcher for **full names** and some nicknames (`D-backs`, `Royals`).
- `tests/ppv/test_matching_validation.py` covers `D-backs` / mascot nicknames but **not** standard MLB three-letter codes (`BAL`, `BOS`, `NYY`).
- `services/reverse_event_matcher/text_processor.py` strips sport tokens including `"mlb"` but does not expand MLB abbreviations.
- `SportsTeam` / sport registry ([57](./57-centralize-sport-key-mappings.md)) may already store abbreviations for some sports — MLB codes should reuse that registry rather than a one-off dict.

## Affected files

- `services/reverse_event_matcher/text_processor.py` — competitor normalization
- `services/reverse_event_matcher/match_strategy.py` — competitor scoring
- `services/ppv/matching/validation.py` — `team_names_match`, `competitors_match_event`
- `services/ppv/extraction/competitors.py` — `extract_competitors` for `BAL at BOS` pattern (already extracts `('BAL', 'BOS')` ✓)
- `models/ppv.py` or sport registry — canonical MLB abbrev → full name
- `config/` or `data/` — MLB abbreviation table if not fully in DB
- Tests: `tests/ppv/test_matching_validation.py`, `tests/test_reverse_event_matcher/`

## Requirements for resolution

### Functional

1. **Standard MLB 30-team abbreviations** (e.g. `BAL`, `BOS`, `NYY`, `TB`, `SF`, `AZ`/`ARI`, `CHC`, `CWS`, etc.) must resolve to canonical TheSportsDB / calendar team names during matching.
2. **`AWAY at HOME` syntax** must map abbreviations to the same entities as `Away Team at Home Team` with full names.
3. **Sport context:** Abbreviation expansion applies when league/sport context is MLB (from category name e.g. `US| PEACOCK PPV`, channel prefix, or calendar event league `MLB`). Must not expand `DAL` in a non-MLB context incorrectly.
4. **Validation parity:** Pairs accepted by the matcher must pass `competitors_match_event` / post-match validation (same requirement as TODO 58).
5. **Time tolerance:** Peacock embed timestamps may differ from game start (e.g. feed `18:30` vs game `22:45`); matching must rely on date + team pair, not exact time equality (existing tolerance — verify not broken by abbrev fix).

### Data

- Source of truth for abbreviations: prefer **`SportsTeam`** rows with `sport='mlb'` and `abbreviation` column; fall back to static map only for gaps.
- Document any ambiguous codes (e.g. `WSH` vs `WAS`) with a single canonical choice.

### Non-functional

- O(1) lookup per abbreviation (dict/registry cache at matcher init).
- No live API calls during matching.

## Proposed solution

1. Add **`resolve_mlb_abbrev(name: str) -> Optional[str]`** in sport registry or `services/ppv/matching/mlb_teams.py`.
2. In **`TextProcessor.normalize_competitor`** (or pre-processing step), expand MLB abbrevs when sport context is MLB.
3. Ensure **`match_strategy` competitor strategy** compares expanded names against calendar `home_team` / `away_team`.
4. Extend **`team_names_match_for_event_validation(..., sport_key="mlb")`** to treat three-letter codes as aliases (similar to existing `D-backs` handling).
5. Optional: normalize at extraction time so downstream logs show full names (prefer normalization at match time only to preserve raw channel title).

## Acceptance criteria

- [x] Production Peacock fixtures match at confidence ≥ 0.7:
  - `BAL at BOS` → `Boston Red Sox vs Baltimore Orioles`
  - `MIN at DET`, `NYY at TOR`, `STL at NYM`, `ATL at NYM`
- [x] Full-name Peacock channels still match at confidence 1.0 (no regression).
- [x] Non-MLB channels with accidental 3-letter tokens are not false-matched (parametrized negative cases).
- [ ] Production Peacock `no_match` count → 0 for current-day MLB games present in calendar after requeue (TODO 124).
- [x] Matcher and validation agree on all MLB abbrev fixtures.

## Test plan

### Unit tests

Extend `tests/ppv/test_matching_validation.py`:

```python
@pytest.mark.parametrize("abbrev,full", [
    ("BAL", "Baltimore Orioles"),
    ("BOS", "Boston Red Sox"),
    ("NYY", "New York Yankees"),
    ("TB", "Tampa Bay Rays"),
    # ... full 30-team table
])
def test_mlb_abbrev_expansion(abbrev, full): ...
```

Add `tests/test_reverse_event_matcher/test_mlb_abbrev_matching.py`:

- Load fixture calendar JSON with one MLB game.
- Assert `find_matches("Away Feed: BAL at BOS (2026-06-03 18:30:00)")` returns the game.
- Assert `find_matches("DAL at NYG ...")` with soccer category does **not** match MLB game.

### Integration tests

- Use recorded calendar snippet from production (`Boston Red Sox vs Baltimore Orioles`, date `2026-06-03`) in test fixture — no live HTTP.
- End-to-end: channel → enrichment pipeline → `EventChannelLink` with `match_method` containing `calendar`.

### Production verification

```bash
docker exec iptv-proxy-v2 python -c "
from services.reverse_event_matcher import get_reverse_matcher
# ... BAL at BOS must match after fix
"
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=no_match&search=Peacock' | jq '.pagination.total'
```

Baseline: **27** Peacock `no_match`. Target: **0** for dates where calendar has the game.

## Dependencies

- [57](./57-centralize-sport-key-mappings.md) — sport registry (done; extend for MLB abbrevs).
- [58](./58-fix-team-resolution-and-validation.md) — validation alignment (done; extend tests).
- [120](./120-fix-ppv-date-extraction-parsing-bugs.md) — date must be correct (Peacock ISO dates already OK; verify after any shared parser changes).
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — re-process existing `no_match` Peacock rows.

## Recommended order

**121 after 120** (or in parallel if date parsing unchanged for ISO Peacock titles). Quick win for ~27+ channels per active MLB day.

## Completion

Implemented `resolve_mlb_abbrev()` with SportsTeam DB lookup and static 30-team fallback (`services/ppv/matching/mlb_teams.py`). Reverse matcher expands MLB codes in channel text before team matching; validation accepts three-letter codes when `sport_key="mlb"`. Tests cover all 30 teams and Peacock production fixtures.
