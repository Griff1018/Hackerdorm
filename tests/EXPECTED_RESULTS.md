# EXPECTED RESULTS (golden values) — BizFlow

**Regenerated 2026-10-10 after the Sprint 1 revisions** (demo dataset: September only, 4 seeded
defects; the other 9 moved to `tests/fixtures/invalid_data/`).
Written **before** the analysis engine exists — nothing here came from the engine (Section 9.3:
set the target before the test, never after).

How these numbers were produced:

1. Worked out by hand with the formulas in `docs/DATA_DICTIONARY.md` (arithmetic shown inline).
2. Cross-checked with `tests/compute_expected_standalone.py`, a deliberately plain single-file
   implementation that shares no code with the engine. **0 mismatches.**

Machine-readable golden files: `tests/fixtures/expected_sample.json`,
`expected_golden_mini.json`, `expected_invalid_data.json`.
Any engine disagreement is a **defect** — investigate, never silently reconcile.

Currency MYR (synthetic). Period **2026-09-01 .. 2026-09-30**. Demand window **2026-09-17 ..
2026-09-30** (14 days). Safety stock **3 days**. Staleness threshold **7 days**.

---

## A. Golden mini fixture (`tests/fixtures/golden_mini/`) — fully hand-computed

### A.1 Sales line classification

| line | product | qty | unit price | discount | status | net revenue | classification |
|---|---|---|---|---|---|---|---|
| L1 | P101 | 10 | 3.00 | 0.00 | completed | **30.00** | eligible |
| L2 | P102 | 4 | 5.00 | 5.00 | completed | **15.00** | eligible |
| L3 | P101 | 5 | 3.00 | 0.00 | cancelled | – | excluded (status) |
| L4 | P103 | 0 | 4.00 | 0.00 | completed | – | **invalid** (quantity not > 0) |
| L5 | P102 | 3 | 5.00 | 0.00 | refunded | – | excluded (status) |
| L6 | P102 | 12 | 5.00 | 3.00 | completed | **57.00** | eligible |
| L7 | P101 | 4 | 3.00 | 0.00 | completed | **12.00** | eligible |
| L8 | P103 | 2 | 4.00 | 8.00 | completed | **0.00** | eligible — discount **equals** line value, net 0 (allowed) |
| L9 | P999 | 2 | 3.00 | 0.00 | completed | – | **invalid** (unknown product_id) |
| L10 | P101 | 2 | 3.00 | 1.00 | completed | **5.00** | eligible |

### A.2 Totals — arithmetic

```
net revenue = 30.00 + 15.00 + 57.00 + 12.00 + 0.00 + 5.00 = 119.00
units sold  = 10 + 4 + 12 + 4 + 2 + 2                     = 34
COGS        = 16 x 1.00 + 16 x 2.00 + 2 x 1.50 = 16.00 + 32.00 + 3.00 = 51.00
gross profit = 119.00 - 51.00                             = 68.00
gross margin = 68.00 / 119.00 x 100                       = 57.14 %
```

### A.3 Per product

| product | units | net revenue | COGS | gross profit | margin % |
|---|---|---|---|---|---|
| P101 Iced Tea Small | 16 | 47.00 | 16.00 | 31.00 | 65.96 |
| P102 Slice Cake | 16 | 72.00 | 32.00 | 40.00 | 55.56 |
| P103 Fresh Juice | 2 | 0.00 | 3.00 | −3.00 | **N/A** (zero revenue) |

Reconciliation: 47.00 + 72.00 + 0.00 = 119.00 ✔ · 31.00 + 40.00 − 3.00 = 68.00 ✔ · 16+16+2 = 34 ✔

### A.4 Recorded expenses: 100.00 paid + 25.50 unpaid + 10.00 unknown = **135.50**

### A.5 Demand, coverage, replenishment

```
P101 window units = 4 + 2 = 6   → 6/14  = 0.428571/day
P102 window units = 12          → 12/14 = 0.857143/day
P103 window units = 2           → 2/14  = 0.142857/day
```

| product | stock | age | days of stock | target | replenishment | result |
|---|---|---|---|---|---|---|
| P101 | 12 | 4 d | 12 / 0.428571 = **28.00** | 0.428571 x 5 = 2.14 | max(0, 2.14−12) = 0 → **0** | no trigger |
| P102 | 5 | 6 d | 5 / 0.857143 = **5.83** | 0.857143 x 6 = 5.14 | max(0, 5.14−5) = 0.14 → pack 4 → **4** | **triggered** (stock 5 ≤ reorder 8; 5.83 d ≤ 3+3) |
| P103 | 0 | 19 d (**stale**) | 0 / 0.142857 = **0.00** | – | **not computed** | dynamic adaptation: stale → recount, no quantity |

### A.6 Expected data-quality issues: L4 invalid quantity (error) · L9 unknown product (error) · P103 stale count 19 days (warning).

### A.7 Cross-check: the standalone calculator returned 119.00 / 51.00 / 68.00 / 57.14 % / 34 units /
135.50 (100.00 / 25.50 / 10.00), per-product 47.00·16.00·31.00·65.96 %, 72.00·32.00·40.00·55.56 %,
0.00·3.00·−3.00·N/A, days of stock 28.00 / 5.83 / 0.00, replenishment 0 / 4 / not-computed.
**Matched the hand arithmetic on every value — 0 mismatches.**

---

## B. Demo dataset (`data/sample/`) — expected results

Row counts: products 5 · sales **59** (all September) · inventory 5 · expenses 8 · materials 20
(17 distinct materials). **4 seeded defects only** (S1, S2, S9, S13).

### B.1 Headline metrics

| metric | expected value |
|---|---|
| net revenue | **2451.25** |
| COGS estimate | **856.80** |
| gross profit estimate | **1594.45** |
| gross margin % | **65.05** |
| units sold | **484** |
| recorded expenses | **1105.70** |
| recorded expenses — paid | 880.50 |
| recorded expenses — unpaid | 171.00 |
| recorded expenses — unknown | 54.20 |
| expense rows counted | 7 (of 8: E-008 is August, outside the period) |

### B.2 Per product

| product | units | net revenue | COGS | gross profit | margin % |
|---|---|---|---|---|---|
| P001 Chocolate Chip Cookies (6pcs) | 161 | 940.80 | 386.40 | 554.40 | 58.93 |
| P002 Iced Lemon Tea 500ml | 206 | 916.20 | 247.20 | 669.00 | 73.02 |
| P003 Banana Muffin | 63 | 309.00 | 113.40 | 195.60 | 63.30 |
| P004 Spicy Chicken Bun | 48 | 261.25 | 100.80 | 160.45 | 61.42 |
| P005 Granola Bar | 6 | 24.00 | 9.00 | 15.00 | 62.50 |

Hand reconciliation:
`940.80 + 916.20 + 309.00 + 261.25 + 24.00 = 2451.25` ✔
COGS: `161x2.40 = 386.40 · 206x1.20 = 247.20 · 63x1.80 = 113.40 · 48x2.10 = 100.80 · 6x1.50 = 9.00 → 856.80` ✔
Gross profit: `554.40 + 669.00 + 195.60 + 160.45 + 15.00 = 1594.45` ✔
Margin: `1594.45 / 2451.25 x 100 = 65.047… → 65.05 %` ✔ Units: `161+206+63+48+6 = 484` ✔

### B.3 Sales processing

| bucket | count |
|---|---|
| total sales rows | 59 |
| eligible lines | **54** |
| duplicate line_id (both copies excluded) | 2 |
| unknown product (P999) | 1 |
| status cancelled | 1 |
| status refunded | 1 |
| rows outside the reporting period | 0 (August rows removed per the Sprint 1 revision) |

### B.4 Stock, demand and replenishment

| product | stock | age | window units | avg/day | days of stock | trigger | replenishment | why |
|---|---|---|---|---|---|---|---|---|
| P001 | 18 | 2 d | 78 | 5.571429 | **3.23** | **yes** | **24** | 18 ≤ reorder 20; 3.23 d ≤ 3+3. Target 5.571429 x 6 = 33.43; raw 33.43−18 = 15.43 → pack 12 → 24 |
| P002 | 96 | 1 d | 97 | 6.928571 | **13.86** | no | **0** | healthy; target 6.928571 x 5 = 34.64 < stock |
| P003 | 22 | 25 d (**stale**) | 28 | 2.000000 | 11.00 | – | **not computed** | dynamic adaptation: stale count → recount, no quantity |
| P004 | 6 | 0 d | 22 | 1.571429 | **3.82** | **yes** | **12** | 6 ≤ reorder 18; 3.82 d ≤ 4+3. Target 1.571429 x 7 = 11.00; raw 5.00 → pack 12 → 12 |
| P005 | 34 | 3 d | **0** | 0.000000 | – | – | **not computed** | has September sales history (6 units) but **zero** in the 14-day window → coverage cannot be estimated |

### B.5 Marketing handoff trigger — **P002 Iced Lemon Tea 500ml**

Rule (documented in `docs/AGENT_WORKFLOW.md` §4): trigger when
`days_of_stock > 2 x (lead_time_days + safety_stock_days)` **and** the product has eligible sales in
the demand window.

```
P001: 3.23 d vs 2 x 6 = 12  → no   (it needs buying, not promoting)
P002: 13.86 d vs 2 x 5 = 10 → YES  (13.86 > 10)  → over-stocked relative to demand
P003: 11.00 d vs 2 x 6 = 12  → no   (and the count is stale)
P004: 3.82 d vs 2 x 7 = 14  → no
P005: no coverage estimate  → no   (cannot be justified from the data)
```

So Operations hands **P002** to Sales & Marketing, and the draft promo post is for Iced Lemon Tea.

### B.6 Seeded defects kept in the demo dataset (4)

| id | file | row/id | issue | severity |
|---|---|---|---|---|
| S1 | sales.csv | S-0011 (two rows) | duplicate line_id | error |
| S2 | sales.csv | S-0059 | unknown product_id 'P999' | error |
| S9 | inventory.csv | P003 | stock count 25 days old (threshold 7) | warning |
| S13 | sales.csv | S-0001 | unit_price 5.00 differs from products.selling_price 6.00 | warning |

---

## C. Invalid-data fixture (`tests/fixtures/invalid_data/`) — 20 seeded defects

The 9 defects moved out of the demo dataset **plus** the Section 9.1 failure cases. All 20 are
detected by the standalone reference implementation (22 issue rows, because each duplicated row
raises its own row).

### C.1 Expected metrics (regardless of the defects)

| metric | expected value |
|---|---|
| net revenue | **50.00** |
| COGS estimate | **24.50** |
| gross profit estimate | **25.50** |
| gross margin % | **51.00** |
| units sold | **13** |
| recorded expenses | **165.00** (paid 110.00, unpaid 55.00) |
| expense rows counted | 3 (of 6) |
| eligible lines | 2 of 16 |

Per product: P201 10 units / 50.00 / 20.00 / 30.00 / 60.00 % · P202 0 / 0.00 / 0.00 / 0.00 / N/A ·
P203 3 / 0.00 / 4.50 / −4.50 / N/A (zero revenue) · P204 0 / N/A · P206 0 / N/A.
Hand check: `50.00 − (20.00 + 4.50) = 25.50` ✔ margin `25.50 / 50.00 = 51.00 %` ✔

### C.2 Expected detections (20)

| id | origin | file | row/id | issue | severity |
|---|---|---|---|---|---|
| I-01 | moved (S-duplicate line) | sales.csv | L12 (two rows) | duplicate line_id | error |
| I-02 | moved S3 | sales.csv | L02 | quantity blank | error |
| I-03 | additional | sales.csv | L03 | quantity non-numeric ('two') | error |
| I-04 | moved S6 | sales.csv | L04 | quantity not > 0 (−3) | error |
| I-05 | moved S4 | sales.csv | L05 | discount greater than gross line value | error |
| I-06 | additional | sales.csv | L06 | discount negative | error |
| I-07 | moved S5 | sales.csv | L07 | invalid date '2026-09-31' | error |
| I-08 | moved S7 | sales.csv | L08 | unrecognised status 'shipped' | error |
| I-09 | additional | sales.csv | L09 | unknown product_id 'P999' | error |
| I-10 | additional | sales.csv | L10 | unit_price blank | error |
| I-11 | moved S8 | inventory.csv | P202 (two rows) | duplicate current inventory record | error |
| I-12 | additional | inventory.csv | P205 | unknown product_id | error |
| I-13 | additional | inventory.csv | P206 | stock_on_hand invalid (−4) | error |
| I-14 | additional | inventory.csv | P204 | invalid last_count_date | error |
| I-15 | additional | inventory.csv | P203 | stock count 22 days old | warning |
| I-16 | moved S10 | expenses.csv | X-02 | invalid date '2026-09-31' | error |
| I-17 | moved S11 | expenses.csv | X-03 | unrecognised paid_status 'pending' | error |
| I-18 | additional | expenses.csv | X-04 | blank category | error |
| I-19 | moved S12 | expenses.csv | X-05 | blank description | warning |
| I-20 | additional | products.csv | P204 | pack_size invalid (0) | error |

### C.3 Non-defect behaviours this fixture also proves

- `L13` (2026-08-15) is a **valid** row outside the period → excluded silently, **not** an error.
- `L14` cancelled and `L15` refunded → excluded, listed in the summary, not errors.
- `L11` (discount = line value) → eligible with net revenue 0.00.
- `P203` stock 0 → 0 days of stock, still a valid record.
- Excluded products (P202, P204, P206) carry the reason "stock data not usable" instead of a number.

---

## D. Supplier scoring — hand-worked example (Section G.11)

Fixture: `tests/fixtures/supplier_score_example.csv`. **Invented test suppliers — not real, not a
recommendation**; every row is labelled and carries no URL.

### D.1 Full tier — "Chocolate chips" (out of 100)

P001 uses 60 g/unit at 5.571429 units/day → 334 g/day. 4 weeks = 28 d → **9.36 kg**;
3 months = 90 d → **30.1 kg**. All listings state a pack size → comparable per kg. Lowest = **28.00**.

| supplier | price/kg | price 40 x (28.00/price) | delivery | MOQ | reliability | location | total |
|---|---|---|---|---|---|---|---|
| BakeMart Malaysia | 28.00 | **40.00** | 2 d → 20 | 5 kg ≤ 9.36 kg → 15 | 10 + 5 = 15 | 10 | **100.00** |
| Cocoa Supply Co | 33.00 | 40 x 0.848485 = **33.94** | 4 d → 12 | 20 kg ≤ 30.1 kg → 8 | 10 + 5 = 15 | 10 | **78.94** |
| GlobalBake | 30.50 | 40 x 0.918033 = **36.72** | 12 d → 0 | 25 kg ≤ 30.1 kg → 8 | 10 + 0 = 10 | 0 | **54.72** |

Rank: BakeMart 100.00 · Cocoa 78.94 · GlobalBake 54.72. Only 3 found → all marked recommended, and
the run must state "3 suppliers found".

### D.2 Light tier — "Sugar" (out of 65: price 40 + reliability 15 + location 10)

| supplier | price/kg | price score | reliability | location | total |
|---|---|---|---|---|---|
| Pasar Bulk Sdn Bhd | 3.20 | **40.00** | 15 | 10 | **65.00** |
| Kedai Runcit Borong | 3.60 | 40 x 0.888889 = **35.56** | 15 | 10 | **60.56** |
| Unbranded Listing | 4.00 | 40 x 0.800000 = **32.00** | 0 | 10 | **42.00** |

Light-tier rows are labelled **"light research"** wherever they appear.

---

## E. Targets for the G.5 metrics — set BEFORE testing

| metric | definition | target |
|---|---|---|
| Detection | seeded defects detected / total seeded defects | **24 / 24 = 100 %** (4 in the demo dataset + 20 in the invalid-data fixture) |
| Correctness | golden calculations passed / total | **100 %** of the assertions in §A, §B, §C |
| Traceability | actions with complete evidence / total actions | **100 %**; otherwise the action is marked "insufficient data" |
| Effort | manual vs agent time on the synthetic dataset | **to be measured in Sprint 4**; no figure claimed now |
| User feedback | 3–5 student sellers | **not yet collected**; if uncollected, slides say user value remains to be validated |

End-to-end target: **3 of 3** clean-state runs produce the complete output set.
