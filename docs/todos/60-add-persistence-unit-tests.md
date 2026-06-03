# Add unit tests for PPV persistence layer

**Status:** 🔄 In review (PR #19)  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

`services/ppv/persistence.py` is on the critical path for all PPV matches but has **no dedicated unit tests**. Behavior is only exercised indirectly via heavily mocked enrichment tests.

Untested logic includes:

- Age rejection (`MAX_EVENT_AGE_DAYS`, `MAX_EVENT_FUTURE_DAYS`)
- `SOURCE_MLB_STATS` source normalization (`mlb_stats_api` → model constant)
- Create vs update branching on `(external_id, source)`
- `link_channel_to_event` confidence upsert
- `persist_match` status transitions (`no_match` on validation failure)
- `sync_enrichment_status_from_links` bulk update
- `clear_event_links_for_channels`

## Affected files

- New: `tests/ppv/test_persistence.py`
- `services/ppv/persistence.py`

## Proposed solution

Add table-driven tests with in-memory DB fixtures:

1. Old event rejected; future event rejected; valid event created.
2. Update existing event fields without duplicate row.
3. MiLB calendar event gets `source=mlb_stats_api`.
4. Link confidence upgrade when higher-confidence match arrives.
5. `persist_match` sets channel status correctly on failure/success.

## Acceptance criteria

- [x] `tests/ppv/test_persistence.py` covers all public functions in persistence module.
- [x] Tests run without mocking enrichment or reverse matcher.

## Completion

- PR #19 — https://github.com/klopstack/iptv-proxy-v2/pull/19

## Test plan

Self-contained — this document **is** the test plan.

## Dependencies

- Supports TODO 54 (persist_match consolidation).
