# PURCHASE PLAN - Enterprise Buddy (draft purchase orders)

**SIMULATED. No order is placed and no money moves.** Each PO below is a draft the owner reviews and pays the supplier directly.

Period 2026-09-01 .. 2026-09-30

| PO | supplier | lines | total | over budget? | needs review? |
|---|---|---|---|---|---|
| PO-2026-09-30-01 | Borong Runcit (listed on Borong) | 1 | 26.80 MYR | no | no |
| PO-2026-09-30-02 | Healthy Baker Malaysia | 1 | 39.80 MYR | no | yes |
| PO-2026-09-30-03 | Image Magic | 1 | 50.00 MYR | no | yes |
| PO-2026-09-30-04 | PJ Grocer Sdn Bhd (listed on Borong) | 1 | 78.50 MYR | no | no |

**Plan total: 195.10 MYR** against a purchasing budget of 800.00 MYR (already committed to purchasing 0.00 MYR before this plan).

## Lines a human must check before paying

- **PO-2026-09-30-02 / Chocolate chips** (Healthy Baker Malaysia): retail
- **PO-2026-09-30-03 / Wax paper** (Image Magic): not certified; warning

These lines scored well on price but carry a caveat recorded from the source (retail listing, ambiguous pack basis, food-contact restriction, product is a spread not butter, supplier currently inactive, and so on). Read the note in `supplier_research.csv` before paying.

## Not ordered - no usable supplier price

- **Butter** (needs 1920.00): no supplier found for the specified material; substitute(s) exist but are shown as 'substitute - owner decides' only (see supplier_research.csv)
- **Paper cookie bag** (needs 24.00): no supplier with a comparable price was found - needs a quotation
- **Chicken filling** (needs 960.00): no available supplier - the priced option(s) are marked unavailable/inactive at source (not ordered)

## Rule

Quantities are rounded up to the supplier's stated pack size. A PO over the remaining budget is never approved automatically, and no PO is ever sent or paid by Enterprise Buddy.

**Budget rule (explicit).** Each PO is checked only against the **purchasing budget** (`business_profile.json` → `purchasing_budget`), which is a *separate* envelope from the operating budget that covers rent, fuel and wages. Recorded expenses such as rent and fuel are **never** deducted from the purchasing budget. POs are paid one at a time: a PO already flagged over-budget is **not** approved and is **not** counted against the remaining budget when checking later POs.
