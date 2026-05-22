# TODO 03: Fix Playlist Config Preview (Live API → Database)

**Priority:** P0  
**Status:** ✅ Complete  
**Estimated scope:** Medium (1 route function, tests)

---

## Problem

`GET /api/playlist-configs/<config_id>/preview` still fetches channels from the **live IPTV provider API** instead of the synced database:

```python
# routes/playlists.py:187-215
service = IPTVService(account.server, account.username, account.password, ...)
streams = cache_service.get_cached_streams(account.id)
if not streams:
    streams = service.get_live_streams()
...
tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, tag_rules)
```

Meanwhile:
- M3U generation from the same config uses `ChannelQueryService.channels_for_playlist_config` (database-first)
- Account preview (`/api/accounts/<id>/preview`) is database-first
- The `/test` UI shows a "Database" vs "API" badge — this endpoint always behaves like API mode

**Impact:** Playlist config preview in the UI can show channels, names, and tags that differ from the actual generated M3U. Requires network access to provider. Ignores filters, PPV visibility, and sync state.

---

## Goal

Replace live IPTV fetching with `ChannelQueryService.channels_for_playlist_config`, matching M3U generation logic.

---

## Proposed solution

### Rewrite `preview_playlist_config`

```python
@playlists_bp.route("/api/playlist-configs/<int:config_id>/preview", methods=["GET"])
def preview_playlist_config(config_id):
    config = PlaylistConfig.query.get_or_404(config_id)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    # Verify synced accounts (same check as _generate_playlist_from_config)
    include_accounts = json.loads(config.include_accounts) if config.include_accounts else []
    ...
    # Return 503 if any account unsynced

    channels = ChannelQueryService.channels_for_playlist_config(
        config,
        apply_filters=True,
        apply_ppv_visibility=True,
    )

    # Build response from Channel ORM objects (not live stream dicts)
    # Load tags via ChannelQueryService._load_tag_names_for_channels or existing batch query

    # Paginate
    total = len(channels)
    paginated = channels[offset : offset + limit]
    ...
```

### Response shape

Preserve existing JSON fields expected by consumers:

```json
{
  "total": 100,
  "offset": 0,
  "limit": 50,
  "showing": 50,
  "channels": [
    {
      "account_id": 1,
      "account_name": "...",
      "stream_id": "123",
      "original_name": "...",
      "cleaned_name": "...",
      "category": "...",
      "tags": ["US", "HD"],
      "icon": "..."
    }
  ],
  "has_more": true
}
```

Map from `Channel` model:
- `original_name` → `channel.name`
- `cleaned_name` → `channel.cleaned_name or channel.name`
- `category` → `channel.category.cleaned_name or channel.category.category_name`
- `icon` → proxied via `ImageCacheService` (optional, match account preview behavior)

### Remove dependencies

After rewrite, this function should no longer need:
- `IPTVService` (for this endpoint)
- `cache_service.get_cached_streams` / `get_cached_categories`
- `TagService.extract_tags` (tags come from DB `ChannelTag` records)

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | Rewrite `preview_playlist_config` |
| `tests/test_playlists_routes.py` | Update mocks — no longer patch `IPTVService` |
| `tests/test_coverage_boost.py` | Update `TestPlaylistPreviewExtended` if it mocks IPTV |

---

## Acceptance criteria

- [x] Preview does not call `IPTVService.get_live_streams`
- [x] Preview returns 503 when account not synced (consistent with M3U)
- [x] Preview channel list matches M3U from same config (same count, same stream_ids)
- [x] Tag include/exclude rules on config respected
- [x] PPV visibility respected
- [x] Pagination (`limit`, `offset`) still works
- [x] Existing tests updated and passing

---

## Test plan

```bash
venv/bin/pytest tests/test_playlists_routes.py -v -k preview --no-cov
```

Replace tests that mock `IPTVService` with tests that seed `Channel` + `ChannelTag` in DB.

Example test:
1. Create config with `include_tags: ["HD"]`
2. Seed two channels — one with HD tag, one without
3. Preview returns only HD channel

---

## Dependencies

- Benefits from TODO 04 (tag ID detection) if configs store tag IDs
- Related to TODO 02 but separate endpoint

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Rewrote preview to use ChannelQueryService; removed IPTVService/cache/TagService deps from endpoint |
