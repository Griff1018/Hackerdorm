# Sprint 3A Checkpoint — Campus Crumb / Enterprise Buddy

**Build-time gate:** Sprint 3A is complete. Per the approved split, stop here before promoting Sprint 3B
(FR-06, FR-03, FR-04, FR-05) into the product. The Sprint 3B code/output rehearsal artifacts are not
claimed as the Sprint 3B checkpoint; they must be rerun and accepted after this gate.

## Scope completed

- **FR-02 full Demo Mode:** Live/Demo toggle; ten-step offline-readable scenario; LIVE FEATURE,
  PROTOTYPE and CONCEPT badges; persistent Demo Mode banner; Back/Next progress controls; reset;
  visible failure when scenario/live outputs cannot be read; Live Mode reads `data/output/`, Demo Mode
  reads `demo/scenario/`.
- **FR-01 Tier B:** synthetic chat ordering; menu/promotion file lookup; one configured add-on; order
  confirmation; order board; policy FAQ; special-request reconfirmation; cancellation before preparation;
  simulated refund within MYR 10.00 limit; above-limit refund escalation; allergy escalation; audit log;
  stock ledger; no changes to `data/sample/inventory.csv`.
- **Demo-site basics:** local accept/reject controls; simulated checkout control; reset; latest-output
  Live Mode metrics; synthetic safety boundary; no real platform or payment connection.
- **Profile alignment:** `data/business_profile.json` now identifies **Campus Crumb**, a student-run
  campus snack and drink seller, with campus delivery area.
- **Supplier follow-up:** FarmiHub confirms an available exact Chicken Fillet source but quotation only;
  KHL Chicken Fillet is marked Pre Order; no verified exact pure dairy Butter listing was found. Chicken
  and Butter remain no eligible priced supplier / quotation-needed cases.
- **Skill proof:** fresh-prompt harness recorded under `data/output/fresh_chat_skill_proof/`.
- **Technology Automation:** hourly automation created and active; configuration viewed successfully.
  The first log row after activation is an on-demand run, so scheduled U1 firing remains honestly marked
  built but not tested until a scheduled callback is observed.

## Evidence

| check | result |
|---|---|
| `tests/test_engine.py` | 24/24 pass |
| `tests/test_features.py` | 3/3 pass |
| Full owner pipeline with FR-01 flags | exit 0; net revenue MYR 2,451.25; 7 actions; Verifier passed 7/7; Technology passed 12/12 |
| FR-01 Tier B report | `data/output/customer_demo/customer_operations_report.md`: 9/9 checks pass |
| Customer golden order | 2 cookies + 1 configured tea add-on = MYR 16.50; ledger writes P001 -2, P002 -1 |
| Customer safety | allergy escalated; special request requires reconfirmation; cancellation does not deduct stock |
| Simulated refunds | MYR 5.00 marked simulated approved; MYR 25.00 escalated above MYR 10.00 limit |
| Source-file safety | `data/sample/*.csv` hashes unchanged after customer and marketplace test replay |
| Demo separation | ten steps/badges/toggle/reset and Live/Demo source separation test pass |
| Fresh Skill owner prompt | `data/output/fresh_chat_skill_proof/run_console.txt`: exit 0; Verifier passed; FR-01 passed |
| Automation | active hourly configuration; scheduled callback still pending observation (U1) |

## Documentation updated

- `docs/CAPABILITIES.md`: FR-01 and FR-02 promoted to built and tested; FR-03/04/05/06 remain Sprint 3B planned;
  hourly firing remains built but not tested.
- `docs/AGENT_WORKFLOW.md`: customer-operations flow, outputs, department handoff, and actual function names updated.
- `PROJECT_STATUS.md`, `CHANGELOG.md`, `DECISIONS_LOG.md`: Sprint 3A checkpoint and decisions recorded.
- `docs/SUPPLIER_FOLLOWUP_2026-10-10.md`, `docs/TECH_AUTOMATION_PROOF.md` added.

## Schedule control

- Sprint 4 testing must start by **00:00**.
- Sprint 5 slides must start by **03:00**.
- During Sprint 3B, if work is still running at **23:00**, downgrade FR-04 first and FR-03 second to
  clearly labelled CONCEPT screens. Do not cut verification, honest badges, testing, or rehearsals.

## Approval gate

**STOP here.** Please approve Sprint 3A and authorize Sprint 3B, or request changes. Sprint 3B will
then implement and test, in order: **FR-06 full seller side**, **FR-03 campaign planner**, **FR-04 job-ad
and hiring kit**, and **FR-05 social feed preview only**. No second store will be built; FR-06 will use the
own sample inbox first and connect to the separate marketplace store only when that store is ready.
