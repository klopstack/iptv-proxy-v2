# TODO 01: Unify EPG Channel Selection

**Priority:** P0  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (1–2 files, focused refactor)

---

## Problem

M3U and Xtream outputs use `ChannelQueryService`, which applies:
- Account/tag filters via `FilterService`
- PPV visibility rules via `PPVVisibilityService`

EPG endpoints do **not** use `ChannelQueryService`:

| Endpoint | Current logic | Missing |
|----------|---------------|---------|
| `GET /epg/<account_id>.xml` (`proxy_epg`) | Inline query + `FilterService` only | PPV visibility |
| `GET /epg/config/<id>.xml` (`_generate_epg_from_config`) | SQL `is_visible` + inline tag SQL | `FilterService`, PPV visibility, `ChannelQueryService` |

The accounts UI claims EPG is “filtered to M3U channels.” That is false when PPV visibility hides channels from M3U but EPG still includes them (or the reverse if `is_visible` is stale).

### Current code paths

**Account EPG** — `routes/playlists.py:598–691`:
```python
channels = query.order_by(Channel.name).all()
channels = FilterService.apply_filters_to_channels(channels, account_id)
# No PPVVisibilityService
```

**Config EPG** — `routes/playlists.py:737–837`:
```python
query = db.session.query(Channel).filter(
    Channel.account_id == account.id, Channel.is_active, Channel.is_visible
)
# Inline tag SQL filtering — duplicates ChannelQueryService logic
# No FilterService.apply_filters_to_channels
# No PPVVisibilityService
```

**Account M3U (correct)** — `routes/playlists.py:322–326`:
```python
channels = ChannelQueryService.channels_for_account(
    account_id, apply_filters=True, apply_ppv_visibility=True,
)
```

---

## Goal

EPG endpoints return guide data for **exactly the same channel set** as the corresponding M3U playlist, including:
- Dynamic filters (not just cached `is_visible`)
- PPV visibility rules
- Tag include/exclude rules on config playlists
- Duplicate collapse when `?collapse_duplicates=true` (already partially implemented)

---

## Proposed solution

### Step 1: Account EPG (`proxy_epg`)

Replace inline channel query + filter with:

```python
channels = ChannelQueryService.channels_for_account(
    account_id,
    apply_filters=True,
    apply_ppv_visibility=True,
)
```

Keep existing duplicate-collapse logic after channel selection (or extract to shared helper in TODO 10).

Respect query params already supported:
- `collapse_duplicates=true`

### Step 2: Config EPG (`_generate_epg_from_config`)

Replace the entire inline account loop + SQL tag filtering with:

```python
channels = ChannelQueryService.channels_for_playlist_config(
    config,
    apply_filters=True,
    apply_ppv_visibility=True,
)
```

Remove duplicate parsing of `include_tags` / `exclude_tags` / account lists for channel selection (keep only what's needed for logging or east/west fallback params).

Keep:
- `east_west_fallback` query param passthrough to `EpgService.generate_epg_for_channels`
- Minimal empty XMLTV response when no channels

### Step 3: Optional helper on `ChannelQueryService`

If duplicate collapse for EPG should mirror M3U exactly, consider adding:

```python
@staticmethod
def channels_for_epg_account(account_id, *, collapse_duplicates=False) -> List[Channel]:
    ...

@staticmethod
def channels_for_epg_config(config, *, collapse_duplicates=False) -> List[Channel]:
    ...
```

Only add this if it avoids duplicating collapse logic in the route; otherwise inline collapse after `channels_for_*` is fine for this TODO.

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | Refactor `proxy_epg`, `_generate_epg_from_config` |
| `tests/test_playlists_routes.py` | Update/add EPG tests |
| `tests/test_playlist_generation.py` | Verify config EPG still respects tag filters |
| `tests/test_channel_query_service.py` | Optional: unit tests if new helpers added |

---

## Acceptance criteria

- [ ] `/epg/<account_id>.xml` channel count matches `/playlist/<account_id>.m3u` for the same account (same filters, no collapse)
- [ ] `/epg/config/<id>.xml` channel set matches `/playlist/config/<id>.m3u` for the same config
- [ ] PPV channel with `ppv_visibility=hide_all` appears in **neither** M3U nor EPG
- [ ] PPV channel with past event + `hide_inactive` appears in **neither** M3U nor EPG
- [ ] `?collapse_duplicates=true` on EPG still works and matches M3U collapse behavior
- [ ] Docstring on `proxy_epg` remains accurate
- [ ] All existing EPG route tests pass

---

## Test plan

```bash
# Run focused tests
venv/bin/pytest tests/test_playlists_routes.py tests/test_playlist_generation.py -v --no-cov

# Manual smoke (with synced account containing PPV channels):
curl -s "http://localhost:8000/playlist/1.m3u" | grep -c '^#EXTINF'
curl -s "http://localhost:8000/epg/1.xml" | grep -c '<channel '
# Channel counts in XML should correspond to tvg-id entries in M3U
```

Add at least one integration test that:
1. Creates account with PPV channel + `ppv_visibility=hide_all`
2. Asserts M3U excludes it AND EPG XML has no `<channel>` for that stream

(Full parity test suite is TODO 08; one smoke test here is enough.)

---

## Out of scope

- Preview API unification (TODO 02)
- Playlist config preview live API (TODO 03)
- Extracting duplicate-collapse helper (TODO 10)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
