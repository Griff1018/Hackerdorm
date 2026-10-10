# CAPABILITIES — what Enterprise Buddy can do (Section G.13 — living document)

Updated: end of **Sprint 3B** (2026-10-10). Updated again at the end of every sprint.
Rule: a capability is marked **built and tested** only with evidence from an actual check.
Nothing is marked tested because it is expected to work.

Legend — `built and tested` · `built, not tested` · `planned` · `dropped`

## 1. Product capabilities

| capability | department | status | evidence | known limits |
|---|---|---|---|---|
| Read and validate the 5 CSV inputs (schema, types, enums, ranges, dates) | Operations | **built and tested** | `app/enterprise_buddy_core.py` `validate()`; run flags 5 issue rows (3 error) | duplicates are excluded, never auto-merged |
| Data-quality issue list (file, row/id, issue, severity, resolution) | Operations | **built and tested** | `data/output/data_quality_report.md` written each run | severity-tagged; resolution is a draft |
| Sales / COGS / gross profit / margin / recorded expenses | Reporting | **built and tested** | verifier recomputed net 2451.25, COGS 856.80, expenses 1105.70 (pass) | gross profit is an **estimate**; expenses never netted off |
| Per-product performance table | Reporting | **built and tested** | `business_snapshot.json` per-product rollups | margin N/A when revenue is zero |
| Demand estimate, days of stock, replenishment rounded to pack size | Operations | **built and tested** | P002 = 13.86 days of stock; replenishment rounded to pack | not computed when the count is stale or demand is zero |
| Prioritised action queue with evidence and confidence | Reporting | **built and tested** | `action_queue.csv`; 6 actions, 0 without evidence (verifier-checked) | rule-based; impact "not estimated" unless computable |
| Raw-material and supplier research, top 3 per material (G.11 scoring) | Operations | **built and tested** | `supplier_research.csv` 39 rows / 17 materials, scored by code; `tests/test_engine.py` SupplierScoring green | 17 distinct materials; web prices are comparison-only |
| Light-tier vs full-tier research decision with logged reason | Operations | **built and tested** | `docs/SUPPLIER_RESEARCH_PLAN.md` + `supplier_coverage.json` tier field | light tier scores out of 65 and is labelled "light research" |
| Unsent supplier inquiry drafts | Operations | **planned** | – | No inquiry-draft files exist yet; coverage gaps are reports only and are never sent |
| Market check — one question per run, one-page brief | Strategy | **built and tested** | `data/output/market_brief.md` for the P002 price question | desk research; labelled "not validated with real customers" |
| Marketing handoff — draft promo post | Sales & Marketing | **built and tested** | `promo_draft.md` for **P005** under the corrected G.9 handoff (stock on hand + zero eligible sales), unsent | draft only, never posted |
| Technology health check (on demand), drafts fixes | Technology | **built and tested** | `tech_health_report.md` status PASS (16 pass / 0 warn / 0 err) on demo pages including social preview | on-demand logic is tested; hourly firing is untested (U1); reads and reports only |
| Verifier — independent recomputation, can reject the run | Verifier | **built and tested** | `verification_report.md` PASSED (7 checks) | one re-run, then visible failure |
| Involvement modes: Auto / Ask me / Approve at end (G.10) | Orchestrator | **planned** | – | CLI flags exist, but flags are not an implemented interaction-mode system; ≤ 3 key decisions and end-approval flow remain untested |
| Business profile (local, no account/card data) (G.14) | Orchestrator | **built and tested** | `data/business_profile.json`; `sanitise_profile` rejects FORBIDDEN_FIELDS; tests green | synthetic profile in the demo |
| Ready-to-pay purchase order (owner pays) (G.14) | Operations | **built and tested** | `data/output/po/PO-*.md` + `purchase_orders.json`; 2 POs flagged over remaining budget, not approved | never placed; budget breaches flagged; 1 material needs a quote |
| Simulated checkout (test data only) (G.14) | Demo site | **built and tested** | `demo/index.html` local checkout control + `tests/test_features.py`; status is local only | labelled "SIMULATED — no real money moves"; no payment occurs |
| Demo site showing the latest real run | Demo | **built and tested** | `demo/index.html` Live Mode reads `data/output/` and Demo Mode reads `demo/scenario/`; separation test green | no server-side app yet; network failure is visible rather than faked |
| One-click accept / reject; one-click demo reset | Demo | **built and tested** | localStorage review controls and reset in `demo/index.html`; feature test green | local/simulated review state only |
| FR-02 full Demo Mode walkthrough | Demo | **built and tested** | `demo/scenario/scenario.json` contains 10 steps; toggle/banner/badges/reset and separation tested in `tests/test_features.py` | offline fetch fallback is implemented; visual browser rehearsal remains scheduled polish |
| FR-01 Tier B customer and order operations | Customer Operations | **built and tested** | `data/output/customer_demo/customer_operations_report.md`: 9 checks pass; orders, order board, stock ledger, FAQ, refunds and audit log | synthetic chat only; no real channel, payment, refund or customer data |
| FR-03 one-week campaign planner | Sales & Marketing | **built and tested** | `campaign_plan.md` + 5 files under `social_posts/`; campaign test pass | draft only; general timing guidance; nothing posted |
| FR-04 recruitment assistant and hiring kit | People | **built and tested** | `job_ad_part_time_campus_snack_assistant.md` + `hiring_kit.md`; pay-range/fair-wording test pass | synthetic role; owner confirms Malaysia minimum-wage compliance; no real applicants |
| FR-05 simulated social feed preview | Demo site | **built and tested** | `demo/social_feed.html` + `social_feed_preview.json`; generic simulated screen test pass | preview only; no second store; no fake engagement or platform connection |
| FR-06 marketplace seller side | Operations | **built and tested** | `fr06_sample_run_console.txt`; valid order completed/shipped, tampered total rejected, out-of-stock rejected, simulated label/current stock/review summary written | external store not connected yet; own synthetic inbox contract tested first |
| Interactive WorkBuddy toolkit routing | Orchestrator | **built and tested** | `app/enterprise_buddy_cli.py` exposes brief, stock, suppliers, po, order, faq, refund, marketplace, reviews, campaign, jobad, market, techcheck, verify and full; 12 prompt routes recorded in `docs/INTERACTIVE_DEMO_TESTS.md` | WorkBuddy supplies natural-language understanding/plan narration; deterministic code owns numbers and writes |

## 2. Infrastructure / evidence capabilities

| capability | department | status | evidence | known limits |
|---|---|---|---|---|
| Reproducible synthetic sample dataset (5 products, 136 sales rows, 17 materials, 13 seeded defects) | Data | **built and tested** | `scripts/generate_sample_data.py` runs clean; `data/sample/*.csv` written; sha256 recorded in `tests/fixtures/expected_sample.json` | only `sales.csv` is generated; the rest are hand-authored |
| Independent golden expected-results calculator | Test | **built and tested** | `tests/compute_expected_standalone.py` runs on both datasets; output matched all hand arithmetic (`tests/EXPECTED_RESULTS.md` §A.7) | it is the reference, so a shared bug would hide itself — mitigations: hand arithmetic + a second tiny fixture |
| Golden mini fixture with fully hand-computed results | Test | **built and tested** | `tests/fixtures/golden_mini/` + `tests/EXPECTED_RESULTS.md` §A | 3 products only |
| Supplier-scoring arithmetic fixture (G.11) | Test | **built and tested** | `tests/fixtures/supplier_score_example.csv`, hand-worked in `EXPECTED_RESULTS.md` §C | invented test suppliers, no source URLs — arithmetic only, not research |
| Deterministic Python runtime with exact decimal money | Platform | **built and tested** | feasibility check F2/F3: `0.1+0.2 = 0.3` exactly; tiny CSV sum 11.90 | – |
| Built-in web research | Platform | **built and tested** | feasibility check F5: 5 results with URLs, retrieved 2026-10-10 | results must carry source + retrieval date; cached fallback labelled |
| Sub-agent execution (Analyst / Verifier split) | Platform | **built and tested** (execution only) | feasibility check F7: two sub-agents wrote `tests/_probe/probe_A.txt` and `probe_B.txt` | **parallel** invocation in one message is not yet tested (U3) |
| WorkBuddy Automation (scheduling) exists | Platform | **built and tested** (configuration) | hourly automation `Enterprise Buddy hourly Technology health check` created and active; view proof recorded in `docs/TECH_AUTOMATION_PROOF.md` | scheduled firing remains pending until the first hourly callback is observed (U1) |
| Local MCP server support | Platform | **not verified** | feasibility check F10/F11: no `mcp.json`; docs page returned empty | do not depend on it; built-ins first (Section D) |
| Hourly Technology Automation producing logged runs | Technology | **built, not tested** | active hourly configuration exists; `tech_health_log.csv` has on-demand proof only | U1 scheduled firing has not been independently observed; needs laptop awake and WorkBuddy running (G.12) |
| Slide preparation inside WorkBuddy | Presentation | planned (Sprint 5) | – | path not yet verified (U5) |

## 3. Explicitly NOT built (roadmap — vision slide only)

Client & Customer Management (onboarding, scheduling, invoice reminders) · Customer Support
(FAQ answers, inquiry sorting) · full "start my business" feasibility mode (audience, market size,
competitors, costs) · period-over-period trends · natural-language questions over computed metrics ·
receipt input.
