# Improve main dashboard — health, live ops, and load time

**Status:** ✅ Done (June 2026)  
**Priority:** P2  
**Audit:** Operator UX / landing-page review, June 2026

## Problem

The main dashboard (`GET /`, `templates/index.html`) is the default landing page after login, but it does not surface the metrics operators care about most when checking system health:

1. **Channel health** — down/degraded/unknown counts exist on `/channel-health` but are not on the dashboard.
2. **Live proxy activity** — no count of currently operating streams or clients, even though the app tracks them (`ActiveStream`, stream multiplexer stats).

The page also **feels slow**: the shell renders quickly, but the user sees “Loading statistics…” until a chain of client-side fetches finishes. With multiple accounts, load time grows roughly linearly because per-account stats are fetched **sequentially**.

Operators need a fast, at-a-glance view; detailed account management belongs on `/accounts`, not blocking the home page.

## Current state

### Routing and template

| Piece | Location | Notes |
|-------|----------|-------|
| Web route | `routes/web.py` — `index()` | Renders `index.html` only; no server-side data |
| Template | `templates/index.html` | ~520 lines inline `<script>`; calls `loadDashboard()` on DOM ready |
| Base layout | `templates/base.html` | Full sidebar + Bootstrap; same as other admin pages |

### Client load sequence (`loadDashboard`)

All work is **client-driven** after HTML loads:

1. **`GET /api/overview/stats`** — `loadOverviewStats()` builds top summary cards (accounts, channels, EPG, tags) + scheduler alerts.
2. **`GET /api/accounts`** — account list.
3. **For each account (sequential):** `GET /api/accounts/{id}/stats` — builds one card per account with channel counts and sync actions.
4. **`GET /api/playlist-configs`** — tag playlists table (optional section).
5. **`GET /api/image-cache/stats`** — image cache card (optional section).
6. Quick Actions links (static HTML).

Nothing is parallelized with `Promise.all`; step 3 blocks step 4+.

### What the dashboard shows today

**Above-the-fold (after load):**

- Accounts enabled/total, synced count
- Visible channel count (global `is_active` + `is_visible`, not playlist-filter semantics)
- EPG program count + coverage % + enabled sources
- Tag count + tagged channels
- Scheduler running / sync intervals / sync-issue alerts (from TODO 91 metadata)
- Per-account cards: server, username, sync badge, channel/category counts, sync + M3U + preview buttons
- Tag playlists table (if any)
- Image cache stats
- Quick Actions list

**Not shown:**

- Channel health summary (healthy / degraded / down / unknown / ignored)
- Active proxied streams or client sessions
- Shared multiplexer upstream streams / subscriber counts
- Link to `/channel-health` for drill-down

### Channel health (existing capability)

| Piece | Location |
|-------|----------|
| UI | `/channel-health` — `templates/channel_health.html` |
| Summary API | `GET /api/channel-health/summary` — `ChannelHealthService.get_health_summary()` |
| Report API | `GET /api/channel-health/report` — full channel list (heavy) |

`get_health_summary()` is documented as **much faster than** `get_health_report`: single aggregated SQL over playlist-visible channels (enabled accounts, active channels, health status outer join). Same semantics as the channel health page summary cards (`summary.by_status.*`, `summary.total`).

Optional query params: `account_id`, `category_id`.

### Streams and clients (existing capability)

Two related concepts — document both in UI copy and open questions:

| Concept | Storage / service | Existing endpoint |
|---------|-------------------|-------------------|
| **Credential multiplexing** | `ActiveStream` rows per `credential_id` | `GET /stream/active` → `ConnectionManager.get_active_streams()` |
| **Shared upstream (FFmpeg backend)** | In-process `FFmpegStreamService._streams` | `GET /stream/multiplexer/stats`, `GET /stream/shared` → `get_stats()` |

`ActiveStream` fields: `stream_id`, `client_ip`, `session_token`, `credential_id`, activity timestamps — each row is one **proxied client session** consuming an upstream connection slot.

`ConnectionManager.get_connection_status(account_id)` returns per-credential `active_connections` / `max_connections` (N queries per credential today).

Multiplexer `get_stats()` returns `active_streams` (shared upstream count), `total_subscribers` (client viewers attached to shared streams), plus per-stream detail.

`STREAM_BACKEND` env selects ffmpeg vs mediaflow; MediaFlow idle/release semantics differ — dashboard counts must respect backend.

### Performance analysis — why it is slow

| Bottleneck | Severity | Detail |
|------------|----------|--------|
| **Sequential per-account stats** | High | `for (const account of accounts) { await fetch(.../stats) }` — N round-trips, no overlap |
| **`get_account_stats` loads all channels** | High | For synced accounts, `visible_count = len(ChannelQueryService.channels_for_account(account_id))` loads **every** active channel, joins categories, applies filters + PPV in Python — not a SQL `COUNT` |
| **`/api/overview/stats` query fan-out** | Medium | Many separate `COUNT()` queries; `EpgProgram.query.count()` on full table; `ChannelTag` distinct count; failed-account list query |
| **`get_epg_coverage_stats` in overview** | Medium | Extra joins/counts on every dashboard load (mapped channels + active channels) |
| **Blocking render** | Medium | `#dashboard-content` stays on loading alert until **entire** `loadDashboard()` completes |
| **Large inline template JS** | Low | Parses/executes on every visit; not cached as separate module (TODO 85/99 ESM pattern not applied to index) |
| **Coverage % bug** | Low (correctness) | `routes/api.py` reads `coverage_stats.get("coverage_percentage", 0)` but `services/epg/coverage.py` returns `coverage_percent` — dashboard EPG card likely shows **0%** always |

Server-side HTML render is cheap; **latency is API-shaped**, not Jinja.

### Related prior work

- [91-scheduler-status-api-failure-metadata.md](./91-scheduler-status-api-failure-metadata.md) — dashboard already consumes `has_sync_issues`, `failed_jobs`, `failed_sync_accounts` from overview stats ✅
- [86-web-smoke-tests-and-pytest-consolidation.md](./86-web-smoke-tests-and-pytest-consolidation.md) — `GET /` smoke test only checks 200, not load time or widget content
- [85-frontend-deduplication-and-esm-migration.md](./85-frontend-deduplication-and-esm-migration.md) / [99](./99-esm-tab-migration-and-eslint.md) — pattern for extracting inline page JS to `static/js/pages/`

## Proposed dashboard widgets / metrics

### Tier 1 — Above the fold (load first)

| Widget | Source (reuse) | Display |
|--------|------------------|---------|
| **Channel health** | `GET /api/channel-health/summary` | Cards or compact bar: healthy / degraded / down / unknown / ignored + total in playlist; badge if `down > 0`; link to `/channel-health` |
| **Active streams** | New aggregate or existing endpoints | Global count; optional split: multiplexed `ActiveStream` vs shared upstream `active_streams` (backend-aware) |
| **Active clients** | Same | Define in implementation (see open questions): e.g. `ActiveStream` row count and/or multiplexer `total_subscribers` |
| **Sync health** | Subset of `/api/overview/stats` | Keep compact scheduler + failed sync alert (already implemented) |

### Tier 2 — Existing overview (defer or slim)

| Widget | Action |
|--------|--------|
| Accounts / channels / EPG / tags cards | Keep but consider slimmer payload; fix EPG coverage key |
| Per-account cards | **Move or collapse** — link “Manage accounts”; show max 3 + “View all” OR load below fold via second request |
| Tag playlists | Below fold or link to `/rulesets#playlists` only |
| Image cache | Below fold or settings-only |
| Quick Actions | Keep static |

### Tier 3 — Drill-down links

- Channel Health → `/channel-health` (pre-filter `status=down` if down count > 0)
- Streams → new lightweight admin panel or document `/stream/active` + `/stream/shared` (today JSON, not linked from nav)

## Performance improvement options

| Option | Effort | Impact | Notes |
|--------|--------|--------|-------|
| **A. `GET /api/dashboard/summary`** | M | High | Single JSON: health summary + stream/client counts + minimal overview + scheduler flags; one DB round-trip batch |
| **B. Parallel frontend fetches** | S | Medium | `Promise.all` for independent sections; render Tier 1 as each completes (skeleton cards) |
| **C. Remove/defer per-account stats on landing** | S | High | Biggest win without new API — drop step 3 or load lazily when user expands “Accounts” |
| **D. SQL aggregates for account visible counts** | M | High | Replace `len(channels_for_account())` with counted query or materialized counter (align with TODO 20 / CQS semantics) |
| **E. Cache expensive overview counts** | M | Medium | TTL 30–60s for `EpgProgram.count`, EPG coverage, tag distinct — acceptable staleness on dashboard |
| **F. Split overview stats** | M | Medium | `GET /api/overview/stats/light` without EPG program total / coverage; full stats on demand |
| **G. ESM `dashboard_page.js`** | S | Low | Extract inline JS; enable Vitest for load order / skeleton behavior |
| **H. Server-render Tier 1** | L | Medium | Optional: embed summary in Jinja from one service call — faster first paint, couples web to DB |

**Recommended default stack:** **A + C + B** (new summary endpoint, stop blocking on N account stats, progressive render). Add **D** if account stats remain on dashboard. Add **E** only if profiling shows EPG counts dominate.

## Implementation phases

### Phase 1 — API and metrics contract

1. Add `GET /api/dashboard/summary` (or extend `/api/overview/stats` with `?light=1` — prefer **new route** to avoid breaking existing consumers).
2. Response shape (illustrative):

   ```json
   {
     "channel_health": { "by_status": { ... }, "total": 0 },
     "streams": {
       "active_sessions": 0,
       "shared_upstream": 0,
       "subscribers": 0,
       "backend": "ffmpeg"
     },
     "overview": { "accounts": { ... }, "scheduler": { ... } },
     "generated_at": "ISO-8601"
   }
   ```

3. Implement stream/client counts:
   - `ActiveStream.query.count()` (and optional per-account breakdown cap).
   - If `STREAM_BACKEND` is ffmpeg: include `get_stream_service().get_stats()` totals (in-process, no DB).
4. Reuse `ChannelHealthService.get_health_summary()` server-side (no extra HTTP from browser).
5. Fix `coverage_percent` vs `coverage_percentage` in overview path (regression test).

### Phase 2 — Landing page UX

1. Redesign `index.html` top row: health + streams + clients + sync alert.
2. Progressive loading: paint Tier 1 from summary endpoint immediately; skeleton for deferred sections.
3. Remove sequential per-account stats from initial load (or gate behind “Show account details”).
4. Add nav/deep links to Channel Health and stream monitoring.
5. (Optional) Extract JS to `static/js/pages/dashboard_page.js` per TODO 85 conventions.

### Phase 3 — Performance hardening

1. Optimize `AccountAdminService.get_account_stats` if still used anywhere on dashboard (`COUNT` + CQS-visible query, not full channel list).
2. Profile `/api/overview/stats` — collapse counts, defer `EpgProgram.query.count()`, document staleness if cached.
3. Add timing/logging for dashboard summary endpoint (debug slow deployments).

### Phase 4 — Tests and docs

1. API tests: summary shape, health counts match `/api/channel-health/summary`, stream counts with seeded `ActiveStream`.
2. Extend smoke test checklist in `docs/SMOKE_TEST_POST_MERGE.md` — dashboard shows health + stream widgets, loads without N+1 (network tab or test hook).
3. Update `docs/API_REFERENCE.md` for new endpoint and stream metric definitions.

## Open questions / decisions

| # | Question | Options |
|---|----------|---------|
| 1 | **“Operating streams”** definition | (a) `ActiveStream` rows — upstream slots in use; (b) multiplexer shared upstream count; (c) both with labels |
| 2 | **“Operating clients”** definition | (a) count of `ActiveStream` sessions; (b) distinct `client_ip`; (c) multiplexer `total_subscribers`; (d) show two metrics with tooltips |
| 3 | Per-account cards on home page | Remove vs collapse vs lazy-load — product preference |
| 4 | Global vs per-account health on dashboard | Summary only vs mini breakdown per account (extra query cost) |
| 5 | Auth exposure for `/stream/active` | Today unauthenticated JSON in tests — confirm Traefik/Authentik still protects; dashboard only links same-origin |
| 6 | MediaFlow backend | Whether `subscribers` / shared stats are meaningful when backend is mediaflow |
| 7 | Staleness | Accept 30–60s cached counts for EPG/health vs real-time |

## Affected files

- `templates/index.html` — layout, load strategy, optional ESM extraction
- `routes/api.py` — new dashboard summary route; fix coverage key in `get_overview_stats`
- `routes/web.py` — only if server-rendering Tier 1
- `services/channel_health_service.py` — reuse `get_health_summary` (no change expected)
- `services/connection_manager.py` — optional `get_global_active_counts()` helper
- `services/account_admin_service.py` — stats counting optimization (if per-account stats kept)
- `services/epg/coverage.py` — key alias or caller fix
- `static/js/pages/` — optional new dashboard module
- `tests/test_api_contract.py`, `tests/test_channel_health.py`, new dashboard tests
- `docs/API_REFERENCE.md`, `docs/SMOKE_TEST_POST_MERGE.md`

## Acceptance criteria

- [x] Dashboard above-the-fold shows channel health summary (at least down + degraded + healthy counts) with link to `/channel-health`
- [x] Dashboard shows current **operating streams** and **operating clients** per agreed definitions, backend-aware where needed
- [x] Initial meaningful paint uses **one** primary API call (or parallel Tier-1 calls), not sequential per-account stats
- [x] With 5+ accounts, dashboard interactive summary loads in bounded time (no per-account stats on first paint)
- [x] EPG coverage % on overview/dashboard is correct (`coverage_percent` wired)
- [x] API tests cover new summary endpoint; smoke doc updated in `docs/API_REFERENCE.md`
- [x] No regression to scheduler sync-issue alerts (TODO 91 fields still visible)

## Completion notes

- Stack **A + C + B**: `GET /api/dashboard/summary`, removed blocking per-account stats, parallel deferred sections.
- Stream metrics: `active_sessions` = `ActiveStream` count; `shared_upstream` / `subscribers` from multiplexer when FFmpeg backend.
- **PR:** [#48](https://github.com/klopstack/iptv-proxy-v2/pull/48) (`feature/dashboard-106`)

## Deferred

Tracked as follow-up TODOs (planning docs on PR branch):

| # | Document | Scope |
|---|----------|-------|
| 107 | [107-dashboard-stats-performance-hardening.md](./107-dashboard-stats-performance-hardening.md) | Phase 3: SQL visible counts for `get_account_stats`, overview stats caching/optimization, dashboard summary timing logs |
| 108 | [108-migrate-overview-stats-api-envelope.md](./108-migrate-overview-stats-api-envelope.md) | `GET /api/overview/stats` → `data_response` envelope (TODO 73 parity with summary endpoint) |
| 109 | [109-update-smoke-test-dashboard-checks.md](./109-update-smoke-test-dashboard-checks.md) | Phase 4: `docs/SMOKE_TEST_POST_MERGE.md` §1 / §7 dashboard checks |
| 110 | [110-dashboard-optional-ux-follow-ups.md](./110-dashboard-optional-ux-follow-ups.md) | P3 optional: lazy per-account cards, server-rendered Tier-1 |

## Test plan

```bash
# API contract
pytest tests/test_api_contract.py -k overview  # extend for dashboard summary
pytest tests/test_channel_health.py -k summary
pytest tests/test_connection_manager.py -k active_streams  # seed counts

# Manual
# 1. Open / with multiple accounts — Network tab: no N× /api/accounts/{id}/stats on first paint
# 2. Start a stream — dashboard stream/client counts increment
# 3. Channel health down count matches /channel-health summary
```

## Dependencies

- None blocking. Optional coordination:
  - [85](./85-frontend-deduplication-and-esm-migration.md) / [99](./99-esm-tab-migration-and-eslint.md) — if extracting dashboard JS to ESM in same PR
  - [73](./73-standardize-api-response-shapes.md) ✅ — use `apiUnwrapData` / `data_response` conventions for new endpoint

## References

- `routes/web.py`, `templates/index.html`
- `routes/api.py` — `get_overview_stats`
- `routes/channel_health.py` — `get_health_summary`
- `routes/streams.py` — `/stream/active`, `/stream/multiplexer/stats`
- `services/connection_manager.py`, `models/account.py` (`ActiveStream`)
- `docs/SMOKE_TEST_POST_MERGE.md` — dashboard row in admin page table
