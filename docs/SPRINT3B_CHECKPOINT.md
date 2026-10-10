# Sprint 3B Checkpoint — Enterprise Buddy

## Scope completed

- **FR-06 full seller side:** processed Enterprise Buddy-owned synthetic inbox files; recomputed totals from the
  catalogue; rejected a tampered total; rejected an out-of-stock order; wrote `orders.csv`,
  `current_stock.csv`, `stock_ledger.csv`, status histories, pick/pack list, simulated shipping label,
  and audit entries; processed delivered/receipt events; wrote review summary with exact quotes, themes,
  action items and P1 allergy escalation.
- **FR-03 campaign planner:** one-week Monday-Friday calendar with five platform drafts under
  `data/output/social_posts/`; all unsent and labelled draft-only.
- **FR-04 People:** synthetic job ad and hiring kit. Pay remains the owner-set **MYR 12.00–15.00/hour**;
  the owner must confirm Malaysia minimum-wage/employment compliance before posting. No real applicants are
  collected or screened.
- **FR-05:** generic social-feed preview only, using `social_feed_preview.json`; no second store, no real
  platform branding, no likes/comments/followers/reviews/ratings.

## FR-06 sample-inbox proof

| sample | result |
|---|---|
| `MP-20261010-0003` | valid order → received → confirmed → packing → shipped → delivered → completed |
| `MP-20261010-0004` | displayed total MYR 0.00 rejected; Enterprise Buddy recomputed MYR 7.50 |
| `MP-20261010-0005` | quantity 999 rejected out of stock; stock unchanged |
| `RV-0003` | packaging theme/action evidence retained as an exact quote |
| `RV-0004` | allergy mention escalated as P1; no safety claim |

Evidence: `data/output/fr06_sample_run_console.txt`, `data/output/marketplace_status/`,
`data/output/shipping_labels/`, `data/output/review_summary.md`.

## Test evidence

- `tests/test_sprint3b.py`: **3/3 pass**.
- `tests/test_features.py`: **3/3 pass**.
- `tests/test_engine.py`: **24/24 pass**.
- Technology on-demand check after social preview added: **16 pass / 0 warning / 0 error**.
- Campaign: 5 draft posts.
- People: job ad + hiring kit.
- Social preview: generic simulated screen with visible synthetic and not-real-platform labels.

## External marketplace connection

No external marketplace store path was supplied in the request. The seller-side implementation is complete
against the project-owned Section 14.3 sample inbox contract. No external connection is claimed. When the
separate store path is supplied, connect only through the documented file boundary and rerun the end-to-end
acceptance test.

## Automation gate

The hourly Technology Automation is active and has a pass row produced after activation. The current check
was made before 16:35; therefore the scheduled callback has not yet been independently confirmed. Keep U1
as **built, not tested** until a post-16:35 row is verified as scheduler-produced rather than manual.

## Schedule protection

- Sprint 4 testing must begin by **00:00**.
- Sprint 5 slides must begin by **03:00**.
- FR-04/FR-03 downgrade at 23:00 was not needed; both were completed. Verification and rehearsals remain protected.
