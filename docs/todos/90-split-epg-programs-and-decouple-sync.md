# Split EPG programs module and decouple sync side effects (architecture)

**Status:** ⬜ Not started  
**Priority:** P3  
**Audit:** Application-wide audit, June 2026

## Problem

Two large service modules mix concerns:

### `services/epg/programs.py` (~1135 lines)

Combines streaming XML parse, DB upsert, cleanup, query API, and XMLTV generation.

### `services/channel_query_service.py` (~786 lines)

Handles EPG ID resolution, tag loading, quality collapse, PPV visibility, health exclusion, backup exclusion, preview queries, playlist config merging, Xtream output.

### `ChannelSyncService` post-sync coupling

IPTV sync inline triggers: filter recompute, PPV re-enrichment, backup pair detection, PPV state resets — sync latency depends on unrelated subsystems.

### Legacy EPG generation

`services/epg/generation.py` documents DB-first but retains URL fetch and full XML filter paths — unclear if production still uses them.

### Preview performance

`ChannelQueryService.preview_channels_*` loads all channels, filters in Python, then slices — O(n) per preview on large accounts.

## Affected files

- `services/epg/programs.py`, `services/epg/generation.py`
- `services/channel_query_service.py`
- `services/sync_service.py`

## Proposed solution

**programs.py split:**
- `epg/programs/sync.py`, `repository.py`, `xmltv_export.py`

**CQS split (incremental):**
- `ChannelTagLoader`, `ChannelVisibilityPipeline`, thin facade

**Sync decoupling:**
- Post-sync event queue: filter compute, PPV requeue, backup detect

**Legacy audit:**
- Grep call sites for `fetch_epg_from_source`; deprecate or gate

## Acceptance criteria

- [ ] Each new module < 400 lines
- [ ] No behavior change in EPG sync and preview tests
- [ ] Post-sync hooks testable with no-op listener

## Test plan

- Full EPG and CQS test suites after each extraction phase

## Dependencies

- TODO 76 (program persistence dedup first)
- See `docs/architecture/epg-service-architecture.md`
