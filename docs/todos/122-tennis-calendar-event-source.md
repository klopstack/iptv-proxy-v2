# Tennis calendar event source for PPV matching

**Status:** ✅ Done  
**Priority:** P2  
**PRs:** [#55](https://github.com/klopstack/iptv-proxy-v2/pull/55) (spike), [#56](https://github.com/klopstack/iptv-proxy-v2/pull/56) (ESPN slice 1)
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`) — [tennis-ppv-production-audit.md](../architecture/tennis-ppv-production-audit.md)  
**Follow-up (secondary calendar):** [125](./125-sofascore-tennis-calendar-slice1.md), [126](./126-sofascore-calendar-multi-sport-and-enrichment.md)

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
   - TheSportsDB tennis leagues (if adequate) — **ruled out** (spike)
   - API-Tennis / Sportradar / other — deferred; spike favored API-Tennis but **superseded by ESPN decision** (below)
   - **ESPN** — primary calendar for ATP/WTA/Challenger (PR #56 slice 1)
   - **SofaScore** — optional secondary for wheelchair, legends, ITF ([125](./125-sofascore-tennis-calendar-slice1.md) / [126](./126-sofascore-calendar-multi-sport-and-enrichment.md))
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

**Phase 2 — ESPN primary (PR #56)**

- Implement ESPN tennis `get_events_for_date(date) -> List[CalendarEvent]` (in-repo module; no wholesale fork of third-party scrapers).
- Register in calendar scraper aggregation alongside TheSportsDB + MiLB **before** SofaScore.
- Normalize to shared `CalendarEvent` shape (`home_team`/`away_team` as player names or `event_name` for doubles).
- `Event.SOURCE_ESPN` (or agreed constant from PR #56); `external_id` from ESPN payload.

**Phase 2b — SofaScore secondary (optional)**

- [125](./125-sofascore-tennis-calendar-slice1.md) — client + parser + fixtures + `SOURCE_SOFASCORE`; not wired to enrichment.
- [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — merge after ESPN; feature flag default off; wheelchair/legends/ITF gaps.

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

### Spike recommendation (2026-06-03): API-Tennis — **superseded**

The spike below recommended API-Tennis. **Current plan (June 2026):** **ESPN** as primary tennis calendar (PR #56); **SofaScore** as optional secondary ([125](./125-sofascore-tennis-calendar-slice1.md), [126](./126-sofascore-calendar-multi-sport-and-enrichment.md)) for wheelchair, legends, ITF, and later niche sports.

| Factor | API-Tennis (spike) | ESPN (chosen primary) | SofaScore (secondary) |
|--------|-------------------|----------------------|------------------------|
| Coverage | Broad draws documented | ATP/WTA/Challenger live draws | Wheelchair, ITF, legends gaps |
| Cost | ~$40/mo API key | In-repo / existing patterns | No key; rate-limited scrape |
| Integration | MiLB merge pattern | PR #56 slice 1 | After ESPN; flag off by default |

**Not chosen for MVP:** Sportradar (enterprise quote), ATP/WTA official (B2B only), API-Tennis (deferred), wholesale fork of [sofascore_scraper](https://github.com/tunjayoff/sofascore_scraper).

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

### Phase 2 MVP outline (ESPN — PR #56)

1. ESPN tennis calendar module — `fetch_espn_tennis_events_for_date()` → `CalendarEvent` with ESPN `source` constant from PR #56
2. Merge in `TheSportsDBCalendarScraper.get_events_for_date()` (MiLB pattern) **before** any SofaScore rows
3. Cache TTL 12h; align rate limits with existing scrapers
4. Detail fetch: skip / `basic` completeness (no TSDB detail queue for non-TSDB sources)
5. Recorded fixtures + integration test

**Estimate:** PR #56 scope. **Blockers:** doubles name parsing; TODO 120 date fix ✅.

### Phase 2b outline (SofaScore — see 125/126)

1. [125](./125-sofascore-tennis-calendar-slice1.md) — isolated client + `SOURCE_SOFASCORE`
2. [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — merge after ESPN; `ppv_sofascore_calendar_enabled` default false

### Open questions for Phase 2–2b

- [ ] ESPN payload coverage for wheelchair/quad draws on same day as production audit?
- [ ] Abbreviated vs full name matching threshold — reuse LastName strategy or tennis-specific?
- [ ] Doubles channel format (`A Hewett G Reid`) — extend competitor extractor or match on combined tokens?
- [ ] SofaScore fixture overlap with ESPN — dedup rules in [126](./126-sofascore-calendar-multi-sport-and-enrichment.md)
- [ ] Legends/exhibition slots — ESPN vs SofaScore vs permanent `no_match` / `skipped`

## Completion

- **PR #55:** [spike/122-tennis-calendar-source](https://github.com/klopstack/iptv-proxy-v2/pull/55) — source evaluation, architecture spike doc
- **PR #56:** [feature/espn-tennis-calendar](https://github.com/klopstack/iptv-proxy-v2/pull/56) — ESPN tennis calendar client, parser, merge into `get_events_for_date`
- **Follow-up:** SofaScore secondary — [125](./125-sofascore-tennis-calendar-slice1.md) ✅ [#58](https://github.com/klopstack/iptv-proxy-v2/pull/58), [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) ✅ [#60](https://github.com/klopstack/iptv-proxy-v2/pull/60)
