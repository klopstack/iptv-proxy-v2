# Post-merge manual smoke test checklist

**Scope:** Waves 1–9 plus TODOs 104 and 105, after all related PRs are merged.  
**Not in scope:** Wave 10 doc-only review (TODO 101).

Use this after deploy or local upgrade — CI covers most behavior; these steps catch UI wiring, envelope regressions, and operator-facing surprises.

---

## How to use

### Recommended order

1. **Environment sanity** — app starts, admin auth works, browser console clean (SRI).
2. **Admin page load** — all 12 pages return 200 and render (TODO 86).
3. **Core workflows** — accounts → EPG → match rules → PPV → settings/scheduler.
4. **API envelope spot checks** — filters, settings, playlists after TODOs 72/73.
5. **Security / XSS** — quick negative tests.
6. **Sign-off** — record environment and notes at the bottom.

### Environment setup

| Mode | Steps |
|------|--------|
| **Docker (production-like)** | From repo root: `docker compose up -d` (or klopstack stack). Confirm admin URL loads behind Traefik. |
| **Local dev** | `make install` once, then `make run` (or `flask run`). Uses `instance/` SQLite by default. |

**Auth:** Admin UI and `/api/*` expect **Traefik + Authentik** in production ([DEPLOYMENT.md](./DEPLOYMENT.md)). Local dev is usually unauthenticated. Log in via Authentik before testing admin pages in production.

**Test data:** At least one IPTV account with categories/channels, one EPG source (XMLTV or Schedules Direct if available), and optional PPV channels speeds up several sections.

**Browser:** Use DevTools → Console on first admin page load; leave open for SRI and JS errors.

**Estimated time:** ~**90–120 minutes** full pass; ~**45 minutes** minimum (sections marked *quick*).

---

## 1. Admin pages — all routes load

*Source: TODO 86. Quick scan: ~10 min.*

Open each URL; expect **HTTP 200**, nav highlights correctly, no blank page or uncaught JS errors.

| Page | Path | Check |
|------|------|--------|
| Dashboard | `/` | Overview cards load; scheduler/sync section appears if scheduler running |
| Accounts | `/accounts` | Account list or empty state |
| Filters | `/filters` | Account selector + filter list area |
| Preview Channels | `/preview` | Account dropdown populated |
| Categories | `/categories` | Category tree or empty state |
| Rulesets | `/rulesets` | Ruleset list loads |
| Settings | `/settings` | Scheduler block, config backup section, PPV config |
| EPG Management | `/epg` | Four main tabs visible (Sources, Channels, Match Rules, Data Preview) |
| Station Lookup | `/stations` | Lookup tabs render |
| Channel Health | `/channel-health` | Health table or empty state |
| PPV Enrichment | `/ppv` | Status cards and queue section |
| Xtream | `/xtream` | API URL / credential info |

- [ ] All 12 pages load without 404/500
- [ ] Sidebar navigation works between pages
- [ ] No Bootstrap/CDN **SRI failures** in console (TODO 98)

---

## 2. Accounts and credentials

*Sources: TODOs 75, 78, 79, 72/73.*

### Categories — no side-effect GET (TODO 75)

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Accounts** → pick an account → **View categories** | Page/modal opens **quickly** (no long upstream wait) |
| 2 | If cache empty | Message suggests **Refresh from provider**, not automatic fetch |
| 3 | Click **Refresh from provider** | Spinner/progress; categories populate; upstream called only on this action |
| 4 | Close and reopen categories | Same cached list without re-fetching (unless you refresh again) |

- [ ] GET categories does not block on IPTV provider
- [ ] Explicit sync button works

### Account CRUD and credentials (TODO 78 / 79)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Create or edit a test account | Save succeeds; list updates |
| 2 | **Test connection** (if shown) | Success or clear error JSON (`success: false`, `error`, optional `code`) |
| 3 | Add/edit Xtream credentials | Validation errors use consistent envelope (not raw stack traces) |

- [ ] Account create/edit/delete work
- [ ] API errors show user-readable messages in UI

---

## 3. EPG Management — tabs 1–6 (ESM migration)

*Sources: TODOs 99 (tabs 1–3), 103 (tabs 4–6), 83/85.*

Main page: **EPG Management** (`/epg`). After Wave 9, tabs 1–6 run as ESM modules (`static/js/pages/*`); legacy bundles for those areas should be retired.

### Tab 1 — EPG Sources

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open **Sources** tab | Source list loads (or empty state) |
| 2 | **Add EPG Source** → pick type (e.g. XMLTV URL) | Modal fields match source type |
| 3 | Save a test source (or edit existing) | Toast/success; source appears in list |
| 4 | **Sync** on a source (if configured) | Progress indicator; no JS error |

- [ ] Sources list CRUD works
- [ ] Source-type-specific fields show/hide correctly

### Tab 2 — Channel mappings

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open **Channels & Mappings** tab | Account dropdown populated |
| 2 | Select account | Mapping list loads (or “select account” prompt) |
| 3 | Open **manual mapping** on a channel (if any unmapped) | Modal opens; EPG channel search works |
| 4 | Save manual mapping | Modal closes; row updates |

- [ ] Mappings list scrolls and filters (mapped/unmapped)
- [ ] Manual mapping modal completes without console errors

### Tab 3 — Match rules: rulesets and rules

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Match Rules** tab → **Rulesets** sub-tab | Rulesets list loads |
| 2 | Open a ruleset → view rules | Rules list renders |
| 3 | **Preview** on a rule (pattern preview button) | Match count and sample channels shown |
| 4 | Create/edit a rule (optional) | Save succeeds |

- [ ] Rulesets and rules CRUD/preview work (TODO 96 route split — same UX)

### Tab 4 — Exclusions and name mappings

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Exclusions** sub-tab | Exclusion list loads on first visit |
| 2 | **Preview** on an exclusion pattern | Preview panel shows match count |
| 3 | **Name Mappings** sub-tab | List loads |
| 4 | **Preview** on a name mapping | Preview panel works |

- [ ] Exclusions CRUD + preview
- [ ] Name mappings CRUD + preview

### Tab 5 — Channels, XMLTV, Schedules Direct, data preview

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Sources** → edit a **Schedules Direct** source | SD credentials/lineup UI loads |
| 2 | Edit an **XMLTV Grabber** source (if used) | Grabber list/config UI loads |
| 3 | Source modal → **EPG channels** section (if present) | Channel list/search works |
| 4 | **Data Preview** main tab → select source | Lineup/channel dropdowns enable appropriately |
| 5 | **Load EPG Data** | Programs table or informative empty state |

- [ ] SD and XMLTV source modals functional
- [ ] Data Preview loads program data or clear empty message

### Tab 6 — Reference data

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open match-rules or source UI that loads **reference data** (networks, callsigns, etc.) | Reference lists populate without JS error |
| 2 | Use reference data in a rule or mapping dropdown | Options appear; selection persists |

- [ ] Reference data loads (no “failed to load reference” toast)

---

## 4. PPV enrichment UI and API

*Sources: TODOs 52–59, 65–66, 102 (no UI change expected).*

### Status and queue (TODO 59)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open **PPV Enrichment** (`/ppv`) | Status section loads (`/api/ppv-enrichment/status`) |
| 2 | Check cumulative stats | `details_fetched` and `calendar_processed` show numbers (not broken/NaN) — TODO 52 |
| 3 | **Process queue** (or equivalent) | JSON success; counts for processed/matched/no_match; errors use `{ success: false, error }` shape |
| 4 | Events/Channels preview tabs | Tables load; search/filter responsive |

- [ ] Status endpoint returns consistent JSON (no raw exception strings)
- [ ] Queue process completes or shows structured error
- [ ] `providers_failed` visible on status if any provider unhealthy (TODO 67)

### Multi-source behavior (TODO 55 — observational)

| Step | Action | Expected |
|------|--------|----------|
| 1 | If MiLB/sports channels exist | Matched events show correct source; no spurious detail-fetch errors for MLB Stats-sourced events |

- [ ] PPV preview shows linked events/channels coherently

### Post-deploy requeue (TODO 124)

After merging PPV matching fixes (TODOs 120–123), re-run enrichment on stale `no_match` channels:

| Step | Action | Expected |
|------|--------|----------|
| 1 | Optional: set deploy timestamp | `Settings.set('ppv_last_deploy_at', '<ISO UTC>')` or use full requeue |
| 2 | Re-queue no_match channels | `POST /api/ppv-enrichment/queue/no-match` with `{}`, or UI **Re-queue no_match** on `/ppv` |
| 3 | Process queue | `POST /api/ppv-enrichment/process` with `{}` |
| 4 | Check dashboard | `recently_enriched_24h` > 0; `no_match_count` may drop; channels show `ppv_enrichment_attempts >= 1` |

Script alternative (dry run first):

```bash
python scripts/rerun_matching.py --status no_match
python scripts/rerun_matching.py --status no_match --execute
curl -X POST http://127.0.0.1:8000/api/ppv-enrichment/process
```

- [ ] Requeue does not delete EventChannelLink rows
- [ ] Attempt counters populate after process run

---

## 5. Match rules, FCC patterns, and stations

*Sources: TODOs 96, 98, 74, 69.*

### EPG match rules (post–route split)

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Auto-Match** on EPG mappings tab (with account + ruleset) | Results alert with match counts |
| 2 | **Re-Match Auto** (optional) | Completes without 500 |

- [ ] Auto-match / rematch endpoints respond and UI updates

### FCC Match Patterns (`/fcc-match-patterns`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open page | Networks / Channel Patterns / Location / Strategies tabs load |
| 2 | Edit a pattern (or add test row) | Save succeeds |
| 3 | **Test Patterns** | Test modal runs without error |
| 4 | Confirm **no “Reset Defaults” HTTP button** | Banner points to `flask reset-fcc-patterns` CLI only (TODO 69) |
| 5 | **Configurable Patterns** link | Secondary page loads; CRUD works (TODO 98 service split) |

- [ ] FCC CRUD unchanged after refactor
- [ ] CLI-only reset documented in UI

### Station Lookup (`/stations`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | **By callsign** search (e.g. known local callsign) | Results or empty list, not JS error |
| 2 | **Popular DMAs** sidebar click | Activates DMA tab and runs search (regression fix) |
| 3 | **Sync FCC facilities** (Settings or Stations) | Uses `POST /api/fcc/facilities/sync` only (TODO 74 — not removed duplicate path) |

- [ ] Callsign lookup finds enriched channels when `fcc_facility_id` set
- [ ] FCC sync uses canonical endpoint

---

## 6. Config import and export

*Sources: TODOs 97, 69.*

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Settings** → **Export Configuration Bundle** | JSON file downloads |
| 2 | Select exported file for import | “Ready to import” message; Import button enables |
| 3 | Import **without** overwrite on a copy DB | Success message; data merged as expected |
| 4 | Import **invalid JSON** or wrong `type` field | Clear error in UI (validation before DB writes — TODO 69) |

- [ ] Export/import round-trip on non-production DB
- [ ] Bad bundle rejected with readable error

---

## 7. Scheduler and sync status

*Sources: TODOs 91, 89, 76–77, 82.*

### Settings scheduler panel

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Settings** → scheduler section | Job list with last/next sync times |
| 2 | If any job failed recently | **Failed** badge and `last_error` text visible (TODO 91) |
| 3 | Adjust interval → **Save** / **Restart scheduler** | Settings persist; status refreshes |
| 4 | **Stop** / **Start** scheduler (non-prod only) | State toggles; status API reflects change |

- [ ] Failure metadata visible without reading server logs
- [ ] Registered jobs include accounts, EPG, PPV prefetch, cleanups, etc.

### Dashboard (`/`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Load dashboard | If `has_sync_issues`, warning lists failed jobs or accounts |
| 2 | Failed account link (if shown) | Navigates to account detail |

- [ ] Overview stats load (`/api/overview/stats` envelope: `{ data: ... }`)

### Background behavior (observational)

| Check | Expected |
|-------|----------|
| Account sync after category failure (TODO 77) | Channels may update but post-sync steps skipped; account shows error status |
| Retention jobs (TODO 82) | No operator action; optional: confirm old events/images pruned on schedule in logs |

---

## 8. Filters, settings, playlists (API envelopes)

*Sources: TODOs 72, 73.*

After envelope migration, admin JS unwraps `{ data }` / `{ success, data }`. Spot-check high-traffic flows:

### Filters (`/filters`)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Select account → list filters | Filters render (array was wrapped in `data`) |
| 2 | Create filter → save | Success; new filter in list |
| 3 | Delete filter | **204 No Content** or success — item removed from UI |

- [ ] Filter CRUD end-to-end

### Settings

| Step | Action | Expected |
|------|--------|----------|
| 1 | Change a non-secret setting → save | Success toast/message |
| 2 | Delete a setting key (if UI allows) | Item removed; 204 handling OK |

- [ ] Settings read/write/delete work

### Playlists / Xtream (client paths)

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Xtream** page: copy playlist URL | URL well-formed |
| 2 | Fetch playlist from client path (curl or IPTV app) | M3U/XML response; grouped PPV modes still work if configured |

- [ ] Playlist generation unaffected by admin API changes

---

## 9. XSS spot checks

*Source: TODO 83.*

| Step | Action | Expected |
|------|--------|----------|
| 1 | **Preview Channels** → account with channel name containing `<test>` (or rename test channel) | Literal `<test>` shown; **no** script execution or HTML injection |
| 2 | **Rulesets** → tag selector / tag badges | Tag names with `<` display escaped |
| 3 | Trigger an API error in EPG UI (e.g. invalid sync) | Error message escaped in alert/toast |

- [ ] No `innerHTML` XSS from provider/account/tag/error strings
- [ ] Browser console free of CSP/script errors from injected names

---

## 10. Security and deploy (high level)

*Sources: TODOs 69, 84, 98.*

| Check | How | Expected |
|-------|-----|----------|
| Destructive APIs | Review [DEPLOYMENT.md — high-privilege admin APIs](./DEPLOYMENT.md#high-privilege-admin-apis) | No HTTP DROP TABLE; FCC reset CLI-only |
| Admin auth | Hit `/accounts` without Authentik (prod) | Redirect/deny from Traefik, not open admin |
| Docker hygiene | Optional: inspect running container user | Non-root where configured (TODO 84) |
| CDN SRI | Load any admin page; check console | Bootstrap/icons load; no integrity mismatch |
| Removed endpoints | `POST /api/fcc-match-patterns/reset-defaults`, `POST /icon/fetch` | 404/405 |

- [ ] Production matches documented security model
- [ ] No unexpected public admin access

---

## Regression red flags

Issues seen in CI or PR test plans — watch for these during smoke testing:

| Area | Symptom | Likely cause | What to do |
|------|---------|--------------|------------|
| **PPV detail fetcher** | Hang on shutdown; stale queue stats | Detail thread / stop sentinel (TODOs 66, 59) | Restart app; check `/api/ppv-enrichment/status` for `queue_stats_error` |
| **Parallel tests (TODO 100)** | Flaky local `make test` | Shared DB/state under xdist | Retry `make test-clean`; compare serial `venv/bin/pytest tests/ -q --no-cov` |
| **Random test order (TODO 105)** | CI fails intermittently | Order-dependent test | Note `--randomly-seed=` from CI log; file issue |
| **ESM tab migration** | Blank EPG tab after merge | Script load order / missing module | Console 404 on `pages/*`; check Network tab |
| **API envelope** | Empty lists, “undefined” in UI | Frontend not unwrapping `data` | Network tab: response has `data` key but UI blank |
| **Category sync failure** | Channels updated but filters/PPV skipped | TODO 77 policy | Expected; verify account `last_sync_status == error` |
| **SRI / CDN** | Blank styled admin page | Bootstrap blocked | Console integrity error; check `base.html` CDN pins |
| **Config import** | Partial import / cryptic 500 | Invalid bundle | Use export file as template; check validation message |
| **Scheduler registry (TODO 89)** | Missing job in status | Registry drift | Compare Settings job list to [scheduler architecture](./architecture/scheduler-and-sync-orchestration.md) |

---

## Optional / lower priority

| Item | Smoke needed? | Notes |
|------|---------------|-------|
| **TODO 102** — PPV `epg` / `extraction` package splits | **No UI change** | Re-run PPV section (§4) only if enrichment behaves oddly |
| **TODO 104** — pre-commit / `lint-py` | **Dev workflow only** | After `make install`, confirm `git commit -am` with hooks succeeds; not an operator UI test |
| **TODO 105** — pytest-randomly | **CI/dev only** | No production smoke; note if CI flakes after merge |
| **TODO 101** — doc review | **Skip** | Documentation sync only |

---

## Sign-off

| Field | Value |
|-------|--------|
| **Date** | |
| **Tester** | |
| **Environment** | ☐ Production ☐ Staging ☐ Local Docker ☐ Local venv |
| **Git ref / image tag** | |
| **Authentik user / group** | |
| **Result** | ☐ Pass ☐ Pass with notes ☐ Fail |

### Notes

<!-- Failed items, blocked checks, follow-up issues -->

---

## Quick reference — wave to feature map

| Waves | Features covered in this doc |
|-------|------------------------------|
| 1 | Safe categories GET, route cleanup, security hardening (69, 74, 75, 84) |
| 2–3 | PPV correctness, enrichment routes (52–59) |
| 4 | Scheduler status, EPG sync dedup, tag loading (76–77, 89–91) |
| 5 | API envelopes, retention (72–73, 82) |
| 6 | XSS, ESM phase 1, admin page smoke (83, 85, 86) |
| 8–9 | Route splits, ESM tabs, FCC/SRI, xdist (96–100, 103) |
| +104, +105 | Dev/CI only (see Optional) |

Detailed acceptance criteria remain in individual TODO files under [docs/todos/](./todos/).
