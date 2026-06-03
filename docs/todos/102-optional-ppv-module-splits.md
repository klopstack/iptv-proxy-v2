# PPV module splits (TODO 65 phases 2–3)

**Status:** ✅ Complete (Wave 9, PR batch **AA**)  
**Priority:** P3  
**Parent:** [65-refactor-enrichment-god-class.md](./65-refactor-enrichment-god-class.md) (phase 1 ✅ PR #35)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **AA**

## Summary

Follow-up to enrichment god-class phase 1: split `services/ppv/epg.py` (~620 lines) and `services/ppv/extraction.py` (~850 lines) using the same phased, test-green approach as phase 1.

## Problem

Phase 1 extracted `CalendarMatchPipeline`, `DetailFetchWorker`, and `EnrichmentSideEffects` from the enrichment coordinator. `epg.py` and `extraction.py` remained oversized god modules — harder to test and extend (e.g. multi-source, new date formats).

## Affected files

- `services/ppv/epg/` (package; replaces monolithic `epg.py`)
- `services/ppv/extraction/` (package; replaces monolithic `extraction.py`)
- `tests/ppv/test_enrichment*.py`, extraction/EPG-related tests

## Proposed solution

**Phase 2:** Split EPG XMLTV builder and sync-adjacent helpers into focused modules; thin facade in `epg/service.py`.

**Phase 3:** Extraction strategy objects per date format; reduce `extraction/extractor.py` surface.

One module per PR; no behavior change; assertion count must not drop.

## Acceptance criteria

- [x] Each phase reduces target file by meaningful amount with coordinator/facade < 300 lines where applicable
- [x] Full `tests/ppv/test_enrichment*.py` and related suites pass
- [x] New modules unit-testable without full enrichment stack

## Implementation notes

| Module | Role |
|--------|------|
| `epg/xmltv.py` | XMLTV builder |
| `epg/queries.py` | Event listing and detail queries |
| `epg/sync.py` | EpgSource / EpgChannel sync helpers |
| `epg/service.py` | `PPVEpgService` coordinator (~78 lines) |
| `extraction/patterns.py` | Regex constants |
| `extraction/competitors.py` | Team/matchup extraction |
| `extraction/date_strategies/` | Per-format date parsers (iso_paren, iso_pipe, iso_date, ddmm, pipe_weekday, month_day) |
| `extraction/extractor.py` | `PPVEventExtractor` coordinator (~271 lines) |

**Before:** `epg.py` 621 lines, `extraction.py` 844 lines.  
**After:** largest module `extractor.py` 271 lines; `epg/service.py` 78 lines.

## Test plan

```bash
venv/bin/pytest tests/ppv/ -q --no-cov
```

**Run:** 445 passed.

## Dependencies

- [65](./65-refactor-enrichment-god-class.md) phase 1 ✅ PR #35
- [66](./66-detail-thread-and-epg-side-effect-decoupling.md) ✅ PR #37
- Waves 2–3 PPV correctness ✅ — stable behavior before further splits

## Completion

- **PR #45:** https://github.com/klopstack/iptv-proxy-v2/pull/45 — `epg/` and `extraction/` package splits (Wave 9 batch **AA**)
