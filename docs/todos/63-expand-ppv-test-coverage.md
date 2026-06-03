# Expand PPV test coverage for orchestrator, cleanup, and providers

**Status:** ✅ Done ([PR #21](https://github.com/klopstack/iptv-proxy-v2/pull/21))  
**Priority:** P2  
**Audit:** PPV audit, June 2026

## Problem

Multiple PPV modules lack meaningful test coverage:

| Module | Gap |
|--------|-----|
| `services/ppv/orchestrator.py` | `_select_enrichable_batch`, adaptive batch sizes, `run_enhanced_fallback` — only mocked in drain tests |
| `services/ppv/queue_cleanup.py` | Route exists; no dedicated tests |
| `services/ppv/cleanup.py` | `prune_orphan_ppv_events` only asserted as mock in enrichment tests |
| `services/ppv/context/providers/football_data.py` | Route test checks settings field only; no HTTP/fixture tests |
| `services/ppv/preview.py` | Channel list API untested |
| `tests/test_ppv_integration.py` | Two tests (visibility + disabled setting); no pipeline test |

Additionally, enrichment tests (`tests/ppv/test_enrichment.py`) rely heavily on mocks — fragile for persistence/status regressions.

## Affected files

- New: `tests/ppv/test_orchestrator.py`, `tests/ppv/test_queue_cleanup.py`, `tests/ppv/test_cleanup.py`, `tests/ppv/test_football_data_provider.py`, `tests/ppv/test_preview.py`
- Extend: `tests/test_ppv_integration.py`, `tests/ppv/test_enrichment.py`

## Proposed solution

1. **Orchestrator:** DB fixtures for queue ordering, skip commits, max_scan cap, batch size selection.
2. **Queue cleanup:** dry_run vs commit, account filter.
3. **Cleanup:** Create orphan PPV event; assert EPG mapping removed after prune.
4. **Football data:** Fixture-based tests mirroring `test_espn_fighter_record.py`.
5. **Integration:** One mocked calendar scrape full pipeline with real reverse matcher + recorded events JSON.
6. **Enrichment:** Add at least one test with minimal mocking (real matcher + fixture calendar).

## Acceptance criteria

- [x] Each listed module has at least one behavior test (not import smoke).
- [x] Integration test runs orchestrator → enrichment → persist without patching core matchers.

## Completion

Implemented in [PR #21](https://github.com/klopstack/iptv-proxy-v2/pull/21): added `test_orchestrator.py`, `test_queue_cleanup.py`, `test_cleanup.py`, `test_football_data_provider.py`, `test_preview.py`; extended `test_ppv_integration.py` with `test_enrichment_pipeline_with_real_reverse_matcher` (real `ReverseEventMatcher`, mocked calendar HTTP only).

## Test plan

Self-contained.

## Dependencies

- TODO 60, 61, 62 can land first for foundation.
