# Spike: NCAA / college / amateur calendar data sources

**Status:** ⬜ Not started  
**Priority:** P1  
**Type:** Research spike (no production wiring in this TODO)  
**Audit:** PPV production report, June 4 2026; [129](./129-ppv-replay-archive-enrichment-flosp.md) Flo replay tail

## Problem

**~243 Flo (FLSP) PPV channels** are archive replays with parseable competitors and explicit dates (mostly **2025**, e.g. `22/10 19:00`), but enrichment returns **`no_match_found`** because no calendar provider returns fixtures for those days.

Flo feed breakdown (production, June 2026):

| Subtype | Channels (approx.) | Example |
|---------|-------------------:|---------|
| College women's | ~86 | `Occidental vs Chapman - Womens - 22/10 19:00` |
| College men's | ~63 | `Guilford vs Randolph - Mens - 22/10 19:00` |
| Junior / minor hockey | ~26 | `Colorado Eagles vs San Diego Gulls - 22/10 22:00` |
| Other college / amateur | ~72 | Field hockey, lacrosse, CJHL, etc. |

[123](./123-extended-calendar-coverage-college-obscure-sports.md) Track A **deferred** WCWS/BTN+ calendar integration — channels **skip** as `unsupported_sport` for live feeds. [129](./129-ppv-replay-archive-enrichment-flosp.md) reverses that product stance for **Flo replays**: we want fixtures, not skip.

Existing infrastructure:

| Source | Today | Gap |
|--------|-------|-----|
| TheSportsDB + MiLB | Live pro + minor baseball | No NCAA, no historical Oct 2025 window for replay |
| ESPN tennis | Primary tennis | N/A for college |
| SofaScore (`tennis` only) | Merged when flag on; **±14 day** fetch window | College slugs untested; window blocks Oct 2025 replay dates |
| Sportsipy | Team DB + **context provider** (H2H, schedules) | NCAAB/NCAAF/NHL schedule classes exist; not wired as **calendar** for PPV day-bucket matching |
| NCAA official APIs | Not integrated | Licensing / coverage unknown |

**Hypothesis:** SofaScore may already expose college basketball, hockey, and amateur fixtures via additional sport slugs — extending [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) could be cheaper than a new vendor. This spike validates or rejects that before [131](./131-sofascore-college-amateur-calendar-provider.md) implementation.

## Spike goals

1. **Inventory** Flo (and similar) PPV channels by sport, date range, and team-name patterns.
2. **Probe candidate APIs** for **3–5 sample historical dates** (e.g. `2025-10-22` from production cluster).
3. **Manual match** ≥20 representative channel titles against each source’s fixture list; record hit rate.
4. **Recommend** primary + fallback provider(s) and document gaps that stay `no_match`.
5. **Deliver** architecture note — no merge code in this TODO.

## Candidate sources to evaluate

### A — SofaScore (extend existing client)

Endpoint (already used for tennis):

```http
GET https://api.sofascore.com/api/v1/sport/{slug}/scheduled-events/{YYYY-MM-DD}
```

Slugs to probe (non-exhaustive — discover via SofaScore sport list):

| Slug (candidate) | Flo / PPV relevance |
|------------------|---------------------|
| `basketball` | NCAA men's/w women's (`- Mens -` / `- Womens -`) |
| `ice-hockey` | AHL, CHL, junior (`Eagles vs Gulls`) |
| `american-football` | NCAAF if present |
| `volleyball` | College volleyball |
| `football` | Soccer vs American — verify payload shape |
| `field-hockey`, `lacrosse`, … | Discover from sport metadata API |

Check: event count per day, team name shape (`homeTeam.name`), tournament/league labels for sport context, rate limit at N slugs × historical dates.

Reference: [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md).

### B — Sportsipy (existing dependency)

Already installed for team refresh (`ncaab`, `ncaaf`, `nhl`, …). Evaluate:

- Per-team `Schedule` pages for Flo example schools on sample dates
- Feasibility of **day-indexed** calendar (vs per-channel team lookup — too slow?)
- Sports Reference rate limits (30 pages/min) vs enrichment batch size
- Women's sports / field hockey coverage gaps

Use as **fallback** if SofaScore misses specific NCAA divisions.

### C — TheSportsDB

- Search existing league IDs for NCAA, AHL, college hockey
- `eventsday.php` / API supplement for sample dates — likely sparse for DIII/LAC

### D — ESPN / NCAA official

- ESPN college scoreboard JSON (unofficial endpoints — document stability)
- NCAA.com / stats.ncaa.org — terms, auth, historical depth
- **Goalserve**, **api-football** college tiers — cost vs coverage (brief table only)

### E — Out of scope for spike (document only)

- Live WCWS/BTN+ ([123](./123-extended-calendar-coverage-college-obscure-sports.md) — separate live feed problem)
- Obscure DAZN regional football ([123](./123-extended-calendar-coverage-college-obscure-sports.md) Track B)

## Spike procedure

### Step 1 — Production sample export

```bash
ssh root@docker.klopnet.com
docker exec iptv-proxy-v2 python -c "
from app import app
from models import Channel
with app.app_context():
    rows = Channel.query.filter(
        Channel.is_ppv==True,
        Channel.name.ilike('%FLSP%'),
    ).all()
    # group by date substring, sport hint; write JSON for spike fixtures
"
```

Target: **≥50 unique content keys**, stratified by sport hint and date.

### Step 2 — Date selection

Pick **3–5 calendar dates** covering the bulk of Flo cluster:

- Primary: `2025-10-22` (densest `22/10` cluster)
- Secondary: adjacent days ±1 if channel dates spread
- Optional: one 2025 non-October sample if inventory shows second cluster

### Step 3 — Source probes (local / manual — not CI)

For each `(source, sport_slug_or_league, date)`:

1. Fetch raw JSON (curl or spike script under `scripts/spike/` — **not committed as production code** unless reused in 131).
2. Count events; filter to fixtures plausibly matching Flo titles.
3. Record **match / partial / miss** for each sample channel:

| Channel title | Source | Fixture found? | Notes (name mismatch, wrong league, etc.) |
|---------------|--------|----------------|-------------------------------------------|

### Step 4 — Decision matrix

| Source | Sports covered | Hit rate on sample | Historical depth | Rate / ops cost | Recommendation |
|--------|----------------|-------------------:|------------------|-----------------|----------------|
| SofaScore `{slug}` | … | …% | … | … | Primary / supplement / reject |
| Sportsipy schedules | … | …% | … | … | … |
| … | | | | | |

**Decision outputs (pick one path per sport family):**

- **Primary:** SofaScore multi-sport → implement [131](./131-sofascore-college-amateur-calendar-provider.md)
- **Supplement:** Sportsipy for gaps SofaScore misses
- **Reject / defer:** Document permanent `no_match` with `unsupported_sport` or low-volume skip

### Step 5 — Architecture deliverable

**New file:** `docs/architecture/ncaa-college-calendar-source-spike.md`

Sections:

1. Executive summary + recommended provider stack
2. Flo channel inventory tables
3. Per-source probe results (redacted fixtures OK in repo under `tests/ppv/fixtures/spike/`)
4. SofaScore slug table update for [sofascore-calendar-sport-slugs.md](../architecture/sofascore-calendar-sport-slugs.md)
5. Historical date window requirement for [129](./129-ppv-replay-archive-enrichment-flosp.md) (likely **>> 14 days** — separate from live `MAX_API_SUPPLEMENT_DAYS_BACK`)
6. Team-name normalization notes for college (`Occidental` vs `Occidental Tigers`, ranking prefixes)
7. Open gaps → future TODO or accept `no_match`

## Acceptance criteria

- [ ] `docs/architecture/ncaa-college-calendar-source-spike.md` merged with decision matrix and **go/no-go for SofaScore 131**.
- [ ] ≥20 Flo sample channels manually scored against ≥2 candidate sources.
- [ ] SofaScore slug probe results documented for **basketball**, **ice-hockey**, and ≥2 other Flo-heavy sports.
- [ ] Explicit note on **historical fetch window** (14-day limit today blocks Oct 2025 replays).
- [ ] [129](./129-ppv-replay-archive-enrichment-flosp.md) Track B updated to link spike outcome (replace inline “Phase 0” with this doc).
- [ ] Recorded JSON fixtures for at least one successful SofaScore college/hockey day committed under `tests/ppv/fixtures/sofascore/` (for 131 tests) **if** spike recommends SofaScore.

## Non-goals

- Merging providers into `TheSportsDBCalendarScraper` ([131](./131-sofascore-college-amateur-calendar-provider.md))
- Enrichability / replay routing ([129](./129-ppv-replay-archive-enrichment-flosp.md))
- Paid API contracts or production keys

## Dependencies

- **Informs:** [131](./131-sofascore-college-amateur-calendar-provider.md), [129](./129-ppv-replay-archive-enrichment-flosp.md) Track B
- **Related:** [126](./126-sofascore-calendar-multi-sport-and-enrichment.md), [123](./123-extended-calendar-coverage-college-obscure-sports.md) Track A (deferred WCWS)
- **Parallel OK:** [128](./128-fix-ppv-year-inference-recent-past-dates.md), [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A

## Recommended order

**130 first** — before significant calendar engineering. Expected duration: **1–2 days** research + doc. If SofaScore hit rate ≥ **60%** on college basketball + hockey samples, proceed to **131**; otherwise spike doc must name alternate before implementation.
