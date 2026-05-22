# TODO 14: Models Package Split

**Priority:** P3  
**Status:** ⬜ Not started  
**Estimated scope:** Large (multi-PR effort)

---

## Problem

`models/_core.py` is **2,063 lines** with ~41 models in a single file. `models/__init__.py` comment says "split package; imports from _core during migration" — migration was started but not finished.

Issues:
- Hard to navigate and review
- Merge conflicts frequent
- mypy/IDE performance suffers
- No domain boundaries in model layer

---

## Goal

Split models into logical modules while preserving `from models import X` public API.

---

## Proposed module structure

```
models/
├── __init__.py          # Re-export all public models (unchanged import path)
├── _base.py             # db instance, mixins, shared helpers
├── account.py           # Account, Credential, XtreamCredential, PlaylistConfig
├── channel.py           # Channel, Category, ChannelTag, Tag, TagRule, Filter, RuleSet
├── epg.py               # EpgSource, EpgChannel, EpgProgram, ChannelEpgMapping, ...
├── ppv.py               # Event, EventChannelLink, PPV enrichment tracking
├── fcc.py               # FccMatchNetwork, FccMatchChannelPattern, ...
├── sync.py              # SyncMetadata, Settings
└── health.py            # ChannelHealthStatus, ChannelHealthConfig
```

Exact grouping subject to review — aim for ~200–400 lines per file.

---

## Migration strategy

### PR 1: Infrastructure
- Create `_base.py` with `db` and declarative base
- Move 2–3 smallest models as proof of concept
- Ensure all tests pass, no import changes for consumers

### PR 2–N: Batch moves
- Move one domain per PR
- Update `__init__.py` re-exports after each batch
- Run full test suite each time

### Final PR
- Delete or thin `_core.py` to re-export-only shim (like service facades)
- Update ARCHITECTURE.md

---

## Constraints

- **Do not** change table names or column definitions in this refactor
- **Do not** break `from models import db, Channel, ...` imports
- Circular imports between model modules — use TYPE_CHECKING or late imports
- Update `migrations/` only if absolutely necessary (should not be)

---

## Files to modify

| File | Action |
|------|--------|
| `models/_core.py` | Gradually empty |
| `models/__init__.py` | Re-export from submodules |
| `models/*.py` | New domain files |
| `docs/ARCHITECTURE.md` | Document structure |

---

## Acceptance criteria

- [ ] No single model file >500 lines
- [ ] All existing imports work unchanged
- [ ] Full test suite passes
- [ ] mypy passes on models package
- [ ] `_core.py` deleted or reduced to deprecation shim

---

## Test plan

```bash
venv/bin/pytest tests/ -q --no-cov
venv/bin/mypy models/ app.py
```

---

## Dependencies

- TODO 09 (update models references) should be done first

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
