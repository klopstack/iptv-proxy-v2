# PPV enrichment attempt tracking and no_match requeue workflow

**Status:** 🟡 In review  
**Priority:** P1  
**Audit:** Production matching analysis, June 2026 (`docker.klopnet.com`)

## Problem

Production database state on 2026-06-03 shows inconsistent enrichment metadata:

| Observation | Value |
|-------------|-------|
| Channels with `ppv_enrichment_status` in (`matched`, `no_match`) | 1,182 |
| Channels with `ppv_enrichment_attempts > 0` | **0** |
| Channels with `ppv_enrichment_last_attempt` set | **0** |
| `recently_enriched_24h` (dashboard) | **0** |
| Enrichment queue (`queued_count`) | **0** |

Statuses were assigned (likely from a prior enrichment run or bulk migration), but **attempt counters and timestamps were never persisted** — or were reset without clearing statuses. Operators cannot tell when a channel was last tried, whether fixes require a manual re-run, or which channels are stale `no_match` from old logic.

Cumulative stats (`calendar_matched: 1256`, `calendar_processed: 27340`) reflect historical orchestrator counters, while only **110** `EventChannelLink` rows exist — past events aged out, but **`no_match` channels are not automatically re-queued** when matching improves.

After implementing TODOs 120–123, production will **not** pick up fixes unless channels are re-enriched.

## Affected files

- `services/ppv/orchestrator.py` — `PPVEnrichmentOrchestrator` process loop
- `services/ppv/enrichment/service.py` — status updates per channel
- `services/ppv/enrichment/side_effects.py` — post-match hooks
- `services/jobs/ppv_enrichment.py` — scheduled job
- `routes/ppv_enrichment.py` — `/process`, `/queue/all-ppv`, `/queue/channels`
- `models/channel.py` — `ppv_enrichment_attempts`, `ppv_enrichment_last_attempt`, `ppv_enrichment_status`
- `services/ppv/dashboard_stats.py` — `recently_enriched_24h`
- `scripts/rerun_matching.py` — existing rerun script (audit and extend)
- UI: `templates/ppv.html` — operator actions
- Tests: `tests/ppv/test_orchestrator.py`, `tests/test_ppv_enrichment_routes.py`

## Requirements for resolution

### Attempt tracking (bug fix)

1. **Every enrichment pass** over a channel (match, no_match, skipped, error) must:
   - Increment `ppv_enrichment_attempts`
   - Set `ppv_enrichment_last_attempt` to UTC now
   - Persist in the same transaction as status update (no partial commits)

2. **Idempotent retries:** Re-queuing the same channel increments attempts again (expected).

3. **Dashboard accuracy:** `recently_enriched_24h` counts channels with `ppv_enrichment_last_attempt >= now - 24h` and terminal status in (`matched`, `enriched`, `no_match`, `skipped`) — verify query matches persisted timestamps.

4. **API exposure:** `/api/ppv-enrichment/channels` already returns attempt fields — values must be non-null after any process run (document in API reference).

### Requeue workflow (operational)

1. **Bulk requeue `no_match`:** Admin action or script to set `ppv_enrichment_status='queued'` for channels where:
   - `status == 'no_match'`
   - Optional filters: `account_id`, name prefix (`Tennis:`, `Peacock`), `ppv_enrichment_last_attempt` older than deploy time

2. **Bulk requeue after deploy:** Document runbook step in `docs/SMOKE_TEST_POST_MERGE.md` — after PPV matching fixes, run requeue + process.

3. **Do not requeue `skipped`** by default (15,443 generic slots) — optional explicit flag `--include-skipped` on script only.

4. **Rate limiting:** Requeue respects existing orchestrator batch size and API rate limits; status endpoint shows queue depth during bulk run.

5. **`rerun_matching.py` audit:** Align script with orchestrator paths; add `--status no_match`, `--dry-run`, `--since-last-deploy` flags.

### Safety

- Requeue must not delete existing valid `EventChannelLink` rows unless `--clear-existing` explicitly passed (existing script behavior).
- Matched channels requeued should re-verify link or skip if link still valid (avoid duplicate events — leverage `persist_match` idempotency from TODO 54).

## Proposed solution

1. **Fix persistence gap** in enrichment service — locate code path that sets `ppv_enrichment_status` without updating attempts; add shared `_record_enrichment_attempt(channel)` helper.
2. **Add route** `POST /api/ppv-enrichment/queue/no-match` with JSON body `{ "account_id": optional, "prefix": optional, "dry_run": bool }`.
3. **Extend** `scripts/rerun_matching.py` or add `scripts/requeue_no_match_channels.py` wrapping same logic as API.
4. **PPV admin UI:** Button “Re-queue no_match channels” with confirmation (optional — API + script minimum).
5. **Migration not required** if columns exist — backfill optional: set `ppv_enrichment_last_attempt = NULL` stays for never-processed; after first post-fix run, timestamps populate.

## Acceptance criteria

- [ ] After single-channel process via API, `ppv_enrichment_attempts >= 1` and `ppv_enrichment_last_attempt` is non-null.
- [ ] Dashboard `recently_enriched_24h` > 0 within 24h of production process run.
- [ ] Bulk requeue of `no_match` channels sets `queued_count` > 0 and process drains queue.
- [ ] Post TODO 120 deploy + requeue: measurable drop in `no_match_count` on production (tracked in deploy notes).
- [x] Unit test fails if enrichment code path sets status without calling attempt recorder (mock/spy).
- [x] `--dry-run` reports count without DB mutation.

## Test plan

### Unit tests

- `tests/ppv/test_enrichment_attempt_tracking.py`:
  - Process one channel → attempts incremented, timestamp set.
  - Process same channel twice → attempts == 2.
  - Skipped channel still records attempt (or document exception if skipped before attempt — prefer record on any evaluation).

### Route tests

Extend `tests/test_ppv_enrichment_routes.py`:

- `POST /api/ppv-enrichment/queue/no-match` with fixtures → N channels queued.
- Dry run → 0 DB changes, response includes count.

### Integration

- Seed 3 channels: `matched`, `no_match`, `skipped`.
- Run orchestrator `process` batch.
- Assert attempt fields on all three; only `no_match` + `matched` change status as expected.

### Production smoke (runbook)

```bash
# Before
docker exec iptv-proxy-v2 curl -s http://127.0.0.1:8000/api/dashboard/summary | jq '.data.ppv.enrichment'

# Requeue + process
docker exec iptv-proxy-v2 curl -s -X POST http://127.0.0.1:8000/api/ppv-enrichment/queue/no-match -H 'Content-Type: application/json' -d '{}'
docker exec iptv-proxy-v2 curl -s -X POST http://127.0.0.1:8000/api/ppv-enrichment/process -H 'Content-Type: application/json' -d '{}'

# After — attempts populated, no_match count changed
docker exec iptv-proxy-v2 python -c "
from app import app
from models import Channel, db
with app.app_context():
    print('with attempts:', Channel.query.filter(Channel.ppv_enrichment_attempts>0).count())
"
```

## Dependencies

- [59](./59-harden-ppv-enrichment-routes.md) — route patterns (done).
- [54](./54-route-enrichment-through-persist-match.md) — idempotent persist (done).
- **Blocks validation of:** [120](./120-fix-ppv-date-extraction-parsing-bugs.md), [121](./121-mlb-team-abbreviation-resolution.md), [122](./122-tennis-calendar-event-source.md), [123](./123-extended-calendar-coverage-college-obscure-sports.md) — all need requeue to verify production impact.

## Recommended order

**124 in parallel with 120** (attempt tracking fix can ship first as a small PR). **Requeue runbook** required before measuring any matching fix on production.

## Completion

- **PR:** https://github.com/klopstack/iptv-proxy-v2/pull/53
- **Deliverables:** `_record_enrichment_attempt` helper; batch commit in `enrich_channels`; `POST /api/ppv-enrichment/queue/no-match`; `services/ppv/requeue.py`; extended `scripts/rerun_matching.py`; dashboard query fix; PPV UI button; runbook in `docs/SMOKE_TEST_POST_MERGE.md`; unit/route tests.
