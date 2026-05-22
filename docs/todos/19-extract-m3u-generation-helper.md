# TODO 19: Extract Shared M3U Generation Helper

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (1 helper module + 2 route functions)

---

## Problem

M3U output formatting is implemented twice with near-identical logic:

| Function | File | Differences |
|----------|------|-------------|
| `generate_playlist` | `routes/playlists.py` | Single account; `use_proxy` / direct URL from account credential |
| `_generate_playlist_from_config` | `routes/playlists.py` | Multi-account; per-channel `account_id` in stream URL; optional multi-account collapse |

Both independently:
- Build `#EXTINF` lines with `tvg-id`, `tvg-name`, `tvg-logo`, `group-title`
- Call `ChannelQueryService.epg_channel_id_for_channel`
- Proxy icons via `ImageCacheService`
- Append stream URLs (`/stream/{account_id}/{stream_id}.ts` vs direct provider URL)

TODO 10 covers **selection** helpers (tags, collapse input). This TODO covers **serialization** to M3U text.

---

## Goal

One function (or small module) turns a resolved `List[Channel]` + render options into M3U bytes/lines. Route handlers only resolve channels via CQS and pass render flags.

---

## Proposed solution

Add `services/playlist_format_service.py` (or methods on an existing service):

```python
def render_m3u_playlist(
    channels: List[Channel],
    *,
    proxy_base: str,
    use_proxy: bool,
    proxy_icons: bool,
    account_for_direct_url: Account | None = None,
    primary_cred: Credential | None = None,
) -> str:
    """Build #EXTM3U body from resolved channels."""
```

Route handlers become:

```python
channels = ChannelQueryService.channels_for_account(...)
if collapse_duplicates:
    channels = collapse_channels(...)
body = render_m3u_playlist(channels, proxy_base=..., use_proxy=..., ...)
return Response(body, mimetype="application/x-mpegurl")
```

Keep account-specific direct-URL credential lookup in the account route; pass result into the helper.

---

## Dependencies

- **After:** TODO 10 preferred (collapse runs before render in both routes today)
- Independent of TODO 17/18

---

## Files to modify

| File | Changes |
|------|---------|
| `services/playlist_format_service.py` | **New** — shared M3U rendering |
| `routes/playlists.py` | `generate_playlist`, `_generate_playlist_from_config` — delegate to helper |
| `tests/test_playlist_generation.py` | Regression tests (output unchanged) |

---

## Acceptance criteria

- [ ] Single implementation of EXTINF + stream URL formatting
- [ ] Account M3U output byte-identical for existing test fixtures (proxy on/off, icons on/off)
- [ ] Config M3U output unchanged for multi-account and collapse scenarios
- [ ] `sanitize_m3u_value` usage centralized in helper

---

## Test plan

```bash
venv/bin/pytest tests/test_playlist_generation.py tests/test_playlists_routes.py tests/test_collapse_duplicates.py -v --no-cov
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
