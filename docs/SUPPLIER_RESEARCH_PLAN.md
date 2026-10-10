# SUPPLIER RESEARCH PLAN — BizFlow (written BEFORE research, per Sprint 1 revision 3)

Section G.11 tiering rule: **full tier** = expensive, large share of cost, specialised, or hard to
find → price, delivery, minimum order and source reliability all researched (score out of 100).
**Light tier** = cheap, generic, easy to find → one quick search for a price and a source
(score out of 65: price 40 + reliability 15 + location 10). The tier and reason are logged for
every material.

The 17 distinct materials come from `data/sample/materials.csv`. "Usage" is from that file;
"expected price band" is a **team estimate used only to decide the tier** — it is not research, is
not shown as a researched fact, and is replaced by whatever the search actually returns.

## Tier decisions

| # | material | used by (qty/unit) | usage | tier | one-line reason |
|---|---|---|---|---|---|
| 1 | Chocolate chips | P001 60 g | 1 product | **FULL** | Flagship ingredient; quality/compound-vs-couverture varies hugely and drives the price spread |
| 2 | Butter | P001 80 g | 1 product | **FULL** | Dairy is price-volatile, the largest single ingredient cost in P001, and halal/quality matter |
| 3 | Chicken filling | P004 80 g | 1 product | **FULL** | Protein: food safety, halal sourcing and freshness are decisive and are the highest-risk choice |
| 4 | Peanut butter | P005 15 g | 1 product | **FULL** | Allergen plus a real brand-vs-generic choice; core ingredient of P005 |
| 5 | Honey | P005 20 g | 1 product | **FULL** | Very wide price spread and adulteration risk; cheap listings are often blends |
| 6 | Flour | P001 200 g, P003 150 g, P004 120 g | 3 products | light | Commodity staple, sold everywhere, stable price |
| 7 | Sugar | P002 25 g, P003 30 g | 2 products | light | Commodity staple, no meaningful quality choice |
| 8 | Tea bag | P002 2 pcs | 1 product | light | Generic commodity; any brand works for iced tea |
| 9 | Lemon syrup | P002 30 ml | 1 product | light | Common branded cordial, easy to find, single flavour attribute |
| 10 | Plastic cup 500ml | P002 1 pcs | 1 product | light | Commodity packaging, price-driven only |
| 11 | Paper cookie bag | P001 1 pcs | 1 product | light | Commodity packaging, price-driven only |
| 12 | Banana | P003 1 pcs | 1 product | light | Fresh but commodity, bought locally at a known price |
| 13 | Muffin cup | P003 1 pcs | 1 product | light | Commodity packaging, price-driven only |
| 14 | Spice mix | P004 10 g | 1 product | light | Generic blended seasoning, widely stocked |
| 15 | Wax paper | P004 1 pcs | 1 product | light | Commodity packaging, price-driven only |
| 16 | Rolled oats | P005 60 g | 1 product | light | Dry commodity staple, long shelf life |
| 17 | Granola bar wrapper | P005 1 pcs | 1 product | light | Commodity packaging, price-driven only |

**Totals: 5 full + 12 light.** Planned effort: full tier up to 3 searches each (15), light tier
1 search each (12) → up to 27 searches. Shared materials (Flour, Sugar) are researched **once** and
linked to every product that uses them.

## Rules applied during research (G.11)

- Only what the source actually states is recorded. A field the source does not state is left
  **blank with a note** — never filled in.
- Every row carries `source_url` and `retrieved_at`.
- Scores are computed by **code** from the recorded fields, never estimated by the model.
- Light-tier rows are labelled **"light research"** everywhere they appear.
- Top 3 per material are marked `recommended = yes`; if fewer than 3 are found, the run states how
  many were found instead of implying a full comparison.
- Researched prices are **comparison only**; they never replace `products.unit_cost` in profit
  calculations unless the owner approves.

## Known limitation

`products.unit_cost` is the owner's own estimate and has not been reconciled against researched
material prices; until that reconciliation is done, the ingredient cost implied by materials.csv
may differ from `unit_cost`. Tracked as risk R-11 in `ASSUMPTIONS_AND_RISKS.md`. It does not affect
any metric BizFlow reports, because every metric uses `unit_cost` only.
