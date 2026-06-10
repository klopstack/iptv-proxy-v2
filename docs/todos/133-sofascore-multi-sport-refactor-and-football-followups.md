# SofaScore multi-sport refactor + football/soccer follow-ups

**Status:** 🟡 Refactor slice implemented — PR pending; P0 production ops deferred to deploy/requeue  
**Priority:** P1 (post–World Cup structural refactor); P0 items only for remaining football production gaps (see below)  
**Roadmap:** [ROADMAP-active.md](./ROADMAP-active.md) — Wave 13 batch **AO**  
**Depends on:** [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) ✅, PR [#74](https://github.com/klopstack/iptv-proxy-v2/pull/74) football merge ✅  
**Related:** [131](./131-sofascore-college-amateur-calendar-provider.md) (college slugs share refactor target), [130](./130-ncaa-college-calendar-source-spike.md) (spike before college wire)

## Summary

PR [#74](https://github.com/klopstack/iptv-proxy-v2/pull/74) shipped SofaScore `football` for FIFA World Cup 2026 as an **urgent tactical slice** — but all SofaScore code still lives in `services/tennis/sofascore_calendar.py` with tennis-centric naming, **separate per-sport feature flags**, and **duplicated fetch/parse/merge paths** in `thesportsdb_calendar_scraper.py`. This TODO tracks (1) remaining football/soccer production follow-ups after WC deploy and (2) the **structural refactor** to make SofaScore a generic multi-sport calendar provider for tennis, football, and future slugs (MMA, table-tennis, college via [131](./131-sofascore-college-amateur-calendar-provider.md)).

## Problem

### Tactical WC slice, not architecture

World Cup coverage required wiring SofaScore `football` before the June 11, 2026 kickoff. The implementation correctly mirrors the tennis pattern from [126](./126-sofascore-calendar-multi-sport-and-enrichment.md), but it **extends the wrong module boundary**:

| Issue | Current state |
|-------|---------------|
| Module path | `services/tennis/sofascore_calendar.py` holds tennis **and** football parsers, HTTP client, cache, rate limiter |
| Scraper merge | `_fetch_sofascore_tennis_events_for_date` + `_fetch_sofascore_football_events_for_date` — separate methods per sport |
| Dedup helpers | `filter_sofascore_tennis_without_espn_duplicates` + `filter_sofascore_football_without_tsdb_duplicates` — parallel implementations |
| Feature flags | `ppv_sofascore_calendar_enabled` (tennis, default off) vs `ppv_sofascore_football_enabled` (football, default on) |
| Extensibility | Each new slug (college basketball, MMA, …) would copy the same boilerplate unless refactored first |

[131](./131-sofascore-college-amateur-calendar-provider.md) already notes the same refactor target (`services/ppv/calendar_providers/sofascore/`) but scopes to college/amateur slugs after [130](./130-ncaa-college-calendar-source-spike.md). **133 owns the shared refactor** so 131 implements college parsers on the generic foundation rather than duplicating a third sport-specific path.

### Remaining football gaps

PR #74 closed the critical WC calendar merge gap (TheSportsDB had 1 of 2 Jun 11 fixtures; SofaScore had full Group A coverage). Production follow-ups and broader soccer coverage remain.

## What's done

| Deliverable | PR / TODO | Notes |
|-------------|-----------|-------|
| SofaScore tennis client + parser | [125](./125-sofascore-tennis-calendar-slice1.md) ✅ [#58](https://github.com/klopstack/iptv-proxy-v2/pull/58) | `fetch_tennis_events_for_date`, recorded fixtures |
| Tennis calendar merge + sport-slug doc | [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) ✅ [#60](https://github.com/klopstack/iptv-proxy-v2/pull/60) | ESPN primary; SofaScore secondary; `ppv_sofascore_calendar_enabled` |
| SofaScore football merge (WC) | PR [#74](https://github.com/klopstack/iptv-proxy-v2/pull/74) ✅ | `fetch_football_events_for_date`, TSDB dedup, `ppv_sofascore_football_enabled` (default **on**) |
| Architecture slug table | [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md) | `football`, `tennis` production; MMA/table-tennis documented |
| Requeue tooling | [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) ✅ [#53](https://github.com/klopstack/iptv-proxy-v2/pull/53) | Ops runbook for post-deploy WC requeue |

## Remaining football / soccer work

### P0 — production validation (post–PR #74 deploy)

| Item | Detail |
|------|--------|
| **FIFA WC league 4429 monitoring** | Confirm TheSportsDB supplement + SofaScore merge cover WC fixtures through the tournament; watch for TSDB gaps on knockout / late-group dates |
| **TSDB supplement gaps** | When TSDB HTML/API returns partial WC days, verify SofaScore fill-only rows appear in merged calendar and match pipeline |
| **National team / WC channel matching** | Validate production `matched` / `no_match` for WC-prefixed channels (e.g. `US: World Cup: …`) after [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) requeue |
| **Requeue / enrichment ops** | Deploy → confirm `ppv_sofascore_football_enabled` true → requeue WC `no_match` → drain queue ([124 runbook](./124-ppv-enrichment-attempt-tracking-and-requeue.md)) |

### P1 — broader soccer (after WC or when `no_match` volume justifies)

| Item | Detail |
|------|--------|
| **Leagues beyond WC** | MLS, UEFA club, domestic cups — enable when TSDB sparse and channel `no_match` volume justifies extra SofaScore `football` traffic |
| **Detection Preview UX (optional)** | Preview panel shows **matched** enrichment results, not raw merged calendar — operators cannot see WC fixtures in calendar until channels match; optional enhancement to surface calendar rows for a date/sport |

## Refactor scope (main deliverable)

Move from sport-specific copies to a **generic SofaScore calendar provider** under `services/ppv/calendar_providers/sofascore/` (preferred; aligns with [125](./125-sofascore-tennis-calendar-slice1.md) original layout and [131](./131-sofascore-college-amateur-calendar-provider.md)).

### Target layout

```
services/ppv/calendar_providers/sofascore/
  client.py           # fetch_scheduled_events(sport_slug, date_str), rate limit, cache
  registry.py         # slug → parser, dedup strategy, enabled flag
  parser_tennis.py
  parser_football.py
  dedup.py            # shared dedup helpers keyed by strategy
  __init__.py         # public fetch_* wrappers for backward compat during migration
```

### Generic client

1. **`fetch_scheduled_events(sport_slug: str, date_str: str, *, force_refresh: bool = False) -> dict`** — single HTTP path for `GET /api/v1/sport/{slug}/scheduled-events/{YYYY-MM-DD}`.
2. Cache key `{slug}:{date}`; shared rate limiter (~20 req/min); 12h TTL (unchanged).
3. Date window: live ±14/90 via existing constants; replay/historical window deferred to [131](./131-sofascore-college-amateur-calendar-provider.md) (do not block 133 on replay plumbing).

### Sport-specific parsers (plugins)

1. Each parser: `parse_scheduled_events(payload, date_str, *, sport_key) -> List[CalendarEvent]`.
2. Tennis: player names in `home_team`/`away_team`; football: team names; future slugs register here.
3. Status filtering unchanged (`notstarted`, `inprogress`, `finished`).

### Unified configuration

Replace separate boolean flags with one of:

- **Option A (preferred):** `ppv_sofascore_enabled_slugs` — comma-separated list (e.g. `tennis,football`); empty = no SofaScore HTTP.
- **Option B (compat):** Keep existing keys as aliases mapping into slug registry until operators migrate.

Document operator toggles in [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md) and `/api/ppv-enrichment/config`.

### Generic merge in scraper

Replace in `services/thesportsdb_calendar_scraper.py`:

- `_fetch_sofascore_tennis_events_for_date` + `_fetch_sofascore_football_events_for_date` → **`_fetch_sofascore_events_for_date(date, sport_filter)`** iterating enabled slugs.
- Sport-specific dedup filters → **registry-driven dedup strategy**:
  - **Tennis:** `(player pair, calendar day)` vs ESPN — ESPN wins ([126](./126-sofascore-calendar-multi-sport-and-enrichment.md)).
  - **Football / team sports:** `(home, away, calendar day)` vs TheSportsDB — TSDB wins (PR #74).
  - **Future:** register per slug in `registry.py`.

Merge order (unchanged):

1. TheSportsDB HTML + API supplement + MiLB  
2. ESPN tennis (primary)  
3. SofaScore tennis (secondary, flag/slug enabled)  
4. SofaScore football (secondary, flag/slug enabled)  
5. *(Future)* SofaScore college/MMA/… after [131](./131-sofascore-college-amateur-calendar-provider.md) / slug doc priorities

### Extensibility

| Slug | Owner TODO | Notes |
|------|------------|-------|
| `tennis`, `football` | **133** | Migrate existing parsers; behavior parity required |
| College (`basketball`, `ice-hockey`, …) | [131](./131-sofascore-college-amateur-calendar-provider.md) | Add parsers **after** 133 refactor + [130](./130-ncaa-college-calendar-source-spike.md) spike |
| `mma`, `table-tennis` | [123](./123-extended-calendar-coverage-college-obscure-sports.md) Track C / slug doc | Parser + flag only when `no_match` justifies |

### Migration / compatibility

1. Deprecate `services/tennis/sofascore_calendar.py` — thin re-export shim for one release if needed, then remove.
2. Update imports in scraper, enrichment status, tests.
3. **Zero behavior change** for tennis + football when flags/slugs match pre-refactor settings (regression tests mandatory).

## Non-goals

- **College/amateur slug implementation** — [131](./131-sofascore-college-amateur-calendar-provider.md) after [130](./130-ncaa-college-calendar-source-spike.md) spike (133 only delivers the shared module + tennis/football migration).
- **Replay historical window (`REPLAY_CALENDAR_DAYS_BACK`)** — [131](./131-sofascore-college-amateur-calendar-provider.md) / [129](./129-ppv-replay-archive-enrichment-flosp.md).
- **Detection Preview calendar view** — optional UX; separate small PR if pursued.
- **Replacing ESPN tennis primary** or TheSportsDB for pro leagues.
- **Live HTTP in CI** — fixtures only.

## Acceptance criteria

### Football follow-ups (P0)

- [ ] Production: merged calendar for WC sample date (e.g. 2026-06-11) includes SofaScore football fixtures when TSDB incomplete.
- [ ] Post-requeue: WC channel sample set shows improved `matched` vs pre–PR #74 baseline (document counts in **Completion**).
- [ ] `ppv_sofascore_football_enabled` false → no football SofaScore HTTP; tennis unaffected.

### Refactor (P1)

- [x] SofaScore code lives under `services/ppv/calendar_providers/sofascore/`; `services/tennis/sofascore_calendar.py` removed or shim-only.
- [x] Single `fetch_scheduled_events(sport_slug, date)` used by all wired slugs.
- [x] Scraper uses one merge path for SofaScore slugs; no `_fetch_sofascore_*_events_for_date` per sport.
- [x] Unified slug config documented and wired (list or registry); tennis default off, football default on preserved.
- [x] All existing SofaScore unit + merge tests pass without behavior change (tennis + football).
- [x] [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md) updated: module path, config, link to this TODO.
- [ ] [131](./131-sofascore-college-amateur-calendar-provider.md) updated to depend on 133 refactor (college parsers = new files in same package).

## Test plan

| Test | File | Criteria |
|------|------|----------|
| Tennis parser parity | `tests/ppv/test_sofascore_tennis_calendar.py` (or renamed) | Same event count/fields vs pre-refactor fixtures |
| Football parser parity | `tests/ppv/test_sofascore_football_calendar.py` | WC fixture JSON; flag off → no HTTP |
| Merge parity | `tests/ppv/test_sofascore_calendar_merge.py`, `test_sofascore_football_calendar_merge.py` | ESPN/TSDB dedup unchanged |
| Generic client | `tests/ppv/test_sofascore_client.py` (new) | Cache, rate limit, slug dispatch |
| Slug registry | same or registry test | Disabled slug → `[]`; enabled → parser invoked |
| Import shim | optional | Old import path warns once if shim retained |

No live HTTP in CI.

## Affected files

- **Move / create:** `services/ppv/calendar_providers/sofascore/` (client, registry, parsers, dedup)
- **Remove / shim:** `services/tennis/sofascore_calendar.py`
- `services/thesportsdb_calendar_scraper.py` — generic SofaScore merge + dedup
- `services/ppv/constants.py` — slug list setting; deprecate duplicate flags gradually
- `models/sync.py` — settings metadata for unified config
- `routes/ppv_enrichment.py` — status/stats per slug
- `docs/architecture/sofascore-calendar-sport-slugs.md`
- `docs/architecture/ppv-multi-source-events.md` — merge diagram
- Tests: `tests/ppv/test_sofascore_*.py`, fixtures under `tests/ppv/fixtures/sofascore/`

## Dependencies

| TODO / PR | Relationship |
|-----------|--------------|
| [125](./125-sofascore-tennis-calendar-slice1.md) ✅ [#58](https://github.com/klopstack/iptv-proxy-v2/pull/58) | Original client/parser |
| [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) ✅ [#60](https://github.com/klopstack/iptv-proxy-v2/pull/60) | Tennis merge semantics |
| PR [#74](https://github.com/klopstack/iptv-proxy-v2/pull/74) ✅ | Football merge — migrate without regression |
| [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) ✅ | WC production requeue / verification |
| [130](./130-ncaa-college-calendar-source-spike.md) | **Blocks college slug wire in 131** — not 133 tennis/football refactor |
| [131](./131-sofascore-college-amateur-calendar-provider.md) | **Should follow 133 refactor** — adds college parsers on shared package |

## Recommended order

```
PR #74 deploy + 124 WC requeue (P0 football ops)
    → 133 refactor (tennis + football parity)
    → 130 spike → 131 college parsers on sofascore/ package
    → optional: mma / table-tennis / MLS expansion when metrics justify
```

**Parallel OK:** P0 football ops with [128](./128-fix-ppv-year-inference-recent-past-dates.md), [127](./127-ppv-multi-player-competitor-extraction.md), [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A. **Do not** start 131 college slug merge until 133 refactor lands (or explicitly scope 131 to “extend in place” — discouraged).

## References

- [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md) — endpoint, merge order, slug table
- [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md) — source precedence
- PR [#74](https://github.com/klopstack/iptv-proxy-v2/pull/74) — WC football wire
- PR [#58](https://github.com/klopstack/iptv-proxy-v2/pull/58) — tennis slice 1
- PR [#60](https://github.com/klopstack/iptv-proxy-v2/pull/60) — tennis merge
- [124 runbook](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — requeue after deploy
