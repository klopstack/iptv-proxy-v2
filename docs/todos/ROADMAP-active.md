# Active implementation roadmap

**Last updated:** June 2026  
**Index:** [ROADMAP.md](./ROADMAP.md) · **Archive (waves 1–10):** [archive/ROADMAP-waves-1-10.md](./archive/ROADMAP-waves-1-10.md)  
**Companion:** [README.md](./README.md) (per-item specs)

Open work only. Completed waves **1–10** (PRs #10–51) live in the archive file — do not duplicate here.

---

## Status snapshot (open work)

| Track | TODOs | Open | Notes |
|-------|-------|------|-------|
| Dashboard follow-ups | 107–110 | **0** | 107–109 ✅; [110](./110-dashboard-optional-ux-follow-ups.md) won't do |
| Wave 11 — PostgreSQL | 111–119 | **9** | Series A + Series B |
| Wave 12 — PPV matching | 121–126 | **6** | 120 ✅; 124 🟡 in review; 125–126 SofaScore |
| **Total required** | | **15** | 111–119, 121–126 |

Waves **1–10** ✅ — see [archive/ROADMAP-waves-1-10.md](./archive/ROADMAP-waves-1-10.md).

**Suggested parallel tracks:** Wave 12 (PPV) and Wave 11 (PostgreSQL prep) can run on separate contributors.

---

## How to use

1. Pick a wave or “next five” item below.
2. Read the linked TODO file before coding.
3. Run that TODO’s test plan; mark ✅ in [README.md](./README.md) and add PR under **Completion** in the TODO.
4. Refresh the snapshot table in [ROADMAP.md](./ROADMAP.md) when counts change.

---

## Cross-track dependency rules (open work)

| Rule | Rationale |
|------|-----------|
| **120 before 121–123** | Correct calendar day before abbrev/source work |
| **122 (ESPN) before 125–126** | Primary tennis before SofaScore secondary |
| **125 before 126** | SofaScore client/parser before enrichment merge |
| **124 with 120+** | Requeue to verify matching fixes on production |
| **111 + 112 → 113 → 114 → 115** | PostgreSQL Series A order |
| **117 + 116 → 118 → 119** | PostgreSQL Series B order |

Full historical rules (55 before 62, etc.) are in the [archive](./archive/ROADMAP-waves-1-10.md#cross-track-dependency-rules).

**Do not batch in one effort:** PostgreSQL switchover (118) + PPV calendar providers (122/125/126) + large route refactors.

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
**Gate:** Series B requires Series A complete. Can run in parallel with Wave 12.

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

## Wave 12 — PPV production matching gaps

**Goal:** Close gaps from live audit (June 2026): dates, MLB abbrevs, tennis calendar, extended sports, requeue.  
**Est. effort:** 2–4 weeks (122/123/125/126 spike-dependent)  
**Prerequisites:** P5 waves 2–3 ✅ (52–67)

Production baselines (2026-06-03): 110 matched, 1,072 `no_match`, 341 tennis `no_match`, 27 Peacock `no_match`, 0 channels with `ppv_enrichment_attempts > 0`.

| Batch | TODOs | Theme | Effort |
|-------|-------|-------|--------|
| **AC** | [124](./124-ppv-enrichment-attempt-tracking-and-requeue.md) | Attempt tracking + requeue | S |
| **AD** | [120](./120-fix-ppv-date-extraction-parsing-bugs.md) | Date extraction parity | M — ✅ done |
| **AE** | [121](./121-mlb-team-abbreviation-resolution.md) | MLB three-letter abbrevs (Peacock) | S |
| **AF** | [122](./122-tennis-calendar-event-source.md) | **ESPN** primary tennis (PR #56) | L |
| **AH** | [125](./125-sofascore-tennis-calendar-slice1.md) | SofaScore client + parser (no wire) | M |
| **AI** | [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) | SofaScore merge + multi-sport doc | M–L |
| **AG** | [123](./123-extended-calendar-coverage-college-obscure-sports.md) | College / obscure / boxing / stale ESPN Play | L |

**Order:** AC + AD first → AE → **AF (ESPN)** → AH (125, parallel with AF tail) → AI (126 after 125 + AF) → AG (parallel). Requeue (124) after each batch to measure impact.

```text
120 ✅ ──► 121
     └──► 122 ESPN (PR #56) ──► 125 SofaScore slice 1 ──► 126 wire + fallback
     └──► 123 (multi-track)
124 requeue ◄── verify all tracks
```

---

## Recommended “next five”

1. **[124](./124-ppv-enrichment-attempt-tracking-and-requeue.md)** — attempt tracking + requeue (batch **AC**)
2. **[121](./121-mlb-team-abbreviation-resolution.md)** — MLB abbrev resolution (batch **AE**)
3. **[122](./122-tennis-calendar-event-source.md)** — ESPN tennis calendar (batch **AF**, PR #56)
4. **[111](./111-pg-prep-raw-sqlite3-audit.md)** — PostgreSQL prep (batch **PG-A1**, parallel)
5. **[125](./125-sofascore-tennis-calendar-slice1.md)** — SofaScore slice 1 (batch **AH**, after AF)

**Next after AF lands:** [126](./126-sofascore-calendar-multi-sport-and-enrichment.md) (**AI**). Optional parallel: [123](./123-extended-calendar-coverage-college-obscure-sports.md) (**AG**).

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

---

## Maintenance

When open work completes:

1. Update [README.md](./README.md) status columns.
2. Refresh snapshot in [ROADMAP.md](./ROADMAP.md).
3. Move finished wave sections from this file to a dated archive note if the active file grows large.
4. Run [87](./87-fix-stale-documentation.md) patterns if index and roadmap diverge.
