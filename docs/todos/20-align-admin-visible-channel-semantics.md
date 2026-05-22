# TODO 20: Align Admin “Visible Channel” Semantics With Playlist Output

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (audit + targeted route updates)

---

## Problem

Client outputs (M3U, EPG, Xtream) use **playlist-visible** semantics:

```
FilterService.apply_filters_to_channels  +  PPVVisibilityService
```

Several admin and UI-support endpoints use **filter-only** semantics (no PPV visibility):

| Endpoint | File | Uses FilterService | Uses PPV visibility |
|----------|------|-------------------|---------------------|
| `GET /api/categories` | `routes/api.py` | ✅ | ❌ |
| `GET /api/accounts/<id>/stats` | `routes/accounts.py` | ✅ | ❌ |
| EPG unmapped/mapped channel lists | `routes/epg/channels.py` | ✅ | ❌ |
| Channel health views | `routes/channel_health.py` | ✅ | ❌ |

This may be **intentional** for admin workflows (show all synced channels including hidden PPV for mapping). It is **misleading** when UI copy implies counts match what subscribers see in playlists.

Example: account with `ppv_visibility=hide_all` and one PPV channel — stats/categories may count the PPV channel as “visible per filters” while M3U excludes it.

---

## Goal

Either:

**Option A (align):** Admin endpoints that drive playlist-adjacent UI use `ChannelQueryService` (filters + PPV) for “visible” counts.

**Option B (document):** Keep admin semantics but rename response fields and UI labels to distinguish **synced/filtered** vs **playlist-visible**.

Pick one approach per endpoint based on product intent; document the decision in route docstrings.

---

## Proposed solution

### Step 1: Audit each endpoint

For each route in the table above, decide:

| Question | Action |
|----------|--------|
| Does the UI present this as “what’s in my playlist”? | Align with CQS |
| Does the UI present this as “all synced channels for admin work”? | Keep filter-only; rename fields |

### Step 2: Add CQS helper for counting (if aligning)

```python
@staticmethod
def visible_channel_set_for_account(account_id: int) -> set[tuple[int, str]]:
    channels = ChannelQueryService.channels_for_account(account_id)
    return {(ch.account_id, str(ch.stream_id)) for ch in channels}
```

Use in categories API and account stats instead of FilterService-only sets.

### Step 3: Update UI labels (if documenting)

Templates/JS that show “visible channels” should clarify when PPV-hidden channels are included.

---

## Dependencies

- **After:** TODO 17 (preview through CQS establishes pattern)
- Independent of TODO 10

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/api.py` | `get_all_categories` — align or relabel counts |
| `routes/accounts.py` | `get_account_stats` — align or relabel |
| `routes/epg/channels.py` | Unmapped channel lists — align or document |
| `routes/channel_health.py` | Health listing — align or document |
| `services/channel_query_service.py` | Optional counting helper |
| `templates/` / static JS | Label updates if Option B |

---

## Acceptance criteria

- [ ] Each affected endpoint has an explicit docstring stating which visibility semantics it uses
- [ ] No endpoint silently uses filter-only counts where UI implies playlist parity
- [ ] If aligned: PPV hide_all reduces category visible counts same as M3U
- [ ] If documented: UI distinguishes admin vs playlist-visible counts

---

## Test plan

```bash
venv/bin/pytest tests/test_api_routes.py tests/test_accounts_routes.py tests/test_epg_routes.py -v --no-cov
```

Add tests for PPV hide_all account: stats/categories count excludes PPV **if Option A chosen**.

---

## Out of scope

- Preview endpoints (TODO 17)
- EPG/M3U generation (already unified)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | Requires product decision: admin sees all synced vs playlist-visible |
