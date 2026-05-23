# TODO 28: Harden Playlist Config API and Slug Routing

**Priority:** P2  
**Status:** ✅ Done  
**Estimated scope:** Medium

---

## Problem

Playlist config endpoints have two **consistency and performance gaps** left after CQS unification.

### Missing PUT validation

| Route | Validation |
|-------|------------|
| `POST /api/playlist-configs` | ✅ `@validate_request_data(PlaylistConfigCreateSchema)` |
| `PUT /api/playlist-configs/<id>` | ❌ Raw `request.json`; no schema |

`PlaylistConfigUpdateSchema` exists in `schemas.py` (lines ~242+) but is only whitelisted in `vulture_whitelist.py` — never applied.

Risk:
- Invalid `tag_match_mode` strings silently stored
- Overlapping include/exclude accounts not rejected on update
- Malformed JSON lists cause 500 instead of 400

### O(n) slug lookup

Slug routes scan **all** configs on every request:

```python
# routes/playlists.py — 3 call sites
configs = PlaylistConfig.query.all()
for c in configs:
    if slugify(c.name) == slug:
        ...
```

Affected routes:
- `GET /playlist/config/by-name/<slug>.m3u`
- `GET /epg/config/by-name/<slug>.xml`
- Likely slug resolution helpers for EPG/M3U by name

With tens of configs this is fine; with hundreds it becomes hot-path overhead on every TiviMate refresh.

### `slugify` lives in routes

`slugify()` is defined only in `routes/playlists.py`. No DB persistence — renaming a config **breaks bookmarked slug URLs**.

---

## Goal

Apply update schema validation; add indexed slug column (or slug field) for O(1) lookup; document slug stability rules.

---

## Proposed solution

### Part A: PUT validation

```python
@playlists_bp.route("/api/playlist-configs/<int:config_id>", methods=["PUT"])
@validate_request_data(PlaylistConfigUpdateSchema)
def update_playlist_config(config_id):
    data = request.validated_data
    ...
```

Handle partial updates via schema `partial=True` if needed (Marshmallow `partial` on load).

Add tests:
- Invalid `tag_match_mode` → 400
- Overlapping include/exclude tags → 400
- Valid partial update (name only) → 200

### Part B: Slug column migration

1. Migration: `playlist_configs.slug VARCHAR(220) UNIQUE NOT NULL`
2. Backfill: `slug = slugify(name)` for existing rows; handle collisions (`name-2`, etc.)
3. On create/update: recompute slug when name changes; optionally allow explicit slug override in API
4. Replace `query.all()` loops with `PlaylistConfig.query.filter_by(slug=slug).first()`

### Part C: Move slugify to shared util

`services/url_service.py` or `services/text_utils.py`:

```python
def slugify(text: str) -> str: ...
```

Import from routes and migration backfill script.

### Part D: API documentation

Document in route docstrings:
- Slug derived from name at save time
- Renaming config changes public URL unless slug field pinned

---

## Dependencies

- **Independent** of EPG/channel selection
- **After:** TODO 22 (doc sync)
- **Related:** TODO 29 (url_service consolidation)

---

## Files to modify

| File | Changes |
|------|---------|
| `routes/playlists.py` | PUT validation; slug query |
| `schemas.py` | Ensure `PlaylistConfigUpdateSchema` supports partial updates |
| `models/account.py` | Add `PlaylistConfig.slug` column |
| `migrations/2026_*_add_playlist_config_slug.py` | New migration + backfill |
| `tests/test_playlists_routes.py` | PUT validation tests |
| `tests/test_playlist_generation.py` | Slug lookup tests |
| `vulture_whitelist.py` | Remove schema whitelist if now used |

---

## Acceptance criteria

- [x] PUT uses `PlaylistConfigUpdateSchema`; invalid payloads return 400 with field errors
- [x] Slug routes use indexed DB lookup — no `query.all()` for slug resolution
- [x] Migration backfills slugs for existing configs; unique constraint enforced
- [x] Renaming config updates slug (or documented exception if slug pinned)
- [x] Tests cover validation errors and slug collision handling

---

## Test plan

```bash
venv/bin/pytest tests/test_playlists_routes.py tests/test_playlist_generation.py tests/test_schemas.py -v -k "playlist" --no-cov
```

---

## Simplifications unlocked

- Remove three O(n) loops in hot paths
- Consistent validation on create/update
- Stable slug URLs if product chooses immutable slug after create

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | PUT uses `PlaylistConfigUpdateSchema` with partial updates and overlap checks; added indexed `playlist_configs.slug` column + migration; moved slugify to `services/text_utils.py`; slug routes use `get_playlist_config_by_slug`; renaming updates slug with collision suffixes. |
