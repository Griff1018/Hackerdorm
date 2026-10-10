# DATA QUALITY REPORT - Enterprise Buddy

Period 2026-09-01 .. 2026-09-30 (inclusive). Currency MYR.

## Input files

| file | rows |
|---|---|
| products.csv | 5 |
| sales.csv | 59 |
| inventory.csv | 5 |
| expenses.csv | 8 |
| materials.csv | 20 |
| distinct_materials.csv | 17 |

## Rules performed

missing required value · invalid date · unrecognised enum value · non-numeric or out-of-range value · duplicate id · unknown product reference · discount greater than the gross line value · unit price differing from the reference price · inventory count older than the staleness threshold · insufficient sales history for a demand estimate · rows outside the reporting period.

## Issues: 5 (3 error, 2 warning)

| # | file | row/id | issue | severity | proposed resolution |
|---|---|---|---|---|---|
| WARN | sales.csv | S-0001 | unit_price 5.00 differs from products.selling_price | warning | keep line; disclose |
| DUP | sales.csv | S-0011 | duplicate line_id | error | exclude all copies; do not auto-pick one |
| DUP | sales.csv | S-0011 | duplicate line_id | error | exclude all copies; do not auto-pick one |
| REF | sales.csv | S-0059 | unknown product_id 'P999' | error | exclude line; add product or fix id |
| STALE | inventory.csv | P003 | stock count is 25 days old (threshold 7) | warning | recount; do not compute replenishment |

## Excluded lines

| reason | lines |
|---|---|
| status_cancelled | 1 |
| status_refunded | 1 |
| duplicate_line_id | 2 |
| unknown_product | 1 |

## Effect on metrics

Excluded rows are never silently treated as valid. Metrics computed from the remaining rows are reported with the exclusion counts above; where a metric cannot be computed (for example stock coverage with no recent sales) it is reported as not available instead of zero.

Duplicates are excluded, never auto-deduplicated (documented default).
