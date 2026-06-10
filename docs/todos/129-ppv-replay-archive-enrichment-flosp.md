# PPV replay/archive enrichment (FloSports and similar providers)

**Status:** 🟡 Track A+C implemented — PR pending; Track B deferred to [131](./131-sofascore-college-amateur-calendar-provider.md)  
**Priority:** P1  
**Audit:** PPV production report, June 4 2026 (`docker.klopnet.com`)

## Problem

**243 of 339** unresolved PPV channels (~72% of the current tail) are **`Flo (FLSP)`** college and minor-league replays. Example:

```
Flo (FLSP) 110: 2025 Occidental vs Chapman - Mens - 22/10 19:00
Flo (FLSP) 161: 2025 Colorado Eagles vs San Diego Gulls Away - 22/10 22:00
```

These are **intentional replays of old games**, not live fixtures. Product expectation:

1. **Enrich them** — match channel titles to real historical events and create `Event` + `EventChannelLink` rows.
2. **Classify as replay** in playlist output — when account `ppv_visibility = group_live_replay`, place under the **Replay** virtual category, not **Live**.

Current behavior is wrong in multiple places:

| Layer | Current behavior | Desired behavior |
|-------|------------------|------------------|
| Enrichability | Parses date/competitors; **not** `stale_archive` (Flo uses `DD/MM`, not ESPN Play `MM-DD-YYYY`) | Treat as **archive-replay enrichable**, not skip |
| Enrichment | **`no_match_found`** — no calendar events for Oct 2025 NCAA / AHL | Historical fixture lookup for explicit archive dates |
| Visibility | Unmatched channels hidden or optimistic; matched past events → replay **only if linked** | Linked archive events → **`PPV_GROUP_REPLAY`** |
| Metrics | 243 channels burn queue cycles; counted as matching failures | Replay bucket separate from live `no_match` |

[123](./123-extended-calendar-coverage-college-obscure-sports.md) Track D added `stale_archive` skip for **ESPN Play** titles with US-format past dates (`11-09-2023`). That reduced noise but **does not apply to Flo** and conflicts with the product goal: **we want these replays enriched**, not skipped.

Production snapshot (2026-06-04):

- **247** Flo/FLSP channels in `queued` (failed match after 1 attempt)
- **~245** carry **2025** or `DD/MM` dates (stale relative to now)
- **0** Flo channels matched today
- Calendar DB has **no** NCAA / FloSports / junior hockey coverage for those dates

Replay classification **already exists** for linked events:

```python
# services/ppv/visibility.py — classify_live_replay_event
if event.scheduled_at < current_time:
    return PPV_GROUP_REPLAY  # "replay"
```

The gap is **getting archive channels matched and linked** with correct `scheduled_at` in the past, not changing Live/Replay window math.

## Affected files

- `services/ppv/enrichability.py` — archive/replay provider detection; do **not** skip Flo/FLSP as `stale_archive`
- `services/ppv/constants.py` — replay provider patterns; optional `REPLAY_ENRICHMENT_LOOKBACK_DAYS`
- `services/ppv/extraction/` — Flo title date format (`22/10`, leading `2025` year); sport hints (Mens/Womens, hockey)
- `services/ppv/enrichment/match_pipeline.py` — calendar lookup keyed to **extracted historical date**, not “today”
- `services/ppv/calendar_providers/` or `services/thesportsdb_calendar_scraper.py` — historical day fetch / cache
- `services/ppv/persistence.py` — mark events `is_ppv=True`, preserve past `scheduled_at`
- `services/ppv/visibility.py` — ensure unmatched **replay-provider** channels are not shown as live optimism (optional)
- `services/playlist_format_service.py`, `routes/xtream.py` — Replay group title (already wired via classification)
- Tests: `tests/ppv/fixtures/flosp_replay_channels.json`, `tests/test_playlist_generation.py`, enrichability tests
- Docs: `docs/architecture/ppv-matching-strategies.md` — live vs replay enrichment matrix

## Requirements for resolution

### Track A — Provider detection and enrichability

1. **Recognize replay/archive providers** by title prefix or category:
   - `Flo (FLSP)`, `(US) (Flo …)`, similar FloSports patterns
   - Optional: extend to other explicit archive feeds (distinct from [123](./123-extended-calendar-coverage-college-obscure-sports.md) ESPN Play **skip** list — product decision per provider)
2. **`classify_ppv_enrichment`:** return **`None`** (enrichable) for replay providers when competitors + parseable date exist — **never** `stale_archive` solely because event date is in the past.
3. **Tag extraction metadata** (e.g. `extraction["replay_archive"] = True` or provider id) for pipeline routing and metrics.
4. **Explicit past dates** in title (`2025 …`, `22/10 19:00`) must parse to the **historical** datetime ([128](./128-fix-ppv-year-inference-recent-past-dates.md) handles ambiguous month/day without year).

**Acceptance:**

- [x] Flo production examples classify as enrichable, not `stale_archive` / `far_future`.
- [ ] `/api/ppv-enrichment/channels` exposes replay-provider flag or filter (optional).

### Track B — Historical calendar matching

1. For replay-tagged channels, calendar lookup uses **extracted event date** (e.g. `2025-10-22`), not reference “today”.
2. Evaluate data sources for college / minor leagues present in Flo feeds — see [130](./130-ncaa-college-calendar-source-spike.md) spike and [131](./131-sofascore-college-amateur-calendar-provider.md) implementation.
3. **Match strategy:** same reverse matcher + validation; tolerate college team name variants (`Occidental` vs `Occidental Tigers`).
4. On successful match: persist `Event.scheduled_at` = historical start; link channel; status **`matched`**.

**Acceptance:**

- [ ] Fixture set of ≥10 Flo channels from production JSON matches when source has that day’s fixtures.
- [ ] Production: Flo `queued`/`no_match` count drops measurably after source + requeue (target TBD in spike — not 100% without full NCAA coverage).
- [ ] Channels without any source fixture remain **`no_match`**, not `skipped`.

### Track C — Live vs replay playlist presentation

1. Matched archive events with `scheduled_at < now` → **`classify_live_replay_event` → `replay`** (verify no special-case hides them when `group_live_replay`).
2. M3U / Xtream: `#EXTINF` group title **Replay** for matched Flo channels (existing `_ppv_group_title` path).
3. **Hide unmatched** archive replays under `hide_inactive` (no false “live” slots) — document behavior.
4. Dashboard/metrics: optional **`replay_matched`** count separate from live PPV matched.

**Acceptance:**

- [x] Integration test: Flo channel linked to past event → playlist category **Replay**, not Live.
- [x] Integration test: same event would be **Live** if `scheduled_at` within 24h window (regression guard).

### Track D — Reconcile with TODO 123 stale archive policy

1. Document matrix: **skip** (ESPN Play ancient junk) vs **enrich as replay** (Flo product feeds).
2. Adjust [123](./123-extended-calendar-coverage-college-obscure-sports.md) Track D docs — `stale_archive` is for **non-enrichable** archive noise, not Flo replays we sell.

## Proposed solution

1. **Spike:** [130](./130-ncaa-college-calendar-source-spike.md) — source decision + recorded fixtures.
2. **Phase 1:** Provider detection + enrichability + extraction hardening for Flo date formats.
3. **Phase 2:** [131](./131-sofascore-college-amateur-calendar-provider.md) + enrichment date routing for `replay_archive` channels.
4. **Phase 3:** Playlist/visibility verification + dashboard split + production requeue (`Flo` prefix filter in [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md)).

## Test plan

### Unit tests

- `tests/ppv/test_replay_provider_enrichability.py` — Flo titles → enrichable; ESPN Play 2023 → still `stale_archive` skip.
- Extend `tests/test_ppv_extraction.py` — Flo `22/10` + `2025` year → `2025-10-22 19:00`.
- `tests/ppv/test_replay_calendar_matching.py` — mocked historical calendar returns fixture; pipeline links channel.

### Integration tests

- `tests/test_playlist_generation.py` — matched past Flo event → group **Replay**.
- `tests/test_xtream.py` — extend live/replay grouping with archive PPV channel.

### Production verification

```bash
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=queued&search=Flo' | jq '.pagination.total'
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=matched&search=Flo' | jq '.pagination.total'
# After fix: generate M3U for account with group_live_replay; grep EXTINF group-title Replay
```

## Dependencies

- [128](./128-fix-ppv-year-inference-recent-past-dates.md) — correct year for ambiguous `@ Jun N` tennis (separate from Flo but same visibility stack).
- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — requeue Flo prefix after deploy.
- [130](./130-ncaa-college-calendar-source-spike.md) — calendar source decision (blocks Track B).
- [131](./131-sofascore-college-amateur-calendar-provider.md) — primary provider implementation after spike.
- [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) — merge patterns ✅.
- **Independent of** [127](./127-ppv-multi-player-competitor-extraction.md) (tennis doubles).

## Recommended order

**129 Phase 1** (enrichability) can land before **131**; **129 Track B** depends on **130 → 131**. Parallel: **128**, **130** spike.

**Impact:** Converts ~72% of current unresolved queue from permanent `no_match` into either matched **Replay** rows or honest `no_match` with a documented source gap — aligns product with “Flo = replay library” intent.
