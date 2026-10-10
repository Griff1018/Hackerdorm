# PROJECT CHARTER — BizFlow (DRAFT, Sprint 1)

Status: **draft**. Pending the Sprint 1 checkpoint and, where the master instructions require it,
explicit user approval. It will be refreshed at the end of each sprint.

## 1. Product

**BizFlow — The AI Operations Agent for Microbusinesses.**
Core promise: *from business data to verified business actions.*

## 2. Problem

A student entrepreneur or microbusiness owner keeps sales, product costs, stock and expenses in
separate, hand-maintained records. Reconciling them by hand costs time, and low stock, thin margins,
incomplete records and urgent tasks are easy to miss. BizFlow validates the records, computes
explainable metrics, identifies supported risks and prepares a prioritised, evidence-backed action
queue for the owner to review.

**Framing discipline:** the pain points above are stated as a **hypothesis** until real user
feedback is collected. No interview has been conducted yet, and no real-world impact figure exists.

## 3. Primary user

Student entrepreneur / microbusiness owner: limited time, limited formal business-analysis
experience, uses spreadsheets or simple exports, needs next steps more than an analytics platform,
and must stay in control of spending and consequential decisions.

Demo persona (synthetic): "Campus Crumb", a student-run campus snack & drink seller in Malaysia
(`data/sample/`).

## 4. Objectives

1. One owner prompt → a complete, verified, end-to-end run with no intermediate hand-holding
   (Section G.7 / judging criterion 4).
2. Every number reproducible by deterministic code; every recommendation traceable to rows or
   formulas (Section 6).
3. Results usable at once: brief, prioritised actions, replenishment list, recount checklist,
   supplier comparison, drafted-but-unsent documents (Section 3, Step 8).
4. Demonstrably safe: nothing is ordered, paid, posted or sent; consequential actions wait for the
   owner (Sections E, 2.3, G.14).

## 5. Scope for the hackathon (Section G.9)

| AI department | status |
|---|---|
| Operations (validation, stock, replenishment, full raw-material & supplier research) | **BUILT (planned for Sprint 2)** |
| Reporting & Housekeeping (sales, COGS, gross profit/margin, expenses, data-quality report, daily brief) | **BUILT (planned for Sprint 2)** |
| Sales & Marketing (light handoff: draft a promo post, never posted) | **BUILT (planned for Sprint 2)** |
| Strategy — light market check (one focused question per run, desk research only) | **BUILT (planned for Sprint 2)** |
| Technology (hourly health check of the demo site + sample shop page, drafts fixes, changes nothing) | **BUILT (planned for Sprint 2/3)** |
| Verifier (independent re-check of every department) | **BUILT (planned for Sprint 2)** |
| Client & Customer Management, Customer Support, full "start my business" feasibility | **ROADMAP — vision slide only** |

## 6. Non-goals

Full accounting / tax / audit · real payments, purchasing or sending orders · live POS, e-commerce,
banking or supplier integrations · automatic external messages · predictive models needing real
training data · open-ended multi-agent collaboration · auth, multi-tenant hosting, billing ·
claims of revenue uplift, stockout prevention or accountant replacement.

Approved exception: ready-to-pay purchase orders the owner pays themselves, and a clearly labelled
**simulated** checkout on test data (Section G.14). No real money moves.

## 7. Success measures (targets set before testing — Section 9.3)

See `tests/EXPECTED_RESULTS.md` §D: seeded-defect detection 13/13, golden calculations 100 %,
action traceability 100 %, end-to-end clean runs 3/3. Effort comparison and user feedback to be
measured or explicitly declared unmeasured.

## 8. Constraints

Deadline **09:30, 2026-10-11** · live demo required · built and presented in Tencent WorkBuddy ·
synthetic data only · no secrets in files, prompts, screenshots or slides · WorkBuddy must be the
runtime, not merely the code writer (G.6).

## 9. Deliverables

Working agent + demo site · short deck (6–7 slides around the live demo) · this documentation set ·
`docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` approved by the user before slides (G.13 gate).
