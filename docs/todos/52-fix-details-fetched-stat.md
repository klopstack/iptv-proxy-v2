# Fix `details_fetched` cumulative stat never incremented

**Status:** ⬜ Not started  
**Priority:** P0  
**Audit:** PPV audit, June 2026

## Problem

The PPV enrichment status API and admin UI expose `cumulative_stats.details_fetched` (backed by `SyncMetadata` key `ppv_details_fetched_count` / `METADATA_KEY_DETAILS_FETCHED`). The value is read in `PPVCalendarEnrichmentService.get_status()` but **nothing ever writes it**.

Operators see a permanently stale or zero metric, undermining trust in enrichment progress dashboards.

## Affected files

- `services/ppv/enrichment.py` — `_fetch_event_details`, `get_status`
- `services/ppv/constants.py` — `METADATA_KEY_DETAILS_FETCHED`
- `routes/ppv_enrichment.py` — status response shape
- `templates/ppv.html` — displays the stat

## Proposed solution

1. After a successful detail fetch in `_fetch_event_details` (API data returned and event updated or already complete), increment the cumulative counter via `SyncMetadata.increment(METADATA_KEY_DETAILS_FETCHED)` (or equivalent set/get pattern used by `METADATA_KEY_CALENDAR_*` keys).
2. Mirror the increment in session stats if that counter is also expected to reflect detail fetches in the current run.
3. Do **not** increment on skipped fetches (event not found, already `full`/`enriched` without refresh, API returned empty).

## Acceptance criteria

- [ ] Processing one new event through the detail queue increases `cumulative_stats.details_fetched` by 1.
- [ ] Skipped/already-complete events do not increment the counter.
- [ ] Status API and UI show a non-zero value after detail fetches in integration tests.

## Test plan

- Unit test: mock `_fetch_event_details` path and assert `SyncMetadata` key increments once per successful fetch.
- Extend existing enrichment test that exercises detail queue to assert cumulative stat changes.

## Dependencies

None.
