# TODO 27: Clarify `is_visible` Semantics and Close Filter Staleness Gaps

**Priority:** P1  
**Status:** ✅ Complete  
**Estimated scope:** Medium (design decision + tests + UI labels)

---

## Problem

Channel visibility uses **two overlapping mechanisms** that confuse admin UI, docs, and tests.

### Mechanism 1: Cached `Channel.is_visible` column

`FilterService.compute_visibility_for_account` writes `is_visible` based on enabled filters. Filter CRUD routes (`routes/filters.py`) trigger recompute on create/update/delete.

### Mechanism 2: Live filter application

`FilterService.apply_filters_to_channels` (used by `ChannelQueryService` for playlists) does:

```python
# Step 1: drop is_visible=False
channels = [ch for ch in channels if ch.is_visible]
# Step 2: re-apply enabled filters live
```

The docstring claims `is_visible` is for **"explicit channel hiding, separate from filters"** — but `compute_visibility_for_account` sets it **from filters**. The comment is wrong.

### Staleness edge case

If `is_visible=False` in DB but filters were relaxed **without** recompute (direct DB edit, failed recompute, or code path that skips `compute_visibility_for_account`):

- Step 1 excludes the channel **before** live filters can include it
- Playlist output stays wrong until manual `POST /api/accounts/<id>/recompute-visibility`

Filter CRUD already recomputes — gap is **undocumented** and **untested** for bypass paths.

### UI mismatch

| Surface | Semantics used |
|---------|----------------|
| M3U / EPG / Xtream / preview | CQS: live filters + PPV |
| `templates/channel_health.html` | DB `is_visible` badge "Hidden" |
| `services/channel_health_service.py` | SQL `Channel.is_visible == True` for counts |
| Preview JSON `is_visible` field | Always `true` for CQS-filtered results (misleading) |

TODO 20 aligned categories/stats with CQS; channel health UI still shows filter-cache semantics.

### Duplicate PPV placeholder patterns

`FilterService` defines `PPV_PLACEHOLDER_PATTERNS` (~40 lines) separately from `services/epg/` constants — drift risk.

---

## Goal

Pick a single **documented model** for `is_visible`, fix misleading comments, align or relabel admin UI, and add regression tests for filter→playlist consistency.

---

## Proposed solution

### Step 1: Product decision (document in this todo when chosen)

**Chosen: Option A — Cache is optimization only.** Playlist/EPG/Xtream/preview paths evaluate filters live via `FilterService.apply_filters_to_channels` and do not read the cached `is_visible` column. The column remains written by `compute_visibility_for_account` for admin/index queries. Health auto-disable excludes channels via `ChannelHealthStatus.auto_disabled_at` in `ChannelQueryService`.

### Step 2: Fix docstrings

Update `FilterService.apply_filters_to_channels` and `compute_visibility_for_account` to describe chosen model.

### Step 3: Channel health UI

If Option C:
- Badge: "Filter-hidden" vs "PPV-hidden" vs "Down"
- API returns `playlist_visible: bool` from CQS helper

If Option A:
- Health listing uses CQS for default view; optional `?show_filter_hidden=true`

### Step 4: Consolidate PPV placeholder patterns

Import from single source (`services/epg/constants.py` or `services/ppv/`).

### Step 5: Add regression tests

In `tests/test_filter_visibility.py` (after TODO 25 rename):

```python
def test_playlist_reflects_filter_change_without_manual_recompute(client, ...):
    # Create blacklist filter via API → assert M3U channel count drops
    # Delete filter via API → assert channel reappears in M3U
    # (proves filter CRUD + playlist path stay in sync)

def test_stale_is_visible_blocks_playlist_if_cache_gate_kept(...):
    # Only if Option B — document expected manual recompute
```

---

## Dependencies

- **After:** TODO 20 (admin CQS alignment baseline)
- **Related:** TODO 25 (rename `test_phase2_filter_visibility.py`)
- **Blocks:** TODO 34 simplification of FilterService

---

## Files to modify

| File | Changes |
|------|---------|
| `services/filter_service.py` | Fix semantics per chosen option |
| `services/channel_query_service.py` | Optional playlist-visible helper for health API |
| `services/channel_health_service.py` | Align queries or add CQS path |
| `routes/channel_health.py` | API field names |
| `templates/channel_health.html` | Label updates |
| `routes/api.py`, `routes/accounts.py` | Preview JSON field naming |
| `tests/test_filter_visibility.py` | New regression tests |

---

## Acceptance criteria

- [x] Documented decision on `is_visible` vs live filters (in DEVELOPER_GUIDE)
- [x] No contradictory docstrings in FilterService
- [x] Filter create/delete changes M3U output without manual recompute (integration test)
- [x] Channel health UI does not label DB `is_visible=False` as "playlist hidden" unless accurate
- [x] PPV placeholder patterns defined in one module

---

## Test plan

```bash
venv/bin/pytest tests/test_filter_visibility.py tests/test_channel_output_parity.py tests/test_channel_health.py -v --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Option A: live filters for client output; `is_visible` is admin cache only. Renamed `test_phase2_filter_visibility.py` → `test_filter_visibility.py`. Channel health UI/API use `playlist_visible` / `filter_hidden` / `admin_disabled`. |
