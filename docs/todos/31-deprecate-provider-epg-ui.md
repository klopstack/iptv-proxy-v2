# TODO 31: Deprecate Provider EPG in UI and Docs

**Priority:** P2  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (product + UI)

---

## Problem

Architecture docs mark **Provider EPG as legacy**:

```markdown
# docs/ARCHITECTURE.md
**Provider EPG (Legacy):**
- Direct passthrough from IPTV provider (deprecated)
```

But the admin UI **still promotes it** as a first-class option:

| Location | Copy |
|----------|------|
| `templates/epg_management.html` | "Manage EPG sources including **provider EPG**, Schedules Direct, and XMLTV grabbers" |
| Add source modal | `<option value="provider">IPTV Provider</option>` |
| Help bullets | "**Provider:** Use EPG data from your IPTV provider" |

Backend still supports provider EPG:
- `routes/epg/channels.py` — `create_account_epg_source` with type `provider`
- `services/epg/generation.py` — provider XMLTV passthrough path
- `routes/epg/channels.py` — sync uses live `IPTVService.get_xmltv` (acceptable for admin sync only)

### User confusion

Users may configure provider EPG expecting parity with Schedules Direct/XMLTV quality, while architecture steers toward SD + grabbers + generated EPG from `ChannelQueryService` channel set.

### Deprecated API surface

| Item | Location |
|------|----------|
| `POST /api/epg/match/<account_id>` | Redirects to rule-based matching (see TODO 23) |
| Provider sync on unsynced account | Partial error handling |

---

## Goal

Align UI and docs with architecture: de-emphasize or hide provider EPG; steer new setups to Schedules Direct, XMLTV grabbers, and filtered generated EPG.

---

## Proposed solution

### Step 1: Product decision (record in Completion)

| Option | Behavior |
|--------|----------|
| **A — Hide** | Remove provider from add-source dropdown; existing sources show "Legacy" badge |
| **B — Warn** | Keep option with prominent deprecation banner + link to migration guide |
| **C — Remove** | Delete provider source type (breaking — requires migration script) |

Recommend **B** short-term, **C** long-term after usage audit.

### Step 2: UI changes (`templates/epg_management.html`)

- Reorder source types: Schedules Direct, XMLTV grabber, Provider (legacy)
- Add `static/js/epg_sources.js` logic to show warning when `provider` selected
- Update help text to match ARCHITECTURE

### Step 3: API responses

Add `"deprecated": true` on provider source objects in list API (optional) for UI badge.

### Step 4: Documentation

- `docs/DEVELOPER_GUIDE.md` — when provider EPG is still valid (e.g., initial bootstrap)
- `README.md` — link to EPG setup recommendation

### Step 5: Tests

- One integration test: create provider source still works (backward compat)
- UI test optional (TODO 32): provider option shows warning

---

## Dependencies

- **After:** TODO 22 (doc sync)
- **Related:** TODO 23 (deprecated match endpoint)
- **Related:** TODO 24 (EPG route tests for source CRUD)

---

## Files to modify

| File | Changes |
|------|---------|
| `templates/epg_management.html` | Copy, ordering, warnings |
| `static/js/epg_sources.js` | Provider deprecation UX |
| `routes/epg/sources.py` | Optional `deprecated` flag in JSON |
| `docs/ARCHITECTURE.md` | Migration path |
| `docs/DEVELOPER_GUIDE.md` | Provider EPG section |
| `tests/test_epg_sources_routes.py` | After TODO 24 split |

---

## Acceptance criteria

- [ ] New users see clear guidance: SD/XMLTV/grabber preferred over provider
- [ ] Provider option either hidden, warned, or documented as legacy per chosen option
- [ ] Existing provider sources continue to work (no breaking change unless Option C)
- [ ] ARCHITECTURE and UI copy consistent

---

## Test plan

```bash
venv/bin/pytest tests/ -k "EpgSource" -v --no-cov
# Manual: open EPG management, verify provider UX
```

---

## Out of scope

- Removing provider generation code (unless Option C chosen)
- Migrating existing provider sources to SD automatically

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | Record chosen option A/B/C |
