# TODO 09: Update models.py References

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Small (docs + config files, no runtime logic)

---

## Problem

Models were moved from `models.py` to `models/_core.py` with re-exports in `models/__init__.py`, but several files still reference the old path:

| File | Issue |
|------|-------|
| `docker-compose.dev.yml` | Mounts `./models.py:/app/models.py` — file does not exist |
| `Makefile` | `mypy app.py models.py ...` and `vulture app.py models.py ...` |
| `README.md` | Project tree shows `models.py` |
| `DEV_SETUP.md` | References `./models.py` |
| `docs/ARCHITECTURE.md` | "models.py: 2,063 lines" |
| `docs/DEVELOPER_GUIDE.md` | `mypy app.py models.py` |
| `.github/copilot-instructions.md` | Same |

Docker dev mounts will create an **empty file** at `/app/models.py`, potentially breaking imports if Python resolves `models` incorrectly (package vs module conflict).

---

## Goal

All tooling, docs, and Docker configs reference `models/` package correctly.

---

## Proposed changes

### docker-compose.dev.yml

Replace:
```yaml
- ./models.py:/app/models.py
```

With:
```yaml
- ./models:/app/models
```

### Makefile

```makefile
MYPY_MODELS = models/
VULTURE_MODELS = models/

lint-py:
	$(MYPY) app.py $(MYPY_MODELS) services/ routes/

vulture:
	$(VULTURE) app.py $(VULTURE_MODELS) services/ routes/ ...
```

### Documentation

Update project tree in README:

```
├── models/
│   ├── __init__.py      # Re-exports
│   └── _core.py         # SQLAlchemy models
```

Update ARCHITECTURE.md, DEVELOPER_GUIDE.md, copilot-instructions similarly.

---

## Files to modify

| File | Changes |
|------|---------|
| `docker-compose.dev.yml` | Mount `models/` directory |
| `Makefile` | Update mypy/vulture paths |
| `README.md` | Project structure |
| `DEV_SETUP.md` | Path references |
| `docs/ARCHITECTURE.md` | Model location |
| `docs/DEVELOPER_GUIDE.md` | mypy command |
| `.github/copilot-instructions.md` | Model references |

---

## Acceptance criteria

- [ ] `make lint-py` runs without "file not found" for models
- [ ] `make vulture` runs successfully
- [ ] `docker-compose -f docker-compose.yml -f docker-compose.dev.yml up` starts without empty models mount
- [ ] No docs reference standalone `models.py` as current layout
- [ ] Optional: add note that `from models import X` import style is unchanged

---

## Test plan

```bash
make vulture
make lint-py  # or mypy portion only if full lint is slow

docker compose -f docker-compose.yml -f docker-compose.dev.yml config  # validate compose
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
