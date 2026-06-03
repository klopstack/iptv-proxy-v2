# Split EPG programs module and decouple sync side effects (architecture)

**Status:** ✅ Done  
**Priority:** P3  
**Audit:** Application-wide audit, June 2026

## Acceptance criteria

- [x] Each new module < 400 lines
- [x] No behavior change in EPG sync and preview tests
- [x] Post-sync hooks testable with no-op listener

## Implementation notes (PR #26)

- Split `programs.py` into `services/epg/programs/{sync,repository,xmltv_export}.py` with backward-compatible re-exports
- Added `services/channel_sync_post_hooks.py`; `ChannelSyncService` delegates post-sync work to hook registry
- `fetch_epg_from_source` has no production call sites; marked deprecated in docstring
- CQS split deferred to follow-up

## Dependencies

- TODO 76 (merged in PR #23)
- See `docs/architecture/epg-service-architecture.md`
