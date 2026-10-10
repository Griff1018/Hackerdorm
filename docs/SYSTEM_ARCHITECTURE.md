# SYSTEM ARCHITECTURE — BizFlow (DRAFT, Sprint 1)

Describes the **intended** architecture. It will be rewritten from the actual implementation in
Sprint 5 (Task 9). Nothing here is presented as built yet.

## 1. Shape of the system

WorkBuddy is the **runtime**, not just the code generator (Section G.6). The owner types one goal
prompt; WorkBuddy plans the run, calls deterministic tools, writes the outputs and presents them.

```
owner prompt (one)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ WorkBuddy agent (orchestrator)                                │
│  intake → plan → inspect → validate → calculate → research    │
│  → diagnose → prioritise → verify → deliver → ask for approval│
└───────┬───────────────────────────────────────────────────────┘
        │ calls (bounded, known tool functions only)
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Deterministic layer — Python scripts under app/               │
│  validate.py   calculate.py   supplier_score.py   tech_check.py│
│  (decimal money, no LLM arithmetic, no invented values)        │
└───────┬───────────────────────────────────────────────────────┘
        │ writes
        ▼
data/output/  business_snapshot.json · action_queue.csv
              data_quality_report.md · daily_brief.md
              supplier_research.csv · market_brief.md · tech_health_report.md
              orders/PO-<id>.md · run_log.jsonl
        │ read by
        ▼
demo site (static HTML + JS, reads the JSON/CSV of the latest run)
```

## 2. Components

| component | responsibility | implementation intent |
|---|---|---|
| Intake | read the goal, derive objective + reporting period, ask the involvement-mode question once | orchestrator |
| Inspector / validator | headers, row counts, types, schema mapping, issue list | `app/validate.py` |
| Deterministic analysis | Section 5 metrics, per-product rollups, demand, replenishment | `app/calculate.py` |
| Supplier research | web search per material; tiering (light/full); G.11 scoring | built-in web search + `app/supplier_score.py` |
| Market check | one question per run, sources + dates, desk-research label | built-in web search |
| Marketing handoff | draft a promo post from an Operations handoff file | orchestrator writes a draft file |
| Technology check | hourly + on demand; checks pages, links, output freshness, shop-page stock vs inventory.csv | `app/tech_check.py` + WorkBuddy Automation |
| Verifier | independently recomputes totals from source rows, checks evidence, can reject | separate role/sub-agent, same deterministic tools |
| Reporting | snapshot, queue, quality report, brief | orchestrator + scripts |
| Demo site | displays real outputs; accept/reject; reset; simulated checkout | static HTML/JS in `demo/` |
| State / audit | run metadata, decisions, issues, test results | `data/output/run_log.jsonl` + the project status files |

## 3. Data flow and handoffs

Each department writes to a **known file** and the next department reads only that verified output
(Section G.9, handoff rule). The run log records which department did what, so the collaboration is
visible live.

```
Operations ──► reporting/ops_handoff.json ──► Reporting ──► snapshot ──► Verifier ──► owner
     │                                                            ▲
     └──► materials → supplier_research.csv ─────────────────────┘
Reporting ──► marketing_handoff.json ──► Marketing (draft only)
Technology ──► tech_health_report.md ──► owner (read-only, never auto-fixes)
```

## 4. Key technical decisions (recorded, reversible)

| decision | choice | why | alternative |
|---|---|---|---|
| Calculation layer | Python 3.13 with `decimal.Decimal` | exact money, no binary float drift; runtime confirmed (F2/F3) | JS, or spreadsheets |
| Inputs | CSV, one current stock record per product | smallest schema that satisfies the contract | a database (out of scope) |
| Outputs | JSON + CSV + Markdown files on disk | inspectable, diffable, easy for the demo site to read | an API (overkill) |
| Research | built-in WorkBuddy web search first | Section D: built-in first; confirmed working (F5) | team MCP server (backup, U2) |
| Scheduling | WorkBuddy desktop Automation, hourly | G.12 | team scheduler if hourly is unavailable |
| Agent roles | Analyst + Verifier as separate sub-agents | G.4/G.9; sub-agents confirmed (F7) | sequential stages, honestly labelled |
| Dashboard | static HTML/JS reading the latest-run files | no external CDN/fonts; works offline in the demo | a framework (rejected: heavier, no benefit) |
| Secrets | environment / WorkBuddy config only, never in files | Section D | none |

## 5. Failure and safety behaviour

- Bounded: ~30 tool/action steps, ≤ 2 retries per stage, explicit stop conditions.
- Any tool failure is recorded; retry only when it is safe and likely to help; otherwise stop with
  a clear blocker.
- Consequential actions (order, payment, post) are **never** executed — only drafted for approval.
- The hourly check only reads and reports; it never edits without approval.
- If live research fails, fall back to the last saved result labelled with its retrieval date.

## 6. Known unknowns that affect this architecture

Local MCP support (U2) · parallel sub-agent execution (U3) · HTML preview in this environment (U4) ·
slide generation path (U5). See `docs/WORKBUDDY_FEASIBILITY_CHECKLIST.md`.
