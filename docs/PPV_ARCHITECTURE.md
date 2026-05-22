# PPV Architecture

PPV enrichment lives in `services/ppv/`.

## Pipeline

1. **Sync** marks `Channel.is_ppv` from category patterns; new/changed PPV channels get `ppv_enrichment_status='queued'`.
2. **PPVEnrichmentOrchestrator** (hourly) runs calendar-based matching via `PPVCalendarEnrichmentService`.
3. **ReverseEventMatcher** matches channel names to calendar events.
4. **persistence** creates `Event` + `EventChannelLink` records.
5. **PPVVisibilityService** filters channels at playlist/Xtream read time.
6. **PPVEpgService** generates XMLTV from `Event` records (`ppv_events` EPG source).

## Public API

- `get_ppv_orchestrator(app)` — scheduler and `/api/ppv-enrichment/*`
- `PPVVisibilityService` — runtime visibility (`hide_all`, `hide_inactive`, `show_all`)
- `PPVEpgService` — event-based XMLTV

Legacy `update_ppv_channel_visibility` and name-based `get_ppv_epg_xmltv` were removed.
