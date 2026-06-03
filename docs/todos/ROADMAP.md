# Post-audit implementation roadmap (index)

**Last updated:** June 2026  
**Companion:** [README.md](./README.md) (per-item specs), [../architecture/](../architecture/) (design notes)

This file is the **index** for roadmap planning. Detailed wave specs are split so completed work does not dominate the open backlog.

| Document | Contents |
|----------|----------|
| **[ROADMAP-active.md](./ROADMAP-active.md)** | Open work: dashboard 107–110, Wave 11 (PostgreSQL), Wave 12 (PPV matching + SofaScore 125–126), next five |
| **[archive/ROADMAP-waves-1-10.md](./archive/ROADMAP-waves-1-10.md)** | Completed waves 1–10, PR batches A–AA, parallel workstreams, historical dependency rules |

Implement from each **TODO file** linked in the active roadmap — not from summaries alone.

---

## Status snapshot

| Track | Range | Open | Notes |
|-------|-------|------|-------|
| P5 — PPV | 52–67, **102** | **0** | Waves 2–3 + 7 + 9 ✅; **65** phases 1–3 ✅ |
| P6 — App-wide | 68–95 | **0** | Waves 1–8 ✅; parents **78**, **85**, **92**, **95** fully complete |
| **Wave 9** | 96–100, 102, 103, 105 | **0** | PRs #39–47 (route splits, ESM, xdist, PPV packages) |
| **Wave 10** | 101 | **0** | Final doc review ✅ |
| **Dashboard follow-ups** | 107–110 | **0** | 107–109 ✅; [110](./110-dashboard-optional-ux-follow-ups.md) won't do |
| **Wave 11 — DB migration** | 111–119 | **9** | SQLite → PostgreSQL; Series A + Series B |
| **Wave 12 — PPV matching** | 121–126 | **6** | 120 ✅; 124 🟡; ESPN [122](./122-tennis-calendar-event-source.md); SofaScore [125](./125-sofascore-tennis-calendar-slice1.md)–[126](./126-sofascore-calendar-multi-sport-and-enrichment.md) |

**Total open (required):** 15 (111–119, 121–126) — see [ROADMAP-active.md](./ROADMAP-active.md).

Waves **1–10** ✅ (PRs #10–51). **Next:** Wave 12 (PPV) and/or Wave 11 (PostgreSQL), in parallel if desired.

Update [README.md](./README.md) status columns as work lands. Mark PR IDs in each TODO’s **Completion** section.

---

## Quick links

- **What to do next:** [ROADMAP-active.md § Recommended “next five”](./ROADMAP-active.md#recommended-next-five)
- **PostgreSQL track:** [ROADMAP-active.md § Wave 11](./ROADMAP-active.md#wave-11--postgresql-migration-track)
- **PPV matching + tennis/SofaScore:** [ROADMAP-active.md § Wave 12](./ROADMAP-active.md#wave-12--ppv-production-matching-gaps)
- **Merged PR batch history:** [archive § Master PR batch index](./archive/ROADMAP-waves-1-10.md#master-pr-batch-index)

---

## How to use

1. Open **[ROADMAP-active.md](./ROADMAP-active.md)** for current waves and batch order.
2. Read linked TODO doc(s) before coding.
3. Prefer **one PR batch at a time**; do not combine migration PRs with large refactors.
4. After merge, mark ✅ in README and note the PR in the TODO file.
5. When a wave completes, refresh the snapshot table above and the active file.

---

## Maintenance

When open work completes:

1. Update statuses in [README.md](./README.md).
2. Add PR links under **Completion** in each TODO file.
3. Refresh snapshot tables in this file and [ROADMAP-active.md](./ROADMAP-active.md).
4. Archive finished wave sections from the active file if it grows unwieldy.
5. Fix [87](./87-fix-stale-documentation.md) if the README and roadmaps diverge.
