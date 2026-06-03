# Update post-merge smoke test for dashboard (TODO 106 phase 4)

**Status:** ✅ Done  
**Priority:** P2  
**Deferred from:** [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) (Phase 4) — [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)  
**Related:** [86-web-smoke-tests-and-pytest-consolidation.md](./86-web-smoke-tests-and-pytest-consolidation.md) ✅

## Problem

`docs/SMOKE_TEST_POST_MERGE.md` still describes the pre–TODO 106 dashboard:

- §1 admin table: “Overview cards load” without channel health / stream widgets or `GET /api/dashboard/summary`.
- §7 dashboard: checks sync alerts and `/api/overview/stats` envelope only; does not verify Tier-1 summary, health/stream metrics, or absence of per-account stats on first paint.

PR #48 deferred this doc update because the smoke file was not on the feature branch at implementation time. Operators need an accurate manual checklist after merge.

## Current state

| Doc section | Gap |
|-------------|-----|
| §1 Dashboard row | No channel health / operating streams / clients checks |
| §7 Dashboard | No `/api/dashboard/summary`; envelope line may be wrong until [108](./108-migrate-overview-stats-api-envelope.md) |
| Network / load | No “no N× `/api/accounts/{id}/stats` on first paint” step |

Automated coverage: `tests/test_dashboard_summary.py`, extended `test_api_contract.py` on the PR branch. Manual smoke remains the gap.

## Proposed solution

Update `docs/SMOKE_TEST_POST_MERGE.md`:

### §1 — Admin pages table (`/` row)

- Tier-1: channel health summary (healthy / degraded / down), operating streams/clients (labels per [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48)), sync alert if issues.
- Primary API: `GET /api/dashboard/summary` returns 200 with `data.channel_health`, `data.streams`, `data.overview`.

### §7 — Dashboard (`/`)

Replace or extend steps:

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `/` → Network (first paint) | `GET /api/dashboard/summary` fires; **no** sequential `GET /api/accounts/{id}/stats` before interactive summary |
| 2 | Channel health card | Counts match `/channel-health` summary (or same API field) |
| 3 | Stream metrics | With an active proxied session, operating stream/client counts update (or match `/stream/active` / multiplexer stats when FFmpeg backend) |
| 4 | Sync issues | If `has_sync_issues`, danger alert lists failed jobs/accounts (TODO 91) |
| 5 | Deferred section | Overview cards load via `/api/overview/stats` (envelope per [108](./108-migrate-overview-stats-api-envelope.md) when done) |

Add checklist bullets for DevTools verification and optional link to `/channel-health` with `status=down` when down count > 0.

### Cross-links

- Reference [106](./106-improve-main-dashboard.md) and metric definitions from PR #48 body.
- Note dependency on [108](./108-migrate-overview-stats-api-envelope.md) for exact overview envelope wording.

## Affected files

- `docs/SMOKE_TEST_POST_MERGE.md` — §1, §7, optional “How to use” estimated time if section grows
- `docs/todos/README.md` — index entry (when marking 109 done)

## Acceptance criteria

- [x] Smoke doc §1 and §7 describe post–TODO 106 dashboard behavior accurately
- [x] Checklist includes first-paint network verification (summary only, no per-account stats storm)
- [x] Channel health and stream/client widgets have explicit expected results
- [x] Overview stats step matches actual API envelope after [108](./108-migrate-overview-stats-api-envelope.md) or documents interim `unwrapData` tolerance
- [x] Linked from [106](./106-improve-main-dashboard.md) deferred/completion section

## Test plan

Docs-only — verify by running the updated §7 steps on a deployment with [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48) merged:

1. Multi-account instance → confirm network pattern.
2. Induce or use existing down channel → health counts match `/channel-health`.
3. Start/stop a stream → dashboard stream row updates.

## Dependencies

- [106-improve-main-dashboard.md](./106-improve-main-dashboard.md) ✅ merged (or PR #48 merged)
- [108-migrate-overview-stats-api-envelope.md](./108-migrate-overview-stats-api-envelope.md) — optional same PR; otherwise smoke doc notes legacy overview shape until 108 lands

## References

- [106](./106-improve-main-dashboard.md) — Phase 4, test plan
- [PR #48](https://github.com/klopstack/iptv-proxy-v2/pull/48) — metric definitions (operating streams vs shared upstream vs subscribers)
- `docs/API_REFERENCE.md` — `GET /api/dashboard/summary`
