# PROJECT STATUS — BizFlow

Last update: **2026-10-10 13:35, end of Sprint 1** (checkpoint pending user approval).

## Where we are

| sprint | window | status |
|---|---|---|
| Sprint 1 — setup, feasibility, data (Tasks 0–2) | 12:00–13:30 | **completed 13:35, awaiting approval** (started 13:15, so ~20 min past the nominal window) |
| Sprint 2 — agent, departments, tools (Tasks 3–4) | 13:30–20:00 | **not started — blocked on approval** |
| Sprint 3 — demo site (Tasks 5–6) | 20:00–00:00 | not started |
| Sprint 4 — test, fix, polish (Tasks 7–8) | 00:00–03:00 | not started |
| Sprint 5 — slides, docs, rehearsal (Tasks 9–11) | 03:00–09:00 | not started; gated on the G.13 approval of CAPABILITIES/AGENT_WORKFLOW |

Hard deadline: **09:30, 2026-10-11** (target submission 09:00).

## What Sprint 1 produced

- Workspace created; the master instructions imported as `docs/MASTER_INSTRUCTIONS_EXTRACT.md`.
- 10 feasibility checks run — 8 PASS, 1 INCONCLUSIVE, 1 NOT VERIFIED (`docs/WORKBUDDY_FEASIBILITY_CHECKLIST.md`).
- Synthetic dataset: 5 products, 136 sales rows, 6 inventory rows, 11 expenses, 20 material rows
  (17 distinct materials), 13 deliberately seeded defects.
- Golden expected results, hand-computed and cross-checked: net revenue 2663.45, COGS 942.30,
  gross profit 1721.15, margin 64.62 %, units 520, recorded expenses 1165.70.
- First versions of `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` (G.13).
- Drafts: charter, requirements, architecture; final: data dictionary.

## Verified tests at this point

| test | result |
|---|---|
| `scripts/generate_sample_data.py` | PASS — 136 rows, reproducible (sha256 recorded) |
| `tests/compute_expected_standalone.py` on `data/sample` | PASS — produced the golden values |
| same script on `tests/fixtures/golden_mini` | PASS — matched **all** hand arithmetic, no mismatch |
| hand arithmetic vs script | PASS — 0 mismatches across ~25 values |
| feasibility F1–F9 | PASS (details in the checklist) |

No product code exists yet, so no product test has been run.

## Current blockers

1. **Sprint 2 is not approved.** Per Section A no further sprint may start without approval.
2. Local MCP support unverified (U2) — not blocking, built-ins are the primary path.
3. Hourly Automation firing unverified (U1) — needed by Sprint 3/4.
4. Parallel sub-agent execution unverified (U3) — affects only the "parallel validation" should-have.
5. Organiser unknowns (G.8): scoring weights, pitch duration, submission method — do not invent.

## Recommended next task

**Sprint 2 — agent, departments and tools (Tasks 3–4).** Everything after Sprint 1 depends on the
calculation engine and the department pipeline; it is also the longest sprint (13:30–20:00 nominal),
and we are already behind the nominal schedule, so the demo-site sprint should not slip into it.
