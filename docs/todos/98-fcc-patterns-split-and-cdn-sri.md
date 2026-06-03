# FCC match patterns route split + CDN SRI (TODO 78 phase 4 + 92)

**Status:** ✅ Done  
**Priority:** P2 (route split) / P3 (SRI)  
**Parents:** [78-split-fat-route-modules.md](./78-split-fat-route-modules.md), [92-cdn-script-sri-hardening.md](./92-cdn-script-sri-hardening.md)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **X**

## Summary

Complete the fat-route program by extracting `routes/fcc_match_patterns.py` (~930 lines) using shared serializers, then harden admin CDN assets with Subresource Integrity (deferred from TODO 84).

## Problem

**FCC routes:** ~8 entity types with repetitive CRUD handlers; logic overlaps config export serialization (TODO 79 ✅) but routes remain bloated.

**CDN scripts:** `templates/base.html` loads Bootstrap and related assets from jsDelivr without `integrity` attributes. A compromised CDN could serve malicious JS to authenticated admin users (behind Authentik).

## Affected files

- `routes/fcc_match_patterns.py`
- `services/serializers/` or schemas from TODO 79
- `templates/base.html` (and other admin templates with external `<script>` / `<link>`)
- `static/` (optional vendoring)
- `docs/DEPLOYMENT.md` or frontend docs — CDN bump procedure

## Proposed solution

### Part A — FCC route extraction (78 phase 4)

1. Apply shared serializers / generic CRUD helper from TODO 79 where pattern tables match.
2. Move non-trivial logic to a small `FccMatchPatternsService` if any remains after serializer dedup.
3. Target ≥30% line reduction in `fcc_match_patterns.py`.

### Part B — CDN SRI (92)

1. Pin CDN URLs to specific versions already in use.
2. Add `integrity` and `crossorigin="anonymous"` on external script/link tags.
3. Prefer vendoring critical admin JS into `static/` where practical.
4. Document CDN update procedure when bumping versions.

## Acceptance criteria

- [x] FCC route module reduced ≥30%; behavior unchanged; CRUD tests pass
- [x] All external `<script>` / `<link>` tags in admin templates have SRI or are self-hosted
- [x] CDN version bump procedure documented

## Test plan

```bash
venv/bin/pytest tests/ -k "fcc" -q --no-cov
# Manual: load admin pages; verify no console SRI failures
# Optional: template lint or snapshot for integrity attributes
make test-fast
```

## Dependencies

- [79](./79-extract-shared-route-serializers.md) ✅ — FCC entity serialization
- [84](./84-docker-and-secrets-hardening.md) ✅ — SRI deferred to this item
- [83](./83-xss-audit-legacy-frontend.md) ✅ — related frontend safety track
- Batch **X** after batch **W** (96–97) recommended — FCC phase benefits from stable route-split patterns

## Completion

- **PR:** _(link added after merge)_
- `routes/fcc_match_patterns.py` 801 → 128 lines (−84%) via `FccMatchPatternsService` + `register_json_crud_routes`
- Shared serializers for country suffix / quality / country / callsign entities in `services/serializers/fcc.py`
- Bootstrap CDN SRI on `templates/base.html`; bump procedure in `docs/DEPLOYMENT.md`
- Tests: `tests/test_fcc_match_patterns_service.py`, `tests/test_cdn_sri.py`
