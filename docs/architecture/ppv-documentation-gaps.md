# PPV Documentation Gaps

**Audit:** PPV audit, June 2026  
**Status:** Draft for review

## Summary

PPV documentation lags significantly behind implementation. Several docs reference removed or renamed components; the canonical architecture file is ~20 lines while the codebase grew MiLB support, context providers, LLM enrichment, team location registry, and multi-source events.

---

## Document inventory

| Document | Status | Issues |
|----------|--------|--------|
| `docs/PPV_ARCHITECTURE.md` | **Severely incomplete** | 20 lines; omits context, timezone, MiLB, enrichability, LLM, API surface |
| `docs/ARCHITECTURE.md` | **Stale** | References `PPVEnrichmentService`; events "from TheSportsDB" only |
| `docs/API_REFERENCE.md` | **Incomplete** | Only `GET /ppv-epg/{account_id}.xml`; missing `/api/ppv-enrichment/*` REST surface |
| `docs/DEVELOPER_GUIDE.md` | **Wrong imports** | Examples use `services.epg.ppv` instead of `services.ppv.detection` |
| `docs/ppv_timezone_analysis.md` | **Partial** | Strong methodology; "Production run (pending)" never filled |
| `services/ppv/extraction.py` header | **Stale** | Describes API-first "Direct Search" workflow |
| `services/ppv/enrichment.py` header | **OK** | Describes v2 calendar workflow |
| `.github/copilot-instructions.md` | **Stale** | Old service names (if present) |

---

## Missing documentation topics

1. **Full REST API** for `/api/ppv-enrichment/*` (status, process, queue, coverage, provider-settings, sportsipy refresh)
2. **Context provider registry** — how to add a provider, coverage_report, LLM prompt flow
3. **Team location pipeline** — `build_team_locations.py`, CI workflow, registry JSON files
4. **MiLB calendar path** — MLB Stats vs TheSportsDB division of responsibility
5. **`ppv_enrichment_status` state machine** — skip reasons, retry semantics
6. **Multi-source Event model** — see `ppv-multi-source-events.md`
7. **Matching strategy selection** — see `ppv-matching-strategies.md`
8. **Auth model** for PPV admin endpoints
9. **Test layout** — why reverse matcher tests live outside `tests/ppv/`

---

## Recommended doc structure after cleanup

```
docs/
  PPV_ARCHITECTURE.md          # Short entry point + links
  architecture/
    ppv-pipeline-and-module-map.md
    ppv-matching-strategies.md
    ppv-multi-source-events.md
    ppv-module-coupling.md
    ppv-sport-registry.md
    ppv-documentation-gaps.md  # this file → archive when done
  ppv_timezone_analysis.md     # operational runbook
  API_REFERENCE.md             # full PPV section
```

---

## Update checklist

- [ ] Expand `PPV_ARCHITECTURE.md` to link architecture/ docs and show pipeline diagram
- [ ] Fix `ARCHITECTURE.md` service names and multi-source event description
- [ ] Add PPV enrichment endpoints to `API_REFERENCE.md`
- [ ] Fix `DEVELOPER_GUIDE.md` import examples
- [ ] Align `extraction.py` module docstring with v2 pipeline
- [ ] Run timezone analysis script; fill production section or mark runbook-only
- [ ] Update copilot instructions if they reference old names
- [ ] Document deploy order for team location migrations + `build_team_locations.py`

---

## Related TODOs

- **53** — detection import paths in developer guide
- **59** — API auth documentation
- **67** — timezone analysis production section

Implementation TODOs do not replace architecture doc updates — docs should land alongside or immediately after P0 fixes so new contributors are not misled.
