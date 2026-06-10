# Active implementation roadmap

**Last updated:** June 2026  
**Index:** [ROADMAP.md](./ROADMAP.md) · **Archive (waves 1–10):** [archive/ROADMAP-waves-1-10.md](./archive/ROADMAP-waves-1-10.md)  
**Companion:** [README.md](./README.md) (per-item specs)

Open work only. Completed waves **1–10** (PRs #10–51) and **Wave 12** (PRs #52–63) live in the archive sections below — do not re-implement.

---

## Status snapshot (open work)

| Track | TODOs | Open | Notes |
|-------|-------|------|-------|
| Dashboard follow-ups | 107–110 | **0** | 107–109 ✅; [110](./110-dashboard-optional-ux-follow-ups.md) won't do |
| Wave 11 — PostgreSQL | 111–119 | **9** | Series A + Series B |
| Wave 12 — PPV matching | 120–126, 123 | **0** | ✅ complete June 2026; 123 A/B in review [#62](https://github.com/klopstack/iptv-proxy-v2/pull/62)/[#63](https://github.com/klopstack/iptv-proxy-v2/pull/63) |
| Wave 13 — PPV follow-ups | 127–131, 133 | **6** | Doubles; dates; Flo replay; NCAA spike + SofaScore refactor/college |
| Wave 14 — Admin UX | 132 | **1** | Xtream credential modal — account dropdown + timezone select |
| **Total required** | | **16** | 111–119, 127–131, 132, 133 |

Waves **1–10** ✅ — see [archive/ROADMAP-waves-1-10.md](./archive/ROADMAP-waves-1-10.md).  
**Wave 12** ✅ — see [§ Wave 12 complete](#wave-12--ppv-production-matching-gaps--complete-june-2026) below.

**Suggested parallel tracks:** Wave 11 (PostgreSQL prep) is the primary open track.

---

## How to use

1. Pick a wave item below (Wave 11).
2. Read the linked TODO file before coding.
3. Run that TODO’s test plan; mark ✅ in [README.md](./README.md) and add PR under **Completion** in the TODO.
4. Refresh the snapshot table in [ROADMAP.md](./ROADMAP.md) when counts change.

---

## Cross-track dependency rules (open work)

| Rule | Rationale |
|------|-----------|
| **111 + 112 → 113 → 114 → 115** | PostgreSQL Series A order |
| **117 + 116 → 118 → 119** | PostgreSQL Series B order |

Historical Wave 12 rules (120 before 121–123, 122 before 125–126, etc.) are satisfied — see [Wave 12 complete](#wave-12--ppv-production-matching-gaps--complete-june-2026).

Full historical rules (55 before 62, etc.) are in the [archive](./archive/ROADMAP-waves-1-10.md#cross-track-dependency-rules).

---

## Dashboard follow-ups (post PR #48)

| TODO | Summary |
|------|---------|
| [107](./107-dashboard-stats-performance-hardening.md) | ✅ CQS visible count, overview EPG cache, timing logs |
| [108](./108-migrate-overview-stats-api-envelope.md) | ✅ `GET /api/overview/stats` → `data_response` |
| [109](./109-update-smoke-test-dashboard-checks.md) | ✅ Smoke doc dashboard §1 / §7 |
| [110](./110-dashboard-optional-ux-follow-ups.md) | 🚫 P3 optional UX — won't do |

---

## Wave 11 — PostgreSQL migration track

**Goal:** Replace SQLite with PostgreSQL as the production database backend.  
**Gate:** Series B requires Series A complete.

### Series A — Preparation (SQLite-safe)

| PR | TODO | Summary | Size |
|----|------|---------|------|
| **PG-A1** | [111](./111-pg-prep-raw-sqlite3-audit.md), [112](./112-pg-prep-json-column-types.md) | Raw sqlite3 audit; JSON columns | S–M |
| **PG-A2** | [113](./113-pg-prep-alembic-migration-system.md) | Alembic replaces custom runner | **L** |
| **PG-A3** | [114](./114-pg-prep-test-db-hardening.md), [115](./115-pg-prep-ci-docker-config.md) | Test DB + CI/Docker PG | M |

### Series B — Switchover (after Series A)

| PR | TODO | Summary | Size |
|----|------|---------|------|
| **PG-B1** | [117](./117-pg-migration-schema-creation.md), [116](./116-pg-migration-data-export-tooling.md) | Schema + data tooling | M |
| **PG-B2** | [118](./118-pg-migration-cutover-procedure.md) | Production cutover | **L** |
| **PG-B3** | [119](./119-pg-migration-cleanup-and-docs.md) | Post-cutover cleanup | M |

---

## Wave 12 — PPV production matching gaps ✅ complete (June 2026)

**Goal:** Close gaps from live audit (June 2026): dates, MLB abbrevs, tennis calendar, extended sports, requeue.  
**Status:** All batches merged or in final PR review. Production requeue still required ([124](./124-ppv-enrichment-attempt-tracking-and-requeue.md)).

| Batch | TODO | PR(s) | Theme |
|-------|------|-------|-------|
| **AC** | [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) | [#53](https://github.com/klopstack/iptv-proxy-v2/pull/53) | Attempt tracking + requeue |
| **AD** | [120](./120-fix-ppv-date-extraction-parsing-bugs.md) | [#52](https://github.com/klopstack/iptv-proxy-v2/pull/52) | Date extraction parity |
| **AE** | [121](./121-mlb-team-abbreviation-resolution.md) | [#54](https://github.com/klopstack/iptv-proxy-v2/pull/54) | MLB three-letter abbrevs (Peacock) |
| **AF** | [122](./122-tennis-calendar-event-source.md) | [#55](https://github.com/klopstack/iptv-proxy-v2/pull/55), [#56](https://github.com/klopstack/iptv-proxy-v2/pull/56) | ESPN primary tennis |
| **AH** | [125](./125-sofascore-tennis-calendar-slice1.md) | [#58](https://github.com/klopstack/iptv-proxy-v2/pull/58) | SofaScore client + parser |
| **AI** | [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) | [#60](https://github.com/klopstack/iptv-proxy-v2/pull/60) | SofaScore merge + multi-sport doc |
| **AG** | [123](./123-extended-calendar-coverage-college-obscure-sports.md) | [#59](https://github.com/klopstack/iptv-proxy-v2/pull/59) (D), [#61](https://github.com/klopstack/iptv-proxy-v2/pull/61) (C), [#62](https://github.com/klopstack/iptv-proxy-v2/pull/62) (B), [#63](https://github.com/klopstack/iptv-proxy-v2/pull/63) (A) | College / obscure / boxing / stale ESPN Play |

**123 track summary:** D stale archive ✅ · C boxing no-date ✅ · B obscure DAZN leagues 🔄 #62 · A WCWS/BTN+ skip 🔄 #63 (WCWS calendar API deferred — see architecture note).

**Production follow-up:** After deploy, run no_match requeue per [124 runbook](./124-ppv-enrichment-attempt-tracking-and-requeue.md) to measure matching impact.

---

## Wave 13 — PPV follow-ups (open)

**Goal:** Close production gaps from June 4 2026 audit: tennis date skip regression, doubles parsing, Flo replay library, college calendar data.

| Batch | TODO | Theme |
|-------|------|-------|
| **AK** | [128](./128-fix-ppv-year-inference-recent-past-dates.md) | `@ Jun N` recent-past year — 332 tennis channels skipped as `far_future` |
| **AJ** | [127](./127-ppv-multi-player-competitor-extraction.md) | 2v2 name parsing + `competitors_match_event` + matcher validation |
| **AL** | [129](./129-ppv-replay-archive-enrichment-flosp.md) | Flo/FLSP archive replays → enrich + **Replay** playlist group |
| **AM** | [130](./130-ncaa-college-calendar-source-spike.md) | Spike: NCAA / college calendar sources (SofaScore slugs, Sportsipy, …) |
| **AN** | [131](./131-sofascore-college-amateur-calendar-provider.md) | SofaScore multi-sport + historical window → calendar merge |
| **AO** | [133](./133-sofascore-multi-sport-refactor-and-football-followups.md) | Generic SofaScore provider refactor; PR #74 WC football ops + soccer follow-ups |

**Order:** **128** before tennis requeue; PR **#74** deploy + **124** WC requeue; **133 refactor** before **131** college slug wire; **130 spike** before **131**; **129 Track B** after **131**; **127** after calendar + 128 (doubles need fixtures).

**Prerequisites:** [122](./122-tennis-calendar-event-source.md) / [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) ✅; [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) requeue after deploy.

**Audit impact:**

- [128](./128-fix-ppv-year-inference-recent-past-dates.md) — `@ Jun 3` parsed as 2027 on production; tennis never reaches matcher.
- [127](./127-ppv-multi-player-competitor-extraction.md) — ~89 unique doubles keys — [tennis-ppv-production-audit.md](../architecture/tennis-ppv-production-audit.md) §4.
- [129](./129-ppv-replay-archive-enrichment-flosp.md) — **243** Flo channels (~72% of 339 queued tail); product intent is replay enrichment, not `stale_archive` skip.
- [130](./130-ncaa-college-calendar-source-spike.md) / [131](./131-sofascore-college-amateur-calendar-provider.md) — calendar gap for Oct 2025 college/hockey; ±14-day SofaScore window blocks historical replay fetch.
- [133](./133-sofascore-multi-sport-refactor-and-football-followups.md) — PR #74 football lives in `services/tennis/sofascore_calendar.py`; refactor unblocks 131 and future slugs.

---

## Wave 14 — Admin UX (open)

**Goal:** Fix operator-facing admin UI regressions unrelated to PPV/DB tracks.

| TODO | Summary |
|------|---------|
| [132](./132-fix-xtream-credential-dialog-ux.md) | `/xtream` Add Credential modal: unwrap `GET /api/accounts` `{ data }` envelope (dropdown stuck on “Loading accounts…”); PPV Rename Timezone → `<select>` |

**Root cause:** [73](./73-standardize-api-response-shapes.md) migrated accounts list to `data_response`; `templates/xtream.html` never adopted `apiUnwrapData` / `account_select.js`.

**Independent of:** Wave 11 (PostgreSQL) and Wave 13 (PPV) — safe to pick up anytime.

---

## Recommended “next five”

1. **[111](./111-pg-prep-raw-sqlite3-audit.md)** — PostgreSQL prep (batch **PG-A1**)
2. **[112](./112-pg-prep-json-column-types.md)** — JSON column types (batch **PG-A1**)
3. **[113](./113-pg-prep-alembic-migration-system.md)** — Alembic migration system (batch **PG-A2**)
4. **[114](./114-pg-prep-test-db-hardening.md)** — Test DB hardening (batch **PG-A3**)
5. **[115](./115-pg-prep-ci-docker-config.md)** — CI/Docker PG (batch **PG-A3**)

**Ops (post Wave 12 deploy):** Requeue `no_match` channels via [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md).

---

## Completed prerequisites (do not re-do)

| Area | Done TODOs |
|------|------------|
| Channel selection parity | 01–08, 17–21 |
| EPG sync orchestration | 40–51 |
| PPV audit remediation | 52–67, 102 |
| App-wide audit | 68–95, 96–105 |
| Dashboard follow-ups | 106–109 ✅ |
| Waves 1–10 execution | See [archive](./archive/ROADMAP-waves-1-10.md) |
| **Wave 12 PPV matching** | 120–126, 123 (tracks A–D) — PRs #52–63 |

---

## Maintenance

When open work completes:

1. Update [README.md](./README.md) status columns.
2. Refresh snapshot in [ROADMAP.md](./ROADMAP.md).
3. Move finished wave sections from this file to a dated archive note if the active file grows large.
4. Run [87](./87-fix-stale-documentation.md) patterns if index and roadmap diverge.
