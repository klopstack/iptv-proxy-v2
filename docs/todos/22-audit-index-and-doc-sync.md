# TODO 22: Sync Audit Index and Stale Documentation

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Small (docs only, no behavior changes)

---

## Problem

The first post-restructuring audit (TODOs 01–21) is largely complete, but several **index entries and docs still describe pre-restructuring behavior**. This creates false work items and misleads contributors about what still needs fixing.

### Stale TODO index

| Document | README status | Reality |
|----------|---------------|---------|
| `18-config-epg-collapse-duplicates.md` | ⬜ Not started | **Implemented** — `_generate_epg_from_config` reads `collapse_duplicates` and calls `ChannelQueryService.collapse_config_channels_if_requested` |
| Parity test | — | `tests/test_channel_output_parity.py::test_config_m3u_epg_same_stream_ids_after_collapse` passes |

### Misleading inline documentation

| Location | Issue |
|----------|-------|
| `routes/playlists.py` `_generate_playlist_from_config` docstring | Still references pre-computed `is_visible` / inline tag SQL; actual path uses `ChannelQueryService` |
| `docs/DEVELOPER_GUIDE.md` | Documents `account_xml_cache` parameter on EPG generation as if it were active |
| `services/epg/generation.py` | Parameter kept but marked deprecated — docs should say "removed in vNext" not "optional cache" |
| `docs/ARCHITECTURE.md` | Line counts and service inventory may be stale after package split |

### Completed work not reflected in audit narrative

TODO 21 removed `_matches_tag_filter` and deduplicated parity tests. The README dependency graph still lists 18 as blocking on 10 even though both are done.

---

## Goal

Make `docs/todos/README.md` and related docs **accurately reflect implemented behavior** so the second-pass audit (TODOs 22–34) starts from truth.

---

## Proposed solution

### Step 1: Mark TODO 18 complete

Update `docs/todos/18-config-epg-collapse-duplicates.md`:
- Status → ✅ Done
- Check all acceptance criteria
- Add completion date and note parity test location

Update `docs/todos/README.md` status column for item 18.

### Step 2: Fix route docstrings

Update `_generate_playlist_from_config` and `_generate_epg_from_config` docstrings in `routes/playlists.py` to describe:
- `ChannelQueryService.channels_for_playlist_config`
- `apply_filters=True`, `apply_ppv_visibility=True`
- Optional `collapse_duplicates` query param

### Step 3: Update DEVELOPER_GUIDE and ARCHITECTURE

- Remove or strike through `account_xml_cache` from API examples; point to TODO 23 for removal
- Refresh ARCHITECTURE service counts / import paths (`services/epg/` package, not monolithic `epg_service.py`)
- Confirm Provider EPG "deprecated" note matches TODO 31 plan

### Step 4: Refresh README dependency graph

Remove completed edges (18, 21) from "recommended order"; add new section linking TODOs 22–34.

---

## Dependencies

- **Independent** — do first before other second-pass items
- Unblocks accurate prioritization of TODOs 23–34

---

## Files to modify

| File | Changes |
|------|---------|
| `docs/todos/README.md` | Mark 18 ✅; add section for 22–34 |
| `docs/todos/18-config-epg-collapse-duplicates.md` | Mark complete |
| `routes/playlists.py` | Fix config M3U/EPG docstrings |
| `docs/DEVELOPER_GUIDE.md` | Deprecate `account_xml_cache` in docs |
| `docs/ARCHITECTURE.md` | Refresh counts and import paths |

---

## Acceptance criteria

- [x] TODO 18 marked ✅ in index and document body with completion notes
- [x] No route docstring describes inline tag SQL or `is_visible`-only config selection
- [x] DEVELOPER_GUIDE does not present `account_xml_cache` as a supported feature
- [x] README lists second-pass todos 22–34 with correct ⬜ status

---

## Test plan

Docs-only change — verify no code regressions:

```bash
venv/bin/pytest tests/test_channel_output_parity.py -v -k "config and collapse" --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Updated `_generate_playlist_from_config` / `_generate_epg_from_config` docstrings; deprecated `account_xml_cache` in DEVELOPER_GUIDE and `services/epg/generation.py`; refreshed ARCHITECTURE service inventory; README first-pass graph marked complete and TODO 22 ✅. |
