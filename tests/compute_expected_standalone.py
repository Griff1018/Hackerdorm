#!/usr/bin/env python3
"""
BizFlow - INDEPENDENT expected-results calculator (golden reference).

Purpose: produce the pre-recorded expected values for data/sample WITHOUT using the
BizFlow analysis engine (which does not exist yet at the time this is written).
This is a deliberately plain, self-contained, single-file implementation so that the
engine built in Sprint 2 can be compared against something that was not derived from it.

Rules implemented here follow docs/DATA_DICTIONARY.md and Section 5 of the master
instructions. Anything this script cannot decide is reported, never invented.

Outputs:
  tests/fixtures/expected_sample.json  - machine-readable golden values
  tests/expected_results_auto.md       - human-readable dump of the same values
"""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Optional CLI: --data <dir> --name <prefix> lets the same independent implementation
# be pointed at the small golden_mini fixture to cross-check hand arithmetic.
_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=str(ROOT / "data" / "sample"))
_ap.add_argument("--name", default="sample")
_ap.add_argument("--outdir", default=str(ROOT / "tests"))
_args, _unknown = _ap.parse_known_args()

SAMPLE = Path(_args.data)
OUT_DIR = Path(_args.outdir)
DATASET_NAME = _args.name

# ---- run configuration (documented defaults) -------------------------------
PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 9, 30)
DEMAND_WINDOW_DAYS = 14          # previous 14 calendar days, ending PERIOD_END
SAFETY_STOCK_DAYS = 3
STALENESS_DAYS = 7               # inventory count older than this (vs PERIOD_END) is stale
CURRENCY = "MYR"
DEC2 = Decimal("0.01")
DEC6 = Decimal("0.000001")


def q2(d: Decimal) -> Decimal:
    return d.quantize(DEC2, rounding=ROUND_HALF_UP)


def q6(d: Decimal) -> Decimal:
    return d.quantize(DEC6, rounding=ROUND_HALF_UP)


def d(s: str):
    """Parse a decimal; return None if blank/non-numeric."""
    try:
        if s is None or s.strip() == "":
            return None
        v = Decimal(s.strip())
        if v.is_nan():
            return None
        return v
    except (InvalidOperation, AttributeError):
        return None


def parse_int(s: str):
    try:
        if s is None or s.strip() == "":
            return None
        return int(s.strip())
    except (ValueError, AttributeError):
        return None


def parse_date(s: str):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def read(name: str) -> list[dict]:
    with (SAMPLE / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sha256(name: str) -> str:
    return hashlib.sha256((SAMPLE / name).read_bytes()).hexdigest()


def main() -> None:
    products = {r["product_id"]: r for r in read("products.csv")}
    sales = read("sales.csv")
    inventory = read("inventory.csv")
    expenses = read("expenses.csv")
    materials = read("materials.csv") if (SAMPLE / "materials.csv").exists() else []

    issues: list[dict] = []

    def add_issue(issue_id, file, ref, issue, severity, resolution):
        issues.append(
            {
                "issue_id": issue_id,
                "file": file,
                "row_or_id": ref,
                "issue": issue,
                "severity": severity,
                "proposed_resolution": resolution,
            }
        )

    # ---------------- products ----------------
    for pid, r in products.items():
        for col in ("unit_cost", "selling_price"):
            v = d(r[col])
            if v is None or v < 0:
                add_issue("PRD", "products.csv", pid, f"{col} missing or negative", "error", "exclude product from money metrics")
        for col in ("reorder_point", "pack_size", "lead_time_days"):
            v = parse_int(r[col])
            if v is None or v < 0 or (col == "pack_size" and v < 1):
                add_issue("PRD", "products.csv", pid, f"{col} invalid", "error", "exclude product from stock metrics")

    # ---------------- sales ----------------
    seen_ids: dict[str, int] = {}
    for r in sales:
        seen_ids[r["line_id"]] = seen_ids.get(r["line_id"], 0) + 1
    dup_ids = {k for k, v in seen_ids.items() if v > 1}

    eligible: list[dict] = []
    excluded: dict[str, int] = {}
    by_status: dict[str, int] = {}
    promo_price_diff = 0

    for r in sales:
        lid = r["line_id"]
        dt = parse_date(r["date"])
        qty = parse_int(r["quantity"])
        up = d(r["unit_price"])
        disc = d(r["discount_amount"])
        status = (r["status"] or "").strip().lower()
        by_status[status] = by_status.get(status, 0) + 1

        def exclude(reason):
            excluded[reason] = excluded.get(reason, 0) + 1

        if lid in dup_ids:
            add_issue("DUP", "sales.csv", lid, "duplicate line_id", "error", "exclude all copies; do not auto-pick one")
            exclude("duplicate_line_id")
            continue
        if status not in ("completed", "cancelled", "refunded"):
            add_issue("VAL", "sales.csv", lid, f"unrecognised status '{r['status']}'", "error", "exclude line; fix export")
            exclude("invalid_status")
            continue
        if dt is None:
            add_issue("VAL", "sales.csv", lid, f"invalid date '{r['date']}'", "error", "exclude line; fix export")
            exclude("invalid_date")
            continue
        if not (PERIOD_START <= dt <= PERIOD_END):
            exclude("outside_reporting_period")
            continue
        if r["product_id"] not in products:
            add_issue("REF", "sales.csv", lid, f"unknown product_id '{r['product_id']}'", "error", "exclude line; add product or fix id")
            exclude("unknown_product")
            continue
        if qty is None:
            add_issue("VAL", "sales.csv", lid, "quantity blank or non-integer", "error", "exclude line")
            exclude("invalid_quantity")
            continue
        if qty <= 0:
            add_issue("VAL", "sales.csv", lid, f"quantity not > 0 ({qty})", "error", "exclude line")
            exclude("invalid_quantity")
            continue
        if up is None or up < 0 or disc is None or disc < 0:
            add_issue("VAL", "sales.csv", lid, "unit_price/discount missing or negative", "error", "exclude line")
            exclude("invalid_money")
            continue
        if disc > q2(Decimal(qty) * up):
            add_issue("VAL", "sales.csv", lid, "discount greater than gross line value", "error", "exclude line")
            exclude("discount_exceeds_line")
            continue
        if status != "completed":
            exclude(f"status_{status}")
            continue
        if up != d(products[r["product_id"]]["selling_price"]):
            promo_price_diff += 1
            add_issue("WARN", "sales.csv", lid, f"unit_price {up} differs from products.selling_price", "warning", "keep line; disclose")

        eligible.append(
            {
                "line_id": lid,
                "date": dt,
                "product_id": r["product_id"],
                "quantity": qty,
                "unit_price": up,
                "discount": disc,
                "net": q2(Decimal(qty) * up - disc),
                "cogs": q2(Decimal(qty) * d(products[r["product_id"]]["unit_cost"])),
            }
        )

    # ---------------- inventory ----------------
    inv_count: dict[str, int] = {}
    for r in inventory:
        inv_count[r["product_id"]] = inv_count.get(r["product_id"], 0) + 1
    dup_inv = {k for k, v in inv_count.items() if v > 1}

    stock: dict[str, dict] = {}
    for r in inventory:
        pid = r["product_id"]
        if pid in dup_inv:
            add_issue("DUP", "inventory.csv", pid, "duplicate current inventory record", "error", "exclude product from stock metrics; recount")
            continue
        if pid not in products:
            add_issue("REF", "inventory.csv", pid, "unknown product_id", "error", "exclude")
            continue
        soh = parse_int(r["stock_on_hand"])
        lcd = parse_date(r["last_count_date"])
        if soh is None or soh < 0:
            add_issue("VAL", "inventory.csv", pid, "stock_on_hand invalid", "error", "exclude product from stock metrics")
            continue
        if lcd is None:
            add_issue("VAL", "inventory.csv", pid, "invalid last_count_date", "error", "exclude product from stock metrics")
            continue
        age = (PERIOD_END - lcd).days
        stale = age > STALENESS_DAYS
        if stale:
            add_issue("STALE", "inventory.csv", pid, f"stock count is {age} days old (threshold {STALENESS_DAYS})", "warning", "recount; do not compute replenishment")
        stock[pid] = {"stock_on_hand": soh, "last_count_date": lcd, "age_days": age, "stale": stale}

    # ---------------- expenses ----------------
    exp_total = Decimal("0.00")
    exp_by_status: dict[str, Decimal] = {}
    exp_rows = 0
    for r in expenses:
        eid = r["expense_id"]
        dt = parse_date(r["date"])
        amt = d(r["amount"])
        ps = (r["paid_status"] or "").strip().lower()
        if dt is None:
            add_issue("VAL", "expenses.csv", eid, f"invalid date '{r['date']}'", "error", "exclude expense")
            continue
        if not (PERIOD_START <= dt <= PERIOD_END):
            continue  # outside period, not an error
        if amt is None or amt < 0:
            add_issue("VAL", "expenses.csv", eid, "amount missing or negative", "error", "exclude expense")
            continue
        if ps not in ("paid", "unpaid", "unknown"):
            add_issue("VAL", "expenses.csv", eid, f"unrecognised paid_status '{r['paid_status']}'", "error", "exclude expense")
            continue
        if not (r["category"] or "").strip():
            add_issue("VAL", "expenses.csv", eid, "blank category", "error", "exclude expense")
            continue
        if not (r["description"] or "").strip():
            add_issue("WARN", "expenses.csv", eid, "blank description", "warning", "keep; disclose")
        exp_total += amt
        exp_by_status[ps] = exp_by_status.get(ps, Decimal("0.00")) + amt
        exp_rows += 1

    # ---------------- headline metrics ----------------
    net_rev = sum((e["net"] for e in eligible), Decimal("0.00"))
    cogs = sum((e["cogs"] for e in eligible), Decimal("0.00"))
    gp = net_rev - cogs
    margin = (gp / net_rev * 100) if net_rev > 0 else None
    units = sum(e["quantity"] for e in eligible)

    # ---------------- per product ----------------
    per_product: dict[str, dict] = {}
    for pid, p in products.items():
        lines = [e for e in eligible if e["product_id"] == pid]
        u = sum(e["quantity"] for e in lines)
        rev = sum((e["net"] for e in lines), Decimal("0.00"))
        c = sum((e["cogs"] for e in lines), Decimal("0.00"))
        g = rev - c
        m = (g / rev * 100) if rev > 0 else None
        per_product[pid] = {
            "product_name": p["product_name"],
            "units_sold": u,
            "net_revenue": str(q2(rev)),
            "cogs_estimate": str(q2(c)),
            "gross_profit_estimate": str(q2(g)),
            "gross_margin_pct": (str(q2(m)) if m is not None else None),
        }

    # ---------------- demand window / stock ----------------
    win_start = PERIOD_END - timedelta(days=DEMAND_WINDOW_DAYS - 1)
    win_units: dict[str, int] = {}
    for e in eligible:
        if win_start <= e["date"] <= PERIOD_END:
            win_units[e["product_id"]] = win_units.get(e["product_id"], 0) + e["quantity"]

    stock_rows: dict[str, dict] = {}
    for pid, p in products.items():
        wu = win_units.get(pid, 0)
        adu = Decimal(wu) / Decimal(DEMAND_WINDOW_DAYS)
        row = {
            "product_name": p["product_name"],
            "window_units": wu,
            "average_daily_units": str(q6(adu)),
            "stock_on_hand": None,
            "days_of_stock": None,
            "coverage_note": None,
            "reorder_point": parse_int(p["reorder_point"]),
            "lead_time_days": parse_int(p["lead_time_days"]),
            "pack_size": parse_int(p["pack_size"]),
            "target_stock_units": None,
            "replenishment_units": None,
            "replenishment_note": None,
        }
        s = stock.get(pid)
        if s is None:
            row["coverage_note"] = "stock not usable (missing, invalid or duplicated inventory record)"
            row["replenishment_note"] = "not computed - stock data not usable"
        else:
            row["stock_on_hand"] = s["stock_on_hand"]
            row["stock_age_days"] = s["age_days"]
            row["stock_stale"] = s["stale"]
            if adu <= 0:
                row["days_of_stock"] = None
                row["coverage_note"] = "cannot be estimated - zero eligible sales in the demand window"
                row["replenishment_note"] = "not computed - no recent demand"
                row["target_stock_units"] = None
                row["replenishment_units"] = None
            else:
                dos = Decimal(s["stock_on_hand"]) / adu
                row["days_of_stock"] = str(q2(dos))
                lead = parse_int(p["lead_time_days"])
                target = adu * Decimal(lead + SAFETY_STOCK_DAYS)
                row["target_stock_units"] = str(q2(target))
                if s["stale"]:
                    row["replenishment_note"] = (
                        f"not computed - stock count is stale ({s['age_days']} days); recount first"
                    )
                else:
                    pack = parse_int(p["pack_size"])
                    raw = max(Decimal("0"), target - Decimal(s["stock_on_hand"]))
                    if raw <= 0:
                        row["replenishment_units"] = 0
                        row["replenishment_note"] = "target stock below current stock - no replenishment"
                    else:
                        import math

                        units_needed = int(math.ceil(raw / Decimal(pack))) * pack
                        row["replenishment_units"] = units_needed
                        row["replenishment_note"] = (
                            f"raw {q2(raw)} rounded up to pack_size {pack}"
                        )
                cover_days = Decimal(lead + SAFETY_STOCK_DAYS)
                row["reorder_trigger"] = bool(
                    s["stock_on_hand"] <= parse_int(p["reorder_point"])
                    or (row["days_of_stock"] is not None and Decimal(row["days_of_stock"]) <= cover_days)
                )
        stock_rows[pid] = row

    # ---------------- assemble ----------------
    result = {
        "generated_by": "tests/compute_expected_standalone.py",
        "currency": CURRENCY,
        "period_start": PERIOD_START.isoformat(),
        "period_end": PERIOD_END.isoformat(),
        "demand_window": {"start": win_start.isoformat(), "end": PERIOD_END.isoformat(), "calendar_days": DEMAND_WINDOW_DAYS},
        "assumptions": {
            "safety_stock_days": SAFETY_STOCK_DAYS,
            "staleness_days": STALENESS_DAYS,
            "excluded_statuses": ["cancelled", "refunded"],
            "duplicate_policy": "all rows sharing a duplicated id are excluded, never auto-deduplicated",
        },
        "dataset": DATASET_NAME,
        "input_fingerprints": {
            n: sha256(n)
            for n in ["products.csv", "sales.csv", "inventory.csv", "expenses.csv", "materials.csv"]
            if (SAMPLE / n).exists()
        },
        "row_counts": {
            "products": len(products),
            "sales": len(sales),
            "inventory": len(inventory),
            "expenses": len(expenses),
            "materials": len(materials),
            "distinct_materials": len({m["material_name"] for m in materials}),
        },
        "sales_processing": {
            "total_rows": len(sales),
            "rows_by_status": by_status,
            "eligible_lines": len(eligible),
            "excluded_lines": excluded,
            "promo_price_differences": promo_price_diff,
        },
        "metrics": {
            "net_revenue": str(q2(net_rev)),
            "cogs_estimate": str(q2(cogs)),
            "gross_profit_estimate": str(q2(gp)),
            "gross_margin_pct": (str(q2(margin)) if margin is not None else None),
            "units_sold": units,
            "recorded_expenses": str(q2(exp_total)),
            "recorded_expenses_by_status": {k: str(q2(v)) for k, v in exp_by_status.items()},
            "expense_rows_counted": exp_rows,
        },
        "per_product": per_product,
        "stock_and_replenishment": stock_rows,
        "data_quality_issues": issues,
        "issue_counts": {
            "total": len(issues),
            "by_severity": {s: sum(1 for i in issues if i["severity"] == s) for s in {i["severity"] for i in issues}},
        },
    }

    (OUT_DIR / "fixtures").mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fixtures" / f"expected_{DATASET_NAME}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    # markdown dump
    L: list[str] = []
    L.append(f"# Expected results - {SAMPLE.as_posix()} (AUTO-GENERATED)\n")
    L.append(f"Generated by `tests/compute_expected_standalone.py` on {date.today().isoformat()}.")
    L.append(f"Machine-readable source of truth: `tests/fixtures/expected_{DATASET_NAME}.json`.\n")
    L.append(f"Period {PERIOD_START} .. {PERIOD_END} (inclusive), currency {CURRENCY}.\n")
    L.append("## Input fingerprints (sha256)\n")
    L.append("| file | sha256 |")
    L.append("|---|---|")
    for k, v in result["input_fingerprints"].items():
        L.append(f"| {k} | `{v[:16]}...` |")
    L.append("")
    L.append("## Headline metrics\n")
    L.append("| metric | expected value |")
    L.append("|---|---|")
    for k, v in result["metrics"].items():
        if isinstance(v, dict):
            v = ", ".join(f"{kk}={vv}" for kk, vv in v.items())
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## Sales processing\n")
    L.append(f"- total rows: {result['sales_processing']['total_rows']}")
    L.append(f"- rows by status: {result['sales_processing']['rows_by_status']}")
    L.append(f"- eligible lines: {result['sales_processing']['eligible_lines']}")
    L.append(f"- excluded lines: {result['sales_processing']['excluded_lines']}")
    L.append("")
    L.append("## Per product\n")
    L.append("| product | units | net revenue | COGS est. | gross profit est. | margin % |")
    L.append("|---|---|---|---|---|---|")
    for pid, r in per_product.items():
        L.append(
            f"| {pid} {r['product_name']} | {r['units_sold']} | {r['net_revenue']} | "
            f"{r['cogs_estimate']} | {r['gross_profit_estimate']} | "
            f"{r['gross_margin_pct'] if r['gross_margin_pct'] is not None else 'N/A (zero revenue)'} |"
        )
    L.append("")
    L.append("## Stock, demand and replenishment\n")
    L.append("| product | stock | count age (d) | window units | avg daily units | days of stock | reorder trigger | replenishment |")
    L.append("|---|---|---|---|---|---|---|---|")
    for pid, r in stock_rows.items():
        L.append(
            f"| {pid} | {r['stock_on_hand']} | {r.get('stock_age_days','-')} | {r['window_units']} | "
            f"{r['average_daily_units']} | {r['days_of_stock'] if r['days_of_stock'] else '-'} | "
            f"{r.get('reorder_trigger','-')} | {r['replenishment_units'] if r['replenishment_units'] is not None else '-'} |"
        )
    L.append("")
    for pid, r in stock_rows.items():
        L.append(f"- **{pid}**: {r['coverage_note'] or 'coverage computed'}; replenishment: {r['replenishment_note']}")
    L.append("")
    L.append("## Expected data-quality issues\n")
    L.append("| # | file | row/id | issue | severity | proposed resolution |")
    L.append("|---|---|---|---|---|---|")
    for i in issues:
        L.append(f"| {i['issue_id']} | {i['file']} | {i['row_or_id']} | {i['issue']} | {i['severity']} | {i['proposed_resolution']} |")
    out_md = OUT_DIR / f"expected_results_auto_{DATASET_NAME}.md"
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(json.dumps(result["metrics"], indent=2))
    print("eligible:", len(eligible), "excluded:", excluded)
    print("issues:", result["issue_counts"])
    print(f"wrote tests/fixtures/expected_{DATASET_NAME}.json and {out_md.name}")


if __name__ == "__main__":
    main()
