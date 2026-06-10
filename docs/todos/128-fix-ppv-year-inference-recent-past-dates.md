# Fix PPV year inference for recent past month/day titles

**Status:** ✅ Implemented — PR pending  
**Priority:** P1  
**Audit:** PPV production report, June 4 2026 (`docker.klopnet.com`)

## Problem

[120](./120-fix-ppv-date-extraction-parsing-bugs.md) fixed several date-parser bugs and added production fixtures (including `@ Jun 3` → `2026-06-03`). **Production still mis-parses the same patterns** as of 2026-06-04: month/day-only titles roll forward to the **next calendar year** when the day-of-month is before “today”, even when the intended date is **yesterday or a few days ago**.

Verified in container (`reference = 2026-06-04`):

| Channel name (truncated) | Parsed date (actual) | Expected | Impact |
|--------------------------|----------------------|----------|--------|
| `Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM` | **2027-06-03** | **2026-06-03** | `classify_ppv_enrichment` → `far_future` → **332 tennis channels skipped** |
| `Tennis: Guy Sasson vs Jin Woodman @ Jun 3 10:55 AM` | **2027-06-03** | **2026-06-03** | Same |

Competitor extraction is fine (`('Anna Kalinskaya', 'Maja Chwalinska')`). The channel never reaches calendar matching — it is filtered as `skip:far_future` before enrichment runs.

This is distinct from [129](./129-ppv-replay-archive-enrichment-flosp.md) (intentional archive/replay feeds). Here the titles describe **recent same-tournament fixtures** (Roland Garros Day 11) that should be enrichable on the correct historical day, then classified as **replay** once linked (see 129 + `PPVVisibilityService.classify_live_replay_event`).

### Root cause (suspected)

- Month/day strategies or shared `date_anchor` logic assume **“if month/day < reference month/day, use next year”** — correct for **upcoming** events in the same season, wrong for **recent past** events still present in provider lineups.
- `inferred_how: full_date` with year **2027** suggests year rollover runs without a **recent-past window** (e.g. if parsed date is within N days before reference, keep current year).
- Possible **deploy drift**: fix landed in repo/tests but production image or one extractor path not updated — verify both `PPVEventExtractor` and `DateExtractor` on production after patch.

## Affected files

- `services/ppv/extraction/date_anchor.py` — shared year rollover / anchor logic (from TODO 120)
- `services/ppv/extraction/date_strategies/` — `month_day.py`, strategy ordering
- `services/reverse_event_matcher/date_extractor.py` — parity with enrichment extractor
- `services/ppv/enrichability.py` — `far_future` gate consumes wrong year
- `services/ppv/extraction/extractor.py` — `is_date_far_future`
- Tests: `tests/ppv/test_date_extraction_production_fixtures.py` (extend), `tests/test_ppv_extraction.py`
- Docs: `docs/architecture/ppv-matching-strategies.md` — document recent-past vs upcoming year rule

## Requirements for resolution

### Functional

1. **Recent-past window:** For month/day-only titles (e.g. `@ Jun 3`, `Jun 4 01:55`) without an explicit year, if the nearest **same-year** occurrence falls within a configurable lookback (default **7 days** before reference UTC), resolve to **that past date**, not next year.
   - Reference `2026-06-04`, title `@ Jun 3 11:00` → **`2026-06-03 11:00`**, not `2027-06-03`.
2. **Upcoming events unchanged:** Title `@ Jun 8` on reference `2026-06-04` → **`2026-06-08`** (same year, future).
3. **Year rollover for distant past:** Title `@ Jun 3` on reference `2026-07-15` ( > lookback ) → **`2027-06-03`** (next occurrence) — document rule.
4. **Explicit year in title** (`2026-06-03`, `2025-10-22`) — unchanged; handled by [129](./129-ppv-replay-archive-enrichment-flosp.md) when date is archive.
5. **Parser parity:** Same channel name + reference datetime → identical naive datetime from `PPVEventExtractor` and `DateExtractor`.
6. **Enrichability:** Recently parsed past dates must **not** trigger `far_future`; may still be `stale_archive` only when beyond [129](./129-ppv-replay-archive-enrichment-flosp.md) / `STALE_ARCHIVE_ENRICHMENT_DAYS` policy (tennis Jun 3 on Jun 4 is **not** stale archive — it is recent replay).

### Non-functional

- Injectable reference datetime in all new tests (`freezegun` or constructor arg).
- Extend existing TODO 120 fixtures — do not duplicate file unless necessary.

## Proposed solution

1. Add **`resolve_month_day_year(month, day, reference, *, lookback_days=7)`** in `date_anchor.py`:
   - Candidate A = `reference.year`
   - Candidate B = `reference.year + 1`
   - Pick candidate minimizing absolute delta to reference, preferring past within lookback over future rollover.
2. Wire into month/day strategies **before** any blind “+1 year if before today” fallback.
3. Add regression tests mirroring **production container output** (assert not `2027-06-03` for Jun 3 tennis on Jun 4 reference).
4. Deploy + requeue tennis channels (currently `skipped:far_future`) via [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) after merge.

## Acceptance criteria

- [x] Production fixture `Tennis: … @ Jun 3 …` with reference `2026-06-04` → **`2026-06-03`**, `classify_ppv_enrichment` → **`None`** (enrichable), not `far_future`.
- [x] Existing `tests/ppv/test_date_extraction_production_fixtures.py` tennis case passes on **both** extractors (re-verify CI green).
- [x] New parametrized cases: yesterday, 6 days ago, 8 days ago (rollover), tomorrow — documented expected year.
- [ ] After deploy + requeue on production: tennis `skipped:far_future` count drops from **~331** toward **0** (remaining gaps are calendar/matching, not date skip).
- [x] No regression on Peacock ISO dates, EPL `19:30` same-day titles, or WCWS `@ Jun 4` cases from TODO 120.

## Test plan

### Unit tests

Extend `tests/ppv/test_date_extraction_production_fixtures.py`:

| Fixture ID | Reference | Input | Expected date |
|------------|-----------|-------|---------------|
| `tennis-jun3-yesterday` | `2026-06-04 12:00 UTC` | `Tennis: Kalinskaya vs Chwalinska @ Jun 3 11:00 AM` | `2026-06-03 11:00` |
| `tennis-jun3-same-day` | `2026-06-03 18:00 UTC` | same | `2026-06-03 11:00` |
| `tennis-jun3-next-season` | `2026-07-01 12:00 UTC` | same | `2027-06-03 11:00` (documented) |
| `jun8-upcoming` | `2026-06-04 12:00 UTC` | `… @ Jun 8 7:00 PM` | `2026-06-08 19:00` |

Assert for **both** extractors. Add enrichability assertion: `classify_ppv_enrichment(name, extraction)` is not `far_future` for `tennis-jun3-yesterday`.

### Production verification

```bash
ssh root@docker.klopnet.com
docker exec iptv-proxy-v2 python -c "
from app import app
from services.ppv.extraction.extractor import PPVEventExtractor
from services.ppv.enrichability import classify_ppv_enrichment
from datetime import datetime
ref = datetime(2026, 6, 4, 12, 0, 0)
name = 'Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM'
with app.app_context():
    ex = PPVEventExtractor(current_date=ref).extract_all(name)
    print(ex.get('date'), classify_ppv_enrichment(name, ex))
"

# After requeue + process:
docker exec iptv-proxy-v2 curl -s 'http://127.0.0.1:8000/api/ppv-enrichment/channels?status=skipped&search=Tennis%3A' | jq '.pagination.total'
```

## Dependencies

- **Blocks:** meaningful tennis enrichment after [128](./128-fix-ppv-year-inference-recent-past-dates.md) + calendar ([122](./122-tennis-calendar-event-source.md), [125](./125-sofascore-tennis-calendar-slice1.md)).
- **Related:** [127](./127-ppv-multi-player-competitor-extraction.md) (doubles parsing), [129](./129-ppv-replay-archive-enrichment-flosp.md) (replay classification for matched past events).
- **Ops:** [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) requeue after deploy.

## Recommended order

**128 before requeue-heavy tennis work** — fixes a silent skip that makes production metrics look healthier than matching reality (tennis hidden in `skipped`, not `no_match`).
