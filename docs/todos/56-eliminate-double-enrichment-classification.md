# Eliminate double `classify_ppv_enrichment` and redundant extraction

**Status:** ✅ Done ([PR #14](https://github.com/klopstack/iptv-proxy-v2/pull/14))  
**Priority:** P1  
**Audit:** PPV audit, June 2026

## Problem

PPV skip classification runs twice per channel on the hot path:

1. **`PPVEnrichmentOrchestrator._select_enrichable_batch`** — calls `classify_ppv_enrichment(channel.name)` while scanning the queue.
2. **`PPVCalendarEnrichmentService.enrich_channels`** — calls `classify_ppv_enrichment(ch.name)` again in the filter loop.

Each `classify_ppv_enrichment` call runs `PPVEventExtractor.extract_all()` (expensive regex/date inference). Channels that pass orchestrator selection are re-classified immediately in enrichment.

Additionally, `enrich_channels` runs `_extract_all_channels` **before** the classify filter, so extraction happens once explicitly and again inside classify.

## Affected files

- `services/ppv/orchestrator.py` — `_select_enrichable_batch`
- `services/ppv/enrichment.py` — `enrich_channels`, `_extract_all_channels`
- `services/ppv/enrichability.py` — `classify_ppv_enrichment`

## Proposed solution

1. **Option A (preferred):** Orchestrator marks skip reason on channel; enrichment trusts `skipped` status and only classifies channels not pre-filtered.
2. **Option B:** Pass precomputed `(channel, extraction, skip_reason)` tuples from orchestrator to enrichment.
3. Refactor `classify_ppv_enrichment` to accept optional precomputed extraction dict to avoid re-running `extract_all`.
4. Single extraction pass: extract once, classify once, group by date.

## Acceptance criteria

- [x] `extract_all` runs at most once per channel per enrichment batch.
- [x] Skip reasons and counts unchanged vs current behavior (regression test).
- [ ] Measurable reduction in CPU time for large batches (optional benchmark in test comment).

## Completion

Implemented in [PR #14](https://github.com/klopstack/iptv-proxy-v2/pull/14): orchestrator uses `classify_ppv_enrichment(..., cheap_only=True)`; enrichment passes precomputed extraction into classify; regression tests in `tests/ppv/test_enrichability.py`.

## Test plan

- Unit test with spy/mock on `PPVEventExtractor.extract_all` — assert call count ≤ channel count.
- Existing `tests/ppv/test_enrichability.py` and `test_enrichment_drain.py` must pass.

## Dependencies

None.
