# TODO 17: Route Preview Endpoints Through ChannelQueryService Entry Points

**Priority:** P1  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (2 route files + small CQS API)

---

## Problem

TODO 02 added PPV visibility to preview endpoints, but previews still **reimplement** channel selection instead of calling `ChannelQueryService` entry points:

| Endpoint | Current wiring | Calls `channels_for_account` / `channels_for_playlist_config`? |
|----------|----------------|------------------------------------------------------------------|
| `GET /api/accounts/<id>/preview` | `base_query` → `FilterService` → `apply_ppv_visibility_to_channels` | ❌ |
| `GET /api/channels/preview` | SQL query → per-account `FilterService` → `apply_ppv_visibility_to_channels` | ❌ |

M3U, EPG, Xtream, and config preview all call:

```python
ChannelQueryService.channels_for_account(...)
# or
ChannelQueryService.channels_for_playlist_config(...)
```

Preview calls the **constituent steps inline**. Behavior matches today (guarded by TODO 08 parity tests when no extra filters), but any future change to `channels_for_account` (ordering, edge cases, new rules) must be manually replicated in preview routes.

---

## Goal

Preview endpoints delegate playlist-equivalent selection to `ChannelQueryService`. Preview-only UX filters (search, category, tag query params) narrow the candidate set **before** CQS runs, or intersect with CQS output afterward.

---

## Proposed solution

### Step 1: Add a CQS helper for pre-filtered candidates

```python
@staticmethod
def channels_for_account_candidates(
    account_id: int,
    candidates: List[Channel],
    *,
    apply_filters: bool = True,
    apply_ppv_visibility: bool = True,
) -> List[Channel]:
    """Apply account selection rules to an already-narrowed channel list."""
    if apply_filters:
        candidates = FilterService.apply_filters_to_channels(candidates, account_id)
    if apply_ppv_visibility:
        candidates = ChannelQueryService.apply_ppv_visibility_to_channels(candidates)
    return candidates
```

Optional: multi-account variant for `/api/channels/preview`.

### Step 2: Refactor `/api/accounts/<id>/preview`

```python
candidate_channels = base_query.all()  # search/category/tag UX filters already applied
filtered_channels = ChannelQueryService.channels_for_account_candidates(
    account_id,
    candidate_channels,
)
# pagination + JSON shaping unchanged
```

Replace both collapse and non-collapse branches — collapse runs **after** CQS selection (same order as M3U today).

### Step 3: Refactor `/api/channels/preview`

Group by account, call `channels_for_account_candidates` per group (or full `channels_for_account` when `account_id` is set and no extra filters).

---

## Dependencies

- **After:** TODO 08 (parity tests exist to catch regressions)
- **Before / parallel with:** TODO 10 (collapse dedup — preview collapse can migrate to shared helper in either order)

---

## Files to modify

| File | Changes |
|------|---------|
| `services/channel_query_service.py` | Add `channels_for_account_candidates` (and optional multi-account helper) |
| `routes/accounts.py` | `preview_account_playlist` — use CQS helper |
| `routes/api.py` | `preview_channels` — use CQS helper |
| `tests/test_channel_query_service.py` | Unit tests for candidate helper |
| `tests/test_channel_output_parity.py` | Extend preview parity if needed |

---

## Acceptance criteria

- [ ] Preview routes contain no direct `FilterService.apply_filters_to_channels` + `apply_ppv_visibility_to_channels` pairs
- [ ] With no search/category/tag params, preview channel set still matches M3U (TODO 08 tests pass)
- [ ] With search/category/tag params, preview returns a **subset** of M3U-equivalent output
- [ ] `collapse_duplicates=true` on preview still works
- [ ] PPV hide_all / hide_inactive scenarios still pass

---

## Test plan

```bash
venv/bin/pytest tests/test_channel_output_parity.py tests/test_accounts_routes.py tests/test_api_routes.py -v -k preview --no-cov
venv/bin/pytest tests/test_channel_query_service.py -v --no-cov
```

---

## Out of scope

- Collapse pipeline deduplication (TODO 10)
- Config playlist preview (already uses `channels_for_playlist_config` — TODO 03)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | Identified post-TODO 08: behavioral parity exists, structural unification does not |
