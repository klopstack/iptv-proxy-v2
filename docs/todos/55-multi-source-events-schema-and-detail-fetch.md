# Multi-source events: schema audit and detail fetch branching

**Status:** ✅ Done (PR #13)  
**Priority:** P0  
**Audit:** PPV audit, June 2026

## Problem

Two related issues block correct MiLB / multi-source PPV operation:

### 1. `external_id` uniqueness constraint

`Event.external_id` has `unique=True` on the column alone:

```python
external_id = db.Column(db.String(50), nullable=False, unique=True, index=True)
```

But `persistence.create_or_update_event` filters by `(external_id, source)`. If TheSportsDB and MLB Stats API ever share numeric IDs, inserts will fail or silently conflict. The column comment still says "TheSportsDB event ID" despite `SOURCE_MLB_STATS` support.

Migration `2026_01_02_add_event_tables.py` created `external_id VARCHAR(50) NOT NULL UNIQUE` with no composite index on `(external_id, source)`.

### 2. Detail fetch hard-coded to TheSportsDB

`_fetch_event_details` always queries `Event.SOURCE_THESPORTSDB` and calls `thesportsdb.get_event_by_id`. MiLB events matched via MLB Stats calendar are never refreshed; the detail worker may log "Event not found" when queued by numeric ID from a different source.

## Affected files

- `models/ppv.py` — `Event.external_id`, `source`, docstrings
- `migrations/` — new migration for composite unique constraint
- `services/ppv/enrichment.py` — `_fetch_event_details`, detail queue population
- `services/ppv/persistence.py` — create/update lookup
- `services/mlb_stats_api.py` — potential detail source

## Proposed solution

1. **Schema audit:** Confirm whether ID collisions exist in production data.
2. **Migration:** Drop single-column unique on `external_id`; add `UniqueConstraint('external_id', 'source')`.
3. **Detail fetch:** Branch on `event.source`:
   - `SOURCE_THESPORTSDB` → existing API path
   - `SOURCE_MLB_STATS` → MLB Stats game endpoint or skip detail queue with `data_completeness='basic'` by design
4. **Queue:** When enqueueing detail fetches, pass `(external_id, source)` tuple, not bare ID string.
5. Update model docstrings and architecture doc.

## Acceptance criteria

- [x] Two events with same `external_id` but different `source` can coexist.
- [x] MiLB-matched events do not produce spurious "not found" warnings in detail loop.
- [x] Detail queue respects source-specific fetch or explicit skip.
- [x] Migration is idempotent and tested against existing DB fixtures.

## Completion

- PR #13 — https://github.com/klopstack/iptv-proxy-v2/pull/13

## Test plan

- Schema migration test with conflicting IDs across sources.
- Integration test: MiLB channel → calendar match → `Event.source == mlb_stats_api` → detail worker behavior (TODO 62).

## Dependencies

- See `docs/architecture/ppv-multi-source-events.md`.
