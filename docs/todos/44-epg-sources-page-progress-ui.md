# TODO 44: EPG Sources Page Progress UI

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Medium  

**Depends on:** [43-per-source-epg-sync-orchestrator.md](./43-per-source-epg-sync-orchestrator.md) (progress columns populated for per-source sync)

---

## Problem

Per-source EPG sync progress is only visible on **Settings** (`templates/settings.html`):

- Polls `GET /api/sync/epg/status` every 5s
- Renders phase, message, programme counters

The **EPG Sources** management page (`templates/epg_sources.html` or equivalent) triggers `POST /api/epg/sources/<id>/sync` but gives no live feedback during long XMLTV/SD runs. Users sync from the sources list and switch to Settings to see status.

---

## Goal

Show the same per-source progress on the EPG sources list (inline row state or modal), reusing `/api/sync/epg/status` without duplicating business logic.

---

## Proposed solution

### 1. Reuse status API

No new endpoint required if TODO 43 wires progress for per-source sync. Poll `/api/sync/epg/status` while any `sync_in_progress` on visible rows.

### 2. UI patterns (pick one)

| Pattern | Pros |
|---------|------|
| **Row badge** | Phase label + spinner on source row |
| **Progress bar** | `programmes_parsed` / estimate when available |
| **Toast + table refresh** | Minimal JS; less detail |

Align styling with settings table (Bootstrap badges: `queued`, `fetching`, `channels`, `programs`, `complete`, `error`).

### 3. JS module

- Extract shared `epgSyncProgress.js` from settings inline script (optional, pairs with TODO 51 test dedup).
- Export `pollEpgSyncStatus(callback)` used by settings + sources pages.

### 4. Bulk actions

If sources page has “sync all”, call `POST /api/sync/epg` and poll same status endpoint.

---

## Affected files

| File | Change |
|------|--------|
| `templates/epg_sources.html` (or `templates/epg/`) | Progress column / poll hook |
| `static/js/` | Shared poll helper (optional) |
| `templates/settings.html` | Import shared helper if extracted |

---

## Acceptance criteria

- [x] Syncing from sources page shows phase within one poll interval (≤5s).
- [x] Error phase shows `last_sync_message` or progress message.
- [x] No duplicate poll timers when navigating settings ↔ sources (cleanup on `pagehide`).
- [x] Works for xmltv_url, provider, SD, grabber source types (all use orchestrator per TODO 43).

---

## Test plan

- Manual: start large source sync, confirm row updates.
- Optional Vitest for poll helper (see TODO 32 patterns).
- Backend covered by TODO 43 route tests.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-26 |
| PR / commit | `lib/epg_sync_progress.js`, `lib/epg_sync_progress_poll.js`, `epg_sources.js`, settings |
