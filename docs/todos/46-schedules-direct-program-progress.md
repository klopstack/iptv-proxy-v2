# TODO 46: Schedules Direct Granular Program Sync Progress

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Medium  

**Related:** [45-ppv-events-epg-progress-callbacks.md](./45-ppv-events-epg-progress-callbacks.md), `services/epg/programs.py` streaming progress pattern

---

## Problem

`sync_schedules_direct_source()` reports progress at phase boundaries only:

- `PHASE_FETCHING` — connect / authenticate
- `PHASE_CHANNELS` — `sync_sd_channels_to_epg`
- `PHASE_PROGRAMS` — single message before `sync_sd_programs_for_source()`

`sync_sd_programs_for_source()` does not accept a `progress_callback`. Long SD programme downloads (many stations × 14 days) show a static “Syncing Schedules Direct programmes” message with no `programmes_parsed` counter unlike XMLTV `sync_programs_for_source()`.

Large SD lineups suffer the same UX issue as monolithic XMLTV syncs before streaming progress was added.

---

## Goal

SD program sync exposes incremental counts to `EpgSyncProgress` (programmes parsed, channels processed) consistent with XMLTV path.

---

## Proposed solution

### 1. Extend `sync_sd_programs_for_source`

Add optional parameter:

```python
progress_callback: Optional[Callable[..., None]] = None
```

Invoke every N programmes or stations (e.g. every 1000 programmes or per station batch), matching `programs.py` `_report_progress` shape:

```python
progress_callback(
    programmes_parsed=...,
    channels_processed=...,
    message="...",
)
```

### 2. Wire in `EpgSyncService.sync_schedules_direct_source`

```python
def program_progress(**counts):
    if progress:
        progress(PHASE_PROGRAMS, **counts)

program_stats = sync_sd_programs_for_source(
    ...,
    progress_callback=program_progress,
)
```

### 3. Performance

- Callback should not commit DB; only update progress JSON (orchestrator’s `EpgSyncProgress.set_phase` commits).
- Throttle callbacks (e.g. max once per second) for huge lineups.

---

## Affected files

| File | Change |
|------|--------|
| `services/epg/sd_programs.py` | `progress_callback` + reporting loops |
| `services/epg_sync_service.py` | Wire callback |
| `tests/test_sd_programs.py` | Assert callback invocations |
| `tests/test_epg_sync_service.py` | SD progress integration test |

---

## Acceptance criteria

- [ ] During SD program sync, `sync_progress` JSON gains increasing `programmes_parsed` (or equivalent).
- [ ] Settings UI programme column updates for SD sources.
- [ ] No significant sync duration regression (<1% overhead).
- [ ] Existing SD program tests pass.

---

## Test plan

```bash
.venv/bin/pytest tests/test_sd_programs.py tests/test_epg_sync_service.py -q --no-cov
```

Mock SD client; assert `progress_callback` called with monotonic counts.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | |
| PR / commit | |
