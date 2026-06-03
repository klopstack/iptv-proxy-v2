# Add MiLB PPV end-to-end integration test

**Status:** ✅ Done  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

MiLB support spans multiple new components:

- `services/mlb_stats_api.py`, `services/mlb_stats_calendar.py`
- `services/milb_team_service.py`
- Calendar scraper MiLB path
- `persistence.create_or_update_event` with `SOURCE_MLB_STATS`

Unit tests exist for MLB Stats API and calendar (`tests/test_mlb_stats_*.py`) but **no PPV integration test** verifies:

```
MiLB channel name → calendar scrape → reverse match → Event persisted → correct source
```

This gap allowed detail-fetch and schema issues (TODO 55) to go unnoticed.

## Affected files

- New or extended: `tests/ppv/test_milb_enrichment_integration.py`
- Fixtures: `tests/fixtures/mlb_stats/*.json` (already present)
- `services/ppv/enrichment.py`, `services/ppv/persistence.py`

## Proposed solution

1. Create test channel with realistic MiLB PPV name matching fixture schedule.
2. Mock HTTP for MLB Stats calendar only; run real extractor + reverse matcher + persistence.
3. Assert `Event.source == Event.SOURCE_MLB_STATS`, link created, channel status `matched`.
4. Optionally assert detail queue behavior (skip or MLB fetch).

## Acceptance criteria

- [x] One integration test passes with recorded fixtures (no live network).
- [x] Test documents expected channel name format in docstring.

## Test plan

Self-contained.

## Dependencies

- TODO 55 (multi-source detail fetch) may extend assertions.

## Completion

- **PR:** [#20](https://github.com/klopstack/iptv-proxy-v2/pull/20) — `tests/ppv/test_milb_enrichment_integration.py` exercises extractor, calendar MiLB path (mocked MLB Stats HTTP), reverse matcher, and `persist_match`; asserts `SOURCE_MLB_STATS`, link, `matched` status, and empty TSDB detail queue.
