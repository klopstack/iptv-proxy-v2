# TODO 33: Error Handling and Logging Hygiene

**Priority:** P3  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (incremental)

---

## Problem

Broad exception handling hides failures and makes production debugging difficult. High `except Exception` counts:

| File | Approx. broad handlers |
|------|------------------------|
| `services/scheduler.py` | 17 |
| `services/image_cache_service.py` | 10 |
| `services/epg_sync_service.py` | 10 |
| `services/ffmpeg_stream_service.py` | 9 |
| `routes/accounts.py` | 7 |
| `services/epg_match_rules_service.py` | multiple |

### Antipatterns observed

```python
except Exception:
    pass  # silent failure
```

```python
except:
    return default  # catches KeyboardInterrupt in Python 2 style
```

Routes using `@handle_errors` decorator **plus** inner try/except that swallows errors before decorator sees them.

### Impact

- Sync/EPG jobs fail partially with no log trail
- Admin UI shows empty data instead of error state
- Tests pass because mocks never trigger exception paths

### Not all broad catches are wrong

Background scheduler loops may legitimately catch per-item errors to continue batch — but should **log at warning** with context.

---

## Goal

Audit high-traffic paths; replace silent catches with structured logging; narrow exception types where feasible.

---

## Proposed solution

### Phase 1: Inventory (automated)

```bash
rg "except Exception|except:" routes/ services/ --glob "*.py" -n
```

Classify each:
- **Fix** — silent pass → log + re-raise or return error JSON
- **Keep** — document why broad catch needed
- **Test** — add test triggering exception path

### Phase 2: Priority files (user-visible)

Fix first in order:

1. `routes/epg/match_rules.py` — admin match operations
2. `routes/api.py` — stats endpoints with swallowed errors
3. `services/epg/programs.py` — program parsing
4. `services/epg_match_rules_service.py` — FCC lookup failures

Pattern:

```python
except SpecificError as e:
    logger.warning("FCC lookup failed for %s: %s", callsign, e)
    return fallback
```

### Phase 3: Scheduler / background jobs

Keep broad catches but ensure:
- `logger.exception` for unexpected errors
- Per-item failure counted in job stats returned to UI

### Phase 4: Tests

Add tests that mock failures and assert:
- HTTP 5xx or structured error JSON (routes)
- Log output (caplog) or returned error dict (services)

---

## Dependencies

- **Independent** — can run parallel to test refactors
- **Easier after:** TODO 30 (smaller match rules modules)

---

## Files to modify

| File | Priority |
|------|----------|
| `routes/epg/match_rules.py` | High |
| `routes/api.py` | High |
| `services/epg/programs.py` | High |
| `services/epg_match_rules_service.py` | Medium |
| `services/scheduler.py` | Medium (log-only) |
| `services/image_cache_service.py` | Low |

---

## Acceptance criteria

- [ ] Zero bare `except:` (no exception type) in routes/
- [ ] Zero `except Exception: pass` in routes/ and services/epg/
- [ ] Each remaining broad catch has comment or log explaining continuation
- [ ] At least 5 new tests for previously silent failure paths

---

## Test plan

```bash
venv/bin/pytest tests/test_error_handling.py tests/test_epg_match_rules.py tests/test_api_routes.py -v --no-cov
rg "except:\s*$|except Exception:\s*pass" routes/ services/
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
