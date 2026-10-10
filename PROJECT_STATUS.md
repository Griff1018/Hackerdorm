# PROJECT STATUS — Enterprise Buddy

Last update: **2026-10-10 16:22, Sprint 3D feasibility gate** (blocked: WorkBuddy CLI unavailable).

## Where we are

| sprint | window | status |
|---|---|---|
| Sprint 1 — setup, feasibility, data (Tasks 0–2) | 12:00–13:30 | **completed + approved 13:35** (5 revisions) |
| Sprint 2 — agent, departments, tools (Tasks 3–4) | 13:30–20:00 | **completed ~14:30 + approved; Sprint 2.1 fixes completed ~15:08** |
| Sprint 3A — Demo Mode + Customer Operations | 15:17–15:30 | **completed + approved** |
| Sprint 3B — marketplace, campaign, People, social preview | 15:39–15:45 | **completed; external marketplace connection pending; U1 scheduled check pending** |
| Sprint 3C — interactive WorkBuddy toolkit + live demo upgrade | 15:56–16:05 | **completed + approved** |
| Sprint 3D — live WorkBuddy Agent Console | 16:21–feasibility gate | **blocked before build: `codebuddy`/`cbc` unavailable** |
| Sprint 4 — test, fix, polish (Tasks 7–8) | 00:00–03:00 | protected; must start by 00:00 |
| Sprint 5 — slides, docs, rehearsal (Tasks 9–11) | 03:00–09:00 | not started; gated on the G.13 approval of CAPABILITIES/AGENT_WORKFLOW |

Hard deadline: **09:30, 2026-10-11** (target submission 09:00).

## What Sprint 1 produced

- Workspace created; the master instructions imported as `docs/MASTER_INSTRUCTIONS_EXTRACT.md`.
- 10 feasibility checks run — 8 PASS, 1 INCONCLUSIVE, 1 NOT VERIFIED (`docs/WORKBUDDY_FEASIBILITY_CHECKLIST.md`).
- Synthetic dataset: 5 products, 136 sales rows, 5 inventory rows, 8 expenses, 20 material rows
  (17 distinct materials), 13 deliberately seeded defects.
- Golden expected results, hand-computed and cross-checked.
- First versions of `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` (G.13).
- Drafts: charter, requirements, architecture; final: data dictionary.

## What Sprint 2 produced

- **Engine** `app/run_enterprise_buddy.py` wired with all six departments: Operations → Reporting →
  Strategy → Marketing → Verifier, plus the continuous Technology health check.
- **Operations supplier research** (`enterprise_buddy_supplier.py` + `scripts/build_supplier_research.py`):
  39 scored rows across 17 materials, G.11 scoring done **by code**. Full tier (100) = price 40 +
  delivery 20 + MOQ 15 + reliability 15 + location 10; light tier (65) = price 40 + reliability 15 +
  location 10. `docs/SUPPLIER_RESEARCH_PLAN.md` lists which tier applies to each of the 17 materials
  (5 FULL: Chocolate chips, Butter, Chicken filling, Peanut butter, Honey; 12 light).
- **Critical rule enforced**: a supplier row with no comparable price is ranked last and **never
  recommended** — added two regression tests (`test_unpriced_rows_are_never_recommended`,
  `test_material_with_no_priced_supplier_has_no_recommendation`).
- **Strategy market check** (`market_brief.md`): P002 priced RM 4.50 vs Malaysian foodpanda band
  RM 2.40–4.70 → working hypothesis: overstock may be a **purchasing-quantity** problem; no demand or
  causal conclusion is claimed.
- **Marketing draft** (`promo_draft.md`): P005 handoff under the complete G.9 rule (stock on hand AND
  zero eligible sales OR overstock cover), **unsent**, with do-not-claim guardrails.
- **Technology health check** (`enterprise_buddy_tech.py` + `demo/index.html`, `demo/shop_page.html`):
  status **PASS** (13 pass / 0 warn / 0 err). Fixed link-resolution to be page-relative and the
  shop-page stock matcher collision on "6pcs".
- **Verifier** (`verification_report.md`): independent recomputation, **PASSED** (7 checks).
- **Business profile** (`data/business_profile.json` + `enterprise_buddy_profile.py`): synthetic, rejects
  FORBIDDEN_FIELDS (card/account/password/pin/otp/cvv/api_key/secret/token).
- **Ready-to-pay purchase orders** (`enterprise_buddy_purchase.py`): 4 draft POs in `data/output/po/`,
  `purchase_plan.md`, `purchase_orders.json`. POs use the separate `purchasing_budget` (MYR 800.00),
  not recorded rent/fuel expenses; over-budget/unapproved POs do not consume later headroom. Butter has
  substitutes only, Chicken filling has no available eligible priced supplier.
- **Sprint 2.1 safety fixes:** unavailable/inactive listings never recommended or ordered; material
  mismatches never recommended; 24 unittest tests pass; P005 G.9 zero-sales marketing branch is tested.
- **Enterprise Buddy Skill:** `skills/enterprise-buddy-pipeline/SKILL.md` created and packaged as `data/output/enterprise-buddy-pipeline.zip`.
  Fresh owner-prompt proof is in `data/output/fresh_chat_skill_proof/` and exits 0.
- **Sprint 3A:** full Demo Mode and FR-01 Tier B are built and tested. Evidence is in `demo/scenario/`,
  `demo/index.html`, `data/output/customer_demo/`, and `tests/test_features.py`.
- **Sprint 3B:** FR-06 seller-side processor tested against own synthetic inbox files; FR-03 campaign planner
  produced 5 platform drafts; FR-04 produced the owner-set MYR 12.00–15.00/hour job ad and hiring kit;
  FR-05 produced a generic social-feed preview only. No second store was built and no external marketplace
  store path was supplied, so connection remains pending.
- **Sprint 3C:** `app/enterprise_buddy_cli.py` now routes free-form owner intents to deterministic department commands;
  `skills/enterprise-buddy-pipeline/SKILL.md` now requires understanding/plan, before/after department narration,
  adaptation, verification, and approval/file-link closeout. Demo Live Mode renders current outputs and
  polls activity; Demo Mode renders visual cards for all ten steps. `docs/INTERACTIVE_DEMO_TESTS.md` records
  12 prompt/tool routes. Paid-to-received PO loop is tested and updates derived stock without editing inventory.csv.
- `docs/CAPABILITIES.md`, `docs/AGENT_WORKFLOW.md`, `docs/DEMO_SCRIPT.md`, and `README.md` updated; U1
  scheduled firing remains pending until the after-16:35 check.

## Verified tests at this point

| test | result |
|---|---|
| `scripts/generate_sample_data.py` | PASS — reproducible |
| `tests/compute_expected_standalone.py` | PASS — golden values |
| `tests/test_engine.py` (24 tests, unittest) | PASS — supplier eligibility, G.9 zero-sales, purchasing-budget regressions |
| `tests/test_features.py` (3 tests) | PASS — FR-01 golden flow, FR-02 separation/badges, FR-06 total recomputation |
| `tests/test_sprint3b.py` (3 tests) | PASS — FR-06 full seller side, FR-03/04 outputs, FR-05 generic feed |
| Full Sprint 3A owner run | PASS — net 2451.25, 7 actions, 4 draft POs, Verifier 7/7, Tech 12/12, FR-01 9/9 |
| FR-06 project sample inbox | PASS — valid order completed, tampered total rejected, out-of-stock rejected, review summary written |
| `tests/test_po_actions.py` (1 test) | PASS — paid PO → received ledger → current_stock update; inventory.csv unchanged |
| Interactive toolkit routes | PASS — 12 prompt/tool routes recorded in `docs/INTERACTIVE_DEMO_TESTS.md` |
| Fresh Skill owner prompt | PASS — full selected pipeline wrapper, exit 0, Verifier passed |
| `enterprise_buddy_profile` forbidden-field rejection | PASS |

## Known gaps (open items for Sprint 3+)

1. **4 materials need a supplier quotation** (no Malaysian price published): Granola bar wrapper,
   Muffin cup, Paper cookie bag, Plastic cup 500ml — recorded in `supplier_coverage.json`, never estimated.
2. **External marketplace connection** remains pending because no store path was supplied.
3. **Hourly Automation firing** (U1) still unverified — the toolkit and on-demand health check are tested;
   scheduled firing must be checked after 16:35.
4. **Parallel sub-agent validation** (U3) untested — affects only a should-have.
5. **Organiser unknowns** (G.8): scoring weights, pitch duration, submission method — do not invent.

## Current blockers / gates

1. **Sprint 3D feasibility failed before build:** `codebuddy` and `cbc` are unavailable on PATH, so the
   live WorkBuddy CLI, streaming events, and restricted-tool test cannot be verified.
2. **External marketplace connection pending:** no external store path was supplied. FR-06 is complete against
   the own synthetic inbox contract and can connect later without building a second store.
3. **Hourly Automation firing U1** is configured and active. It must be checked after 16:35 against the
   timestamp/trigger in `tech_health_log.csv` before the capability is promoted to fully tested.
4. Local MCP support unverified (U2) and parallel sub-agent validation untested (U3) remain non-blocking.

## Recommended next task

Install/log in to the WorkBuddy CLI and rerun `docs/SPRINT3D_FEASIBILITY_CHECK.md`. Do not build the live
Agent Console until the streaming and restricted-tool checks pass. If the CLI cannot be made available,
choose the documented file-bridge or labelled recorded-replay fallback without presenting it as a live
WorkBuddy agent.
