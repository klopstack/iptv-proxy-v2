# Multi-player (2v2) competitor extraction and doubles matching

**Status:** ✅ Implemented (branch `todo/tennis-doubles`)  
**Priority:** P1  
**Audit:** [tennis-ppv-production-audit.md](../architecture/tennis-ppv-production-audit.md), June 2026

## Problem

Tennis PPV channels often use **four-player** titles (doubles, wheelchair doubles, legends exhibitions). The calendar already ingests these fixtures when ESPN/SofaScore list them — e.g. `home_team` / `away_team` as `"Guo Hanyu / Kristina Mladenovic"` vs `"Shuko Aoyama / En-Shuo Liang"` ([`espn_calendar.py`](../../services/tennis/espn_calendar.py)).

**Competitor extraction** still assumes **two sides × one name each**:

```
Tennis: A Cornet D Hantuchova vs M Hingis A Kerber @ Jun 3 10:55 AM
  -> ('A Cornet D Hantuchova', 'M Hingis A Kerber')   # wrong

Tennis: Y Kamiji Z Zhu vs A Bernal J Griffioen @ Jun 3 13:00 PM
  -> ('Y Kamiji Z Zhu', 'A Bernal J Griffioen')       # wrong
```

Downstream effects:

1. **`competitors_match_event`** in [`validation.py`](../../services/ppv/matching/validation.py) compares two bogus strings to two calendar player names → permanent `competitor_mismatch` even when the fixture exists.
2. **`LastNameMatchStrategy`** may partially hit one surname but never validates all four players as a set.
3. Production audit: **~89 unique doubles keys (~53% of tennis `no_match` content)** blocked by this alone; singles are largely unblocked after [122](./122-tennis-calendar-event-source.md).

Wheelchair **singles** (`Andy Lapthorne vs Niels Vink`) already extract correctly; the gap is **multi-token sides**, not wheelchair-specific calendar data.

## Affected files

- `services/ppv/extraction/competitors.py` — `extract_competitors`, `clean_team_name`
- `services/ppv/extraction/types.py` — `MatchupInfo` (may need `format` or player list)
- `services/ppv/extraction/extractor.py` — `extract_all` / `extract_matchup`
- `services/ppv/matching/validation.py` — `competitors_match_event`, player vs team helpers
- `services/ppv/enrichment/match_pipeline.py` — post-match validation gate
- `services/reverse_event_matcher/match_strategy.py` — optional doubles-aware strategy
- `services/reverse_event_matcher/orchestrator.py` — tennis strategy selection
- `tests/ppv/test_matching_validation.py`, `tests/test_ppv_extraction.py`
- `tests/ppv/fixtures/` — production doubles channel name samples (from audit)

## Requirements

### Functional

1. **Detect format** when a side has multiple abbreviated players (initial + surname tokens), e.g.:
   - `A Cornet D Hantuchova` → Cornet, Hantuchova
   - `T Golovin G Forget` → Golovin, Forget
   - `Y Kamiji Z Zhu` → Kamiji, Zhu
2. **Extract four player identities** (or two sides of two) from channel titles while preserving singles behavior for `First Last vs First Last`.
3. **Match calendar events** where each side is stored as `"Name A / Name B"` (ESPN roster) or equivalent SofaScore team names.
4. **Order-independent** player matching within a side and across home/away (feed may reverse sides).
5. **Validation parity:** Pairs accepted by the reverse matcher must pass `competitors_match_event` for doubles (same bar as [58](./58-fix-team-resolution-and-validation.md) / [121](./121-mlb-team-abbreviation-resolution.md)).
6. **Sport context:** Apply doubles logic when sport is tennis (channel hint or matched event), not for team sports with `X` separators.

### Parsing heuristics (starting point)

| Signal | Interpretation |
|--------|----------------|
| Side has ≥3 tokens, multiple capitalized surname-like words | Likely doubles initials format |
| Side contains `/` or ` and ` between names | Explicit doubles separator (if seen in feeds) |
| Calendar side contains ` / ` | Target comparison shape from ESPN |

Reject or leave unchanged:

- `Tennis: Multiview`, court aggregates, `Primetime` slots ([audit §2](./../architecture/tennis-ppv-production-audit.md))
- Team sports `DAL at NYG` (existing MLB/NFL paths)

### Non-functional

- No live HTTP in new tests; use recorded production title fixtures.
- Singles extraction must not regress (audit: **53/53** clean singles patterns).

## Proposed solution

**Phase 1 — Extraction**

- Add `parse_tennis_side_players(side: str) -> list[str]` (or similar) using token rules tuned on audit samples.
- Extend `extract_competitors` to return either:
  - `Tuple[str, str]` for singles (unchanged), or
  - A structured doubles type, e.g. `Tuple[Tuple[str, str], Tuple[str, str]]` or `MatchupInfo` with `players: tuple[tuple[str, str], tuple[str, str]]` and `format="doubles"`.
- Document format in `MatchupInfo` for downstream logging.

**Phase 2 — Validation**

- `competitors_match_event_doubles(players, event)`:
  - Split `event.home_team` / `event.away_team` on ` / `.
  - Fuzzy match each extracted player to one calendar name (reuse `team_names_match_for_event_validation` / last-name rules).
  - Require bijection: 4 channel players ↔ 4 calendar players.

**Phase 3 — Matcher (if needed)**

- If `LastNameMatchStrategy` alone is insufficient, add `DoublesMatchStrategy` or extend tennis branch to score events where ≥3 of 4 surnames hit.
- Prefer validation-driven acceptance over lowering global confidence.

## Acceptance criteria

- [x] Production fixture set (≥10 doubles + ≥5 wheelchair doubles + ≥10 singles controls) in `tests/ppv/fixtures/tennis_doubles_channels.json`.
- [x] `extract_competitors` returns four logical players for audit examples (Cornet/Hantuchova, Kamiji/Zhu, etc.).
- [x] Enrichment validation passes mocked ESPN doubles `"A / B"` calendar rows paired with production-style channel titles.
- [x] Singles channels in fixture set still extract and validate as today.
- [x] `competitors_match_event` / `competitors_match_event_doubles` passes for doubles fixtures paired with calendar rows.
- [ ] Production tennis `no_match` count drops by **≥40%** from doubles slice alone after requeue (baseline ~200 channel rows / ~89 unique keys from audit), in addition to singles gains from calendar sources.

## Test plan

### Unit

- `tests/ppv/test_tennis_doubles_extraction.py` — parse sides and full channel titles from fixtures.
- `tests/ppv/test_tennis_doubles_validation.py` — four-player ↔ calendar ` / ` names.
- Extend `tests/ppv/test_matching_validation.py` with doubles parametrized cases.

### Integration

- `find_matches` + `match_pipeline` with ESPN doubles `CalendarEvent` + production channel name → `matched`, `competitor_mismatch` not triggered.

### Production verification

```bash
# After deploy + requeue Tennis: prefix
curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=no_match&search=Tennis%3A' | jq '.pagination.total'
```

Compare doubles-heavy subset via `scripts/analyze_match_patterns.py` or audit SQL from [tennis-ppv-production-audit.md](../architecture/tennis-ppv-production-audit.md).

## Dependencies

- [122](./122-tennis-calendar-event-source.md) — calendar must list doubles fixtures (ESPN WTA/ATP) ✅
- [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — optional secondary fixtures ✅
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — requeue after fix ships
- [120](./120-fix-ppv-date-extraction-parsing-bugs.md) — correct calendar day ✅

## Out of scope

- Parsing every international naming convention (e.g. all non-Latin scripts) in v1 — cover audit Latin initial+surname pattern first.
- Matching aggregate feeds (`Multiview`, `Courtside`, `Philippe Chatrier ft …`) — remain `skipped` / non-calendar.
- Non-tennis doubles (e.g. beach volleyball) unless trivially shared via ` / ` calendar shape.

## Related docs

- [122 § Out of scope](./122-tennis-calendar-event-source.md) — explicitly deferred doubles extraction to a follow-up
- [ppv-matching-strategies.md](../architecture/ppv-matching-strategies.md) — add subsection when implemented

## Recommended order

**127 after Wave 12 calendar + requeue** — calendar sources without doubles parsing still leave ~half of tennis `no_match` on the table. Can spike parsing on fixtures in parallel with production requeue for singles.
