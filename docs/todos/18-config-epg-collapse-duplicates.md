# TODO 18: Add Config EPG `collapse_duplicates` Parity

**Priority:** P1  
**Status:** ⬜ Not started  
**Estimated scope:** Small (1 route function + tests)

---

## Problem

Account outputs support `?collapse_duplicates=true` consistently:

| Endpoint | Supports `collapse_duplicates`? |
|----------|--------------------------------|
| `GET /playlist/<account_id>.m3u` | ✅ |
| `GET /epg/<account_id>.xml` | ✅ |
| `GET /playlist/config/<id>.m3u` | ✅ |
| `GET /epg/config/<id>.xml` | ❌ |

Config EPG (`_generate_epg_from_config`) calls `ChannelQueryService.channels_for_playlist_config` but never applies duplicate collapse, even when the matching config M3U would collapse duplicates.

Users expecting EPG to mirror config M3U channel count after collapse will see **more** `<channel>` elements in config EPG than `#EXTINF` lines in config M3U.

---

## Goal

`GET /epg/config/<id>.xml?collapse_duplicates=true` returns guide data for the same collapsed channel set as `GET /playlist/config/<id>.m3u?collapse_duplicates=true`.

---

## Proposed solution

Mirror account EPG logic in `_generate_epg_from_config`:

```python
collapse_duplicates = request.args.get("collapse_duplicates", "").lower() == "true"

channels = ChannelQueryService.channels_for_playlist_config(
    config,
    apply_filters=True,
    apply_ppv_visibility=True,
)

if collapse_duplicates:
    channels = collapse_channels_for_playlist_config(channels, config)  # TODO 10 helper
```

Prefer implementing collapse via the shared helper from TODO 10 if that lands first; otherwise copy the existing config M3U collapse block once and replace when TODO 10 completes.

Update route docstrings and any UI copy that describes config EPG query params.

---

## Dependencies

- **After:** TODO 01 (config EPG already uses CQS)
- **Related:** TODO 10 (shared collapse helper avoids a third copy-paste)
- **Extend:** TODO 08 parity tests with a config collapse scenario

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | `_generate_epg_from_config` — add collapse param + logic |
| `tests/test_channel_output_parity.py` | Config M3U vs config EPG collapse scenario |
| `tests/test_playlist_generation.py` | Config EPG collapse smoke test (optional) |

---

## Acceptance criteria

- [ ] `GET /epg/config/<id>.xml?collapse_duplicates=true` channel count matches config M3U with same param
- [ ] Without param, behavior unchanged (no collapse)
- [ ] `tvg-id` / XMLTV `<channel id>` sets match between config M3U and config EPG after collapse
- [ ] Existing config EPG tests pass

---

## Test plan

```bash
venv/bin/pytest tests/test_channel_output_parity.py tests/test_playlist_generation.py -v -k "config and epg" --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
