# PPV Architecture

PPV enrichment lives in `services/ppv/`. **This file is a quick reference; detailed architecture docs are in [`docs/architecture/`](architecture/).**

## Pipeline

1. **Sync** marks `Channel.is_ppv` from category patterns; new/changed PPV channels get `ppv_enrichment_status='queued'`.
2. **PPVEnrichmentOrchestrator** (hourly) selects enrichable channels and runs calendar-based matching via `PPVCalendarEnrichmentService`.
3. **PPVEventExtractor** + **channel_matching** infer UTC calendar days from channel names.
4. **Calendar scraper** loads TheSportsDB and MiLB (MLB Stats API) events per day.
5. **ReverseEventMatcher** scores channels against calendar events.
6. **persistence** creates `Event` + `EventChannelLink` records (enhanced fallback uses `persist_match`; calendar path should too — see TODO 54).
7. **Background detail queue** fetches full event data (TheSportsDB today; MiLB pending — see TODO 55).
8. **Context providers** + optional LLM enrich EPG descriptions.
9. **PPVVisibilityService** filters channels at playlist/Xtream read time.
10. **PPVEpgService** generates XMLTV from `Event` records (`ppv_events` EPG source).

## Event sources

| Source | Constant | Calendar | Detail fetch |
|--------|----------|----------|--------------|
| TheSportsDB | `Event.SOURCE_THESPORTSDB` | Yes | Yes |
| MLB Stats API (MiLB) | `Event.SOURCE_MLB_STATS` | Yes | Not yet |
| Manual / import | `SOURCE_MANUAL`, `SOURCE_IMPORT` | — | — |

## Public API

- `get_ppv_orchestrator(app)` — scheduler and `/api/ppv-enrichment/*`
- `PPVVisibilityService` — runtime visibility (`hide_all`, `hide_inactive`, `show_all`)
- `PPVEpgService` — event-based XMLTV

REST endpoints are under `/api/ppv-enrichment/` and `/api/ppv-epg/` (see TODO 59 / architecture doc for full list).

## Architecture docs (June 2026 audit)

| Document | Topic |
|----------|-------|
| [ppv-pipeline-and-module-map.md](architecture/ppv-pipeline-and-module-map.md) | Module map, status machine, scheduler |
| [ppv-matching-strategies.md](architecture/ppv-matching-strategies.md) | Calendar vs enhanced vs reverse matcher |
| [ppv-multi-source-events.md](architecture/ppv-multi-source-events.md) | Schema, detail fetch, MiLB |
| [ppv-module-coupling.md](architecture/ppv-module-coupling.md) | Singletons, inverted dependencies |
| [ppv-sport-registry.md](architecture/ppv-sport-registry.md) | Proposed sport key centralization |
| [ppv-documentation-gaps.md](architecture/ppv-documentation-gaps.md) | Stale docs inventory |

## Work items

See [`docs/todos/README.md`](todos/README.md) section **P5 — PPV audit (June 2026)** (TODOs 52–67).

Legacy `update_ppv_channel_visibility` and name-based `get_ppv_epg_xmltv` were removed.
