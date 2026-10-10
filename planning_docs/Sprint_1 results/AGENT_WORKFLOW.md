# AGENT WORKFLOW — what BizFlow plans and does (Section G.13 — living document)

Updated: end of **Sprint 1** (2026-10-10).
This describes the run the **product** will perform. It is **not** the build process: the
build-time checkpoint rule (Section A) is separate and is explained in §9, per Section G.7.
Items are marked **[planned]** until they are actually implemented and tested.

## 1. The run, from one prompt to delivery

```
 owner: "Check this month's records in data/sample, tell me what needs attention,
         and prepare everything I need to act on it."
        │
        ▼
 [0] INTAKE  ── asks once: "How involved do you want to be?"  (Auto / Ask me / Approve at end)
        │        default if unanswered: Auto
        ▼
 [1] PLAN    ── writes the run plan (stages, tools, expected outputs) into the run log
        ▼
 [2] INSPECT ── headers, row counts, types, schema mapping      tool: validate.py
        ▼
 [3] VALIDATE─ issues with file/row/id/severity                 tool: validate.py
        ▼
 [4] CALCULATE ── snapshot metrics, per-product rollups         tool: calculate.py
        │
        ├─► Operations ── stock, replenishment, materials ──► supplier_research.csv
        │        tools: calculate.py + built-in web search + supplier_score.py
        ├─► Reporting ── snapshot, action queue, quality report, daily brief
        ├─► Strategy  ── one market-check question ──► market_brief.md   [planned]
        └─► Marketing ── promo draft from the Operations handoff          [planned]
        ▼
 [5] VERIFY  ── Verifier recomputes totals from source rows, checks evidence, can reject
        ▼
 [6] DELIVER ── brief + top 3 actions + draft-ready documents (replenishment list,
                 recount checklist, unsent supplier messages, PO drafts)
        ▼
 [7] REVIEW  ── owner accepts / rejects / edits; nothing leaves the machine
```

Meanwhile, outside the run: **Technology** runs every hour (and on demand via "Run check now"),
checks the demo site and the sample shop page, writes `tech_health_report.md`, appends one row to
`tech_health_log.csv`, drafts fixes and changes **nothing** without approval.

## 2. Departments, order and handoffs (Section G.9)

| order | department | reads | writes | handoff to |
|---|---|---|---|---|
| 1 | Operations | products/inventory/sales/materials | `ops_findings.json`, `supplier_research.csv`, replenishment list, recount checklist | Reporting, Marketing |
| 2 | Reporting | validated sales + ops_findings | `business_snapshot.json`, `action_queue.csv`, `data_quality_report.md`, `daily_brief.md` | Verifier |
| 3 | Strategy | one question + web research + own sales data | `market_brief.md` | Verifier |
| 4 | Sales & Marketing | `marketing_handoff.json` from Operations | `promo_draft.md` (**unsent**) | Verifier |
| 5 | Verifier | source rows + every department file | `verification_report.md`, pass/fail on the run | Owner |

Handoff rule: each department writes a known file; the next reads **only** that verified output.
The run log records which department produced or checked each output.

## 3. Tools the agent calls

| tool | kind | used by | status |
|---|---|---|---|
| file read / write | WorkBuddy built-in | all | confirmed (F1) |
| Python deterministic scripts (`validate`, `calculate`, `supplier_score`, `tech_check`) | WorkBuddy code execution | Operations, Reporting, Technology | runtime confirmed (F2/F3); scripts **[planned]** |
| built-in web search | WorkBuddy built-in | Operations (suppliers), Strategy (market check) | confirmed working (F5, retrieved 2026-10-10) |
| WorkBuddy Automation, hourly | WorkBuddy built-in | Technology | listing confirmed (F6); hourly **[planned, Sprint 3]** |
| team MCP server | optional, only for missing capability | fallback | **not verified** (U2) — built-ins come first (Section D) |
| sub-agents (Analyst / Verifier) | WorkBuddy Agent | Verifier | execution confirmed (F7); parallelism untested (U3) |

## 4. Key decisions and their options

Every key decision is recorded with its options and the recommended choice, whatever the mode.

| decision | options | recommended | who decides |
|---|---|---|---|
| involvement mode | Auto / Ask me at key decisions / Approve at end | **Auto** for the live demo | owner, at the start |
| supplier shortlist per material | up to 3 scored suppliers | the highest-scoring, with the breakdown shown | owner (Auto picks and logs why) |
| which product to promote | products meeting the documented trigger | the one with the largest over-stock ratio | owner |
| market-check question | any one focused question | proposed from the data (e.g. demand among campus students) | owner |
| approving a restock / PO | approve / reject / edit | presented, never auto-approved | owner, always |

## 5. Dynamic adaptation rules (logged, with a reason each time)

1. **Stale stock count** → do not compute a replenishment quantity; create a "recount stock" action.
2. **Sales history shorter than the demand window** → use the available days, label low-confidence,
   disclose it.
3. **Excluded or invalid rows affect a metric** → mark that metric as affected in the snapshot and brief.
4. **Verifier mismatch** → re-run the affected calculation once; if it remains, mark the run failed
   and show the mismatch.
5. **Live research unavailable** → use the last saved result labelled with its original retrieval date.

## 6. Allowed pauses at runtime (Section G.7) — and nothing else

0. Once at the start, to ask the involvement-mode question.
1. A required file is missing, or an ambiguity has no documented safe default.
2. At key decisions — **only** if the owner chose "Ask me at key decisions" (max 3 per run).
3. At the end, for the owner to approve consequential actions.

In every other case the agent applies the documented default, logs it and continues.

## 7. Limits and stop conditions

- Step budget: up to **30** tool/action steps per end-to-end run (provisional; confirm in Sprint 2).
- Retries: at most **2** per stage, only when a retry is safe and likely to help.
- On failure: record the error, stop with a clear blocker; never loop indefinitely.
- Write locations are known and fixed; original input files are never overwritten.

## 8. Output files

`data/output/business_snapshot.json` · `action_queue.csv` · `data_quality_report.md` ·
`daily_brief.md` · `supplier_research.csv` · `market_brief.md` · `promo_draft.md` ·
`tech_health_report.md` · `tech_health_log.csv` · `orders/PO-<id>.md` · `run_log.jsonl`
(all **[planned]** — none exist yet at the end of Sprint 1).

## 9. Build-time checkpoints vs runtime autonomy (Section G.7)

**Build time:** while BizFlow is being built, WorkBuddy stops after every sprint, reports and waits
for the team's approval. This is a *team* control, not product behaviour.

**Runtime:** the owner's single goal prompt runs the whole chain in §1 without intermediate
hand-holding, subject only to the pauses in §6. The two must never be confused on the slides: the
judges see one prompt run end to end.
