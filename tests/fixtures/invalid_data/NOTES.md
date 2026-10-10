# Invalid-data fixture — `tests/fixtures/invalid_data/`

Purpose: hold every destructive/failure case **out of the demo dataset** so the demo stays readable,
while still exercising the validation layer and still counting for the **G.5 detection metric**
(20 seeded defects here + 4 in the demo dataset = 24).

Synthetic data. Period 2026-09-01 .. 2026-09-30. Currency MYR.

## Files

products.csv (5, one with an invalid pack_size) · sales.csv (16) · inventory.csv (7) ·
expenses.csv (6).

## Seeded defects (20) and where each came from

| id | origin | file | row/id | issue | severity |
|---|---|---|---|---|---|
| I-01 | moved from demo (duplicate line) | sales.csv | L12 x2 | duplicate line_id | error |
| I-02 | moved S3 | sales.csv | L02 | quantity blank | error |
| I-03 | additional (9.1) | sales.csv | L03 | quantity non-numeric ('two') | error |
| I-04 | moved S6 | sales.csv | L04 | quantity not > 0 (−3) | error |
| I-05 | moved S4 | sales.csv | L05 | discount greater than gross line value | error |
| I-06 | additional (9.1) | sales.csv | L06 | discount negative | error |
| I-07 | moved S5 | sales.csv | L07 | invalid date '2026-09-31' | error |
| I-08 | moved S7 | sales.csv | L08 | unrecognised status 'shipped' | error |
| I-09 | additional (9.1) | sales.csv | L09 | unknown product_id 'P999' | error |
| I-10 | additional (9.1) | sales.csv | L10 | unit_price blank | error |
| I-11 | moved S8 | inventory.csv | P202 x2 | duplicate current inventory record | error |
| I-12 | additional (9.1) | inventory.csv | P205 | unknown product_id | error |
| I-13 | additional (9.1) | inventory.csv | P206 | stock_on_hand invalid (−4) | error |
| I-14 | additional (9.1) | inventory.csv | P204 | invalid last_count_date | error |
| I-15 | additional (9.1) | inventory.csv | P203 | stock count 22 days old | warning |
| I-16 | moved S10 | expenses.csv | X-02 | invalid date '2026-09-31' | error |
| I-17 | moved S11 | expenses.csv | X-03 | unrecognised paid_status 'pending' | error |
| I-18 | additional (9.1) | expenses.csv | X-04 | blank category | error |
| I-19 | moved S12 | expenses.csv | X-05 | blank description | warning |
| I-20 | additional (9.1) | products.csv | P204 | pack_size invalid (0) | error |

## Non-defect behaviours proven here

- L13 (2026-08-15): valid row outside the period → excluded, **not** reported as an error.
- L14 cancelled / L15 refunded → excluded and listed in the summary.
- L11: discount equals the line value → eligible, net revenue 0.00.
- P203: zero stock → 0 days of stock, still a valid record.
- Excluded products report "stock data not usable" instead of a number.

## Expected results

`tests/EXPECTED_RESULTS.md` §C; machine-readable: `tests/fixtures/expected_invalid_data.json`.

```
python tests/compute_expected_standalone.py --data tests/fixtures/invalid_data --name invalid_data
```

Reference implementation currently reports **22 issue rows** (the two duplicate defects each raise
one row per offending row) covering **all 20 seeded defects**.
