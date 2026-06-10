# SofaScore college / amateur calendar provider (multi-sport extension)

**Status:** ✅ Complete  
**Priority:** P1  
**Depends on:** [130](./130-ncaa-college-calendar-source-spike.md) ✅ — hybrid go-ahead ([spike doc](../architecture/ncaa-college-calendar-source-spike.md))  
**Blocks:** [129](./129-ppv-replay-archive-enrichment-flosp.md) Track B (historical replay matching)

## Problem

Flo and other archive PPV channels need **day-indexed fixtures** for NCAA, junior hockey, and amateur college sports. [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) wired **tennis only**; [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md) lists MMA/table-tennis as future slugs but **not college**.

Production blockers today:

1. **No parser** for team-sport SofaScore payloads (tennis uses player `homeTeam`/`awayTeam` names — same shape, but league/sport registry differs).
2. **`_is_date_in_window`** in `services/tennis/sofascore_calendar.py` uses `MAX_API_SUPPLEMENT_DAYS_BACK = 14` — Flo replays from **Oct 2025** return **zero events** even if the API has data.
3. **No merge** of non-tennis SofaScore rows into `TheSportsDBCalendarScraper.get_events_for_date()`.
4. Sportsipy schedules ([130](./130-ncaa-college-calendar-source-spike.md)) may fill gaps but are not a substitute unless spike rejects SofaScore.

## Scope

Implement the **spike-recommended hybrid path** ([130](../architecture/ncaa-college-calendar-source-spike.md)): SofaScore `ice-hockey` slug + Sportsipy `ncaab` supplement for DIII basketball. This TODO covers the SofaScore slice and replay window plumbing; Sportsipy fallback hooks live in `match_pipeline.py`.

### In scope (Phase A — minimum for Flo replay)

| Sport family | SofaScore slug (from spike) | PPV examples |
|--------------|----------------------------|--------------|
| College / pro-adjacent hockey | `ice-hockey` | `Colorado Eagles vs San Diego Gulls` |
| College basketball (DIII) | Sportsipy `ncaab` supplement — **not** SofaScore `basketball` | `Occidental vs Chapman - Mens` |
| Additional slug(s) from spike | TBD | Field hockey, volleyball, etc. |

### Phase B (optional flags)

Per-sport feature flags (`ppv_sofascore_basketball_enabled`, …) — only when volume justifies ([126](./126-sofascore-calendar-multi-sport-and-enrichment.md) pattern).

## Affected files

- `services/ppv/calendar_providers/sofascore/` — add `parser_ice_hockey.py` on [133](./133-sofascore-multi-sport-refactor-and-football-followups.md) foundation ✅
- `services/thesportsdb_calendar_scraper.py` — merge SofaScore team-sport events; replay date bypass hook
- `services/ppv/constants.py` — replay calendar lookback (`REPLAY_CALENDAR_DAYS_BACK`); new settings keys
- `services/ppv/sport_registry.py` — map SofaScore categories → internal sport keys (`ncaab`, hockey, …)
- `services/ppv/enrichment/match_pipeline.py` — when `replay_archive` metadata set, allow calendar fetch outside ±14d live window ([129](./129-ppv-replay-archive-enrichment-flosp.md))
- `models/ppv.py` / settings — per-sport SofaScore flags
- `docs/architecture/sofascore-calendar-sport-slugs.md` — slug table from spike
- `docs/architecture/ppv-multi-source-events.md` — merge order diagram
- Tests: `tests/ppv/fixtures/sofascore/`, `tests/ppv/test_sofascore_college_calendar.py`, merge tests

## Requirements

### Client & historical window

1. **Replay calendar window:** When enrichment requests events for `replay_archive` channels (or explicit historical date from title), fetch SofaScore for that date if within `REPLAY_CALENDAR_DAYS_BACK` (default **400 days** — tune from spike; must cover Oct 2025 from Jun 2026).
2. **Live window unchanged:** Non-replay enrichment keeps `MAX_API_SUPPLEMENT_DAYS_BACK/AHEAD` (14 / 90).
3. Shared rate limiter (~20 req/min); cache TTL 12h keyed by `{slug}:{date}`.
4. Feature flag **`ppv_sofascore_college_enabled`** (default off) gates Phase A slugs; master `ppv_sofascore_calendar_enabled` may OR with tennis flag — document operator toggles.

### Parsers

1. **`parse_team_scheduled_events(payload, date_str, *, sport_key)`** → `List[CalendarEvent]`:
   - `external_id`, `source=sofascore`, `home_team`, `away_team`, `scheduled_at`, `sport`, `league_name` from tournament metadata
   - Same status filtering as tennis (`notstarted`, `inprogress`, `finished`)
2. **Sport registry mapping** from tournament category (e.g. `"USA", "NCAA"` hints) for matcher validation.
3. **Name normalization hooks** compatible with college aliases (strip `- Mens -` / `- Womens -` suffixes from channel side in extractor, not parser).

### Calendar merge

1. Merge order after TSDB + MiLB + ESPN tennis + SofaScore tennis:
   - **SofaScore college/amateur** (flag on)
2. De-dupe vs TSDB on `(home, away, calendar day)` if duplicate — prefer TSDB for pro leagues, SofaScore for college-only fixtures (document rule from spike).
3. `/api/ppv-enrichment/status` — extend `get_sofascore_calendar_stats()` with per-slug counts.

### Enrichment integration

1. `match_pipeline` calendar load for replay channels uses **extracted event date** ([129](./129-ppv-replay-archive-enrichment-flosp.md)).
2. Successful match → `Event.scheduled_at` in past → visibility **Replay** (no code change if link exists).

## Acceptance criteria

- [x] With flags on, `get_events_for_date("2025-10-22")` includes SofaScore college/hockey events (count > 0 when API has fixtures — use recorded fixture in CI).
- [x] With college flag off, behavior identical to pre-131 (tennis-only SofaScore).
- [x] ≥10 Flo sample titles from [130](./130-ncaa-college-calendar-source-spike.md) match in integration test (mocked fixture JSON).
- [x] Replay-dated channel (`2025-10-22`) triggers fetch despite date > 14 days ago; live channel on same code path without `replay_archive` does **not** expand window.
- [x] Rate limit + cache tests ported from tennis module.
- [x] Architecture docs updated; spike doc linked in **Completion**.
- [ ] Production: Flo `matched` count > 0 after [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A + requeue ([124](./124-ppv-enrichment-attempt-tracking-and-requeue.md)).

## Test plan

| Test | File | Criteria |
|------|------|----------|
| Parser fixture | `test_sofascore_college_calendar.py` | Basketball + hockey events parsed |
| Historical window | same | `2025-10-22` allowed for replay context only |
| Merge | `test_sofascore_calendar_merge.py` | College rows appear in scraper output |
| E2E replay | `test_replay_calendar_matching.py` (129) | Flo channel links to past event |
| Flag off | same | No HTTP / no merge |

Fixtures: commit redacted JSON from spike under `tests/ppv/fixtures/sofascore/scheduled_events_20251022_basketball.json` (names from spike).

## Proposed implementation phases

1. **Refactor** SofaScore module to shared client + sport-specific parsers (tennis parser unchanged behavior).
2. **Historical window** plumbing in scraper + match_pipeline replay hook.
3. **Phase A slugs** from spike (likely `basketball`, `ice-hockey`).
4. **Production enable** + Flo prefix requeue + metrics in Completion.

## Dependencies

- [130](./130-ncaa-college-calendar-source-spike.md) — **required** slug list + hit-rate gate
- [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A — replay provider metadata for window routing
- [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — merge patterns ✅
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — production verification

## Fallback (if spike rejects SofaScore for a sport)

Document in [130](./130-ncaa-college-calendar-source-spike.md) Completion; optional follow-up TODO:

- **Sportsipy day calendar adapter** — team schedule aggregation for NCAAB/NCAAF/NHL only
- **ESPN unofficial college scoreboard** — narrow scope, high maintenance

Do not start fallback implementation until spike closes and 131 scope is adjusted in this file’s **Completion** note.

## Recommended order

```
130 spike → 131 SofaScore college wire → 129 Track B replay matching → 124 requeue Flo
```

Parallel: [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A (enrichability) can land before 131 if calendar merge follows immediately after.

## Completion

Implemented hybrid stack from [130 spike](../architecture/ncaa-college-calendar-source-spike.md):

- SofaScore `ice-hockey` slug behind `ppv_sofascore_college_enabled` with `parser_ice_hockey.py` and TSDB hockey dedup
- `REPLAY_CALENDAR_DAYS_BACK=400` replay window bypass in client + scraper + match_pipeline date routing
- Sportsipy `ncaab` supplement hook in `match_pipeline` for `- Mens -` / `- Womens -` Flo replay channels (not day-bucket merge)
- Rejected SofaScore `basketball` for college — spike confirmed 0% DIII hit rate
- Fixtures: `tests/ppv/fixtures/sofascore/ice_hockey_2025-10-22.json`, `ice_hockey_2025-10-23.json`

**Deferred to 129 Track B:** E2E Flo channel → past `Event.scheduled_at` → Replay visibility wiring; production Flo requeue verification.
