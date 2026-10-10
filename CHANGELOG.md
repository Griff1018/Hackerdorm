# CHANGELOG — Enterprise Buddy

Entries record meaningful changes to the product, architecture, calculations, interface and
deliverables. Updated at the end of every sprint.

## 2026-10-10 — Sprint 1 (Tasks 0–2): setup, feasibility and data

**Added**
- Workspace created at the WorkBuddy project root: `docs/`, `data/sample/`, `data/output/`,
  `tests/fixtures/`, `scripts/`, `demo/`, `presentation/`, `app/`, `skills/`.
  Deviation from §7.4: `scripts/` was added for the data generator.
- `docs/MASTER_INSTRUCTIONS_EXTRACT.md` — the master instructions imported into the workspace.
- `PROJECT_STATUS.md`, `DECISIONS_LOG.md`, `ASSUMPTIONS_AND_RISKS.md`, `CHANGELOG.md` (this file).
- `docs/PROJECT_CHARTER.md` (draft), `docs/REQUIREMENTS.md` (draft), `docs/SYSTEM_ARCHITECTURE.md`
  (draft), `docs/DATA_DICTIONARY.md`, `docs/WORKBUDDY_FEASIBILITY_CHECKLIST.md`.
- `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` — first versions (G.13).
- `docs/DEPENDENCIES.md`, `docs/FEATURE_REQUESTS.md`, `README.md` (draft).
- Sample data: `data/sample/products.csv`, `sales.csv`, `inventory.csv`, `expenses.csv`,
  `materials.csv`, `DATASET_NOTES.md`.
- `scripts/generate_sample_data.py` — seeded (20261010), regenerates `sales.csv` only.
- `tests/compute_expected_standalone.py` — independent golden calculator.
- `tests/fixtures/golden_mini/` — 4 small CSVs with fully hand-computed results.
- `tests/fixtures/supplier_score_example.csv` — G.11 arithmetic fixture (invented suppliers, no URLs).
- `tests/EXPECTED_RESULTS.md` — hand arithmetic, golden values, G.5 targets set before testing.
- `tests/fixtures/expected_sample.json`, `tests/fixtures/expected_golden_mini.json`,
  `tests/expected_results_auto_sample.md`, `tests/expected_results_auto_golden_mini.md`.

**Changed**
- `sales.csv` generation was reduced from 1 259 rows to 136 rows (one aggregated line per
  product per day, sold-day probability per product) so the dataset stays auditable.
- `inventory.csv`: the duplicate record moved from P003 to P005 and the stale count stayed on P003,
  so the duplicate defect and the stale-count dynamic adaptation are both visible instead of one
  masking the other.
- Sample CSVs were rewritten without a UTF-8 BOM (a BOM broke the `product_id` header lookup).

**Decisions recorded**: D-01 … D-10 in `DECISIONS_LOG.md` (all pending approval).

**Not done**: no product code, no agent, no demo site, no slides — deliberately (Section 14).

## 2026-10-10 — Sprint 2 (Tasks 3–4): agent, departments and tools

**Added**
- `app/enterprise_buddy_core.py` — Config, `validate()`, `calculate()` (decimal money), snapshot + action queue.
- `app/enterprise_buddy_supplier.py` — G.11 scoring (`score_material`), full/light tiers, parses `price_unit`,
  **never recommends an unpriced row**.
- `app/enterprise_buddy_outputs.py` — reports (snapshot, action queue, data-quality, daily brief), market brief,
  promo draft builders.
- `app/enterprise_buddy_profile.py` — business profile load + `sanitise_profile` (rejects FORBIDDEN_FIELDS).
- `app/enterprise_buddy_purchase.py` — draft PO builder: cumulative remaining-budget check, pack-round-up,
  review-flag keywords, never auto-approves an over-budget or no-price line.
- `app/enterprise_buddy_tech.py` — Technology hourly/on-demand health check (read-only, page-relative links).
- `app/run_enterprise_buddy.py` — orchestrator wiring all six departments + CLI (`--profile`, `--market-check`,
  `--po`, `--tech`, `--tech-trigger`).
- `scripts/build_supplier_research.py` — builds `supplier_research_input.csv` from raw research; prices
  normalised **by code**, gaps left blank (never estimated).
- `data/business_profile.json`, `data/market_check.json` — synthetic profile + Strategy research input.
- `demo/index.html`, `demo/shop_page.html` — synthetic storefront + shop page (SYNTHETIC-labelled,
  stock mirrored from `inventory.csv` for the tech check).
- `docs/SUPPLIER_RESEARCH_PLAN.md` — per-material light/full tier decision (5 FULL, 12 light).

**Changed**
- Supplier scoring now ranks unpriced rows last and forces `recommended=no` (was incorrectly marking
  them recommended). Two regression tests added (20 total, all green).
- Purchase budget accounting changed from static per-PO to **cumulative** remaining (POs are paid one
  at a time); output field renamed `budget_remaining_after_this`.
- Tech health check link resolution changed from project-root-relative to **page-relative** (correct
  for sibling links); fixed a stock-matcher collision on the "6pcs" pack token in P001.
- `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` promoted Sprint 2 items to **built and tested**.
- `PROJECT_STATUS.md` advanced to end-of-Sprint-2.

**Verified**
- Full engine run (`--po --tech`): net 2451.25, 6 actions, verify PASSED (7 checks), tech PASSED
  (13/0/0), 6 draft POs (2 over budget, 1 material needs a quote).
- `tests/test_engine.py`: 20/20 pass.

**Open gaps (hand to Sprint 3+)**
- 4 materials need a supplier quotation (Granola bar wrapper, Muffin cup, Paper cookie bag, Plastic cup
  500ml) — recorded in `supplier_coverage.json`, never estimated.
- Simulated checkout + demo-site live wiring + one-click review (Sprint 3).
- Hourly Automation firing (U1) and parallel sub-agent validation (U3) still unverified.

## 2026-10-10 — Sprint 2.1: safety and evidence fixes

**Changed**
- Supplier eligibility now requires a comparable price, an available/active listing, and a match to
  the specified material. Inactive SupplyBunny chicken is never recommended or ordered; Butter spreads
  are shown as `substitute - owner decides` and never recommended. No exact eligible supplier produces
  `no supplier found` rather than a misleading PO.
- Added separate `purchasing_budget` and `purchasing_budget_used` profile fields. Rent/fuel/other
  recorded expenses no longer reduce PO headroom; an over-budget/unapproved PO does not consume later
  headroom. The rule is printed in `purchase_plan.md` and each PO.
- Restored complete G.9 marketing trigger. P005 now qualifies through stock-on-hand + zero eligible
  sales in the demand window; the deviation and correction are recorded in `DECISIONS_LOG.md`.
- Reworded Strategy output as a testable hypothesis, not a demand or causal conclusion.
- Downgraded unsupported capability claims: interaction modes are planned, supplier inquiry drafts are
  planned, and hourly Technology firing is built but not tested (U1).
- Fixed workflow documentation to use actual function names (`enterprise_buddy_core.validate`,
  `enterprise_buddy_core.calculate`, `enterprise_buddy_supplier.score_material`, `enterprise_buddy_tech.run_check`).

**Added**
- 4 new regression tests (24 total): unavailable supplier, substitute material, unapproved-PO budget
  carry-forward, and G.9 zero-sales marketing branch.
- `skills/enterprise-buddy-pipeline/SKILL.md` and validated package `data/output/enterprise-buddy-pipeline.zip`.
- Skill proof in `data/output/skill_proof/`: one owner prompt completed the full pipeline with exit 0,
  verification passed, 4 draft POs and Technology health pass.
- `docs/FEATURE_UPDATE_01.md` (saved addendum) and FR-01..FR-06 entries/options in
  `docs/FEATURE_REQUESTS.md`.

**Verified**
- `tests/test_engine.py`: **24/24 pass**.
- Full corrected engine run: net 2451.25, 7 actions, 13 priced-material listings, 4 draft POs,
  3 no-PO needed-material gaps, Verifier passed 7/7, Technology on-demand passed 13/13.

**Gate**
- Feature Update 01 was approved in full and split into gated Sprint 3A/3B work. Sprint 3A is complete;
  Sprint 3B remains blocked until the Sprint 3A checkpoint is approved.

## 2026-10-10 — Sprint 3A: Demo Mode and Customer Operations

**Added**
- `app/enterprise_buddy_customer.py` — FR-01 Tier B synthetic customer operations: menu lookup, one configured
  add-on, confirmation, order board, policies FAQ, special-request reconfirmation, cancellation,
  allergy escalation, simulated refund limit, stock ledger, audit log and transcripts.
- `demo/scenario/scenario.json` and rebuilt `demo/index.html` — FR-02 full ten-step Demo Mode with
  Live/Demo separation, badges, banner, progress controls, reset, offline-visible failures, local review
  controls and simulated checkout.
- `data/sample/menu.csv`, `promotions.csv`, `customers.csv`, `business_policies.md` — synthetic FR-01 contracts.
- `tests/test_features.py` — FR-01/FR-02/FR-06 deterministic checks.
- `docs/SPRINT3A_CHECKPOINT.md`, `docs/SUPPLIER_FOLLOWUP_2026-10-10.md`,
  `docs/TECH_AUTOMATION_PROOF.md`.

**Changed**
- Profile and demo naming aligned to **Campus Crumb**, the student-run campus snack and drink seller.
- `docs/CAPABILITIES.md`, `docs/AGENT_WORKFLOW.md`, `PROJECT_STATUS.md` updated at the Sprint 3A gate.

**Verified**
- `tests/test_engine.py`: 24/24 pass.
- `tests/test_features.py`: 3/3 pass.
- FR-01 Tier B report: 9/9 checks pass; golden order total MYR 16.50; allergy and refund controls pass.
- Full Sprint 3A owner run: exit 0; net revenue MYR 2,451.25; Verifier 7/7; Technology 12/12.
- Source CSV hashes unchanged after feature replay.

**Gate**
- STOP at `docs/SPRINT3A_CHECKPOINT.md`. Sprint 3B must not be promoted until checkpoint approval.
- FR-06, FR-03, FR-04 and FR-05 remain planned for Sprint 3B. If still running at 23:00, downgrade
  FR-04 then FR-03 to CONCEPT screens, preserving Sprint 4 testing and Sprint 5 rehearsals.

## 2026-10-10 — Sprint 3B: seller side, campaign, People and social preview

**Added**
- `app/enterprise_buddy_marketplace.py` — full synthetic seller-side processor: recomputed totals, invalid/out-of-stock
  rejection, internal marketplace orders, stock ledger/current stock, status history, pick/pack list,
  simulated shipping label, buyer events, review summary and audit trail.
- `app/enterprise_buddy_campaign_people.py` — FR-03 five-day campaign planner and FR-04 synthetic job ad/hiring kit.
- `demo/social_feed.html` + `data/output/social_feed_preview.json` — FR-05 generic simulated social preview;
  no second store and no real platform branding.
- `tests/test_sprint3b.py` — 3B contract tests.

**Changed**
- `enterprise_buddy_tech.py` now checks the social-feed preview in addition to Live/Demo and shop pages.
- `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` promoted FR-03/04/05/06 with evidence and kept
  the external-store connection explicitly pending.
- Campaign/job outputs use the owner-set synthetic pay range **MYR 12.00–15.00/hour** and require the
  owner to confirm minimum-wage compliance before posting.
- Marketing evidence correctly identifies **P005**, not P002, as the current G.9 handoff.

**Verified**
- `tests/test_sprint3b.py`: **3/3 pass**.
- Project sample inbox: valid order `MP-20261010-0003` reached completed; `MP-20261010-0004` tampered total
  rejected; `MP-20261010-0005` out-of-stock rejected; review summary includes exact quotes and P1 allergy escalation.
- FR-03: 5 draft posts; FR-04: job ad + hiring kit; FR-05: generic simulated feed preview.
- Technology: 16/16 on-demand checks pass after adding the social preview.

**Open proof**
- The hourly Automation is active and has an activation-proof log row. Current time is before 16:35, so the
  scheduled callback has not yet been checked; U1 remains built but not tested until the post-16:35 inspection.
- External marketplace store path was not supplied; no connection is claimed.

## 2026-10-10 — Sprint 3C: interactive WorkBuddy toolkit and live demo upgrade

**Added**
- `app/enterprise_buddy_cli.py` — deterministic subcommands: `brief`, `stock`, `suppliers`, `po`, `order`, `faq`,
  `refund`, `marketplace`, `reviews`, `campaign`, `jobad`, `market`, `techcheck`, `verify`, `full`.
- `app/enterprise_buddy_po_actions.py` — owner-controlled simulated paid/received PO state; received materials append
  `purchase_stock_ledger.csv` and update derived `current_stock.csv` without editing `inventory.csv`.
- `tests/test_po_actions.py` — received-stock loop regression test.
- `docs/INTERACTIVE_DEMO_TESTS.md` — 12 free-form prompt routes with plans/departments/commands/evidence.
- `docs/DEMO_SCRIPT.md` — projector demo flow and interactive WorkBuddy moment.

**Changed**
- `skills/enterprise-buddy-pipeline/SKILL.md` now mandates understanding/plan narration, before/after department
  narration, adaptation, verification of new numbers, permission boundaries and evidence-link closeout.
- `demo/index.html` now renders real Live Mode sections: attention/daily brief, supplier scoring/source links,
  POs, customer board/chat, campaign, job ad, marketplace label/review summary, and auto-refresh activity.
- Demo Mode now shows a visual card/table/chat/PO/label/post for every one of its ten steps.
- `README.md` now contains the one-line `python -m http.server 8080` start command and the no-server guidance.
- Technology static-link checking ignores runtime template links while continuing to check all static links.

**Verified**
- `tests/test_engine.py`: 24/24 pass.
- `tests/test_features.py`: 3/3 pass.
- `tests/test_sprint3b.py`: 3/3 pass.
- `tests/test_po_actions.py`: 1/1 pass.
- Toolkit help exposes all requested subcommands; 12 interactive routes are recorded and pass.
- Skill package validates and is refreshed at `data/output/enterprise-buddy-pipeline.zip`.

**Checkpoint**
- Sprint 3C is complete. External marketplace connection remains pending because no store path was supplied.
- Hourly Automation scheduled-callback proof remains a separate post-16:35 check; do not promote U1 before that evidence exists.
