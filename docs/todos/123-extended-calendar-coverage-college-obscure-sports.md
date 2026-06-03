# Extended calendar coverage: college, obscure leagues, boxing

**Status:** ⬜ Not started  
**Priority:** P2  
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`)

## Problem

Several PPV channel categories have valid competitor extraction and (after TODO 120) reasonable dates, but **no corresponding event in TheSportsDB calendar**. These are distinct from tennis (TODO 122) — each may need a different data source or an explicit **unsupported** classification.

Production examples (2026-06-03 audit):

| Category | Example channel | Calendar lookup | Active `no_match` (approx.) |
|----------|-----------------|-----------------|------------------------------|
| English lower-league / playoffs | `Live Football 01: Charlton Athletic vs Leicester City 12:30pm` | **0** events for Charlton/Leicester on Jun 3 | 1+ (Championship playoff) |
| College softball | `#11 Texas Tech vs #2 Texas (WCWS Finals Game 1) @ Jun 4 01:55` | **0** WCWS events | 2 |
| Obscure DAZN football | `FC Kallon vs Old Edwardians FC \| Premier League - Sierra Leone` | **0** | ~5 |
| College BTN+ | `(US) (BTN+ 001) \| Baseball: Michigan Wolverines Vs. Washington Huskies` | **0** | scattered |
| Stale ESPN Play archive | `(AU) ESPN PLAY 52: … Cal State Northridge vs. Idaho \| 11-09-2023` | N/A (past) | ~3 |
| Boxing | `Boxing 1 : Oleksandr Usyk vs. Rico Verhoeven` | **0** boxing in calendar | ~47 |

TheSportsDB calendar for 2026-06-03 (213 events) is dominated by **MLB, NBA/WNBA, international soccer friendlies, handball** — not college championships, lower-tier international leagues, or combat sports.

## Affected files

- `services/thesportsdb_calendar_scraper.py` — league coverage gaps
- `services/sportsipy_service.py` — college schedules (NCAA) if reused
- `services/thesportsdb_service.py` — league-specific fetches
- `services/ppv/enrichability.py` — classify stale archive / unsupported sport → `skipped` not `no_match`
- `services/ppv/extraction/competitors.py` — sport hints from category (`BTN+`, `DAZN`, `WCWS`)
- New providers under `services/ppv/calendar_providers/` (or similar)
- Architecture: [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md)
- Tests: `tests/ppv/fixtures/` per sport

## Requirements for resolution

This TODO is intentionally **multi-track**. Each track has independent acceptance criteria; complete tracks independently.

### Track A — College sports (WCWS, BTN+, NCAA)

**Requirements:**

1. Identify API/source for **NCAA softball/baseball** (WCWS), at minimum for championship / high-profile games present in PPV feeds.
2. **Sportsipy** or NCAA official feeds — evaluate licensing and reliability; document choice.
3. Team names: resolve `#11 Texas Tech` → `Texas Tech Red Raiders` (ranking prefix strip already partial in extractor — verify).
4. Match confidence and validation distinct from MLB (sport context from category `DISNEY+ PPV`, `BTN+ PPV`).

**Acceptance:**

- [ ] WCWS production example (`Texas Tech vs Texas`, Jun 4 2026) matches when game exists in source.
- [ ] BTN+ channels for games in source match; out-of-source remain documented `no_match`.

### Track B — Lower-tier / regional football

**Requirements:**

1. Charlton vs Leicester (Championship playoff) — determine if TSDB league ID missing from scraper config vs truly absent.
2. If absent: evaluate **football-data.org** (already a context provider?) for English Championship playoff round.
3. Obscure DAZN leagues (Sierra Leone, Aruba, etc.) — **default: no source** unless ROI justifies; classify as `skipped` with reason `unsupported_league` instead of perpetual `no_match`.

**Acceptance:**

- [ ] Charlton/Leicester fixture matches on correct date if source added, OR documented as unsupported with enrichability skip.
- [ ] DAZN obscure league channels no longer inflate `no_match` metrics (moved to `skipped` with visible reason in API).

### Track C — Boxing / combat sports

**Requirements:**

1. Audit boxing channel volume and provider patterns (~47 `no_match`).
2. If volume justifies: add boxing event source OR integrate with existing ESPN context provider for fight cards.
3. Channels with **no date** must not receive garbage default dates (depends on TODO 120); status should be `skipped` / `no_date`.

**Acceptance:**

- [ ] Usyk vs Verhoeven-style channels: `extract_date` → `None`; enrichability → `skipped` (not wrong-day search).
- [ ] If boxing source added: ≥ 50% of dated boxing PPV channels match on event day.

### Track D — Stale archive channels

**Requirements:**

1. Detect **explicit past dates** in title (`11-09-2023`, `01-18-2024`) beyond enrichment window (e.g. > 21 days past).
2. Mark `skipped` with reason `stale_archive`, not `no_match`.
3. Optional cleanup job to deactivate `is_active=False` for ancient ESPN Play rows.

**Acceptance:**

- [ ] ESPN Play 2023/2024 examples move from `no_match` to `skipped`.
- [ ] `/api/ppv-enrichment/channels?status=skipped` summary includes stale archive count or filter.

## Proposed solution

1. **Inventory script** (optional): `scripts/analyze_no_match_by_league.py` — group `no_match` by extracted sport/league prefix.
2. **Per-track providers** registered in calendar aggregation (same pattern as TODO 122).
3. **Enrichability extensions** for unsupported/stale paths — reduces noise in `no_match` metric.
4. Update **`docs/architecture/ppv-matching-strategies.md`** with supported vs unsupported sport matrix.

## Test plan

### Per-track fixture tests

| Track | Fixture file | Assert |
|-------|--------------|--------|
| A | `tests/ppv/fixtures/wcws_channels.json` | Match or explicit skip |
| B | `tests/ppv/fixtures/championship_playoff.json` | Charlton/Leicester |
| C | `tests/ppv/fixtures/boxing_channels.json` | No date → skip |
| D | `tests/ppv/fixtures/stale_espn_play.json` | stale → skip |

### Integration

- Mock calendar provider per track; run enrichment orchestrator on fixture channel list; assert status distribution.

### Production verification

```bash
docker exec iptv-proxy-v2 python scripts/show_unmatched_channels.py --reason no-match | head
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/dashboard/summary' | jq '.data.ppv.enrichment'
```

Track progress by **`no_match_count`** vs **`skipped`** with documented reasons — total unsolved channels may stay similar but metrics become honest.

## Dependencies

- [120](./120-fix-ppv-date-extraction-parsing-bugs.md) — prerequisite for all tracks.
- [122](./122-tennis-calendar-event-source.md) — tennis split out; do not bundle here.
- [57](./57-centralize-sport-key-mappings.md) — sport context for college vs pro.
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — re-evaluate channels after changes.

## Recommended order

**123 after 120**; tracks A–D can be parallelized by priority:

1. **Track D** (stale archive) — quick enrichability win, clears metric noise.
2. **Track A** (WCWS) — high-visibility live events.
3. **Track B** (Charlton/Leicester) — investigate TSDB config first (may be quick fix).
4. **Track C** (boxing) — lower volume unless provider adds more fights.
