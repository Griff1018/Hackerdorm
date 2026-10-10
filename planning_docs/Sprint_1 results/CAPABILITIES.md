# CAPABILITIES — what Enterprise Buddy can do (Section G.13 — living document)

Updated: end of **Sprint 1** (2026-10-10). Updated again at the end of every sprint.
Rule: a capability is marked **built and tested** only with evidence from an actual check.
Nothing is marked tested because it is expected to work.

Legend — `built and tested` · `built, not tested` · `planned` · `dropped`

## 1. Product capabilities

| capability | department | status | evidence | known limits |
|---|---|---|---|---|
| Read and validate the 5 CSV inputs (schema, types, enums, ranges, dates) | Operations | planned (Sprint 2) | – | – |
| Data-quality issue list (file, row/id, issue, severity, resolution) | Operations | planned (Sprint 2) | – | duplicates are excluded, never auto-merged |
| Sales / COGS / gross profit / margin / recorded expenses | Reporting | planned (Sprint 2) | – | gross profit is an **estimate**; expenses never netted off |
| Per-product performance table | Reporting | planned (Sprint 2) | – | margin N/A when revenue is zero |
| Demand estimate, days of stock, replenishment rounded to pack size | Operations | planned (Sprint 2) | – | not computed when the count is stale or demand is zero |
| Prioritised action queue with evidence and confidence | Reporting | planned (Sprint 2) | – | rule-based; impact "not estimated" unless computable |
| Raw-material and supplier research, top 3 per material (G.11 scoring) | Operations | planned (Sprint 2) | – | 17 distinct materials in the sample; web prices are comparison-only |
| Light-tier vs full-tier research decision with logged reason | Operations | planned (Sprint 2) | – | light tier scores out of 65 and is labelled "light research" |
| Unsent supplier inquiry drafts | Operations | planned (Sprint 2) | – | never sent |
| Market check — one question per run, one-page brief | Strategy | planned (Sprint 2) | – | desk research; labelled "not validated with real customers" |
| Marketing handoff — draft promo post | Sales & Marketing | planned (Sprint 2) | – | draft only, never posted |
| Technology health check (hourly + on demand), drafts fixes | Technology | planned (Sprint 2–3) | – | reads and reports only; changes nothing without approval |
| Verifier — independent recomputation, can reject the run | Verifier | planned (Sprint 2) | – | one re-run, then visible failure |
| Involvement modes: Auto / Ask me / Approve at end (G.10) | Orchestrator | planned (Sprint 2) | – | ≤ 3 key decisions when asking; Auto default |
| Business profile (local, no account/card data) (G.14) | Orchestrator | planned (Sprint 2) | – | synthetic profile in the demo |
| Ready-to-pay purchase order (owner pays) (G.14) | Operations | planned (Sprint 2–3) | – | never placed; budget breaches flagged |
| Simulated checkout (test data only) (G.14) | Demo site | planned (Sprint 3) | – | labelled "SIMULATED — no real money moves"; first item offered for cutting |
| Demo site showing the latest real run | Demo | planned (Sprint 3) | – | reads generated files; no hard-coded numbers |
| One-click accept / reject; one-click demo reset | Demo | planned (Sprint 3) | – | local/simulated review state only |

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
| WorkBuddy Automation (scheduling) exists | Platform | **built, not tested** (listing only) | feasibility check F6: list call succeeded, empty | hourly firing untested (U1); created in Sprint 3 |
| Local MCP server support | Platform | **not verified** | feasibility check F10/F11: no `mcp.json`; docs page returned empty | do not depend on it; built-ins first (Section D) |
| Hourly Technology Automation producing logged runs | Technology | planned (Sprint 3) | – | needs the laptop awake and WorkBuddy running (G.12) |
| Slide preparation inside WorkBuddy | Presentation | planned (Sprint 5) | – | path not yet verified (U5) |

## 3. Explicitly NOT built (roadmap — vision slide only)

Client & Customer Management (onboarding, scheduling, invoice reminders) · Customer Support
(FAQ answers, inquiry sorting) · full "start my business" feasibility mode (audience, market size,
competitors, costs) · period-over-period trends · natural-language questions over computed metrics ·
receipt input.
