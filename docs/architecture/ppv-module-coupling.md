# PPV Module Coupling and Dependency Inversion

**Audit:** PPV audit, June 2026  
**Status:** Draft for review

## Overview

Several architectural choices in the PPV stack create testing friction, state divergence, and inverted dependencies. These are not blockers for daily operation but will compound as multi-source and provider count grows.

---

## Global singletons

| Singleton | Module | Risk |
|-----------|--------|------|
| `get_calendar_enrichment_service(app)` | `enrichment.py` | Owns ReverseEventMatcher instance + detail thread |
| `get_ppv_orchestrator(app)` | `orchestrator.py` | OK as app-scoped |
| `get_enhanced_ppv_matcher()` | `matching/enhanced.py` | Separate matcher state/cache |
| `get_reverse_matcher()` | `reverse_event_matcher/__init__.py` | May differ from enrichment's instance |
| `get_registry()` | `context/registry.py` | Provider list fixed at first call |

**Problem:** Enrichment constructs its own `ReverseEventMatcher`; enhanced matcher may use another. Calendar index caches can diverge within one process.

**Recommendation:**

- App-scoped service container on `Flask.extensions['ppv']` holding shared matcher + scraper
- `reset_ppv_services()` for tests
- Document singleton lifetime in developer guide

---

## Model layer imports services (inverted dependency)

`models/ppv.py` → `SportsTeam.home_timezone_for_team` imports:

- `services.ppv.city_timezone_map`
- `services.team_location_registry`

ORM models should not call service layers at runtime. This prevents testing models in isolation and risks circular imports as services import models.

**Recommendation:**

- Move all timezone resolution to `services/ppv/timezone_resolution.py`
- `SportsTeam` exposes data fields only; callers invoke service explicitly
- Deprecate `SportsTeam.home_timezone_for_team` classmethod with thin wrapper during migration

---

## Cross-domain coupling

| From | To | Issue |
|------|-----|-------|
| `channel_matching.py` | `services.epg.fcc.matching` | PPV pre-match uses FCC tag loader |
| `enrichment.py` | EPG sync + orphan prune | Matching tests must mock EPG |
| `filter_service.py` | `services.epg.ppv` | Legacy detection import path |
| `context/providers/thesportsdb.py` | `thesportsdb_service.py` | Duplicate API client paths |

**Recommendation:**

- Shared `channel_tags` service or inject tag resolver interface
- Post-enrichment hooks (TODO 66) for EPG side effects
- Unified TheSportsDB client module

---

## Thin public package vs large surface

`services/ppv/__init__.py` exports ~10 symbols; 30+ modules exist. Callers import internals ad hoc (`matching.context`, `channel_matching`, `persistence`).

**Recommendation:**

- Subpackage entrypoints: `services.ppv.matching`, `services.ppv.context`
- Or expand `__all__` with documented stable API
- Mark modules `_internal` in docstrings if not public

---

## Threading and Flask lifecycle

Detail fetch daemon thread holds one `app_context` for process lifetime. Conflicts with:

- SQLAlchemy scoped session in web workers
- Graceful shutdown
- Multi-worker deployments (duplicate detail threads per worker)

**Recommendation:** Scheduler/job queue per TODO 66; single worker owns detail fetch OR use distributed lock.

---

## Provider registration failures

`context/registry.py` catches import errors per provider and logs warning. Production may run missing ESPN/football-data without hard fail.

**Recommendation:** Expose `registry.coverage_report()` on status API; alert on empty provider set for enabled sports.

---

## Related TODOs

| TODO | Topic |
|------|-------|
| 53 | Detection module unification |
| 65 | God class split |
| 66 | Detail thread + EPG hooks |
| 67 | Provider health reporting |
| 58 | Model timezone inversion |
