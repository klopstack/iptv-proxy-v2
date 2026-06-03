# Channel Visibility and the `is_visible` Column

**Audit:** Application-wide audit, June 2026  
**Status:** Draft for review

## Two visibility models

The codebase uses **two different concepts** of channel visibility:

| Model | Mechanism | Used by |
|-------|-----------|---------|
| **Live filters** | `FilterService.apply_filters_to_channels()` evaluates rules at read time | `ChannelQueryService`, M3U, EPG output, previews |
| **Cached `is_visible`** | Boolean column updated during IPTV sync / filter recompute | Admin stats, EPG auto-matching (**bug**), some legacy paths |

## The bug (TODO 70)

EPG match-rules orchestrator calls `apply_filters_to_channels` but then filters on `ch.is_visible`:

```python
FilterService.apply_filters_to_channels(all_channels, account_id)
channels = [ch for ch in all_channels if ch.is_visible]  # WRONG
```

The return value is discarded. After a filter rule change without sync, `is_visible` is stale.

## Correct pattern

```python
channels = FilterService.apply_filters_to_channels(all_channels, account_id)
```

This is what `ChannelQueryService` does for playlist/EPG output.

## Who mutates `is_visible`?

- `ChannelSyncService` during filter recompute after sync
- `ChannelHealthService` may mutate visibility
- Admin APIs may display cached counts

## Long-term options

| Option | Description |
|--------|-------------|
| **A. Rename column** | `filter_cache_visible` — signals admin-only cache |
| **B. Remove column** | Compute on demand for admin; materialized view if needed |
| **C. Keep + document** | Strict rule: never use for matching/output; admin only |

**Recommendation:** Fix bug immediately (TODO 70); plan Option A or B in next major version.

## Decision log

| Question | Decision |
|----------|----------|
| EPG matching uses live filters? | **Yes** (after TODO 70) |
| Admin channel counts use cache or live? | Document in TODO 20 (completed) — verify still accurate |
| Deprecate column? | _TBD_ |

## Related TODOs

- **70** — fix EPG matching bug
- **27** (completed) — clarify semantics
- **90** — CQS visibility pipeline extraction
