# Post-Restructuring TODO Index

This directory contains detailed work items identified during the post-restructuring codebase audit (May 2026). Each document is self-contained: problem statement, affected files, proposed solution, acceptance criteria, and test plan.

**Open backlog (35 items):** see **[ROADMAP.md](./ROADMAP.md)** for waves, PR batches (A–U), dependencies, and parallel workstreams. Per-item specs stay in the linked TODO files below.

**Work through items in roadmap order** (or pick one explicitly). Later items may depend on earlier ones (especially P0 channel-selection unification — now ✅).

## Status legend

| Symbol | Meaning |
|--------|---------|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Done |

Update the status column in this index as each item is completed.

---

## P0 — User-visible correctness (do first)

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 01 | [01-unify-epg-channel-selection.md](./01-unify-epg-channel-selection.md) | ✅ | Route account + config EPG endpoints through `ChannelQueryService` so EPG matches M3U |
| 02 | [02-unify-preview-channel-selection.md](./02-unify-preview-channel-selection.md) | ✅ | Route preview APIs through `ChannelQueryService` (PPV visibility + filters) |
| 03 | [03-fix-playlist-config-preview-live-api.md](./03-fix-playlist-config-preview-live-api.md) | ✅ | Replace live IPTV API in playlist-config preview with database-first logic |
| 04 | [04-fix-tag-id-detection.md](./04-fix-tag-id-detection.md) | ✅ | Fix `ChannelQueryService` tag ID vs name detection when only exclude_tags are IDs |

## P1 — Important fixes and consistency

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 05 | [05-align-proxy-defaults.md](./05-align-proxy-defaults.md) | ✅ | Align default `proxy=` behavior between single-account and config M3U |
| 06 | [06-fix-thesportsdb-league-ids.md](./06-fix-thesportsdb-league-ids.md) | ✅ | Replace placeholder US league IDs in TheSportsDB integration |
| 07 | [07-fix-test-db-isolation.md](./07-fix-test-db-isolation.md) | ✅ | Prevent corrupted/stale test DB from breaking the suite |
| 08 | [08-add-epg-m3u-parity-tests.md](./08-add-epg-m3u-parity-tests.md) | ✅ | Contract tests: same channel set for M3U, EPG, Xtream, previews |

## P2 — Developer experience and deduplication

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 09 | [09-update-models-py-references.md](./09-update-models-py-references.md) | ✅ | Fix Makefile, Docker, docs referencing deleted `models.py` |
| 10 | [10-deduplicate-channel-processing.md](./10-deduplicate-channel-processing.md) | ✅ | Extract shared tag-loading and duplicate-collapse helpers |
| 11 | [11-test-hygiene.md](./11-test-hygiene.md) | ✅ | Remove 26 skipped legacy tests; consolidate fixtures in conftest |
| 12 | [12-ui-and-nav-cleanup.md](./12-ui-and-nav-cleanup.md) | ✅ | Nav links, `/test` route naming, artifact cleanup |

## P3 — Optional / longer-term

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 13 | [13-coverage-test-audit.md](./13-coverage-test-audit.md) | ✅ | Audit and trim coverage-padding test modules |
| 14 | [14-models-package-split.md](./14-models-package-split.md) | ✅ | Continue splitting `models/_core.py` into domain modules |
| 15 | [15-facade-layer-consolidation.md](./15-facade-layer-consolidation.md) | ✅ | Gradually remove backward-compat service facades |
| 16 | [16-frontend-tests.md](./16-frontend-tests.md) | ✅ | Add minimal JS/HTML lint test coverage |

## P1–P2 — Remaining structural deduplication (post-TODO 08 audit)

These items close gaps where **behavioral parity exists** (TODO 08 tests) but **parallel implementations remain** in route code. Not fully covered by TODO 10 alone.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 17 | [17-route-preview-through-cqs.md](./17-route-preview-through-cqs.md) | ✅ | Preview endpoints call CQS entry points, not inline FilterService + PPV |
| 18 | [18-config-epg-collapse-duplicates.md](./18-config-epg-collapse-duplicates.md) | ✅ | Add `?collapse_duplicates=true` to config EPG (parity with config M3U) |
| 19 | [19-extract-m3u-generation-helper.md](./19-extract-m3u-generation-helper.md) | ✅ | Shared M3U EXTINF/URL formatting for account vs config routes |
| 20 | [20-align-admin-visible-channel-semantics.md](./20-align-admin-visible-channel-semantics.md) | ✅ | Align or document filter-only counts in stats/categories/EPG admin APIs |
| 21 | [21-remove-dead-channel-selection-code.md](./21-remove-dead-channel-selection-code.md) | ✅ | Remove `_matches_tag_filter`, orphan tests, sync stale todo statuses |

---

## Dependencies between items (first pass — complete)

All P0–P3 items **01–21** are ✅. The graph below is kept for historical context.

```
01-unify-epg ──────────┐
02-unify-preview ──────┼──► 08-parity-tests ──► 17-preview-through-cqs ──► 20-admin-visible-semantics
03-config-preview ─────┤                      └──► 21-dead-code-cleanup
04-tag-id-detection ───┘

01 + 02 ──► 10-deduplicate-channel-processing ──► 18-config-epg-collapse, 19-m3u-format-helper

09-models-py-refs ── (independent)

07-test-db-isolation ──► 08 (reliable CI)
```

---

## P1–P3 — Second-pass audit (May 2026)

Follow-up audit after TODOs 01–21. Focus: dead shims, test duplication, semantic footguns, missing backend coverage, UI/doc drift.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 22 | [22-audit-index-and-doc-sync.md](./22-audit-index-and-doc-sync.md) | ✅ | Sync stale index (incl. TODO 18 ✅), fix misleading docstrings |
| 23 | [23-remove-backward-compat-shims.md](./23-remove-backward-compat-shims.md) | ✅ | Delete 6 facade shims, `models/_core.py`, `account_xml_cache` param |
| 24 | [24-consolidate-epg-route-tests.md](./24-consolidate-epg-route-tests.md) | ✅ | Merge 3 overlapping EPG route test modules (~2,700 lines) |
| 25 | [25-refactor-epg-service-and-phase-tests.md](./25-refactor-epg-service-and-phase-tests.md) | ✅ | Split `test_epg_service.py` (3.4k lines); rename phase-era tests |
| 26 | [26-mediaflow-stream-backend-tests.md](./26-mediaflow-stream-backend-tests.md) | ✅ | Test stream factory + MediaFlow service (zero tests today) |
| 27 | [27-clarify-is-visible-semantics.md](./27-clarify-is-visible-semantics.md) | ✅ | Resolve `is_visible` cache vs live filters; channel health UI |
| 28 | [28-playlist-config-hardening.md](./28-playlist-config-hardening.md) | ✅ | PUT schema validation; indexed slug column (replace O(n) scan) |
| 29 | [29-deduplicate-shared-helpers.md](./29-deduplicate-shared-helpers.md) | ✅ | Single `get_iptv_service_for_account`; Xtream CQS cleanup |
| 30 | [30-split-epg-match-rules-service.md](./30-split-epg-match-rules-service.md) | ✅ | Split 2k-line `epg_match_rules_service.py` into `services/epg/match_rules/` |
| 31 | [31-deprecate-provider-epg-ui.md](./31-deprecate-provider-epg-ui.md) | ✅ | Align EPG management UI with deprecated provider EPG |
| 32 | [32-expand-frontend-js-tests.md](./32-expand-frontend-js-tests.md) | ✅ | Extend Vitest beyond 2 files / 18 JS modules |
| 33 | [33-error-handling-and-logging-hygiene.md](./33-error-handling-and-logging-hygiene.md) | ✅ | Replace silent `except` blocks in routes/services |
| 34 | [34-post-cleanup-simplifications.md](./34-post-cleanup-simplifications.md) | ✅ | Final layer removal after 22–33 (EpgService facade, FilterService) |

### Recommended order for items 22–34

```
22-doc-sync ──► 23-shim-removal ──► 34-simplifications
     │                │
     ├──► 24-epg-route-tests ──► 31-provider-epg-ui
     ├──► 25-epg-service-tests
     ├──► 26-mediaflow-tests
     ├──► 27-is-visible ──► 34-simplifications
     ├──► 28-playlist-config
     ├──► 29-shared-helpers ──► 34-simplifications
     ├──► 30-match-rules-split
     ├──► 32-frontend-tests
     └──► 33-error-handling
```

**Highest impact first:** 22 (truth in docs) → 26 (untested MediaFlow) → 27 (visibility semantics) → 24 (CI time / maintainability).

---

## P4 — Database hardening (May 2026)

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 35 | [35-referential-integrity-and-account-delete.md](./35-referential-integrity-and-account-delete.md) | ✅ | FK pragma, AccountDeleteService, model ondelete alignment |
| 36 | [36-schema-lifecycle-and-migration-tracking.md](./36-schema-lifecycle-and-migration-tracking.md) | ✅ | schema_migrations table, create_all+migrate boot, playlist_configs migration |
| 37 | [37-sync-lock-hardening.md](./37-sync-lock-hardening.md) | ✅ | Atomic sync lock, sync_started_at, stale lock recovery |
| 38 | [38-data-retention-and-growth-control.md](./38-data-retention-and-growth-control.md) | ✅ | EPG/health cleanup scheduler, prune inactive channel_tags |
| 39 | [39-indexing-test-parity-and-docs.md](./39-indexing-test-parity-and-docs.md) | ✅ | channel_tags index, schema parity tests, developer docs |

## P1–P2 — EPG sync orchestration follow-up (May 2026)

Audit of parallel EPG sync + per-source progress (orchestrator, `EpgSyncProgress`, settings UI). Items **40–51** address correctness bugs, integration gaps, test holes, and duplicated tests.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 40 | [40-epg-sync-last-sync-on-failure.md](./40-epg-sync-last-sync-on-failure.md) | ✅ | Do not advance `last_sync` when per-source sync fails |
| 41 | [41-epg-sync-global-metadata-on-failure.md](./41-epg-sync-global-metadata-on-failure.md) | ✅ | Do not set global `last_epg_sync` when all sources fail |
| 42 | [42-epg-bulk-sync-concurrency-guard.md](./42-epg-bulk-sync-concurrency-guard.md) | ✅ | Atomic `sync_in_progress` / skip overlapping scheduler + API sync |
| 43 | [43-per-source-epg-sync-orchestrator.md](./43-per-source-epg-sync-orchestrator.md) | ✅ | Route `POST /api/epg/sources/<id>/sync` through orchestrator + progress |
| 44 | [44-epg-sources-page-progress-ui.md](./44-epg-sources-page-progress-ui.md) | ✅ | Show live sync progress on EPG sources page (not only Settings) |
| 45 | [45-ppv-events-epg-progress-callbacks.md](./45-ppv-events-epg-progress-callbacks.md) | ✅ | Wire `progress` through `sync_ppv_events_source` |
| 46 | [46-schedules-direct-program-progress.md](./46-schedules-direct-program-progress.md) | ✅ | Granular programme counters for SD program sync |
| 47 | [47-epg-sync-phase-skipped.md](./47-epg-sync-phase-skipped.md) | ✅ | Implement or remove unused `PHASE_SKIPPED` |
| 48 | [48-epg-sync-failure-semantics-tests.md](./48-epg-sync-failure-semantics-tests.md) | ✅ | Contract tests for `last_sync` + global metadata on failure |
| 49 | [49-epg-orchestrator-integration-tests.md](./49-epg-orchestrator-integration-tests.md) | ✅ | Orchestrator + real `EpgSyncService` (mocked HTTP) integration tests |
| 50 | [50-fix-stale-scheduler-epg-tests.md](./50-fix-stale-scheduler-epg-tests.md) | ✅ | Fix `_sync_epg_sources` stale mock; `run_scheduler` smoke tests |
| 51 | [51-consolidate-bulk-epg-sync-api-tests.md](./51-consolidate-bulk-epg-sync-api-tests.md) | ✅ | Merge duplicate `POST /api/sync/epg` tests into one module |

### Recommended order for items 40–51

```
40-last-sync ──┬──► 48-failure-tests
41-metadata ───┘
42-concurrency ──► 47-skipped (optional) ──► 43-per-source-route ──► 44-sources-ui
45-ppv-progress ──► 46-sd-progress (independent)
49-integration-tests (after 40–43)
50-scheduler-tests
51-dedupe-api-tests (anytime)
```

**Highest impact first:** 40 → 41 → 48 (correct retry + honest status) → 42 → 43 (safe concurrent sync + unified entry points).

---

## P5 — PPV audit (June 2026)

Full-stack review of PPV handling: enrichment pipeline, multi-source events (MiLB), context providers, tests, and documentation. Architectural findings live in [`docs/architecture/`](../architecture/) for separate review.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 52 | [52-fix-details-fetched-stat.md](./52-fix-details-fetched-stat.md) | ⬜ | `details_fetched` cumulative stat is never incremented |
| 53 | [53-unify-ppv-detection-modules.md](./53-unify-ppv-detection-modules.md) | ⬜ | Consolidate `services/epg/ppv.py` and `services/ppv/detection.py` |
| 54 | [54-route-enrichment-through-persist-match.md](./54-route-enrichment-through-persist-match.md) | ⬜ | Calendar path bypasses `persist_match`; fix counters and link errors |
| 55 | [55-multi-source-events-schema-and-detail-fetch.md](./55-multi-source-events-schema-and-detail-fetch.md) | ⬜ | Composite `(external_id, source)` unique; MiLB detail fetch |
| 56 | [56-eliminate-double-enrichment-classification.md](./56-eliminate-double-enrichment-classification.md) | ⬜ | Stop running `classify_ppv_enrichment` + `extract_all` twice per channel |
| 57 | [57-centralize-sport-key-mappings.md](./57-centralize-sport-key-mappings.md) | ⬜ | Single sport registry for timezone, context, matching |
| 58 | [58-fix-team-resolution-and-validation.md](./58-fix-team-resolution-and-validation.md) | ⬜ | Substring team matching, WNBA in SPORTS, validation alignment |
| 59 | [59-harden-ppv-enrichment-routes.md](./59-harden-ppv-enrichment-routes.md) | ⬜ | Error handling, memory footgun, queue stats logging |
| 60 | [60-add-persistence-unit-tests.md](./60-add-persistence-unit-tests.md) | ⬜ | Unit tests for `services/ppv/persistence.py` |
| 61 | [61-add-channel-matching-tests.md](./61-add-channel-matching-tests.md) | ⬜ | Unit tests for UTC calendar-day grouping |
| 62 | [62-add-milb-ppv-integration-test.md](./62-add-milb-ppv-integration-test.md) | ⬜ | End-to-end MiLB channel → Event with `mlb_stats_api` source |
| 63 | [63-expand-ppv-test-coverage.md](./63-expand-ppv-test-coverage.md) | ⬜ | Orchestrator, cleanup, football-data provider, integration |
| 64 | [64-consolidate-ppv-detection-tests.md](./64-consolidate-ppv-detection-tests.md) | ⬜ | Deduplicate overlapping detection test modules |
| 65 | [65-refactor-enrichment-god-class.md](./65-refactor-enrichment-god-class.md) | ⬜ | Phased split of ~860-line enrichment service |
| 66 | [66-detail-thread-and-epg-side-effect-decoupling.md](./66-detail-thread-and-epg-side-effect-decoupling.md) | ⬜ | Replace daemon detail thread; optional EPG hooks |
| 67 | [67-ppv-misc-cleanup.md](./67-ppv-misc-cleanup.md) | ⬜ | Constants, heuristics validation, provider health, docstrings |

### Recommended order for items 52–67

```
52-details-stat ──► 54-persist-match ──► 60-persistence-tests
53-detection-unify ──► 64-test-dedup
55-multi-source ──► 62-milb-e2e
56-no-double-classify
57-sport-registry ──► 58-team-validation
59-route-hardening
61-channel-matching-tests
63-test-expansion
65-god-class-split ──► 66-detail-thread-decouple
67-misc-cleanup (anytime)
```

**Architecture review (before large refactors):** [ppv-pipeline-and-module-map.md](../architecture/ppv-pipeline-and-module-map.md), [ppv-matching-strategies.md](../architecture/ppv-matching-strategies.md), [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md), [ppv-module-coupling.md](../architecture/ppv-module-coupling.md), [ppv-sport-registry.md](../architecture/ppv-sport-registry.md), [ppv-documentation-gaps.md](../architecture/ppv-documentation-gaps.md)

**Highest impact first:** 52 → 55 → 54 → 53 → 60 → 62 (correct metrics, multi-source correctness, unified persistence, then tests).

### P5 findings summary

**Bugs / misleading behavior:**
- `details_fetched` stat never written (52)
- `events_created` counts updates (54)
- Detail fetch TSDB-only; MiLB events orphaned in detail queue (55)
- Possible `external_id` global unique vs multi-source (55)

**Structural debt:**
- Duplicate PPV detection modules (53)
- Calendar enrichment bypasses `persist_match` (54)
- Double extraction/classification per channel (56)
- Sport keys duplicated in 4+ modules (57)
- ~860-line enrichment god class (65)
- Three overlapping matching pipelines (architecture doc)

**Test gaps:**
- No tests for `persistence.py`, `channel_matching.py` (60, 61)
- No MiLB PPV E2E (62)
- Heavy mock reliance in enrichment tests (63)

**Documentation:**
- `PPV_ARCHITECTURE.md` ~20 lines; API reference incomplete (see architecture/ppv-documentation-gaps.md)

---

## P6 — Application-wide audit (June 2026)

Routes, services (EPG/sync/scheduler/CQS), models/migrations, frontend, CI, and non-PPV documentation. Architectural findings in [`docs/architecture/`](../architecture/).

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 68 | [68-document-proxy-authentication-model.md](./68-document-proxy-authentication-model.md) | ✅ | Document Traefik + Authentik auth (klopstack); remove fictitious `/login` |
| 69 | [69-lock-down-destructive-admin-endpoints.md](./69-lock-down-destructive-admin-endpoints.md) | ⬜ | App-level hardening: FCC reset CLI-only, SSRF, import validation (not Flask auth) |
| 70 | [70-fix-is-visible-epg-matching-bug.md](./70-fix-is-visible-epg-matching-bug.md) | ✅ | EPG matching uses stale `is_visible` instead of live filters |
| 71 | [71-fix-scheduler-sync-status-semantics.md](./71-fix-scheduler-sync-status-semantics.md) | ✅ | Account sync always "success"; job timestamps advance on failure |
| 91 | [91-scheduler-status-api-failure-metadata.md](./91-scheduler-status-api-failure-metadata.md) | ⬜ | Status API + SyncMetadata for per-job scheduler failures (deferred from 71) |
| 72 | [72-standardize-api-error-handling.md](./72-standardize-api-error-handling.md) | ⬜ | `@handle_errors` on ~30–40% of routes; extends TODO 33 |
| 73 | [73-standardize-api-response-shapes.md](./73-standardize-api-response-shapes.md) | ⬜ | Inconsistent success/error JSON envelopes |
| 74 | [74-remove-dead-routes-and-dangerous-patterns.md](./74-remove-dead-routes-and-dangerous-patterns.md) | ✅ | Dead blueprint, duplicate FCC/categories endpoints |
| 75 | [75-fix-side-effect-get-account-categories.md](./75-fix-side-effect-get-account-categories.md) | ✅ | GET categories triggers upstream IPTV fetch |
| 76 | [76-deduplicate-epg-sync-infrastructure.md](./76-deduplicate-epg-sync-infrastructure.md) | ⬜ | Program persistence, sync locks, EAST/WEST constants |
| 77 | [77-centralize-tag-loading-and-category-sync-policy.md](./77-centralize-tag-loading-and-category-sync-policy.md) | ⬜ | Tag loader N+1; category sync failure policy |
| 78 | [78-split-fat-route-modules.md](./78-split-fat-route-modules.md) | ⬜ | Phased extraction from 500–1500 line route files |
| 79 | [79-extract-shared-route-serializers.md](./79-extract-shared-route-serializers.md) | ⬜ | Shared CRUD serializers and Marshmallow schemas |
| 80 | [80-align-test-db-with-production-schema.md](./80-align-test-db-with-production-schema.md) | ⬜ | pytest `create_all` skips migration-only indexes |
| 81 | [81-model-fk-ondelete-alignment.md](./81-model-fk-ondelete-alignment.md) | ⬜ | FK ondelete drift; migration FK pragma |
| 82 | [82-scheduled-data-retention.md](./82-scheduled-data-retention.md) | ⬜ | Events and cached images grow unbounded |
| 83 | [83-xss-audit-legacy-frontend.md](./83-xss-audit-legacy-frontend.md) | ⬜ | innerHTML with API data in legacy JS + TagSelector |
| 84 | [84-docker-and-secrets-hardening.md](./84-docker-and-secrets-hardening.md) | ✅ | `.dockerignore`, non-root container, Flask sessions disabled (no SECRET_KEY) |
| 85 | [85-frontend-deduplication-and-esm-migration.md](./85-frontend-deduplication-and-esm-migration.md) | ⬜ | escapeHtml/loadAccounts/datetime dupes; epg_management migration |
| 86 | [86-web-smoke-tests-and-pytest-consolidation.md](./86-web-smoke-tests-and-pytest-consolidation.md) | ⬜ | Admin page smoke tests; duplicate pytest fixtures |
| 87 | [87-fix-stale-documentation.md](./87-fix-stale-documentation.md) | ⬜ | API_REFERENCE auth/Xtream URLs; missing P4 todo files |
| 88 | [88-expand-ci-quality-gates.md](./88-expand-ci-quality-gates.md) | ⬜ | vulture, Docker build on PR, pre-commit tests |
| 89 | [89-refactor-scheduler-job-registry.md](./89-refactor-scheduler-job-registry.md) | ⬜ | Split 676-line scheduler god class |
| 90 | [90-split-epg-programs-and-decouple-sync.md](./90-split-epg-programs-and-decouple-sync.md) | ⬜ | Split programs.py; decouple sync post-processing |
| 92 | [92-cdn-script-sri-hardening.md](./92-cdn-script-sri-hardening.md) | ⬜ | CDN Subresource Integrity (deferred from 84) |

### Recommended order for items 68–90

```
70-is-visible-bug ──► 71-scheduler-semantics ──► 91-scheduler-failure-status-api
68-doc-proxy-auth ✅ (see DEPLOYMENT.md)
69-destructive-endpoint-hardening (parallel with 68)
84-docker-secrets
72-errors ──► 73-response-shapes
76-epg-dedup ──► 77-tag-loading
80-schema-test-parity ──► 81-fk-alignment
83-xss ──► 85-frontend-dedup
87-docs-sync
89-scheduler-refactor ──► 90-epg-split (architecture review first)
78-fat-routes ──► 79-serializers
```

**Architecture review:** [admin-auth-and-deployment-security.md](../architecture/admin-auth-and-deployment-security.md), [api-contract-errors-and-responses.md](../architecture/api-contract-errors-and-responses.md), [channel-visibility-is-visible.md](../architecture/channel-visibility-is-visible.md), [scheduler-and-sync-orchestration.md](../architecture/scheduler-and-sync-orchestration.md), [epg-service-architecture.md](../architecture/epg-service-architecture.md), [frontend-architecture-debt.md](../architecture/frontend-architecture-debt.md), [schema-lifecycle-and-test-parity.md](../architecture/schema-lifecycle-and-test-parity.md), [api-layer-and-fat-routes.md](../architecture/api-layer-and-fat-routes.md)

**Highest impact first (open work):** see [ROADMAP.md](./ROADMAP.md) — Wave 2 PPV (52–55) → 91. Wave 1 complete (69, 84, 75, 74). Auth docs: ✅ 68 + [DEPLOYMENT.md](../DEPLOYMENT.md). Scheduler semantics: ✅ 71.

### P6 findings summary

**Critical bugs (fixed):**
- ~~EPG auto-matching ignores live filter return value~~ (70 ✅)
- ~~Scheduler marks failed syncs success; timestamps advance on failure~~ (71 ✅)
- Scheduler status API lacks per-job failure metadata (91 — see [ROADMAP](./ROADMAP.md) Wave 4)

**Security:**
- Admin auth via Traefik + Authentik — documented in [DEPLOYMENT.md](../DEPLOYMENT.md) (TODO 68 ✅)
- Destructive HTTP endpoints including DROP TABLE — harden in 69 even behind proxy
- XSS in legacy frontend (83)
- Docker secrets/build context (84)

**Structural debt:**
- Fat route modules up to 1500 lines (78)
- Scheduler + programs.py + ChannelQueryService god classes (89, 90)
- Duplicate EPG sync infrastructure (76)
- Test DB diverges from production schema (80)

**Documentation:**
- API_REFERENCE fictitious auth and wrong Xtream URLs (87)
- README links to missing P4 todo files 35–39

## How to use these documents

1. Open the next ⬜ item in order (or pick one explicitly).
2. Read the full document before coding.
3. Implement only what that document specifies — avoid scope creep.
4. Run the test plan listed in the document.
5. Mark the item ✅ in this index and note the commit/PR in the document's **Completion** section.

## Audit source

These items were derived from full codebase reviews covering:
- **First pass (TODOs 01–21):** EPG/M3U/preview divergence, parity tests, deduplication, UI/nav cleanup
- **Second pass (TODOs 22–34):** Dead shims, test monoliths, MediaFlow gaps, `is_visible` semantics, provider EPG UI drift, silent error handling
- **Third pass (TODOs 40–51):** EPG sync orchestration, failure semantics, progress UI
- **Fourth pass (TODOs 52–67):** PPV enrichment pipeline, multi-source events, test gaps, documentation (June 2026)
- **Fifth pass (TODOs 68–90):** Auth/security, EPG matching bug, scheduler semantics, API consistency, EPG/sync dedup, schema parity, frontend/CI (June 2026)

### Second-pass findings summary (healthy vs debt)

**Healthy (guarded by tests):**
- Channel selection unified via `ChannelQueryService` for M3U, EPG, Xtream, previews
- Parity contract tests in `tests/test_channel_output_parity.py`
- Config EPG `collapse_duplicates` implemented (TODO 18 — index was stale)
- Models package split; proxy defaults aligned; admin visible counts use CQS (TODO 20)

**Remaining debt (EPG sync orchestration — see 40–51):**
- ~~Failed sync advances `last_sync` and global `last_epg_sync` metadata~~ (fixed in 40–41)
- ~~Per-source sync bypasses orchestrator/progress; progress UI only on Settings~~ (fixed in 43)
- ~~Bulk sync can overlap scheduler; no EPG stale-lock recovery~~ (fixed in 42)
- ~~Duplicate `POST /api/sync/epg` tests; stale `_sync_epg_sources` scheduler mock~~ (fixed in 50–51)
- ~~Orchestrator integration tests only mocked `sync_source`~~ (fixed in 49)

**Other remaining debt:**
- EPG test modules remain large (~2.7k lines across orchestrator/service/route tests); further consolidation optional
- `is_visible` column semantics contradict FilterService docstrings (TODO 27 documents admin-only use)
- Playlist config PUT lacks schema validation; slug lookup is O(n)
- Provider EPG de-emphasized in UI with deprecation warnings (TODO 31 ✅)
- Vitest coverage expanded across lib helpers (TODO 32 ✅)
- MediaFlow/stream-factory tests added (TODO 26 ✅)
- PPV audit remediation (52–67) and app-wide backlog (69–91): see [ROADMAP.md](./ROADMAP.md)
