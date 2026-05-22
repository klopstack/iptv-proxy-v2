# TODO 02: Unify Preview Channel Selection

**Priority:** P0  
**Status:** ✅ Complete  
**Estimated scope:** Medium (2 route files)

---

## Problem

The channel preview UI (`/test` page) and related APIs show channels that may differ from generated M3U/Xtream output because they bypass `ChannelQueryService` and **PPV visibility**:

| Endpoint | File | Uses `ChannelQueryService`? | PPV visibility? |
|----------|------|----------------------------|-----------------|
| `GET /api/accounts/<id>/preview` | `routes/accounts.py:827` | ❌ | ❌ |
| `GET /api/channels/preview` | `routes/api.py:372` | ❌ | ❌ |

Both endpoints:
- Query DB channels directly
- Apply `FilterService.apply_filters_to_channels` only
- Do **not** call `PPVVisibilityService`

Users use preview to validate what will appear in playlists. Showing PPV channels that M3U will hide is misleading.

---

## Goal

Preview endpoints return the same channel set as `ChannelQueryService.channels_for_account` / equivalent multi-account logic, including PPV visibility.

---

## Proposed solution

### `/api/accounts/<account_id>/preview`

After building the base query (tags, category, search filters), replace the filter-only path with:

```python
# Option A: Get all candidate channels from query, then filter through CQS
all_channels = base_query.all()
channels = ChannelQueryService.channels_for_account(
    account_id,
    apply_filters=True,
    apply_ppv_visibility=True,
)
# Intersect with search/category/tag pre-filters OR apply those filters before CQS
```

**Recommended approach:** Apply search/category/tag filters first (these are preview-specific UX filters), then run results through PPV visibility:

```python
candidate_channels = base_query.all()
filtered = FilterService.apply_filters_to_channels(candidate_channels, account_id)
ppv = PPVVisibilityService(account)
filtered = [ch for ch in filtered if ppv.should_show_channel(ch)]
```

Or add a parameter to `ChannelQueryService.channels_for_account` to accept a pre-filtered list — only if cleaner than inline PPV pass.

**Important:** Search and category filters are preview-only (not in M3U). Document that preview with no search/tags shows M3U-equivalent output; with search/tags it is a subset.

### `/api/channels/preview` (all accounts)

For each account group after tag/category filtering:

```python
account = db.session.get(Account, acc_id)
ppv = PPVVisibilityService(account)
filtered = [ch for ch in acc_channels if ppv.should_show_channel(ch)]
```

Or refactor to call `ChannelQueryService` per account when `account_id` is set; for "all accounts" mode, group by account and apply PPV per account.

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/accounts.py` | `preview_account_playlist` — add PPV visibility |
| `routes/api.py` | `preview_channels` — add PPV visibility per account |
| `tests/test_accounts_routes.py` | Preview tests with PPV scenarios |
| `tests/test_api_routes.py` | Multi-account preview PPV tests |

---

## Acceptance criteria

- [x] Account preview without extra filters matches M3U channel count (± pagination)
- [x] PPV channel hidden by `hide_all` does not appear in preview
- [x] PPV channel with past event hidden by `hide_inactive` does not appear in preview
- [x] Search/category/tag filters still work as additional narrowing (preview UX)
- [x] `collapse_duplicates` preview option still works
- [x] `using_database: true` still returned in response

---

## Test plan

```bash
venv/bin/pytest tests/test_accounts_routes.py tests/test_api_routes.py -v -k preview --no-cov
```

Add test case:
1. Account with `ppv_visibility=hide_all`, one PPV channel, one regular channel
2. `GET /api/accounts/{id}/preview` returns only the regular channel

---

## UI note

`templates/test.html` shows a Database vs API badge. After TODO 03, playlist-config preview will also be database-first. No template changes required for this TODO unless response shape changes.

---

## Dependencies

- Can be done in parallel with TODO 01
- TODO 03 is separate (playlist-config preview endpoint)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Added `ChannelQueryService.apply_ppv_visibility_to_channels`; wired into both preview endpoints |
