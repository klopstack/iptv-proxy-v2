# Dashboard stats performance hardening (TODO 106 phase 3)

**Status:** ⬜ Not started  
**Priority:** P2  
**Deferred from:** [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) (Phase 3) — [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)  
**Audit:** Operator UX / landing-page review, June 2026

## Problem

[TODO 106](./106-improve-main-dashboard.md) removed sequential per-account stats from the landing page and added `GET /api/dashboard/summary` for Tier-1 paint. Deferred sections still call `GET /api/overview/stats`, and account detail pages still use `GET /api/accounts/{id}/stats`.

Remaining hotspots:

1. **`AccountAdminService.get_account_stats`** — for synced accounts, `visible_count = len(ChannelQueryService.channels_for_account(account_id))` materializes the full filtered channel list in Python instead of a SQL `COUNT` aligned with CQS/playlist semantics ([TODO 20](./20-align-admin-visible-channel-semantics.md) ✅).
2. **`GET /api/overview/stats`** — many separate `COUNT()` queries per request; `EpgProgram.query.count()` on the full table; EPG coverage joins on every deferred dashboard load.
3. **`GET /api/dashboard/summary`** — no request timing or structured slow-query logging for production diagnosis.

## Current state

| Endpoint / code | Location | Notes |
|-----------------|----------|-------|
| Dashboard Tier-1 | `routes/api.py` — `get_dashboard_summary()` | Reuses `ChannelHealthService.get_health_summary()`, stream counts, slim overview |
| Deferred overview cards | `static/js/pages/dashboard_page.js` — `loadOverviewStatsDeferred()` | Still fetches `/api/overview/stats` after summary paints |
| Per-account stats | `routes/accounts.py`, `AccountAdminService.get_account_stats` | Used on `/accounts` and account APIs, not landing page |
| Overview route | `routes/api.py` — `get_overview_stats()` | Returns `jsonify(stats)` (legacy shape); see [108](./108-migrate-overview-stats-api-envelope.md) |

## Proposed solution

### 1. SQL-visible count for account stats

- Add `ChannelQueryService.count_channels_for_account(account_id)` (or equivalent) using the same filter/PPV path as `channels_for_account`, but returning an integer only.
- Replace `len(playlist_visible)` in `get_account_stats` with the count helper.
- Regression tests: count matches `len(channels_for_account())` on representative fixtures (multi-account, PPV, tag filters).

### 2. Overview stats query optimization

- Profile `get_overview_stats()` with realistic DB sizes (accounts, EPG programs, tags).
- Collapse redundant counts where safe; consider optional TTL cache (30–60s) for expensive fields (`EpgProgram.count`, EPG coverage) with documented staleness.
- Optional: `GET /api/overview/stats?light=1` or move heavy EPG totals out of deferred dashboard path if summary + slim overview suffice.

### 3. Dashboard summary observability

- Log wall-clock duration and key sub-step timings for `get_dashboard_summary()` at `DEBUG` or behind a config flag.
- Document expected latency budget in `docs/API_REFERENCE.md` if thresholds are defined.

## Affected files

- `services/account_admin_service.py` — `get_account_stats`
- `services/channel_query_service.py` (or CQS module) — visible count query
- `routes/api.py` — `get_overview_stats`, `get_dashboard_summary`
- `services/epg/coverage.py` — only if coverage path is cached or split
- `tests/test_account_admin_service.py`, `tests/test_dashboard_summary.py`, overview stats tests
- `docs/API_REFERENCE.md` — staleness / performance notes if applicable

## Acceptance criteria

- [ ] `get_account_stats` visible channel count does not load full channel objects for synced accounts
- [ ] Count semantics match playlist-visible CQS output (parity test vs `channels_for_account` sample)
- [ ] `get_overview_stats` measurably faster or cached on deferred dashboard load (before/after note in PR or comment)
- [ ] `get_dashboard_summary` emits timing logs suitable for slow-deployment diagnosis
- [ ] No regression to [106](./106-improve-main-dashboard.md) Tier-1 behavior or [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48) dashboard tests

## Test plan

```bash
pytest tests/test_account_admin_service.py -q --no-cov
pytest tests/test_dashboard_summary.py -q --no-cov
pytest tests/test_api_contract.py -k overview -q --no-cov

# Manual: /accounts with 5+ synced accounts — stats cards load without multi-second stall
# Manual: / deferred section — Network tab shows faster /api/overview/stats (or fewer DB hits via logs)
```

## Dependencies

- [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) ✅ — landing dashboard redesign ([PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48))
- [20-align-admin-visible-channel-semantics.md](./20-align-admin-visible-channel-semantics.md) ✅ — visible count semantics
- Optional: [108](./108-migrate-overview-stats-api-envelope.md) — envelope change can land in same PR or separately

## References

- `services/account_admin_service.py` — `get_account_stats`
- `routes/api.py` — `get_overview_stats`, `get_dashboard_summary`
- [106](./106-improve-main-dashboard.md) — Phase 3 table (options D, E) and performance analysis
