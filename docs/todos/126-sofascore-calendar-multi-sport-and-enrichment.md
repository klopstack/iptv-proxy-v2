# SofaScore calendar — multi-sport, merge, and enrichment fallback

**Status:** ✅ Done  
**Priority:** P2  
**PR:** https://github.com/klopstack/iptv-proxy-v2/pull/60
**Roadmap:** [ROADMAP-active.md](./ROADMAP-active.md) — Wave 12 batch **AI**  
**Depends on:** [125](./125-sofascore-tennis-calendar-slice1.md), [122](./122-tennis-calendar-event-source.md) ESPN slice merged

## Summary

Wire SofaScore into the merged PPV calendar after ESPN tennis: feature-flagged secondary source, sport-slug documentation, optional multi-sport expansion (MMA, table tennis, etc.), and overlap notes with [123](./123-extended-calendar-coverage-college-obscure-sports.md).

## Problem

Slice 1 ([125](./125-sofascore-tennis-calendar-slice1.md)) delivers an isolated client/parser. Production matching still ignores SofaScore until:

1. Events merge into `TheSportsDBCalendarScraper.get_events_for_date()` (MiLB pattern).
2. Operator enables `ppv_sofascore_calendar_enabled`.
3. Merge order avoids duplicate/conflicting fixtures vs ESPN primary.

Residual tennis `no_match` after ESPN should prefer SofaScore only when ESPN returned no candidate for that player-day; wheelchair/legends/ITF are the main targets.

## Affected files

- `services/thesportsdb_calendar_scraper.py` — merge SofaScore events when flag on
- `services/ppv/calendar_providers/sofascore/` — extend beyond tennis parser
- `services/ppv/enrichment/match_pipeline.py` — calendar day load includes merged events
- `services/reverse_event_matcher/orchestrator.py` — multi-source load (if filtered by source)
- `routes/ppv_enrichment.py` — status/cache stats for SofaScore counts
- `docs/architecture/ppv-multi-source-events.md` — source precedence diagram
- **New:** `docs/architecture/sofascore-calendar-sport-slugs.md` — slug table + rate budget
- Tests: integration with mocked ESPN + SofaScore fixtures

## Merge semantics

| Order | Source | Role |
|-------|--------|------|
| 1 | TheSportsDB + MiLB | Existing production merge |
| 2 | **ESPN tennis** | Primary tennis ([122](./122-tennis-calendar-event-source.md)) |
| 3 | **SofaScore** | Secondary — fill gaps only when flag enabled |

**De-duplication:** Same `(player pair, calendar day)` from ESPN and SofaScore → keep ESPN row; log debug on SofaScore skip. Different `external_id` / `source` per [55](./55-multi-source-events-schema-and-detail-fetch.md).

**Detail fetch:** SofaScore events likely `data_completeness='basic'` — do not enqueue TheSportsDB detail worker (mirror `api_tennis` plan in spike doc).

## Requirements

### Wiring

1. When `ppv_sofascore_calendar_enabled` is true, merge SofaScore tennis events for the requested UTC day into calendar aggregation.
2. When flag false, zero SofaScore HTTP and zero merged rows (regression-safe).
3. `/api/ppv-enrichment/status` (or calendar stats subsection) exposes SofaScore cache hit/miss or event count per day when enabled.

### Sport slug documentation

Create `docs/architecture/sofascore-calendar-sport-slugs.md`:

| Slug | PPV use | Priority |
|------|---------|----------|
| `tennis` | Wheelchair, ITF, legends gaps | P0 (with 125) |
| `mma` | Future combat PPV overlap with [123](./123-extended-calendar-coverage-college-obscure-sports.md) Track C | P2 |
| `table-tennis` | Niche feeds | P3 |
| … | Document discovery process | — |

Include daily request budget: N sports × 1 req/day × 7-day window ≤ rate limit envelope.

### Multi-sport implementation (phased)

- **Phase A:** Tennis only in production merge (minimum for 126 AC).
- **Phase B:** Additional slugs behind per-sport flags (`ppv_sofascore_mma_enabled`, etc.) — implement only when production `no_match` volume justifies.

### Fallback behavior

1. Load ESPN tennis for day.
2. If channel sport is tennis and reverse match failed, optional second pass includes SofaScore-only events not deduped against ESPN (document algorithm in architecture doc).
3. Provider failure surfaces in enrichment status `providers_failed` pattern ([67](./67-ppv-misc-cleanup.md)).

### Overlap with TODO 123

- **Boxing / MMA:** Prefer existing ESPN context provider where fight cards exist; SofaScore `mma` slug is optional calendar supplement — coordinate in [123](./123-extended-calendar-coverage-college-obscure-sports.md) Track C.
- **College / obscure football:** Out of scope for SofaScore; remain 123 Tracks A–B.

## Acceptance criteria

- [ ] With flag on + fixtures, merged calendar for 2026-06-03 includes SofaScore tennis events with `source=sofascore`.
- [ ] With flag off, merged calendar identical to pre-126 behavior (ESPN + TSDB + MiLB only).
- [ ] ESPN + SofaScore duplicate matchup → single effective event for matching (ESPN wins).
- [ ] Integration test: tennis channel matches via SofaScore when ESPN fixture list empty for that player pair (mocked).
- [ ] Sport slug doc merged and linked from [122](./122-tennis-calendar-event-source.md) and README architecture section.
- [ ] Production tennis `no_match` drops measurably for wheelchair/ITF sample set after [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) requeue (target: document % in Completion, not fixed % in spec).
- [ ] No live HTTP in CI integration tests.

## Test plan

- `tests/ppv/test_sofascore_calendar_merge.py` — merge order, dedup, flag off
- `tests/ppv/test_tennis_enrichment_sofascore_fallback.py` — E2E with mocked ESPN empty + SofaScore populated
- Extend calendar scraper tests if centralized there

## Dependencies

- [125](./125-sofascore-tennis-calendar-slice1.md) — client, parser, `SOURCE_SOFASCORE` ✅ required
- [122](./122-tennis-calendar-event-source.md) — ESPN primary merged first
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — production verification after wire-up
- [123](./123-extended-calendar-coverage-college-obscure-sports.md) — coordinate MMA/boxing scope (parallel OK)

## Recommended order

```
122 ESPN merge (PR #56) → 125 SofaScore slice 1 → 126 wire + doc → 124 requeue
```

125 and 122 ESPN implementation can proceed in parallel until 126.

## Completion

- **PR:** https://github.com/klopstack/iptv-proxy-v2/pull/60
- **Deliverables:** SofaScore tennis wired into `get_events_for_date`; ESPN dedup filter; `ppv_sofascore_calendar_enabled` flag; `docs/architecture/sofascore-calendar-sport-slugs.md`; calendar merge tests with mocked supplemental fetches.
