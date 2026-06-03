# Fix PPV date extraction parsing bugs

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`)

## Problem

Date parsing errors are a primary cause of `no_match` for otherwise matchable PPV channels. Competitors extract correctly, but the channel is bucketed onto the wrong calendar day (or wrong year), so reverse matching finds no event.

Production examples verified on 2026-06-03 (reference “now” = `2026-06-03T18:00Z`):

| Channel name (truncated) | Parsed date (actual) | Expected | Impact |
|--------------------------|----------------------|----------|--------|
| `Live Football 01: Charlton Athletic vs Leicester City 12:30pm` | **2027-01-03** | 2026-06-03 (today + time) | Wrong day → no calendar lookup |
| `#11 Texas Tech vs #2 Texas (WCWS Finals Game 1) @ Jun 4 01:55` | **2026-11-03** | 2026-06-04 | Month confusion (`Jun 4` → Nov 3) |
| `Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM` | **2027-06-03** | 2026-06-03 | Year off by one |
| `Boxing 1 : Oleksandr Usyk vs. Rico Verhoeven` | **2027-01-03** | None or infer from context | Garbage default date |

Two parallel date parsers exist and must stay aligned:

1. **`PPVEventExtractor`** — `services/ppv/extraction/date_strategies/*` (used by enrichment, enrichability, `show_unmatched_channels.py`)
2. **`DateExtractor`** — `services/reverse_event_matcher/date_extractor.py` (used by `ReverseEventMatcher.find_matches`)

A fix in only one path will leave enrichment grouping and reverse matching out of sync.

### Root causes (suspected)

- **`dateparser` `PREFER_DATES_FROM: future`** combined with bare month/day fragments resolves ambiguous strings to the wrong year or month.
- **Time-only strings** (`12:30pm`) parsed as dates without anchoring to “today” or an explicit `@ Jun N` fragment in the same title.
- **`Jun 4 01:55`** without year: dateparser may interpret `4` as day-of-month in a different month context (observed: Nov 3).
- **No shared “reference now”** in production scripts — `show_unmatched_channels.py` uses `DateExtractor()` with live clock while enrichment may use injectable `current_date`; tests may not pin a reference date.

## Affected files

- `services/ppv/extraction/date_strategies/` — especially `month_day.py`, `base.py`, `__init__.py`
- `services/ppv/extraction/extractor.py` — `is_date_far_future`, strategy ordering
- `services/reverse_event_matcher/date_extractor.py` — dateparser settings, strategy order
- `services/ppv/channel_matching.py` — UTC day bucketing consumes extracted dates
- `services/ppv/enrichability.py` — far-future / skip decisions
- Tests: `tests/test_ppv_extraction.py`, `tests/ppv/test_channel_matching.py`, new parametrized fixture file

## Requirements for resolution

### Functional

1. **Explicit `@ Mon D` / `Jun 4` patterns** in channel names must resolve to the **nearest upcoming occurrence** relative to a configurable reference datetime (default: UTC now), not an arbitrary future year.
   - `Jun 3 11:00 AM` on reference `2026-06-03` → `2026-06-03 11:00`, not `2027-06-03`.
   - `Jun 4 01:55` on reference `2026-06-03` → `2026-06-04 01:55`, not `2026-11-03`.

2. **Time-only suffixes** (`12:30pm`, `7:00 PM`) when no standalone date is present must combine with:
   - an explicit date fragment in the same string (`@ Jun 3`, ISO date, pipe date), **or**
   - “today” on the reference date when the channel context implies a live event (document the rule; prefer explicit date in name when present).

3. **ISO and pipe timestamps** (`2026-06-03 18:30:00`, `start:2026-06-03 …`) must continue to parse unchanged — regression-free.

4. **Far-future guard** (`is_date_far_future`, `_validate_date_range`) must reject garbage parses (e.g. defaulting to Jan 3 2027 for boxing with no date) and surface **`skipped` / `no_date`** instead of searching the wrong calendar day.

5. **Parser parity:** Given the same channel name and reference datetime, `PPVEventExtractor.extract_date()` and `DateExtractor.extract_date()` must return the same naive datetime (or both return `None`).

6. **Document** ambiguous cases and precedence in `docs/architecture/ppv-matching-strategies.md` (short “date extraction” subsection).

### Non-functional

- Deterministic tests via injectable `current_date` / `freezegun` — no tests that depend on the day the suite runs.
- No new dependency unless justified; prefer tightening strategy order and regex before adding libraries.

## Proposed solution

1. Add **`MonthDayStrategy`** (or extend existing) with explicit English month abbrev handling **before** falling through to `dateparser.search_dates`.
2. Add **`TimeWithAnchorStrategy`**: if time-only matches and an `@ Mon D` or `Mon D` anchor exists elsewhere in the string, combine them.
3. Tighten **`DateExtractor`** dateparser settings for strategy 4: use `PREFER_DATES_FROM: "current_period"` or custom logic for month/day without year; cap year rollover to ±1 from reference.
4. Shared helper module (e.g. `services/ppv/extraction/date_anchor.py`) imported by both extractors to avoid drift.
5. Re-run enrichment for affected `no_match` channels after merge (see [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md)).

## Acceptance criteria

- [ ] Production fixture set (below) passes in both extractors with `reference = 2026-06-03 18:00 UTC`.
- [ ] `show_unmatched_channels.py --reason no-match` count drops for date-related failures (measure on staging/production after requeue).
- [ ] No regression on existing `tests/test_ppv_extraction.py` and `tests/ppv/test_channel_matching.py`.
- [ ] Charlton/Leicester channel resolves to **2026-06-03** (or `None` if only time — then combined with provider date metadata if available); must **not** produce 2027-01-03.
- [ ] WCWS channel resolves to **2026-06-04**, not 2026-11-03.
- [ ] Tennis `@ Jun 3` resolves to **2026-06-03**, not 2027-06-03.
- [ ] Channels with no date signal return `None`, not a spurious default date.

## Test plan

### Unit tests (required)

New file: `tests/ppv/test_date_extraction_production_fixtures.py`

Parametrize with `reference_date = datetime(2026, 6, 3, 18, 0, 0)`:

| Fixture ID | Input channel name | Expected `extract_date` |
|------------|-------------------|-------------------------|
| `football-time-only` | `Live Football 01: Charlton Athletic vs Leicester City 12:30pm` | `2026-06-03 12:30` (or documented rule) |
| `wcws-jun4` | `#11 Texas Tech vs #2 Texas (WCWS Finals Game 1) @ Jun 4 01:55` | `2026-06-04 01:55` |
| `tennis-jun3` | `Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM` | `2026-06-03 11:00` |
| `boxing-no-date` | `Boxing 1 : Oleksandr Usyk vs. Rico Verhoeven` | `None` |
| `iso-peacock` | `US (Peacock 001) \| Away Feed: BAL at BOS (2026-06-03 18:30:00)` | `2026-06-03 18:30` (unchanged) |
| `albania-jun3` | `Albania vs Israel @ Jun 3 20:50` | `2026-06-03 20:50` (unchanged) |

Each case asserted for **both** `PPVEventExtractor(current_date=reference)` and `DateExtractor` (with monkeypatched `RELATIVE_BASE` or equivalent).

### Integration tests

- `ReverseEventMatcher.find_matches()` with calendar loaded for `2026-06-03`–`2026-06-04`: after date fix, tennis/football channels still may not match if event absent from calendar — assert **date filter uses correct day**, not that match succeeds (avoid coupling to TODO 122/123).
- `build_channel_matching_context()` groups fixed fixtures into expected UTC day buckets.

### Production verification

After deploy + requeue (TODO 124):

```bash
docker exec iptv-proxy-v2 python scripts/show_unmatched_channels.py --reason no-date
docker exec iptv-proxy-v2 python scripts/analyze_matching_stats.py
```

Compare `no_match` count and “had competitors + date but no match” bucket vs baseline (1072 `no_match`, ~2127 competitor+date unlinked at 2026-06-03 audit).

## Dependencies

- [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) — re-process channels after fix.
- [122](./122-tennis-calendar-event-source.md), [123](./123-extended-calendar-coverage-college-obscure-sports.md) — calendar coverage; date fix alone will not match events missing from TheSportsDB.

## Recommended order

**120 first** — highest leverage; unblocks correct calendar day lookup for hundreds of channels before adding new event sources.
