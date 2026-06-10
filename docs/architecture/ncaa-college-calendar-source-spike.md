# NCAA / college / amateur calendar source spike (TODO 130)

**Date:** June 2026  
**Status:** Complete — informs [131](../todos/131-sofascore-college-amateur-calendar-provider.md) and [129](../todos/129-ppv-replay-archive-enrichment-flosp.md) Track B  
**Production audit:** June 4 2026 — ~243 Flo (FLSP) replay channels in `no_match`

## Executive summary

| Decision | Outcome |
|----------|---------|
| **Go for 131?** | **Yes — hybrid stack** |
| **Primary provider** | SofaScore `ice-hockey` slug (AHL, OHL, QMJHL, WHL, ECHL) |
| **Supplement** | Sportsipy per-team `ncaab` schedules for DIII / small-college basketball |
| **Reject as sole source** | SofaScore `basketball` slug for college — no NCAA/DIII day feed on sample dates |
| **Historical window** | **400 days** (`REPLAY_CALENDAR_DAYS_BACK`) — required; live ±14-day gate blocks Oct 2025 replays today |

SofaScore alone would match roughly **15–25%** of the Flo tail (hockey-heavy slice). Adding Sportsipy team lookups for college basketball targets the **~60%** of Flo channels that are men's/women's college hoops. Remaining gaps (field hockey, lacrosse, obscure amateur) stay honest `no_match` until a dedicated source is justified.

## Flo channel inventory (production stratification)

Source: June 2026 production audit + `tests/ppv/fixtures/flosp_replay_channels.json` + spike sample set `tests/ppv/fixtures/spike/flo_spike_sample_channels.json`.

| Subtype | Approx. share | Date pattern | Example |
|---------|--------------:|--------------|---------|
| College women's basketball | ~35% | `DD/MM` + `- Womens -` | `Occidental vs Chapman - Womens - 22/10 19:00` |
| College men's basketball | ~26% | `DD/MM` + `- Mens -` | `Guilford vs Randolph - Mens - 22/10 19:00` |
| Junior / minor hockey | ~11% | `DD/MM` time | `Colorado Eagles vs San Diego Gulls - 22/10 22:00` |
| Canadian junior (OHL/QMJHL) | ~5% | `DD/MM` | `Ottawa 67s vs Windsor Spitfires - 23/10 19:05` |
| Other college / amateur | ~23% | mixed | field hockey, lacrosse, CJHL, volleyball |

**Densest calendar date:** `2025-10-22` (European `22/10` cluster). Secondary: `2025-10-23`, `2025-11-01` (QMJHL).

## Spike procedure

### Dates probed

| Date | Rationale |
|------|-----------|
| `2025-10-22` | Primary Flo cluster |
| `2025-10-23` | Adjacent OHL/QMJHL spillover |
| `2025-11-01` | QMJHL sample (`Sherbrooke Phoenix`) |

### Sources evaluated

| Source | Endpoint / API | Notes |
|--------|----------------|-------|
| **SofaScore** | `GET /api/v1/sport/{slug}/scheduled-events/{YYYY-MM-DD}` | Existing client; `curl_cffi` Chrome TLS required from Docker |
| **Sportsipy** | `Schedule(school_abbr, year=2025)` per team | Already a dependency; 30 pages/min limit; not day-indexed |
| **TheSportsDB** | `eventsday.php` | 3 basketball events on `2025-10-22` — sparse for college |
| **NCAA / ESPN official** | Not probed live | Licensing/stability unknown; defer unless hybrid fails |

Probe script (local only): `scripts/spike/ncaa_college_calendar_probe.py`

## Per-source results

### A — SofaScore `ice-hockey` (primary for hockey)

| Date | Events | Flo-relevant leagues present |
|------|-------:|------------------------------|
| 2025-10-22 | 153 | AHL, OHL, ECHL |
| 2025-10-23 | 163 | AHL, OHL, ECHL |
| 2025-11-01 | 563 | OHL, QMJHL, WHL |

**Sample matches (full table in spike fixture JSON):**

| Channel title | Result | Fixture |
|---------------|--------|---------|
| Colorado Eagles vs San Diego Gulls | **Match** — AHL, exact names | `ice-hockey` 2025-10-22 |
| Ottawa 67s vs Windsor Spitfires | **Match** — OHL; normalize `67s` ↔ `67's` | `ice-hockey` 2025-10-23 |
| Sherbrooke Phoenix vs Chicoutimi Sagueneens | **Partial** — QMJHL; home listed as `Sagueneens Chicoutimi` | `ice-hockey` 2025-11-01 |
| Sault Ste Marie Greyhounds vs Erie Otters | **Match** — OHL (extra sample) | `ice-hockey` 2025-10-22 |

Recorded fixtures: `tests/ppv/fixtures/sofascore/ice_hockey_2025-10-22.json`, `ice_hockey_2025-10-23.json`.

### B — SofaScore `basketball` (reject for college calendar)

| Date | Events | USA college events |
|------|-------:|-------------------|
| 2025-10-22 | 368 | **0** NCAA/DIII (14 NBA under `USA`) |
| 2025-10-23 | 424 | **0** NCAA/DIII |

SofaScore exposes a `USA (College)` category (`id: 2346`, slug `usa-college`) but **no scheduled events** on probe dates. DIII schools (Occidental, Chapman, Guilford, Randolph) are absent.

| Channel title | Result |
|---------------|--------|
| Occidental vs Chapman - Mens | **Miss** |
| Guilford vs Randolph - Mens | **Miss** |
| Occidental vs Chapman - Womens | **Miss** |

**Conclusion:** Do not wire `basketball` slug expecting NCAA/DIII coverage. Use Sportsipy supplement.

### C — SofaScore `american-football`

| Date | Events | NCAA |
|------|-------:|------|
| 2025-10-22 | 4 | 0 |
| 2025-11-01 | 299 | 194 under `NCAA, Regular Season` |

Useful for **NCAAF** replay channels when present; low volume in Oct 22 Flo cluster. Optional Phase B flag in 131.

### D — SofaScore `volleyball` / `football` (soccer)

Hundreds of international events per day; **no hits** on Flo college samples. Not primary for this tail.

### E — Sportsipy `ncaab` (supplement for college basketball)

| Approach | Feasibility |
|----------|-------------|
| Day-indexed calendar | **Poor** — requires iterating all ~350+ D-I teams or conference pages |
| Per-channel team lookup | **Good** — Flo titles already parse to two school names; map to Sports Reference abbreviations via `SportsTeam` DB |
| Rate limit | 20–30 req/min; acceptable for replay batch (243 channels) with caching |
| Women's / DIII | Coverage varies; DIII schools exist in Sports Reference but spike hit HTTP 429 during bulk probe — **feasible with throttled per-team fetch** |

**Recommendation:** Sportsipy **supplement only** — invoked when `replay_archive` + sport hint `Mens`/`Womens` and SofaScore basketball returns no candidate. Not merged into day-bucket calendar scrape; targeted lookup in match pipeline.

### F — TheSportsDB

3 basketball events on `2025-10-22`. Insufficient for college replay tail.

## Decision matrix

| Source | Sports covered | Hit rate on 24-channel spike set | Historical depth | Ops cost | Recommendation |
|--------|----------------|--------------------------------:|------------------|----------|----------------|
| SofaScore `ice-hockey` | AHL, OHL, QMJHL, WHL, ECHL | **100%** (6/6 hockey samples) | API returns Oct 2025 when queried directly | ~20 req/min; 1 req/date/slug | **Primary** for hockey |
| SofaScore `basketball` | NBA, intl; not NCAA DIII | **0%** (0/12 college hoops samples) | N/A for college | Low | **Reject** for college |
| SofaScore `american-football` | NCAA FBS/FCS | **0%** on Oct 22 set; viable on Nov 1 | Good for fall Saturdays | Low | **Optional Phase B** |
| Sportsipy `ncaab` | NCAA D-I–DIII per school | **TBD** — architecture fit; not day-indexed | 2025 season pages | Per-team HTTP; cache | **Supplement** |
| TheSportsDB | Pro + sparse college | **0%** on samples | Limited | Already wired | No change |

**Stratified estimate (243 Flo channels):**

- Hockey (~16%): **~95%** match with SofaScore + name normalization
- College basketball (~61%): **~40–70%** with Sportsipy supplement (depends on DB team mapping quality)
- Other amateur (~23%): **<10%** without new vendor

**Blended post-131 target:** 30–50% Flo `matched` after requeue — not 100% (document permanent gaps).

## Historical fetch window

Current gate in `services/ppv/calendar_providers/sofascore/client.py`:

```python
# is_date_in_window — MAX_API_SUPPLEMENT_DAYS_BACK = 14
```

Oct 2025 replays queried in June 2026 are **~230 days** in the past → **zero events** even when the API has data.

| Window | Value | Use |
|--------|------:|-----|
| Live enrichment | ±14 / +90 days | Unchanged |
| Replay archive (`replay_archive` metadata) | **400 days** | New `REPLAY_CALENDAR_DAYS_BACK` in 131 |

SofaScore API returned full `ice-hockey` payloads for `2025-10-22` when queried **without** the 14-day gate (spike script bypass).

## Team-name normalization notes

| Pattern | Channel | API | Rule |
|---------|---------|-----|------|
| Apostrophe | `Ottawa 67s` | `Ottawa 67's` | Strip punctuation for compare |
| Word order | `Chicoutimi Sagueneens` | `Sagueneens Chicoutimi` | Token-sort match |
| Suffix noise | `- Mens -`, `- Womens -` | — | Strip in extractor (already in 129) |
| Mascot drop | `Occidental` | `Occidental Tigers` | Prefix / alias table via `SportsTeam` |

## Open gaps (permanent `no_match` until new source)

- Field hockey, lacrosse, water polo — no SofaScore slug hits on samples
- Obscure CJHL / amateur leagues not in SofaScore `ice-hockey` tournament list
- Women's sports with no Sports Reference page

## 131 implementation checklist (from spike)

1. Add `parser_ice_hockey.py` (team names, tournament → `ahl` / `ohl` / `qmjhl` sport keys).
2. Wire `ice-hockey` slug behind `ppv_sofascore_college_enabled` or unified slug list.
3. Bypass `is_date_in_window` when `extraction["replay_archive"]` and date within `REPLAY_CALENDAR_DAYS_BACK`.
4. Sportsipy fallback hook in `match_pipeline` for `Mens`/`Womens` college basketball channels.
5. Commit fixtures from this spike for CI (ice-hockey JSON above).

## References

- [sofascore-calendar-sport-slugs.md](./sofascore-calendar-sport-slugs.md) — slug table update in same PR
- [131-sofascore-college-amateur-calendar-provider.md](../todos/131-sofascore-college-amateur-calendar-provider.md)
- [129-ppv-replay-archive-enrichment-flosp.md](../todos/129-ppv-replay-archive-enrichment-flosp.md) Track B
- Probe script: `scripts/spike/ncaa_college_calendar_probe.py`
- Sample scoring: `tests/ppv/fixtures/spike/flo_spike_sample_channels.json`
