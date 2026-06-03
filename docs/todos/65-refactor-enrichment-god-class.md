# Refactor PPV enrichment service (phased god-class split)

**Status:** ⬜ Not started  
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

- `services/ppv/enrichment.py`
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

- [ ] `enrichment.py` coordinator < 300 lines after phase 1.
- [ ] No behavior change in enrichment test suite.
- [ ] Detail fetch and match pipeline independently instantiable in tests.

## Test plan

- Full `tests/ppv/test_enrichment*.py` suite after each phase.
- No reduction in assertion count.

## Dependencies

- TODO 54, 55, 65 should precede or land with phase 1.
- See `docs/architecture/ppv-module-boundaries.md`.
