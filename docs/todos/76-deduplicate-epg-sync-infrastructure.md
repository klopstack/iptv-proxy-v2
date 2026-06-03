# Deduplicate EPG program persistence and sync infrastructure

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Copy-paste duplication across EPG sync infrastructure:

| Duplication | Locations |
|-------------|-----------|
| Program create/update field mapping | `services/epg/programs.py` vs `services/epg/sd_programs.py` |
| Sync lock + stale recovery | `services/sync_service.py` vs `services/epg_sync_orchestrator.py` |
| EAST/WEST tag constants | `sync_service.py` vs `services/epg/constants.py` |
| Progress tracker classes | `epg_sync_progress.py` vs `sd_lineup_sync_progress.py` |

SD program update always overwrites; XMLTV path tracks dirty fields — divergence risk on schema changes.

## Affected files

- `services/epg/programs.py`, `services/epg/sd_programs.py`
- `services/sync_service.py`, `services/epg_sync_orchestrator.py`
- `services/epg/constants.py`
- `services/epg_sync_progress.py`, `services/sd_lineup_sync_progress.py`

## Proposed solution

1. Extract `services/epg/program_persistence.py` with unified create/update
2. Generic `acquire_sync_lock(model, id, ...)` utility
3. Import `EAST_FEED_TAGS` / `WEST_FEED_TAGS` from `epg/constants.py` in sync_service
4. Base `SyncProgressTracker` parameterized by model (architecture — can phase)

## Acceptance criteria

- [ ] Single program persistence module used by both sync paths
- [ ] One sync lock helper used by account and EPG source sync
- [ ] No duplicate EAST/WEST constants

## Test plan

- Existing EPG sync tests must pass unchanged
- Add unit test for shared program persistence

## Dependencies

None for items 1–3; item 4 is optional follow-up.
