# Sprint 2 Checkpoint Report — BizFlow

**Mandatory build-time checkpoint (Section A).** Per the master instructions, WorkBuddy stops after
every sprint, reports, and waits for approval. **Sprint 3 must not start until this checkpoint is
approved.** This report is separate from the Section G.7 runtime autonomy rule.

- Sprint: 2 (Tasks 3–4: agent, departments, tools)
- Window: 13:30–20:00 nominal · **completed/ready for review ~14:30**
- Status: **DONE — awaiting your approval to proceed to Sprint 3**
- Engine run verified: `python app/run_bizflow.py --data data/sample --output data/output --po --tech`
  → net revenue 2451.25 · 6 actions · verify PASSED (7 checks) · tech PASSED (13/0/0)

---

## 1. Files created / modified in Sprint 2

**Application code (`app/`)**
- `bizflow_core.py` — Config, `validate()`, `calculate()` (exact decimal money), snapshot + action queue.
- `bizflow_supplier.py` — G.11 scoring (`score_material`), full/light tiers, price-unit parsing.
  **Unpriced rows are ranked last and forced `recommended=no`.**
- `bizflow_outputs.py` — reports, market-brief and promo-draft builders.
- `bizflow_profile.py` — profile load + `sanitise_profile` (rejects FORBIDDEN_FIELDS).
- `bizflow_purchase.py` — draft PO builder (cumulative budget, pack round-up, review flags).
- `bizflow_tech.py` — Technology health check (read-only; page-relative link resolution).
- `run_bizflow.py` — orchestrator wiring all six departments + CLI flags.

**Research / build scripts**
- `scripts/build_supplier_research.py` — builds the scored input CSV; prices **normalised by code**,
  gaps left blank (never estimated).

**Data & demo**
- `data/business_profile.json` (synthetic, no forbidden fields), `data/market_check.json`.
- `demo/index.html`, `demo/shop_page.html` (SYNTHETIC-labelled; stock mirrored from `inventory.csv`).

**Docs**
- `docs/SUPPLIER_RESEARCH_PLAN.md` (per-material light/full tier: 5 FULL, 12 light).
- `docs/CAPABILITIES.md`, `docs/AGENT_WORKFLOW.md` — promoted Sprint 2 items to **built and tested**.
- `PROJECT_STATUS.md`, `CHANGELOG.md` — advanced to end of Sprint 2.

**Generated outputs (`data/output/`, reproducible every run)**
- `supplier_research.csv` (39 rows / 17 materials, scored), `supplier_coverage.json` (gap report)
- `market_brief.md`, `promo_draft.md`, `marketing_handoff.json`
- `purchase_plan.md`, `purchase_orders.json`, `po/PO-2026-09-30-01..06.md`
- `verification_report.md`, `tech_health_report.md`, `tech_health_log.csv`
- `business_snapshot.json`, `action_queue.csv`, `data_quality_report.md`, `daily_brief.md`

---

## 2. Checks performed

| area | what was checked | result |
|---|---|---|
| Validation | 5 CSV inputs schema/types/enums/ranges | 5 issue rows (3 error) surfaced |
| Calculation | net revenue, COGS, gross profit, margin, expenses | net 2451.25, COGS 856.80, expenses 1105.70 |
| Verifier | independent recomputation from source rows | **PASSED — 7/7 checks** |
| Supplier scoring | G.11 formula applied **by code**; 17 materials, top-3 recommended | 39 rows; unpriced rows never recommended |
| Coverage | priced supplier found per material | 13/17 have a price; 4 need a quotation |
| Strategy | P002 price vs Malaysian market | RM 4.50 vs band RM 2.40–4.70 → quantity problem |
| Marketing | promo handoff → P002, draft only | unsent; do-not-claim guardrails present |
| Technology | demo pages + links + stock vs inventory + freshness | **PASS — 13 pass / 0 warn / 0 error** |
| Purchase | cumulative remaining budget; over-budget & no-price handling | 2 POs flagged over budget; 1 material not ordered |
| Profile safety | forbidden fields refused | `FORBIDDEN_FIELDS` enforced by test |
| Regression suite | `tests/test_engine.py` (20 tests, unittest) | **20/20 PASS** (2 new supplier-scoring regressions) |

---

## 3. Acceptance-criteria status (Sprint 2 scope)

| criterion | status |
|---|---|
| Six departments wired and run end-to-end | met |
| G.11 scoring computed by code, not estimated | met |
| Unpriced supplier rows never recommended | met (regression-tested) |
| Strategy light market check (one question/page) | met |
| Marketing draft-only, never posted | met |
| Technology hourly/on-demand check, read-only, drafts fixes | met (now PASS) |
| Verifier independent recomputation, can reject | met (PASSED) |
| Business profile, no card/account data (G.14) | met |
| Ready-to-pay PO, owner pays, budget breaches flagged (G.14) | met |
| Light vs full research tier decision logged | met (`SUPPLIER_RESEARCH_PLAN.md`) |

---

## 4. Known gaps (carried forward, not hidden)

1. **4 materials need a supplier quotation** — no Malaysian price was published for Granola bar wrapper,
   Muffin cup, Paper cookie bag, Plastic cup 500ml. Recorded in `supplier_coverage.json`; **never
   estimated**, never recommended. Real quotes required before those lines can be ordered.
2. **Simulated checkout (G.14)** and the **demo site showing the latest run** are Sprint 3 work.
3. **Hourly Automation firing (U1)** still unverified — needed for the continuous Tech check in
   production (the logic runs on demand and PASSES; the scheduled hourly firing is untested).
4. **Parallel sub-agent validation (U3)** untested — affects only a should-have.
5. **Organiser unknowns (G.8)** — scoring weights, pitch duration, submission method — not invented.

---

## 5. Recommended next sprint

**Sprint 3 — demo site (Tasks 5–6):** wire the demo pages to the generated files (read-only, no
hard-coded numbers), build the simulated-checkout flow ("SIMULATED — no real money moves"; first item
offered for cutting; no card/PIN/OTP ever requested or stored), and one-click accept/reject + demo
reset. Then Sprint 4 (test/fix/polish) and Sprint 5 (slides/docs/rehearsal) per Section 10.0.

### Alternatives (pick one or suggest another)

- **A (recommended):** proceed to Sprint 3 as scoped above.
- **B:** insert a short Sprint 2.5 to (i) obtain the 4 supplier quotations and re-run scoring, and
  (ii) verify the hourly Automation firing (U1) before any demo-site work — de-risks Sprint 4.
- **C:** prioritise slides/docs (Sprint 5) earlier so the narrative is locked before polish, then
  return to the demo site — useful if judge messaging matters more than live wiring.
- **D:** hold Sprint 3 and first harden the Verifier/Technology loop with a second independent dataset
  (the golden-mini is small) to raise confidence in the autonomy claims.

---

## 6. Approval gate

Per **Section A**, I am **stopping here**. Please confirm one of the following:

1. **Approve Sprint 2 → start Sprint 3** (option A), or
2. **Approve Sprint 2 → start a different option** (B/C/D, or your own), or
3. **Request changes** to Sprint 2 before approval.

I will not begin Sprint 3 until you say so.
