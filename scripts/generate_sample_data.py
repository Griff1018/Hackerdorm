#!/usr/bin/env python3
"""
Enterprise Buddy - synthetic sample data generator (sales.csv only).

All other sample CSVs (products, inventory, expenses, materials) are hand-authored
files in data/sample/ and are deliberately NOT touched by this script.

Deterministic: seeded with SEED, so re-running reproduces byte-identical sales.csv.
Synthetic demonstration data - no real business, person or transaction is described.
"""
import csv
import hashlib
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

SEED = 20261010
# User decision 2026-10-10 (Sprint 1 revision 4): no August rows in the demo dataset.
# The demo dataset now covers the September reporting period only.
START = date(2026, 9, 1)
END = date(2026, 9, 30)
# P005 sells only in the first ten days of September: it has sales history but ZERO sales
# in the 14-day demand window (2026-09-17..2026-09-30), which is the "no recent demand" case.
P005_LAST_SALE_DAY = date(2026, 9, 10)

# base = typical units sold on a day the product sells at all
# prob  = share of days on which the product sells (keeps the file small enough to audit)
PRODUCTS = {
    "P001": {"price": Decimal("6.00"), "base": 8, "prob": 0.60},
    "P002": {"price": Decimal("4.50"), "base": 12, "prob": 0.60},
    "P003": {"price": Decimal("5.00"), "base": 6, "prob": 0.45},
    "P004": {"price": Decimal("5.50"), "base": 5, "prob": 0.40},
    "P005": {"price": Decimal("4.00"), "base": 2, "prob": 0.35},
}
ORDER = ["P001", "P002", "P003", "P004", "P005"]

OUT = Path(__file__).resolve().parents[1] / "data" / "sample" / "sales.csv"


def money(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build() -> list[dict]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    n = 0
    day = START
    while day <= END:
        weekend = 1.35 if day.weekday() >= 5 else 1.0
        day_lines: list[dict] = []
        for pid in ORDER:
            if pid == "P005" and day > P005_LAST_SALE_DAY:
                continue
            spec = PRODUCTS[pid]
            if rng.random() > spec["prob"]:
                continue  # no sale for this product on this day
            q = max(1, int(round(spec["base"] * weekend)) + rng.randint(-2, 2))
            n += 1
            price = spec["price"]
            gross = Decimal(q) * price
            disc = Decimal("0.00")
            if rng.random() < 0.12:
                disc = money(gross * Decimal("0.10"))
            day_lines.append(
                {
                    "line_id": f"S-{n:04d}",
                    "date": day.isoformat(),
                    "product_id": pid,
                    "quantity": q,
                    "unit_price": f"{price:.2f}",
                    "discount_amount": f"{disc:.2f}",
                    "status": "completed",
                }
            )
        # group the day's lines into orders of 1-3 lines
        k = 0
        oidx = 1
        while k < len(day_lines):
            size = rng.choice([1, 2, 3])
            oid = f"O-{day.isoformat()}-{oidx:02d}"
            for row in day_lines[k : k + size]:
                row["order_id"] = oid
            k += size
            oidx += 1
        rows.extend(day_lines)
        day += timedelta(days=1)

    # --- non-completed statuses (valid enum, excluded from recognised sales) ---
    def first_in_sept(pid: str) -> dict | None:
        for r in rows:
            if r["product_id"] == pid and r["date"] >= "2026-09-01":
                return r
        return None

    r2 = first_in_sept("P002")
    if r2:
        r2["status"] = "refunded"
    r3 = first_in_sept("P003")
    if r3:
        r3["status"] = "cancelled"

    # --- S13: unit_price differs from products.selling_price (warning only) ---
    r1 = first_in_sept("P001")
    if r1:
        r1["unit_price"] = "5.00"

    # --- seeded defect rows ---
    n += 1
    dup_src = rows[10]
    dup = dict(dup_src)  # S1: duplicate line_id
    rows.append(dup)

    def add(line_id, d, pid, q, up, disc, status):
        return {
            "line_id": line_id,
            "order_id": f"O-{d}-99",
            "date": d,
            "product_id": pid,
            "quantity": q,
            "unit_price": up,
            "discount_amount": disc,
            "status": status,
        }

    n += 1
    rows.append(add(f"S-{n:04d}", "2026-09-04", "P999", "2", "3.00", "0.00", "completed"))  # S2

    # User decision 2026-10-10 (Sprint 1 revision 2): the demo dataset keeps only S1, S2, S9
    # and S13. Every other seeded defect now lives in tests/fixtures/invalid_data/ so the demo
    # stays readable while the detection metric still counts them all.

    cols = ["line_id", "order_id", "date", "product_id", "quantity", "unit_price", "discount_amount", "status"]
    return rows, cols


def main() -> None:
    rows, cols = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"wrote {OUT}")
    print(f"rows (excl. header): {len(rows)}")
    print(f"sha256: {digest}")


if __name__ == "__main__":
    main()
