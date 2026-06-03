# Optional PPV module splits (TODO 65 phases 2–3)

**Status:** ⬜ Not started (optional)  
**Priority:** P3  
**Parent:** [65-refactor-enrichment-god-class.md](./65-refactor-enrichment-god-class.md) (phase 1 ✅ PR #35)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **AA** (optional)

## Summary

Optional follow-up to enrichment god-class phase 1: split `services/ppv/epg.py` (~620 lines) and `services/ppv/extraction.py` (~850 lines) using the same phased, test-green approach as phase 1.

## Problem

Phase 1 extracted `CalendarMatchPipeline`, `DetailFetchWorker`, and `EnrichmentSideEffects` from the enrichment coordinator. `epg.py` and `extraction.py` remain oversized god modules — harder to test and extend (e.g. multi-source, new date formats).

## Affected files

- `services/ppv/epg.py`
- `services/ppv/extraction.py`
- `tests/ppv/test_enrichment*.py`, extraction/EPG-related tests

## Proposed solution

**Phase 2:** Split EPG XMLTV builder and sync-adjacent helpers into focused modules; thin facade in `epg.py`.

**Phase 3:** Extraction strategy objects per date format; reduce `extraction.py` surface.

One module per PR; no behavior change; assertion count must not drop.

## Acceptance criteria

- [ ] Each phase reduces target file by meaningful amount with coordinator/facade < 300 lines where applicable
- [ ] Full `tests/ppv/test_enrichment*.py` and related suites pass
- [ ] New modules unit-testable without full enrichment stack

## Test plan

```bash
venv/bin/pytest tests/ppv/ -q --no-cov
```

## Dependencies

- [65](./65-refactor-enrichment-god-class.md) phase 1 ✅ PR #35
- [66](./66-detail-thread-and-epg-side-effect-decoupling.md) ✅ PR #37
- Waves 2–3 PPV correctness ✅ — stable behavior before further splits
- **Optional:** defer if Wave 9 **W–Z** are higher priority; no blocker for 96–101

## Completion

_(Add PR link when merged.)_
