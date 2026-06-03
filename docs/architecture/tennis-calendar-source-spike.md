# Tennis calendar source spike (TODO 122 Phase 1)

**Date:** 2026-06-03  
**Status:** Spike complete — ready for Phase 2 implementation  
**Production baseline:** 341 active `Tennis:` channels with `ppv_enrichment_status=no_match`

## Executive summary

TheSportsDB (TSDB) is **not viable** as the sole tennis calendar source. Production scrape for **2026-06-03** returns **79 total events** but only **2 tennis** (both Roland Garros ATP men's quarter-finals). WTA, wheelchair, junior, ITF, and challenger draws that dominate the IPTV feed are absent despite TSDB having player records for many of those names.

**Recommendation:** Add **API-Tennis** (`api.api-tennis.com`) as a dedicated second calendar source, following the MiLB integration pattern (`services/mlb_stats_calendar.py` → merge in `TheSportsDBCalendarScraper.get_events_for_date`).

| Verdict | Source | Use for PPV matching? |
|---------|--------|----------------------|
| **No** | TheSportsDB tennis | Ruled out — ~2 events/day vs dozens needed |
| **Yes (Phase 2)** | API-Tennis | Primary tennis calendar |
| **No (MVP)** | Sportradar Tennis API | Enterprise pricing; no self-host |
| **No (MVP)** | ATP/WTA official feeds | B2B / partner-only; not self-hostable |
| **Discouraged** | ESPN / HTML scrape | Fragile; ToS risk |

---

## 1. TheSportsDB audit

### Code paths reviewed

- `services/thesportsdb_calendar_scraper.py` — HTML calendar + `API_SUPPLEMENT_SPORTS` includes `"Tennis"`; MiLB merged via `_fetch_milb_events_for_date`
- `services/thesportsdb_service.py` — league/event detail APIs; no tennis-specific league IDs in `LEAGUE_ID_MAP`

### Queries run (2026-06-03)

| Method | Result |
|--------|--------|
| Production `get_events_for_date("2026-06-03", force_refresh=True)` | **79 events total**, **2 tennis** |
| `eventsDay.php?s=Tennis` (free API key) | 2 events |
| `eventsDay.php` unfiltered (free key) | 3 baseball only (rate-limited key) |
| HTML `browse_calendar/?s=Tennis&d=2026-06-03` | 2 event links |
| HTML `browse_calendar/?s=&d=2026-06-03` (free) | 5 event links, 0 tennis rows |
| `searchplayers.php` | Kalinskaya, Chwalinska, Sabalenka, Shnaider, Lapthorne — **all found** |
| `nextLeagueEvents` league 4464 (ATP World Tour) | 1 event on Jun 3 |
| `nextLeagueEvents` league 4517 (WTA Tour) | **0 events** on Jun 3 |

### Production tennis events (only 2)

```json
[
  {
    "idEvent": "2479089",
    "strEvent": "Roland Garros Félix Auger Aliassime vs Flavio Cobolli",
    "strLeague": "ATP World Tour",
    "dateEvent": "2026-06-03",
    "strTime": "11:20:00",
    "strHomeTeam": null,
    "strAwayTeam": null
  },
  {
    "idEvent": "2479102",
    "strEvent": "Roland Garros Matteo Berrettini vs Matteo Arnaldi",
    "strLeague": "ATP World Tour",
    "dateEvent": "2026-06-03",
    "strTime": "18:15:00",
    "strHomeTeam": null,
    "strAwayTeam": null
  }
]
```

### TSDB data quality issues for tennis

1. **Sparse calendar** — Grand Slam day with 30+ real courts/matches; TSDB returns 2 ATP singles only.
2. **No `strHomeTeam` / `strAwayTeam`** — players embedded in `strEvent` prefix (`"Roland Garros Player A vs Player B"`). Existing `_parse_teams_from_event_name` can split on `vs`, but league prefix pollutes matching.
3. **WTA gap** — WTA league `4517` returns zero upcoming events despite active Roland Garros WTA draw.
4. **No wheelchair / junior / ITF** in TSDB calendar for sample day.
5. **Player search works; event linkage does not** — confirms TSDB is a poor calendar, not a naming problem.

### TSDB verdict: **No** (ruled out)

Pass criteria from TODO 122: event count > 0 **or** ruled out → **ruled out** for production tennis matching. Partial presence (2 ATP) is insufficient for 341 channels.

### Production note (out of spike scope)

During production scrape, `API eventsDay failed for 2026-06-03 sport=Baseball: cannot import name 'get_ppv_event_title' from ... circular import`. This may suppress API supplement for non-tennis sports; separate bug, but worth fixing before Phase 2.

---

## 2. Alternative API evaluation

| Source | Coverage (ATP/WTA/Challenger/ITF/WC/Juniors) | License / cost | Rate limits | Self-host | Name format vs channels | Verdict |
|--------|-----------------------------------------------|----------------|-------------|-----------|-------------------------|---------|
| **TheSportsDB** | Partial — ATP singles only on sample day | Free tier + optional paid key; site login for HTML | 30–100 RPM (paid) | N/A (API) | `"Roland Garros First Last vs First Last"`; null team fields | **No** |
| **API-Tennis** | ATP, WTA, Challenger, ITF, Boys/Girls, Exhibition per docs; wheelchair **not documented** in event types | ~$40/mo (8k req/day), 14-day trial | 8k–200k req/day by tier | Cloud API only | `event_first_player` / `event_second_player` as `"A. Lastname"` — needs fuzzy expansion | **Yes — recommended** |
| **Sportradar Tennis v3** | Official ATP + 4k+ competitions | Enterprise quote; 30-day trial | Contract / overage fees | Hosted B2B only | Structured competitor objects | Defer — cost/opaque |
| **ATP/WTA official** | Best accuracy | Partner/B2B | N/A | No public self-host API | Full names | Defer — access barrier |
| **ESPN / scrape** | Broad | ToS risk | Fragile | N/A | Variable | **Discouraged** |

### API-Tennis fixture shape (from public docs)

```
GET https://api.api-tennis.com/tennis/?method=get_fixtures
    &APIkey=<REDACTED>
    &date_start=2026-06-03
    &date_stop=2026-06-03
```

```json
{
  "success": 1,
  "result": [
    {
      "event_key": "143104",
      "event_date": "2022-06-17",
      "event_time": "18:00",
      "event_first_player": "M. Navone",
      "first_player_key": "949",
      "event_second_player": "C. Gomez-Herrera",
      "second_player_key": "3474",
      "event_type_type": "Challenger Men Singles",
      "tournament_name": "Corrientes Challenger Men",
      "tournament_key": "2646",
      "tournament_round": "",
      "tournament_season": "2022"
    }
  ]
}
```

**Mapping to `CalendarEvent`:**

| API-Tennis field | CalendarEvent field |
|------------------|---------------------|
| `event_key` | `event_id` (string) |
| `event_first_player` + `event_second_player` | `home_team` / `away_team` (order TBD — document in Phase 2) |
| `tournament_name` + `event_type_type` | `league_name` |
| `event_date` + `event_time` | `date`, `time_utc` |
| — | `source="api_tennis"` |

### Rate budget (7-day window)

| Approach | Calls per enrichment cycle | Daily budget @ $40 tier |
|----------|---------------------------|-------------------------|
| One `get_fixtures` per UTC day (7 calls) | 7 | 8,000 — trivial |
| Single `get_fixtures` with `date_start`/`date_stop` spanning ±7 days | **1** | 8,000 — preferred |
| Per-channel lookup | 341+ | **Avoid** |

Align cache TTL with TSDB: **12 hours** (`CACHE_TTL_SECONDS`), or **6 hours** during Grand Slams.

---

## 3. Production sample (unique matchups)

Fetched via production API (`status=no_match&search=Tennis:&limit=20` returns 50 rows / 341 total). Deduplicated by player pairing:

| # | Representative channel | Inferred UTC | Draw |
|---|------------------------|--------------|------|
| 1 | `Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM :MAX NL 13` | 2026-06-03T09:00:00Z | WTA RG QF |
| 2 | `Tennis: Aryna Sabalenka 1 vs Diana Shnaider @ Jun 3 07:30 AM :MAX US 28` | 2026-06-03T11:30:00Z | WTA RG QF |
| 3 | `Tennis: Andy Lapthorne vs Niels Vink @ Jun 3 07:00 AM :MAX US 23` | 2026-06-03T11:00:00Z | Wheelchair quad singles QF |
| 4 | `Tennis: A Hewett G Reid vs F Cattaneo D Rodrigues @ Jun 3 07:00 AM :MAX US 17` | 2026-06-03T11:00:00Z | Wheelchair men's doubles QF |
| 5 | `Tennis: Anastasija Cvetkovic vs Paola Pinera Celorio @ Jun 3 10:55 AM :MAX NL 08` | 2026-06-03T08:55:00Z | Junior girls RG |
| 6 | `Tennis: A Gabet M Kaouk vs J Mackenzie VJ Reisach @ Jun 3 13:00 PM :MAX US 59` | 2026-06-03T05:00:00Z | Junior boys doubles |
| 7 | `Tennis: A Cornet D Hantuchova vs M Hingis A Kerber @ Jun 3 04:55 AM :MAX US 03` | 2026-06-03T08:55:00Z | Legends / exhibition doubles (retired players) |

Additional production patterns: seed numbers in names (`Sabalenka 1`, `Kalinskaya 22`), doubles abbreviated as `A Lastname B Lastname`, regional `:MAX NL` / `:Tennis` suffixes (already stripped by competitor extraction).

---

## 4. Sample match verification (manual, 2026-06-03)

| Channel (deduped) | Real event confirmed? | In TSDB calendar? | Expected in API-Tennis? |
|-------------------|----------------------|-------------------|-------------------------|
| Kalinskaya vs Chwalinska | Yes — RG WTA QF ([rolandgarros.com](https://www.rolandgarros.com/en-us/article/2026-edition-sf-chwalinska-kalinskaya)) | **No** | **Yes** (WTA Singles) |
| Sabalenka vs Shnaider | Yes — RG WTA QF ([rolandgarros.com](https://www.rolandgarros.com/en-us/article/2026-edition-qf-sabalenka-shnaider-)) | **No** | **Yes** (WTA Singles) |
| Lapthorne vs Vink | Yes — RG quad wheelchair QF ([BBC](https://www.bbc.com/sport/tennis/articles/ce3p9xe7d3vo)) | **No** | **Unknown** — wheelchair not in public event-type list |
| Hewett/Reid vs Cattaneo/Rodrigues | Yes — RG wheelchair doubles QF ([HBO Max schedule](https://www.hbomax.com/ch/en/sports/2026-6-3/ccb4eed9-c556-58e7-8c47-e72edef92ac6)) | **No** | **Unknown** |
| Cvetkovic vs Pinera Celorio | Yes — RG junior girls ([azscore](https://azscore.ru/tennis/game/anastasija-cvetkovic-paola-pinera-celorio-2026-06-03)) | **No** | **Likely** (Girls Singles) |
| Cornet/Hantuchova vs Hingis/Kerber | Unverified legends slot; retired WTA names | **No** | **Unlikely** — may remain `no_match` or `skipped` |

**Estimated TSDB match rate on sample:** 0/6 verified professional/junior singles (0%).  
**Estimated API-Tennis match rate (hypothesis):** 4–5/6 if wheelchair included; 3–4/6 if wheelchair excluded.

---

## 5. Codebase integration points (Phase 2 — not implemented)

### Pattern to follow: MiLB

```
services/mlb_stats_calendar.py     → fetch_milb_events_for_date()
services/thesportsdb_calendar_scraper.py → _fetch_milb_events_for_date() merged in get_events_for_date()
models/ppv.py                      → Event.SOURCE_MLB_STATS = "mlb_stats_api"
services/ppv/enrichment/types.py   → source normalization
services/ppv/persistence.py          → create_or_update_event(source=...)
```

Proposed parallel:

```
services/tennis_calendar.py          → fetch_tennis_events_for_date()  # API-Tennis client
services/thesportsdb_calendar_scraper.py → _fetch_tennis_events_for_date() merge
models/ppv.py                        → Event.SOURCE_API_TENNIS = "api_tennis"
```

### Orchestrator

`services/reverse_event_matcher/orchestrator.py` loads events via `self.scraper.get_events_for_date_range()` — **no orchestrator change** if tennis events are merged at scraper level (same as MiLB).

Consider `_individual_sport_strategies` ordering (already prefers `EventNameMatchStrategy` + `LastNameMatchStrategy`) for tennis channels.

### Multi-source schema (TODO 55 — done)

- Composite unique `(external_id, source)` — use `event_key` from API-Tennis as `external_id`, `source=api_tennis`
- Detail fetch: skip or metadata-only for `api_tennis` (fixtures already carry tournament + round)
- Status API: extend `providers_failed` pattern (TODO 67) for tennis provider outages

### Architecture docs

- [ppv-multi-source-events.md](./ppv-multi-source-events.md) — add tennis source row to diagram
- [ppv-sport-registry.md](./ppv-sport-registry.md) — `calendar_source: api_tennis` for tennis sport key

### Tests (Phase 2)

- `tests/fixtures/api_tennis/fixtures_2026-06-03.json` — recorded response
- `tests/ppv/test_tennis_calendar_provider.py`
- Integration: merged calendar match for Kalinskaya channel

---

## 6. Phase 2 MVP recommendation

### Provider interface

```python
def fetch_tennis_events_for_date(date_str: str, *, force_refresh: bool = False) -> List[CalendarEvent]:
    """Fetch tennis fixtures from API-Tennis for one UTC day."""
```

- Settings key: `ppv_api_tennis_key` (mirror `ppv_thesportsdb_api_key`)
- In-memory + optional disk cache (reuse `calendar_cache.json` with key prefix `api-tennis-v1:{date}` **or** separate `tennis_calendar_cache.json` — prefer **shared file, namespaced keys** to match MiLB/TSDB pattern)
- Refresh: **12h TTL**, force refresh on enrichment requeue (TODO 124)
- Window: **±7 days** per existing `MAX_API_SUPPLEMENT_DAYS_*`

### `(external_id, source)` scheme

| Source | `Event.source` | `external_id` example |
|--------|----------------|----------------------|
| TheSportsDB | `thesportsdb` | `2479089` |
| API-Tennis | `api_tennis` | `11847293` (API `event_key`) |
| MiLB | `mlb_stats_api` | `777777` (MLB `gamePk`) |

No prefix in `external_id` — disambiguation is via `source` column per TODO 55.

### Name matching notes

- API-Tennis uses abbreviated names (`A. Kalinskaya`); channels use full names — existing `LastNameMatchStrategy` + fuzzy should work; may need tennis-specific threshold in `constants.py` (Phase 3).
- Doubles channels encode both surnames in one competitor string — may need competitor extraction extension (document as Phase 2 stretch / Phase 3).

### Detail fetch policy

Accept `data_completeness='basic'` from fixture metadata; do not enqueue TSDB detail worker for `api_tennis` events.

---

## 7. Phase 2 estimate and blockers

| Item | Estimate |
|------|----------|
| API-Tennis client + `CalendarEvent` mapper | 0.5–1 day |
| Scraper merge + settings UI key | 0.5 day |
| `Event.SOURCE_API_TENNIS` + persistence | 0.25 day |
| Fixtures + unit tests | 0.5 day |
| Integration test + manual prod verify | 0.5 day |
| **Total Phase 2 MVP** | **2–3 days** |

### Blockers / open questions

1. **API-Tennis trial key** — need account signup to validate wheelchair + legends coverage and confirm Jun 3 fixture counts.
2. **Wheelchair / quad** — not listed in public `get_events` type enum; verify with trial API before promising 70% `no_match` reduction.
3. **Doubles competitor parsing** — `A Hewett G Reid` format may not split into pairs; scope extension or match on concatenated last names.
4. **Player order** — API `first_player` vs `second_player` may not match channel home/away; matcher should treat as unordered pair.
5. **Circular import** in production API supplement — fix before relying on merged calendar stats.
6. **TODO 120** — date bucketing prerequisite for correct day load.

---

## 8. Optional probe script

See `scripts/spike_tennis_calendar.py` — run with `PPV_API_TENNIS_KEY` set to validate live fixture counts (not wired to production).
