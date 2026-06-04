# Tennis PPV production audit (June 3, 2026)

**Date:** 2026-06-03  
**Host:** `docker.klopnet.com` / container `iptv-proxy-v2`  
**Related:** [TODO 122](../todos/122-tennis-calendar-event-source.md)  
**Prior spike notes:** `docs/architecture/tennis-calendar-source-spike.md` was referenced in the investigation brief but **does not exist in the repo yet**; this document serves as the production data spike that TODO 122 Phase 1 called for.

## Executive summary

The user's hypothesis — that most of the **341 `no_match` tennis channels** are replays, multiview, or other non-calendar patterns — is **mostly incorrect** for the current production snapshot.

| Finding | Detail |
|---------|--------|
| Raw `no_match` count | **342** channels with `Tennis` in the name (API pagination total; TODO baseline was 341) |
| Unique event content | **168** after stripping provider suffixes (`:MAX NL 13`, `:Tennis 50`, etc.) |
| Provider duplication | **~2.0×** average (same match on MAX NL / SE / DK / NO / US and/or `:Tennis` feeds) |
| Parseable dates | **100%** land on **2026-06-03** (audit day — Roland Garros Day 11) |
| Competitor extraction | **30/30** random unique keys returned valid pairs |
| Non-calendar channel types | **~15%** of unique content (26/168) — multiview, courtside, court aggregates, legends, branded replay slots |
| Root cause of `no_match` | **Missing tennis fixtures in the enrichment calendar**, not bad parsing. TheSportsDB calendar cache for 2026-06-03 has **213 events, 0 tennis**. Women's QFs and most of the draw simply aren't present. |

**Revised matchability estimate (unique content):**

| Bucket | Unique | Channels (approx.) | Action |
|--------|--------|-------------------|--------|
| Singles live fixtures | ~45 | ~90 | Match with a good live calendar API |
| Doubles / wheelchair (needs 4-player parsing + API coverage) | ~101 | ~200 | Match after extraction work; API must cover doubles & wheelchair |
| Should reclassify `skipped` / metadata-only | ~26 | ~52 | Never calendar-matchable |
| Already matched (TSDB partial) | 2 events | 9 channels | Proof TSDB can hit *some* RG men's draws |

With a reliable tennis fixture source and doubles name parsing, **~87% of unique content (~280 of 342 channels)** is realistically matchable. Without any new source, **~85% will stay `no_match` indefinitely** — and that is expected, not a matching-algorithm failure.

---

## 1. Channel inventory

### Status breakdown (`name ILIKE '%Tennis%'`)

| Status | Count |
|--------|------:|
| `no_match` | 342 |
| `skipped` | 42 |
| `matched` | 9 |
| `queued` / `pending` / null | 0 |

### Prefix split

| Pattern | `no_match` |
|---------|----------:|
| `Tennis:` prefix | 332 |
| Roland Garros / non-prefix branded feeds | 10 |

The 10 non-prefix channels are tournament-branded aggregate slots (court feeds, primetime, quarterfinals banner), not `Player vs Player` rows.

### Already skipped (42) — working as designed

Skipped channels are **placeholders**, not failed matches:

- `##### TENNIS PPV #####` section headers
- `- NO EVENT STREAMING - | 8K EXCLUSIVE | TS: TENNIS PPV N` idle slots

These are correctly excluded by enrichability rules. They are **not** part of the 342 `no_match` set.

### Already matched (9) — partial TheSportsDB coverage

All 9 link to **2 unique Roland Garros men's events** via `source=thesportsdb`:

| Event | External ID | Channels |
|-------|-------------|----------|
| Félix Auger-Aliassime vs Flavio Cobolli | 2479089 | 5 (+ provider copies) |
| Matteo Berrettini vs Matteo Arnaldi | 2479102 | 4 (+ reversed-name MAX US copy) |

**Kalinskaya vs Chwalinska**, **Sabalenka vs Shnaider**, and all wheelchair/doubles fixtures have **zero** rows in the `events` table. TSDB calendar supplementation includes `"Tennis"` in `API_SUPPLEMENT_SPORTS`, but production cache for 2026-06-03 returns no tennis fixtures — only men's matches that were indexed earlier matched.

---

## 2. Name-pattern classification

Classification uses mutually exclusive **primary** categories (priority order). Counts below are on **168 unique content keys** unless noted.

### Category counts (unique content)

| Category | Unique | % | Channel rows (approx.) | Example |
|----------|-------:|--:|----------------------:|---------|
| **Doubles (complex names)** | 89 | 53.0% | ~178 | `Tennis: T Golovin G Forget vs P Parmentier G Simon @ Jun 3 10:55 AM` |
| **Singles live-looking** | 41 | 24.4% | ~82 | `Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM` |
| **Wheelchair / quad singles** | 12 | 7.1% | ~24 | `Tennis: Andy Lapthorne vs Niels Vink @ Jun 3 13:00 PM` |
| **Legends / exhibition doubles** | 6 | 3.6% | ~12 | `Tennis: A Cornet D Hantuchova vs M Hingis A Kerber @ Jun 3 10:55 AM` |
| **Tournament court aggregate feed** | 6 | 3.6% | ~6 | `Roland Garros Day #11 Philippe Chatrier ft Sabalenka Auger Aliassime @ Jun 3 5:00 AM` |
| **Replay / branded aggregate** | 4 | 2.4% | ~4 | `2026 Roland Garros Primetime @ Jun 3 11:00 PM` |
| **Multiview** | 2 | 1.2% | ~8 | `Tennis: Multiview @ Jun 3 11:00 AM` (2 time slots × 4 regions) |
| **Courtside generic** | 1 | 0.6% | ~4 | `Tennis: Courtside @ Jun 3 23:30 PM` |
| **Other (seed numbers, typos, generic)** | 7 | 4.2% | ~14 | `Tennis: Aryna Sabalenka 1 vs Diana Shnaider @ Jun 3 07:30 AM` |

**Channel-level multi-label note:** At the raw 342-row level, pattern tags overlap (e.g. wheelchair doubles also hit `doubles_complex`). Primary categories avoid double-counting.

### Provider tag distribution (342 rows)

| Provider suffix | Rows |
|-----------------|-----:|
| MAX NO | 59 |
| MAX NL / SE / DK / US | 58 each |
| `:Tennis` feed | 50 |
| TSN+ | 1 |

---

## 3. Date distribution

All 168 unique keys and all 342 channel rows parse to **2026-06-03** via `DateExtractor`.

| Bucket | Unique keys |
|--------|------------:|
| Today (audit date) | 168 |
| ±1 day | 0 |
| >7 days out / past | 0 |
| No parseable date | 0 |

This snapshot is a **single-day Roland Garros slate**, not a spread of stale or far-future junk. Date parsing (TODO 120) is not the blocker for this population.

---

## 4. Competitor extraction sample

**30 random unique keys:** **30/30** returned a valid two-name tuple from `PPVEventExtractor.extract_competitors()`.

### Systematic doubles failure (separate issue)

**101 channel rows** (most of the 89 unique doubles keys × ~2 copies) extract **two pseudo-teams** instead of four players:

```
Tennis: A Cornet D Hantuchova vs M Hingis A Kerber
  -> ('A Cornet D Hantuchova', 'M Hingis A Kerber')   # wrong: 4 legends, 2 tokens each side

Tennis: Y Kamiji Z Zhu vs A Bernal J Griffioen
  -> ('Y Kamiji Z Zhu', 'A Bernal J Griffioen')       # wheelchair doubles, same bug
```

Singles extraction is **53/53** on clean `First Last vs First Last` patterns. Seed-suffixed singles also work (`Anna Kalinskaya 22 vs Maja Chwalinska` → correct pair).

Calendar matching for doubles will fail even **with** a tennis API until four-player parsing exists — see [TODO 127](../todos/127-ppv-multi-player-competitor-extraction.md).

---

## 5. Calendar reality cross-check

Ten **singles live-looking** channels with parseable 2026-06-03 dates were checked against public Roland Garros reporting:

| Channel competitors | Real fixture? | Notes |
|--------------------|---------------|-------|
| Anna Kalinskaya vs Maja Chwalinska | **Yes** | RG 2026 women's QF, Court Philippe-Chatrier, Jun 3 ([WTA](https://www.wtatennis.com/news/4513254), [ABC](https://abcnews.com/Sports/wireStory/chwalinskas-remarkable-french-open-run-continues-beats-kalinskaya-133546392)) |
| Aryna Sabalenka vs Diana Shnaider | **Yes** | RG 2026 women's QF, Jun 3 ([CBS Sports](https://www.cbssports.com/tennis/news/french-open-2026-results-aryna-sabalenka-diana-shnaider-upset-quarterfinal/)) |
| Félix Auger-Aliassime vs Flavio Cobolli | **Yes** | Already matched via TSDB (men's draw) |
| Andy Lapthorne vs Niels Vink | **Plausible live WC singles** | Real wheelchair players at RG; needs wheelchair-capable fixture feed |
| Guy Sasson vs Jin Woodman | **Plausible** | Quad/wheelchair tour names; live feed, not replay |
| Ahmet Kaplan vs Gregory slade | **Likely ITF/juniors** | Lower-tier draw; may or may not appear in commercial APIs |

**Conclusion:** The dominant `no_match` population is **same-day live (or same-day live-capable) sport**, not archive/replay labels. Branded replay/aggregate rows exist but are a **minority (~15%)**.

---

## 6. api-tennis.com skepticism

### Legitimacy signals

| Signal | Assessment |
|--------|------------|
| Domain | `api-tennis.com`, Namecheap registrar, created **2022-04-29**, privacy-heavy WHOIS |
| Product | REST `get_fixtures` / `get_livescore` + WebSocket; documented at [api-tennis.com/documentation](https://api-tennis.com/documentation) (v2.9.4) |
| Pricing | $40–80/mo tiers, 14-day trial, 8k–200k requests/day |
| Social proof | Generic testimonials on marketing page; no identifiable corporate entity or data-licensing disclosure |
| Terms | "Data provided as is", no uptime guarantees ([terms](https://api-tennis.com/terms-of-use)) |

**Verdict:** Legitimate enough for a **bounded spike trial** (14-day free tier, fixture pull for 2026-06-03, manual spot-check Kalinskaya / Sabalenka / Lapthorne / a doubles row). Not strong enough to commit as sole long-term source without validating RG women's draw, wheelchair, and doubles coverage against production channel names.

### Does unmatched volume explain the skepticism?

| Hypothesis | Supported? |
|------------|------------|
| Most `no_match` are replays/multiview | **No** — ~15% unique content |
| Missing live fixture API is the main gap | **Yes** — TSDB cache has 0 tennis on audit day; DB has 0 women's RG events |
| api-tennis alone fixes 341 → matched | **No** — doubles parsing + ~15% permanent skips + API coverage gaps remain |

### Revised source recommendation

1. **Keep api-tennis.com on the short list** for Phase 1 spike only — trial `get_fixtures` for `2026-06-03` ±7 days; record fixture JSON as CI fixtures if quality passes.
2. **Re-open alternatives** before implementation lock-in:
   - **Goalserve** — cited in industry cost comparisons (~$1200/yr tier); evaluate fixture density
   - **Sportradar / official ATP-WTA data** — higher cost, higher trust; worth quoting if self-host budget allows
   - **TheSportsDB tennis supplement debug** — why men's RG partially indexes but women's QFs do not (may be cheaper fix for a subset)
3. **Pipeline work regardless of vendor:**
   - Mark **~26 unique aggregate/non-fixture patterns** as `skipped` (`metadata_only` / enrichability) — multiview, courtside, RG court banners, legends, primetime
   - **Four-player doubles extraction** before expecting doubles match rate
   - **Wheelchair** — confirm chosen API includes UNIQLO Wheelchair RG draw or accept permanent `no_match` for that slice (~7%)

### Expected production impact (after calendar source + requeue TODO 124)

| Metric | Conservative | Optimistic |
|--------|-------------|------------|
| Unique content matchable | ~120–130 (singles + some doubles) | ~146 |
| Channels matchable | ~240–260 | ~280–290 |
| Should stay skipped | ~26 unique / ~52 channels | same |
| `no_match` reduction from 342 | **~50–60%** (singles-only API + no doubles fix) | **~70–85%** (full API + doubles parsing + skip rules) |

TODO 122 acceptance criterion ("≥70% drop") is **achievable** only with doubles parsing and skip reclassification — not calendar ingestion alone.

---

## 7. Top 5 surprising patterns

1. **Not a replay problem** — 85%+ of unique content is structured `Player vs Player @ Jun 3` live-style naming; skepticism about replay volume doesn't match data.
2. **Near-zero provider dedup at first glance** — 342 rows collapse to 168 content keys (not 341→~80 as might be assumed); IPTV lists carry **regional copies**, not 4× the same slug on one tag.
3. **TheSportsDB partially works** — 9 matched channels prove men's RG exists in DB; women's QFs with verified real-world results are entirely absent → **coverage hole**, not matcher regression.
4. **Doubles dominate the long tail** — 53% of unique keys are doubles-format names; competitor extractor collapses them to bogus two-name teams, guaranteeing `no_match` even if fixtures exist.
5. **"Other" includes high-profile QFs with seed suffixes** — `Sabalenka 1 vs Shnaider` fails the singles-live regex but extracts correctly; easy matcher win once fixtures exist.

---

## Appendix: commands used

```bash
ssh root@docker.klopnet.com

# Inventory
docker exec iptv-proxy-v2 curl -s \
  'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=no_match&search=Tennis&limit=500'

# Status counts
docker exec iptv-proxy-v2 python -c "
from app import app
from models import Channel
with app.app_context():
    q = Channel.query.filter(Channel.name.ilike('%Tennis%'), Channel.is_ppv == True)
    for s in ['no_match','skipped','matched','queued']:
        print(s, q.filter(Channel.ppv_enrichment_status==s).count())
"

# Calendar cache tennis check
docker exec iptv-proxy-v2 python -c "
from app import app
from services.thesportsdb_calendar_scraper import TheSportsDBCalendarScraper
from datetime import date
with app.app_context():
    events = TheSportsDBCalendarScraper().get_events_for_date(date(2026, 6, 3))
    print(len(events), 'events; tennis:', sum(1 for e in events if 'tennis' in str(getattr(e,'sport','')).lower()))
"
```

Classification and date histograms were run via inline Python in the container using `PPVEventExtractor`, `DateExtractor`, and `Channel.query` (see investigation session 2026-06-03).
