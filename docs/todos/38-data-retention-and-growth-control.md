# TODO 38: Data Retention and Growth Control

**Priority:** P4  
**Status:** ✅ Done  

---

## Solution

- Scheduled `cleanup_expired_programs` (daily) and `cleanup_old_health_checks` (weekly) in [`services/scheduler.py`](../../services/scheduler.py)
- `ChannelSyncService.prune_inactive_channel_tags` after each successful sync
- `health_check_retention_days` in [`models/health.py`](../../models/health.py) DEFAULTS
- Tests in [`tests/test_data_retention.py`](../../tests/test_data_retention.py)

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
