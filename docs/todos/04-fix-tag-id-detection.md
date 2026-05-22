# TODO 04: Fix Tag ID vs Name Detection in ChannelQueryService

**Priority:** P0  
**Status:** ⬜ Not started  
**Estimated scope:** Small (1 function, few tests)

---

## Problem

In `ChannelQueryService.channels_for_playlist_config`, tag filter mode is determined by:

```python
# services/channel_query_service.py:176
use_ids = include_tags and isinstance(include_tags[0], int)
```

This fails when:
- `include_tags` is empty but `exclude_tags` contains integer tag IDs
- `include_tags` is empty and `exclude_tags` contains string tag names (works by accident)
- Mixed storage formats in existing playlist configs

In the empty-include + ID-exclude case, code falls through to name-based filtering, and numeric exclude IDs are compared as tag **names** — exclusions silently do nothing.

---

## Goal

Correctly detect whether playlist config tags are stored as IDs or names, and apply the appropriate filter path for both include and exclude lists.

---

## Proposed solution

### Detection helper

```python
@staticmethod
def _tags_are_ids(include_tags: list, exclude_tags: list) -> bool:
    """Return True if config tags are stored as numeric IDs."""
    sample = (include_tags or exclude_tags or [])
    if not sample:
        return False
    return isinstance(sample[0], int)
```

Or more defensive — check all elements:

```python
all_tags = (include_tags or []) + (exclude_tags or [])
if not all_tags:
    return False
return all(isinstance(t, int) for t in all_tags)
```

**Decision needed:** If a config has mixed int/str (legacy bad data), prefer IDs if any int present, or reject/log warning. Document chosen behavior.

### Update filter branch

```python
use_ids = ChannelQueryService._tags_are_ids(include_tags, exclude_tags)
if use_ids:
    tags_map = ChannelQueryService._load_tag_ids_for_channels(channels)
    ...
else:
    tags_map = ChannelQueryService._load_tag_names_for_channels(channels)
    ...
```

### JSON parsing note

After `json.loads`, tag IDs may arrive as ints. Tag names are strings. Ensure `PlaylistConfigCreateSchema` and UI consistently store one format — check `schemas.py` and playlist config UI if needed.

---

## Files to modify

| File | Changes |
|------|---------|
| `services/channel_query_service.py` | Fix detection logic, add helper |
| `tests/test_channel_query_service.py` | Add exclude-only-ID test cases |

---

## Acceptance criteria

- [ ] Config with `exclude_tags: [5]` (ID) and empty `include_tags` correctly excludes channels with tag ID 5
- [ ] Config with `exclude_tags: ["PPV"]` (name) still works
- [ ] Config with `include_tags: [1, 2]` still uses ID path
- [ ] Empty include and empty exclude → no tag filtering (all channels pass tag stage)
- [ ] No regression in existing tag filter tests

---

## Test plan

Add to `tests/test_channel_query_service.py`:

```python
def test_playlist_config_exclude_tag_ids_only(app):
    """exclude_tags as IDs works when include_tags is empty."""
    ...

def test_playlist_config_exclude_tag_names_only(app):
    """exclude_tags as names works when include_tags is empty."""
    ...
```

```bash
venv/bin/pytest tests/test_channel_query_service.py -v --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
