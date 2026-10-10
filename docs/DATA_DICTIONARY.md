# DATA DICTIONARY — BizFlow

Version: Sprint 1 (2026-10-10). Currency **MYR** for the sample dataset. All sample data is synthetic.
Formulas follow Section 5 of the master instructions; where a choice had to be made, the choice is
recorded here and in `ASSUMPTIONS_AND_RISKS.md`.

## 1. Input files

### 1.1 products.csv

| field | type | rules | meaning |
|---|---|---|---|
| product_id | string | required, unique, non-empty | stable product identifier |
| product_name | string | required | human-readable name |
| unit_cost | decimal ≥ 0 | required | **estimated** cost per unit; used for COGS, labelled an estimate |
| selling_price | decimal ≥ 0 | required | reference/current selling price; used only as a comparison baseline and for the price-difference warning |
| reorder_point | integer ≥ 0 | required | stock at or below which replenishment should be considered |
| pack_size | integer ≥ 1 | required | purchase multiple; replenishment is rounded up to it |
| lead_time_days | integer ≥ 0 | required | estimated supplier lead time |

### 1.2 sales.csv

| field | type | rules | meaning |
|---|---|---|---|
| line_id | string | required, unique | unique sales-line identifier |
| order_id | string | required | groups lines belonging to the same order |
| date | ISO date `YYYY-MM-DD` | required, valid calendar date | line date |
| product_id | string | must reference products.product_id | |
| quantity | integer > 0 | required | units on the line |
| unit_price | decimal ≥ 0 | required | actual selling price per unit on that line |
| discount_amount | decimal ≥ 0 and ≤ quantity × unit_price | required | **total** discount for the line, not per unit |
| status | enum: `completed` / `cancelled` / `refunded` | required, case-insensitive after trim | only `completed` lines are recognised sales |

Semantics: `cancelled` and `refunded` lines are excluded from sales and COGS and are listed in the
data summary. Partial refunds are out of scope → flagged for review, never guessed.
Payment settlement is **not** inferred from status.

### 1.3 inventory.csv

| field | type | rules | meaning |
|---|---|---|---|
| product_id | string | must reference products.product_id; **one current record per product** | |
| stock_on_hand | integer ≥ 0 | required | current counted stock |
| last_count_date | ISO date | required, valid | date of the last physical count |

Two records for one product = validation error (the product is excluded from stock metrics).
No locations or batches in the MVP.

### 1.4 expenses.csv

| field | type | rules | meaning |
|---|---|---|---|
| expense_id | string | required, unique | |
| date | ISO date | required, valid | |
| category | string | required, non-empty | |
| amount | decimal ≥ 0 | required | |
| description | string | may be blank → **warning** | |
| paid_status | enum: `paid` / `unpaid` / `unknown` | required, case-insensitive after trim | |

Expenses are reported **separately** from gross profit. We never claim net profit unless revenue,
cost and expense completeness are established and approved; the MVP says "recorded expenses".

### 1.5 materials.csv (input — Section 4.7)

| field | type | rules | meaning |
|---|---|---|---|
| product_id | string | must reference products.product_id | the product that uses the material |
| material_name | string | required, non-empty | raw material or packaging item |
| quantity_per_unit | decimal > 0 | required | amount used to make **one unit** of the product |
| unit | string | e.g. `g`, `ml`, `pcs` | unit of `quantity_per_unit` |

A material shared by several products is researched and scored **once**, then linked to every
product that uses it.

### 1.6 supplier_research.csv (output — written by the agent, Sprint 2)

`material_name, supplier_name, listed_price, currency, price_unit, minimum_order,
delivery_or_lead_time, location, source_url, retrieved_at, score, score_breakdown, rank,
recommended (top 3 = yes), notes`

Rules: if the source does not state a value the field is left **blank with a note** — never guessed.
Web prices are "as listed on the retrieval date" and may exclude delivery/tax; they never replace
`products.unit_cost` in profit calculations unless the owner approves.

## 2. Validation rules (Section 4.6)

Detected: missing file or required column · blank required value · invalid date · unrecognised enum
value · non-numeric or out-of-range value · duplicate id (`line_id`, `expense_id`, duplicate product
id, duplicate inventory record) · reference to an unknown product · discount greater than gross line
value · unit_price differing from the reference price (**warning**) · inventory count older than the
staleness threshold (**warning**) · insufficient sales history for a demand estimate (**warning**) ·
date/period mismatch between files (**warning**).

**Duplicate policy (documented default):** rows sharing a duplicated identifier are **all excluded**
and reported. BizFlow never silently picks one copy. The owner may approve a different rule.

## 3. Calculation specification

| id | formula | notes |
|---|---|---|
| eligible line | `status = completed` ∧ date ∈ [period_start, period_end] ∧ numeric/product data valid | |
| line net revenue | `(quantity × unit_price) − discount_amount` | demo management metric, not tax/accounting treatment |
| COGS (line) | `quantity × products.unit_cost` | estimate |
| gross profit | `total net revenue − total COGS` | estimate |
| gross margin % | `gross profit / total net revenue × 100` when revenue > 0; otherwise **null / "not applicable"** | never 0 %, never an error, never infinity |
| recorded expenses | Σ valid in-period amounts, split by paid / unpaid / unknown | never double-subtracted from gross profit |
| average daily units | `eligible units in window / calendar days in window` | window defaults to the last **14** calendar days, including zero-sales days |
| days of stock | `stock_on_hand / average_daily_units`, only when ADU > 0 and stock data is valid | |
| target stock | `average_daily_units × (lead_time_days + safety_stock_days)` | safety stock default **3 days** |
| replenishment | `max(0, target_stock − stock_on_hand)`, then **round up** to a multiple of `pack_size` | display the facts and formula |
| reorder trigger | `stock ≤ reorder_point` **or** `days_of_stock ≤ lead_time_days + safety_stock_days` | if the two rules conflict, flag the conflict instead of hiding it |

Rounding: money to 2 dp, percentages to 2 dp. Money uses `decimal.Decimal`, never binary floats.
Sorting of "sales by product" states its criterion (units or revenue); we never claim the
best-selling product is the most profitable one.

### Run configuration defaults (all disclosed in outputs)

| setting | default | where it appears |
|---|---|---|
| currency | MYR (from dataset metadata) | snapshot, brief, demo site |
| reporting period | proposed from the data if the owner does not state one | snapshot, brief |
| demand window | 14 calendar days ending at period end | snapshot assumptions |
| safety_stock_days | 3 | snapshot assumptions, stock table |
| inventory staleness threshold | 7 days vs period end | data-quality report |
| excluded statuses | cancelled, refunded | snapshot assumptions |
| duplicate policy | exclude all copies | data-quality report |

## 4. Output contracts (Section 7.5)

**business_snapshot.json** — `schema_version, run_id, generated_at (ISO 8601 with offset), currency,
period_start, period_end, data_quality_status, metrics{net revenue, COGS estimate, gross profit
estimate, gross margin %, recorded expenses, units sold, products analysed, excluded row counts},
products[], assumptions{}, limitations[]`.

**action_queue.csv** — `action_id, priority, title, reason, evidence_refs, metric_values, confidence,
suggested_next_step, impact_estimate, status`. Status ∈ proposed / accepted / rejected / completed.

**data_quality_report.md** — input files and detected periods · rules performed · issues with
file, row/id, issue, severity, proposed resolution · accepted/rejected/uncertain counts · impact on
each affected metric · unresolved limitations.

**daily_brief.md** — period and currency · executive summary · key verified metrics · top 3–5 actions
with evidence · data-quality cautions · decisions needing owner approval.

Priorities (rule-based, never a hidden model score): **P1** urgent, objectively supported, may
immediately disrupt operations · **P2** high, supported risk needing action soon · **P3** routine
improvement · **INFO** noteworthy but not actionable.

## 5. Terms explained in one line (for the UI)

- **COGS** — what the units sold cost to make or buy.
- **Gross profit** — revenue minus that cost, before other expenses.
- **Gross margin** — gross profit as a percentage of revenue.
- **Days of stock** — how long current stock lasts at the recent sales rate.
- **Reorder point** — the stock level at which you should consider buying again.
