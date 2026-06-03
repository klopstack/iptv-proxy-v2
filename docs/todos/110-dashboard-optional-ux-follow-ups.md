# Dashboard optional UX follow-ups (TODO 106 backlog)

**Status:** 🚫 Won't do (P3 optional — Tier-1 summary + `/accounts` suffice; lazy cards/server-render add complexity without operator demand)
**Priority:** P3 (optional)  
**Deferred from:** [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) open questions / options H — [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)

## Problem

[TODO 106](./106-improve-main-dashboard.md) shipped the recommended stack (**A + C + B**): dashboard summary endpoint, no blocking per-account stats, parallel deferred sections ([PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)). Two product/UX options were explicitly **not** required for acceptance but may be desired later:

1. **Per-account cards on home page** — removed from initial load (option C). Operators may want a collapsed preview (e.g. top 3 accounts + “View all”) without restoring sequential N× stats on first paint.
2. **Server-rendered Tier 1** (option H) — embed health + stream summary in Jinja on `GET /` for faster first paint without waiting for JS + API round-trip.

Neither blocks operator workflows today (`/accounts` remains the management surface).

## Current state

| Area | State after 106 |
|------|-----------------|
| Landing `/` | Tier-1 from `GET /api/dashboard/summary` via `static/js/pages/dashboard_page.js` |
| Per-account cards | Not rendered on dashboard; link to `/accounts` via Quick Actions |
| Server render | `routes/web.py` `index()` renders empty shell only |

## Proposed solution

### A. Lazy-load per-account cards (optional)

1. Add “Account snapshot” collapsible below Tier-1 (default collapsed).
2. On expand: `Promise.all` over `GET /api/accounts` + parallel `GET /api/accounts/{id}/stats` (cap concurrency, e.g. 3) **or** a new batch endpoint after [107](./107-dashboard-stats-performance-hardening.md).
3. Show max 3 cards + link to `/accounts`; never block Tier-1 paint.
4. Vitest: expand triggers fetches; collapsed does not.

### B. Server-render Tier 1 (optional)

1. Call shared builder used by `get_dashboard_summary()` from `routes/web.py` `index()`.
2. Pass `channel_health`, `streams`, slim `overview` into `templates/index.html` as JSON bootstrap or pre-rendered HTML fragments.
3. `dashboard_page.js` hydrates or skips duplicate fetch when bootstrap present.
4. Document trade-off: couples web route to DB on every `/` GET.

Pick **A**, **B**, or both only if product requests; otherwise close as won’t-do.

## Affected files

- `templates/index.html`, `static/js/pages/dashboard_page.js`
- `routes/web.py`, `routes/api.py` — shared summary builder
- `tests/test_app_routes.py`, `tests/test_dashboard_summary.py`
- `docs/API_REFERENCE.md` — if bootstrap contract is public

## Acceptance criteria

- [ ] Chosen option does not reintroduce sequential per-account stats on **initial** paint (106 regression)
- [ ] Tier-1 metrics still correct when optional section is collapsed or JS disabled (server-render path)
- [ ] Tests cover lazy-expand or server-render bootstrap behavior
- [ ] Documented in operator-facing docs if behavior is user-visible

## Test plan

```bash
pytest tests/test_dashboard_summary.py tests/test_app_routes.py -q --no-cov
npm test  # if dashboard_page.js behavior changes

# Manual: / first paint unchanged when optional UI collapsed
# Manual: expand account snapshot OR hard refresh with server-render — metrics match summary API
```

## Dependencies

- [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) ✅ ([PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48))
- [107-dashboard-stats-performance-hardening.md](./107-dashboard-stats-performance-hardening.md) — recommended before lazy per-account stats (avoids slow N× `get_account_stats`)

## References

- [106](./106-improve-main-dashboard.md) — open questions 3, 4; option H table
- `routes/web.py`, `templates/index.html`
