# Refactor PPV enrichment service (phased god-class split)

**Status:** ✅ Ready for review (Wave 8 / PR phase 1)  
**Priority:** P3  
**Audit:** PPV audit, June 2026

## Problem

`PPVCalendarEnrichmentService` in `services/ppv/enrichment.py` (~860 lines) is a god class owning:

- Channel extraction grouping
- Calendar I/O and caching
- Reverse event matching
- Direct persistence (bypassing `persist_match` — see TODO 54)
- Session/cumulative stats
- Background detail-fetch daemon thread
- TheSportsDB API updates
- LLM description enrichment
- EPG sync triggers after enrichment
- Orphan event pruning

This makes unit testing, multi-source extension (MiLB), and reasoning about side effects difficult. Tests patch heavily (`sync_ppv_epg_after_enrichment`, `prune_orphan_ppv_events`, reverse matcher).

Related: `services/ppv/epg.py` (~620 lines) and `services/ppv/extraction.py` (~850 lines) are similarly oversized.

## Affected files

- `services/ppv/enrichment/` (package; replaces monolithic `enrichment.py`)
- `services/ppv/epg.py` (optional phase 2)
- `services/ppv/extraction.py` (optional phase 3)
- All enrichment/orchestrator tests

## Proposed solution

**Phase 1 — Extract without behavior change:**

1. `CalendarMatchPipeline` — extract, classify, group, match, persist (via `persist_match`).
2. `DetailFetchWorker` — queue, rate limit, API update, LLM hook.
3. `EnrichmentSideEffects` — EPG sync, orphan prune (optional hooks — see TODO 65).
4. Thin `PPVCalendarEnrichmentService` coordinator wiring the above.

**Phase 2+:** Split EPG XMLTV builder; extraction strategy objects per date format.

Do **not** big-bang rewrite — each phase must keep tests green.

## Acceptance criteria

- [x] `enrichment.py` coordinator < 300 lines after phase 1 (`service.py` ~170 lines).
- [x] No behavior change in enrichment test suite.
- [x] Detail fetch and match pipeline independently instantiable in tests.

## Implementation notes (phase 1)

| Module | Role |
|--------|------|
| `enrichment/match_pipeline.py` | `CalendarMatchPipeline` |
| `enrichment/detail_fetch.py` | `DetailFetchWorker` |
| `enrichment/side_effects.py` | `EnrichmentSideEffects` |
| `enrichment/service.py` | `PPVCalendarEnrichmentService` coordinator |
| `enrichment/__init__.py` | Public API + patch targets (`sync_ppv_epg_after_enrichment`, etc.) |

## Test plan

- Full `tests/ppv/test_enrichment*.py` suite after each phase.
- No reduction in assertion count.

**Phase 1 run:** `venv/bin/pytest tests/ppv/test_enrichment*.py --no-cov` — 83 passed.

## Dependencies

- TODO 54, 55, 65 should precede or land with phase 1.
- See `docs/architecture/ppv-module-boundaries.md`.
