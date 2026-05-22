# TODO 10: Deduplicate Channel Processing Logic

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Medium–Large (refactor)

---

## Problem

The same patterns are copy-pasted across multiple files:

### Tag loading (batch query, 500 chunk size)

- `routes/playlists.py` — `generate_playlist`, `proxy_epg`
- `routes/xtream.py` — `collapse_duplicate_channels`
- `routes/accounts.py` — `preview_account_playlist`

Partially centralized in `ChannelQueryService._load_tag_names_for_channels` / `_load_tag_ids_for_channels` but routes don't use it consistently.

### Duplicate collapse pipeline

Build dict → `QualityService.collapse_duplicates` → extract channels:

- `routes/playlists.py` (account M3U, account EPG, config M3U)
- `routes/xtream.py` (with extra health/EPG mapping data)

---

## Goal

Single implementation for tag loading and duplicate collapse preparation, used by all routes.

---

## Proposed solution

### Extend `ChannelQueryService` or add `services/channel_list_helpers.py`

```python
def load_tags_for_account_channels(
    account_id: int,
    channels: List[Channel],
    *,
    by_id: bool = False,
) -> dict:
    """Delegate to _load_tag_names_for_channels or _load_tag_ids_for_channels."""

def prepare_collapse_input(
    channels: List[Channel],
    tags_map: dict,
    *,
    include_health: bool = False,
    include_epg_mappings: bool = False,
) -> List[dict]:
    """Build channel dicts for QualityService.collapse_duplicates."""

def collapse_channels(
    channels: List[Channel],
    account_id: int | None = None,
    *,
    include_health: bool = False,
    include_epg_mappings: bool = False,
) -> List[Channel]:
    """Load tags, build dicts, collapse, return Channel list."""
```

Keep Xtream-specific health/EPG mapping as optional flags rather than separate copy.

### Migration order

1. Replace tag loading in `routes/playlists.py` with CQS helpers
2. Replace tag loading in `routes/accounts.py` preview
3. Refactor `routes/xtream.py` collapse to use shared helper
4. Delete duplicated batch loops

---

## Dependencies

Best done **after** TODO 01–03 so route logic is stable before extraction.

---

## Files to modify

| File | Changes |
|------|---------|
| `services/channel_query_service.py` | Add public helper methods (or new helper module) |
| `routes/playlists.py` | Use helpers |
| `routes/xtream.py` | Use helpers |
| `routes/accounts.py` | Use helpers |
| `tests/test_channel_query_service.py` | Tests for new helpers |

---

## Acceptance criteria

- [ ] No duplicated tag batch-loading loops in route files
- [ ] Collapse behavior unchanged (existing collapse tests pass)
- [ ] Xtream collapse still includes health/EPG data when enabled
- [ ] Line count reduction in `routes/playlists.py` (target: −80 lines minimum)

---

## Test plan

```bash
venv/bin/pytest tests/test_playlists_routes.py tests/test_xtream.py tests/test_channel_query_service.py -v --no-cov
```

No new behavior — regression tests only.

---

## Related todos

| TODO | Relationship |
|------|--------------|
| 17 | Preview routes should consume shared collapse helper after extraction |
| 18 | Config EPG collapse should use shared helper (avoid third copy-paste) |
| 19 | M3U formatting is separate from selection/collapse (different concern) |

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
