# SofaScore tennis calendar — slice 1 (client + parser)

**Status:** ✅ Done  
**Priority:** P2  
**PR:** https://github.com/klopstack/iptv-proxy-v2/pull/58
**Roadmap:** [ROADMAP-active.md](./ROADMAP-active.md) — Wave 12 batch **AH** (after ESPN tennis, [122](./122-tennis-calendar-event-source.md))  
**Audit:** [tennis-ppv-production-audit.md](../architecture/tennis-ppv-production-audit.md), June 2026

## Summary

Implement a **small in-repo** SofaScore calendar client and tennis event parser: recorded fixtures, unit tests, and `Event.SOURCE_SOFASCORE`. This slice does **not** merge into `TheSportsDBCalendarScraper` or the enrichment pipeline — that is [126](./126-sofascore-calendar-multi-sport-and-enrichment.md).

SofaScore is the **optional secondary** tennis calendar source for gaps ESPN does not cover well (wheelchair, legends, ITF, exhibition). **ESPN** remains the primary tennis source ([122](./122-tennis-calendar-event-source.md), PR #56 slice 1).

## Problem

Production tennis `no_match` volume (~341 channels) is driven by missing calendar fixtures, not parsing. ESPN (PR #56) should cover ATP/WTA/Challenger draws for the main feed. Residual categories (wheelchair, legends, some ITF) may still lack events after ESPN ships.

SofaScore exposes a stable public schedule endpoint without a paid API key:

```http
GET https://api.sofascore.com/api/v1/sport/tennis/scheduled-events/2026-06-03
```

We need a testable module that maps responses to the shared `CalendarEvent` shape before any production wiring.

## Non-goals (this slice)

- Wiring into `thesportsdb_calendar_scraper.py` or enrichment ([126](./126-sofascore-calendar-multi-sport-and-enrichment.md))
- Forking or vendoring [tunjayoff/sofascore_scraper](https://github.com/tunjayoff/sofascore_scraper) wholesale — use it only as a **reference** for rate-limit / backoff patterns
- Replacing ESPN as primary tennis source
- Multi-sport slugs (MMA, table tennis, etc.) — documented in 126

## Affected files (expected)

- **New:** `services/ppv/calendar_providers/sofascore/` (or `services/sofascore_calendar.py` — match ESPN tennis module layout from PR #56)
  - HTTP client with rate limit + cache
  - Tennis response → `CalendarEvent` mapper
- `models/ppv.py` — `Event.SOURCE_SOFASCORE = "sofascore"`; extend `SOURCE_TYPES`
- `config.py` / settings — feature flag `ppv_sofascore_calendar_enabled` (default **off**)
- **New:** `tests/ppv/fixtures/sofascore/` — recorded JSON per date
- **New:** `tests/ppv/test_sofascore_tennis_calendar.py`
- Architecture (optional this slice): short note in [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md) linking SOURCE + flag

## API and operational constraints

| Constraint | Value | Notes |
|------------|-------|-------|
| Endpoint pattern | `/api/v1/sport/{sport}/scheduled-events/{YYYY-MM-DD}` | Slice 1: `sport=tennis` only |
| Rate limit | ~**20 req/min** with jitter | Align with existing scrapers (`thesportsdb_calendar_scraper`, MiLB) |
| Cache TTL | **12 hours** | Disk or namespaced keys in shared calendar cache — match MiLB/TSDB pattern |
| Feature flag | Default **off** | No production traffic until [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) |
| CI | **Fixtures only** | No live HTTP in unit tests |

Reference implementation patterns (not a dependency): [sofascore_scraper](https://github.com/tunjayoff/sofascore_scraper) — backoff, spacing between requests.

## Requirements

### Client

1. `fetch_scheduled_events(sport: str, date_str: str, *, force_refresh: bool = False) -> dict` — raw JSON or typed wrapper.
2. Respect global rate limiter shared with other calendar HTTP clients (or module-local limiter with same constants).
3. Persist cache entries with TTL 12h; cache key includes sport + date + schema version.
4. On HTTP errors / empty body: log and return empty list from parser layer (no exception through public API).

### Tennis parser

1. Map SofaScore scheduled events to `CalendarEvent`:
   - `external_id` — stable SofaScore event id from payload
   - `source` — `sofascore`
   - `home_team` / `away_team` — player names (singles); doubles documented if payload differs
   - `event_date` / start time — UTC-normalized per existing calendar conventions
   - `sport` — tennis registry key
2. Filter to **scheduled / in-progress / finished** types appropriate for PPV matching (document excluded statuses in module docstring).
3. Name normalization hooks compatible with existing last-name fuzzy strategies (no enrichment wire yet).

### Model constant

```python
Event.SOURCE_SOFASCORE = "sofascore"
```

Composite uniqueness follows [55](./55-multi-source-events-schema-and-detail-fetch.md): `(external_id, source)`.

## Proposed solution

1. Add `services/ppv/calendar_providers/sofascore/client.py` — session, rate limit, cache read/write.
2. Add `parser_tennis.py` — `parse_tennis_scheduled_events(payload, date_str) -> List[CalendarEvent]`.
3. Export `fetch_tennis_events_for_date(date_str: str, *, force_refresh: bool = False) -> List[CalendarEvent]` for tests and future merge in 126.
4. Record one production-like fixture date (2026-06-03 audit day) under `tests/ppv/fixtures/sofascore/`.
5. Settings: `ppv_sofascore_calendar_enabled: bool = False`.

## Acceptance criteria

- [ ] `Event.SOURCE_SOFASCORE` defined; migrations/tests accept new source value.
- [ ] Parser converts recorded fixture to ≥1 `CalendarEvent` with correct `external_id` and player names for a known RG 2026-06-03 matchup from audit (e.g. Kalinskaya vs Chwalinska **if** present in fixture; else document nearest sample).
- [ ] Rate limiter unit test or mock proves spacing ≥ configured minimum between burst requests.
- [ ] Cache hit skips HTTP on second call within TTL (mock transport).
- [ ] Feature flag off → public fetch function returns `[]` without HTTP (or raises clear `DisabledError` only in tests).
- [ ] **No** imports from enrichment orchestrator, `match_pipeline`, or `thesportsdb_calendar_scraper` merge path.
- [ ] All tests pass without network.

## Test plan

| Test | File | Pass criteria |
|------|------|---------------|
| Parser fixture | `tests/ppv/test_sofascore_tennis_calendar.py` | Event count > 0; fields populated |
| Cache | same | Second call uses cache mock |
| Rate limit | same | N rapid calls spaced |
| Source constant | model test or parser test | `source == "sofascore"` |
| Flag off | same | Empty result, no HTTP |

Manual spike (optional, local only):

```bash
# Not in CI — verify endpoint still responds
curl -s 'https://api.sofascore.com/api/v1/sport/tennis/scheduled-events/2026-06-03' | jq '.events | length'
```

## Dependencies

- [122](./122-tennis-calendar-event-source.md) — ESPN primary path (PR #56); avoid duplicate primary integration work.
- [55](./55-multi-source-events-schema-and-detail-fetch.md) — composite `(external_id, source)` ✅.
- [120](./120-fix-ppv-date-extraction-parsing-bugs.md) — correct calendar day bucketing ✅ (enrichment still benefits when wired in 126).

## Blocks

- [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — calendar merge + fallback ordering.

## Completion

- **PR:** https://github.com/klopstack/iptv-proxy-v2/pull/58
- **Deliverables:** `services/tennis/sofascore_calendar.py`; `Event.SOURCE_SOFASCORE`; recorded fixtures in `tests/ppv/fixtures/sofascore/`; unit tests without network.
