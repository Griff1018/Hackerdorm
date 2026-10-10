# REQUIREMENTS — Enterprise Buddy (DRAFT, Sprint 1)

Every committed requirement has an ID and an acceptance test. IDs are stable and are referenced by
`docs/CAPABILITIES.md` and `docs/TEST_PLAN.md` (Sprint 4).

Conventions: **MUST** = committed MVP; **SHOULD** = after the MVP works; **WON'T** = non-goal.

## 1. Functional requirements

| ID | requirement | acceptance test |
|---|---|---|
| FR-01 | Load the four CSV inputs (products, sales, inventory, expenses) and materials.csv | all five files read; row counts reported; input files left byte-identical |
| FR-02 | Validate schema and contents per `docs/DATA_DICTIONARY.md` §2 | all 13 seeded defects in `data/sample/DATASET_NOTES.md` are reported with file, row/id, severity |
| FR-03 | Classify rows as valid / rejected / uncertain; never silently convert a bad value | counts of accepted, rejected and uncertain rows reported; excluded rows reconcile with the quality report |
| FR-04 | Compute the Section 5 metric set deterministically | every value equals `tests/fixtures/expected_sample.json` and `expected_golden_mini.json` |
| FR-05 | Per-product units, net revenue, COGS, gross profit, margin | matches the per-product tables in `tests/EXPECTED_RESULTS.md`; margin is N/A when revenue is zero |
| FR-06 | Demand estimate, days of stock, replenishment rounded to pack size | P001 → 24, P002 → 0, P004 → 12, P003 → not computed (stale), P005 → cannot be estimated |
| FR-07 | Build an action queue with ID, priority rule, evidence, confidence, next step, status | 100 % of quantitative actions carry at least one evidence reference, or are marked "insufficient data" |
| FR-08 | Verifier role independently recomputes key totals from source rows | a deliberately seeded mismatch is caught and logged; the run is marked failed, not quietly corrected |
| FR-09 | Operations: research every material in materials.csv, score every supplier found (G.11), mark the top 3 | 17 distinct materials appear in `supplier_research.csv`; every row has source URL + retrieval date or "not found"; scores reproduce the G.11 rule |
| FR-10 | Reporting: snapshot, action queue, data-quality report, daily brief | all four files exist, are readable and reconcile with each other |
| FR-11 | Strategy: one focused market-check question per run → one-page brief, labelled desk research | brief exists, carries sources and retrieval dates, and is labelled "not validated with real customers" |
| FR-12 | Marketing handoff: draft a promo post for a product that needs selling | draft exists in a known file and is **never posted**; the run log shows no external send |
| FR-13 | Technology: hourly health check of the demo site + `demo/shop_page.html`, writes `tech_health_report.md` and appends to `tech_health_log.csv` | a seeded website problem is detected with evidence; nothing is changed without approval |
| FR-14 | "Run check now" triggers the same Technology check on demand | button works live in the demo |
| FR-15 | Three involvement modes at the start of a run (Auto / Ask me at key decisions / Approve at end) | mode question asked once; Auto is the default if unanswered; ≤ 3 key decisions when asking |
| FR-16 | Business profile saved locally (`data/business_profile.json`) — name, area, delivery area, monthly budget, preferred payment type, preferred suppliers | no account/card/e-wallet number, password, PIN or OTP field exists anywhere; if a user types one, it is refused and not stored |
| FR-17 | Ready-to-pay purchase order on approval (`data/output/orders/PO-<id>.md`) | PO contains supplier, pack-rounded quantities, prices with source + retrieval date, total, remaining-budget check, payment type, supplier link; status draft → approved → ready to pay → paid |
| FR-18 | Simulated checkout (test data only) | every screen and receipt shows "SIMULATED — no real money moves"; no network call to a live payment account |
| FR-19 | Demo site shows the **actual** outputs of the latest run | figures reconcile to `business_snapshot.json`; no hard-coded demo numbers |
| FR-20 | One-click accept / reject on an action; one-click demo reset | status changes are recorded; reset returns the workspace to a clean state |
| FR-21 | Run metadata: run_id, period, currency, assumptions, warnings, completion status | present in the snapshot and on the site; stale outputs cannot be mistaken for the latest run |
| FR-22 | Dynamic adaptation with logged reasons | ≥ 1 adaptation path demonstrated (stale count → recount; short history → low-confidence label; excluded rows → metric marked affected; verifier mismatch → one re-run then visible failure) |

## 2. Non-functional requirements

| ID | requirement | acceptance test |
|---|---|---|
| NFR-01 | Deterministic, reproducible calculations using decimal money | golden tests pass on two consecutive clean runs |
| NFR-02 | Bounded run: step budget ~30 tool/action steps, ≤ 2 retries per stage, no infinite loops | a run either completes or stops with a clear blocker |
| NFR-03 | No external side effects: no orders, payments, emails, posts | run log shows zero external writes |
| NFR-04 | No secrets in files, prompts, screenshots or slides | repository scan for key-like strings in Sprint 4; none found |
| NFR-05 | Synthetic data visibly labelled | the label appears on the demo site and in every report |
| NFR-06 | Clear empty / loading / error / invalid-data states | each section reviewed against an empty and a broken dataset |
| NFR-07 | Accessibility basics: contrast, keyboard support for key controls, readable type, responsive layout | check in Sprint 4; limitations stated if unmet |
| NFR-08 | WorkBuddy is the runtime (G.6) | the demo run starts with a prompt inside WorkBuddy |
| NFR-09 | Web findings show source and retrieval date; cached fallback is labelled | every research row carries both; a network failure falls back to a labelled cached file |
| NFR-10 | Failure honesty | no "pass" is claimed without evidence; failed tests are preserved in `docs/TEST_RESULTS.md` |

## 3. Non-goals (WON'T, unless the user approves)

Full accounting / tax / audit · real payment or purchasing · live POS / banking / supplier
integrations · automatic external messaging · predictive models on real data · unbounded multi-agent
collaboration · auth / hosting / billing · claims of real-world revenue uplift.

## 4. Definition of done (MVP)

All release gates in master-instructions Section 9.2 are true, or every exception is explicit and
approved by the user; `docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` match the build and are
user-approved (G.13).
