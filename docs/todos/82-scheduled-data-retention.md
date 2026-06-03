# Scheduled data retention for events and cached images

**Status:** ✅ Ready for review  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Data retention is uneven:

| Data | Retention |
|------|-----------|
| EPG programs | Scheduled cleanup (7d default) ✅ |
| Health checks | Scheduled cleanup (30d) ✅ |
| Finished events | Manual script only (`scripts/cleanup_old_events.py`) |
| PPV orphan events | Inline from enrichment, not scheduler |
| Cached images | API/manual `cleanup_expired`, not scheduled |

Tables can grow unbounded on long-running installs.

## Affected files

- `services/scheduler.py` — add jobs
- `services/scheduler_registry.py`
- `services/scheduler_jobs/cleanup.py`
- `services/event_retention.py`
- `scripts/cleanup_old_events.py`
- `services/image_cache_service.py`
- `tests/test_data_retention.py`

## Proposed solution

1. Add scheduler job for old finished events (configurable max age, default 90d)
2. Add scheduler job for expired cached images
3. Optionally move PPV orphan prune to scheduler instead of inline enrichment hook — **deferred** (out of scope; see TODO 79)
4. Document retention policy in DEVELOPER_GUIDE / ops runbook

## Acceptance criteria

- [x] Events older than configured age are pruned on schedule
- [x] Expired cached images cleaned on schedule
- [x] Retention defaults documented and tested

## Test plan

- Extend `tests/test_data_retention.py`
- Unit test with frozen clock and sample rows

## Dependencies

None.
