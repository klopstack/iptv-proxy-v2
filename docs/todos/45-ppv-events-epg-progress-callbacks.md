# TODO 45: PPV Events EPG Source Progress Callbacks

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Small  

**Related:** [46-schedules-direct-program-progress.md](./46-schedules-direct-program-progress.md)

---

## Problem

`EpgSyncService.sync_source()` passes `progress` to all types except `ppv_events`:

```python
elif source.source_type == "ppv_events":
    return EpgSyncService.sync_ppv_events_source(source)  # no progress= kwarg
```

`sync_ppv_events_source()` has no `progress` parameter and never calls `PHASE_FETCHING` / `PHASE_CHANNELS` / `PHASE_PROGRAMS`.

Orchestrator + settings UI will show `queued` → immediate `complete` or `error` for PPV sources with no intermediate visibility during `PPVEpgService.sync_ppv_events_to_epg_channels()` or XMLTV generation.

---

## Goal

PPV event sources report the same phase progression as other types where work exists.

---

## Proposed solution

### 1. Signature alignment

```python
def sync_ppv_events_source(source: EpgSource, progress: ProgressCallback = None) -> Tuple[bool, str, Dict]:
```

### 2. Phase mapping

| Step | Phase | Message example |
|------|-------|-----------------|
| Sync events → channels | `PHASE_CHANNELS` | Syncing PPV events to channels |
| Generate XMLTV | `PHASE_PROGRAMS` | Generating PPV XMLTV |
| Cache write | (merge) | Caching guide data |

### 3. Dispatcher

```python
return EpgSyncService.sync_ppv_events_source(source, progress=progress)
```

### 4. Optional counts

If `PPVEpgService` can report event/channel counts mid-flight, pass via `progress(PHASE_PROGRAMS, programmes_parsed=N)`.

---

## Affected files

| File | Change |
|------|--------|
| `services/epg_sync_service.py` | `sync_ppv_events_source`, dispatcher |
| `services/ppv/epg.py` | Optional hooks for counts (if needed) |
| `tests/test_epg_sync_service.py` | Progress test for ppv_events |
| `tests/ppv/test_epg.py` | If route-level sync tested |

---

## Acceptance criteria

- [ ] PPV source sync invokes progress at least twice (channels + programs or equivalent).
- [ ] Settings UI shows non-idle phases during PPV sync.
- [ ] Failure still sets `PHASE_ERROR` via orchestrator.
- [ ] No behavior change to PPV XML output.

---

## Test plan

```python
@patch("services.ppv.epg.PPVEpgService.sync_ppv_events_to_epg_channels", return_value=(1, 0))
@patch("services.ppv.epg.PPVEpgService.generate_ppv_epg_xmltv", return_value=b"<tv/>")
def test_ppv_events_reports_progress(...):
    phases = []
    EpgSyncService.sync_ppv_events_source(source, progress=lambda p, **kw: phases.append(p))
    assert PHASE_CHANNELS in phases
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | |
| PR / commit | |
