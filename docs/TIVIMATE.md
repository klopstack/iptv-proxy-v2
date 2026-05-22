# TiviMate Setup

This proxy exposes a **live-only** Xtream Codes API (`routes/xtream.py`).

## Configuration

1. Create an **Xtream credential** in the web UI pointing at:
   - A single **Account**, or
   - A **Playlist config** that aggregates multiple provider accounts (`include_accounts`).
2. In TiviMate:
   - **Server URL**: `http://your-proxy:8000`
   - **Username / Password**: credential from the UI
3. EPG: use the built-in Xtream EPG (`get_short_epg`) or external URL `/xmltv.php?username=...&password=...`.

## EPG channel IDs

Live streams use `epg_channel_id` = `ch-{account_id}-{stream_id}`. PPV channels with matched events may use `event-{event_id}` in M3U `tvg-id`.

## M3U stream URLs

Both `/playlist/<account_id>.m3u` and `/playlist/config/<slug>.m3u` default to **proxied** stream URLs (`/stream/{account_id}/{stream_id}.ts`). This matches the accounts page links and supports multi-credential accounts.

Query parameters:

- `proxy=false` — use direct provider URLs instead of the proxy
- `proxy=true` — explicit proxied URLs (default when omitted)
- `proxy_icons=false` — skip icon URL caching through the proxy

Multi-credential accounts always use proxied URLs, even when `proxy=false`.

## Limitations

VOD and series endpoints are not implemented (live TV only).
