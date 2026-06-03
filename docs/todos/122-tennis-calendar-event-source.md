# Tennis calendar event source for PPV matching

**Status:** 🟡 Phase 1 spike complete — Phase 2 not started  
**Priority:** P2  
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`)

## Problem

Tennis is the **largest single `no_match` category** in production: **341 active channels** with names like:

```
Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM :MAX NL  13
Tennis: Andy Lapthorne vs Niels Vink @ Jun 3 13:00 PM :MAX NL  17
```

Competitor extraction works. After fixing date parsing (TODO 120), channels will bucket to the correct day — but **TheSportsDB calendar scrape for that day contains zero tennis events** (213 events on 2026-06-03: basketball, baseball, soccer, handball only).

The enrichment pipeline therefore cannot match tennis PPV feeds using the current sole calendar source.

### Scope note

This TODO covers **professional tennis** (ATP/WTA/Challenger/ITF singles and doubles) and **wheelchair/exhibition** names that appear in provider feeds. It does **not** cover generic `Tennis: Multiview` placeholder slots (those should remain `skipped` via enrichability rules).

## Affected files

- `services/thesportsdb_calendar_scraper.py` — if tennis exists in TSDB under different sport keys (investigate first)
- New or existing: `services/tennis/` or extend `services/thesportsdb_service.py`
- `services/reverse_event_matcher/orchestrator.py` — multi-source event loading
- `models/ppv.py` — `Event.SOURCE_*` constant for new source
- `services/ppv/enrichment/match_pipeline.py` — calendar day load includes tennis source
- Architecture: [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md), [55](./55-multi-source-events-schema-and-detail-fetch.md)
- Tests: new integration fixtures under `tests/ppv/fixtures/`

## Requirements for resolution

### Discovery (spike — required before implementation)

1. **Audit TheSportsDB** for tennis coverage: league IDs, event density, name format vs channel titles (player order, `@` times).
2. **Evaluate alternative APIs** (document in TODO before coding):
   - TheSportsDB tennis leagues (if adequate)
   - API-Tennis / Sportradar / other (license, rate limits, self-host constraints)
   - ESPN/scrape (discouraged unless no API)
3. **Decision record** in architecture doc: chosen source, refresh interval, composite `(external_id, source)` scheme per TODO 55.

### Functional

1. **Calendar ingestion:** Tennis events available per UTC day for at least **±7 days** (align with existing calendar cache window).
2. **Player name matching:** Fuzzy match channel competitors to event players:
   - Handle `First Last` vs `Last, First`
   - Doubles: `A Cornet D Hantuchova vs M Hingis A Kerber` — multi-player extraction may need extension (separate sub-task if out of scope; document)
3. **Event persistence:** Matched tennis events stored with correct `source` and `external_id`; detail fetch strategy documented (TSDB detail vs metadata-only).
4. **Cache:** Tennis calendar obeys same persistent cache / TTL patterns as TheSportsDB scraper (`calendar_cache.json` or separate file — document tradeoff).
5. **Graceful degradation:** If tennis source unavailable, enrichment logs provider failure on status API (pattern from TODO 67 `providers_failed`); channels remain `no_match`, not crash.

### Out of scope (explicit)

- Matching every `Tennis: Multiview` aggregate channel.
- Historical tennis replays with dates in the past beyond retention window.

## Proposed solution

**Phase 1 — Spike (1–2 days)**

- Sample 20 production tennis channel names; manually verify which appear in candidate APIs for the inferred date.
- Fill decision table in this TODO or architecture doc.

**Phase 2 — Minimal viable source**

- Implement `TennisCalendarProvider.get_events_for_date(date) -> List[CalendarEvent]`.
- Register in calendar scraper aggregation alongside TheSportsDB + MiLB.
- Normalize to shared `CalendarEvent` shape (`home_team`/`away_team` as player names or `event_name` for doubles).

**Phase 3 — Matching tuning**

- Lower confidence threshold for tennis only if needed (document in `constants.py`).
- Optional: sport-specific strategy in `match_strategy.py`.

## Acceptance criteria

- [ ] Spike complete: data source chosen and documented with sample API responses.
- [ ] ≥ **80%** of production sample set (20 channels from 2026-06-03 audit) match when enrichment runs on their calendar day.
- [ ] Production `no_match` count for `Tennis:` prefix drops from **341** by ≥ **70%** after requeue (TODO 124).
- [ ] New events use distinct `Event.source` value; no `external_id` collision with TheSportsDB rows.
- [ ] Calendar cache stats on `/api/ppv-enrichment/status` include tennis entry counts or documented separately.
- [ ] Unit + integration tests use **recorded fixtures** only (no live HTTP in CI).

## Test plan

### Spike checklist

| Step | Command / action | Pass criteria |
|------|------------------|---------------|
| TSDB tennis leagues | Query TSDB API for tennis events on 2026-06-03 | Event count > 0 or ruled out |
| Sample channel match | Manual: Kalinskaya vs Chwalinska on Jun 3 | Found in chosen source |
| Rate limits | Load 7 days of tennis | Within API budget |

### Unit tests

- `tests/ppv/test_tennis_calendar_provider.py` — parse API fixture → `CalendarEvent` list.
- `tests/ppv/test_tennis_name_matching.py` — player name normalization cases.

### Integration tests

- Load merged calendar (TSDB + tennis) for fixed date; `find_matches("Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM")` returns event.
- Enrichment E2E with mocked tennis provider → `EventChannelLink` created.

### Production verification

```bash
docker exec iptv-proxy-v2 python scripts/analyze_matching_stats.py
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=no_match&search=Tennis%3A' | jq '.pagination.total'
```

Baseline: **341** tennis-prefixed `no_match`.

## Dependencies

- [120](./120-fix-ppv-date-extraction-parsing-bugs.md) — correct `@ Jun 3` date bucketing (prerequisite).
- [55](./55-multi-source-events-schema-and-detail-fetch.md) — composite external IDs (done; follow same patterns).
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — re-process tennis channels after source live.

## Recommended order

**122 after 120** — date fix alone will not match tennis; new source required. Can run spike in parallel with 121.

---

## Phase 1 spike completion (2026-06-03)

**Spike doc:** [tennis-calendar-source-spike.md](../architecture/tennis-calendar-source-spike.md)  
**Probe script:** `scripts/spike_tennis_calendar.py` (requires `PPV_API_TENNIS_KEY`; not production-wired)

### TSDB verdict: **No** (ruled out)

Production `get_events_for_date("2026-06-03")` → **79 events, 2 tennis** (ATP RG men's QF only). WTA, wheelchair, junior, and ITF draws missing. Player search finds Kalinskaya/Sabalenka/etc., but no corresponding events. TSDB cannot support 341 `no_match` tennis channels.

### Recommended source: **API-Tennis** (`api.api-tennis.com`)

| Factor | Rationale |
|--------|-----------|
| Coverage | ATP/WTA/Challenger/ITF/Boys/Girls documented; date-range `get_fixtures` fits ±7 day window |
| Cost | ~$40/mo, 8k req/day — one call per date range ≪ budget |
| Integration | Same merge pattern as MiLB in `thesportsdb_calendar_scraper.py` |
| Self-host | Cloud API (acceptable; same as TSDB/MLB Stats) |
| Names | `event_first_player` / `event_second_player` as `"F. Last"` — needs last-name fuzzy match (existing strategies) |

**Not chosen for MVP:** Sportradar (enterprise quote), ATP/WTA official (B2B only), ESPN scrape (discouraged).

### Sample API responses (keys redacted)

**TheSportsDB** — only tennis on 2026-06-03:

```json
{"idEvent": "2479089", "strEvent": "Roland Garros Félix Auger Aliassime vs Flavio Cobolli", "strLeague": "ATP World Tour", "dateEvent": "2026-06-03", "strHomeTeam": null, "strAwayTeam": null}
```

**API-Tennis** (documented fixture shape; live validation pending trial key):

```json
{"event_key": "143104", "event_date": "2026-06-03", "event_time": "11:00", "event_first_player": "A. Kalinskaya", "event_second_player": "M. Chwalinska", "event_type_type": "Wta Singles", "tournament_name": "French Open", "tournament_round": "Quarter-finals"}
```

### Sample channel verification (5 matchups)

| Channel | Real event? | TSDB | API-Tennis (expected) |
|---------|-------------|------|------------------------|
| Kalinskaya vs Chwalinska | Yes (RG WTA QF) | No | Yes |
| Sabalenka vs Shnaider | Yes (RG WTA QF) | No | Yes |
| Lapthorne vs Vink | Yes (wheelchair quad QF) | No | TBD — wheelchair not in public type list |
| Hewett/Reid vs Cattaneo/Rodrigues | Yes (WC doubles QF) | No | TBD |
| Cvetkovic vs Pinera Celorio | Yes (junior girls) | No | Likely |

### Phase 2 MVP outline

1. `services/tennis_calendar.py` — `fetch_tennis_events_for_date()` → `CalendarEvent` with `source=api_tennis`
2. `Event.SOURCE_API_TENNIS = "api_tennis"`; `external_id` = API `event_key`
3. Merge in `TheSportsDBCalendarScraper.get_events_for_date()` (MiLB pattern)
4. Settings: `ppv_api_tennis_key`; cache TTL 12h; single `get_fixtures` for ±7 day window
5. Detail fetch: skip / `basic` completeness (no TSDB detail queue)
6. Recorded fixtures + integration test

**Estimate:** 2–3 days. **Blockers:** API-Tennis trial to confirm wheelchair coverage; doubles name parsing; TODO 120 date fix; production circular-import in API supplement.

### Open questions for Phase 2

- [ ] Does API-Tennis include wheelchair/quad draws on Starter plan?
- [ ] Abbreviated vs full name matching threshold — reuse LastName strategy or tennis-specific?
- [ ] Doubles channel format (`A Hewett G Reid`) — extend competitor extractor or match on combined tokens?
- [ ] Shared `calendar_cache.json` vs separate tennis cache file?
- [ ] Legends/exhibition slots (Cornet/Hingis) — accept permanent `no_match`?
