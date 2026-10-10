"""BizFlow deterministic core: configuration, validation and calculation.

Rules: Section 5 and docs/DATA_DICTIONARY.md. Money uses decimal.Decimal, never float.
No value is ever invented: anything undecidable is reported, not filled in.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

DEC2 = Decimal("0.01")
DEC6 = Decimal("0.000001")
ZERO = Decimal("0.00")

# Statuses that exist in the data but are NOT recognised sales.
EXCLUDED_STATUSES = ("cancelled", "refunded")
VALID_STATUSES = ("completed",) + EXCLUDED_STATUSES
VALID_PAID_STATUS = ("paid", "unpaid", "unknown")


# --------------------------------------------------------------------------- config
@dataclass
class Config:
    data_dir: Path
    output_dir: Path
    currency: str = "MYR"
    period_start: date = date(2026, 9, 1)
    period_end: date = date(2026, 9, 30)
    demand_window_days: int = 14
    safety_stock_days: int = 3
    staleness_days: int = 7
    excluded_statuses: tuple = EXCLUDED_STATUSES
    duplicate_policy: str = "exclude_all_copies"
    # Marketing handoff: days_of_stock more than this multiple of (lead + safety)
    overstock_multiple: Decimal = Decimal("2")

    @property
    def window_start(self) -> date:
        return self.period_end - timedelta(days=self.demand_window_days - 1)


def q2(d: Decimal) -> Decimal:
    return d.quantize(DEC2, rounding=ROUND_HALF_UP)


def q6(d: Decimal) -> Decimal:
    return d.quantize(DEC6, rounding=ROUND_HALF_UP)


def dec(s) -> Decimal | None:
    try:
        if s is None or str(s).strip() == "":
            return None
        v = Decimal(str(s).strip())
        return None if v.is_nan() else v
    except (InvalidOperation, ValueError):
        return None


def integer(s) -> int | None:
    try:
        if s is None or str(s).strip() == "":
            return None
        return int(str(s).strip())
    except (ValueError, TypeError):
        return None


def iso_date(s) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def money_str(d: Decimal | None) -> str | None:
    return None if d is None else f"{q2(d):.2f}"


def pct_str(d: Decimal | None) -> str | None:
    return None if d is None else f"{q2(d):.2f}"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- issues
@dataclass
class Issue:
    issue_id: str
    file: str
    row_or_id: str
    issue: str
    severity: str          # error | warning
    proposed_resolution: str


@dataclass
class ValidationResult:
    products: dict = field(default_factory=dict)
    sales_rows: list = field(default_factory=list)
    inventory: dict = field(default_factory=dict)
    expenses_rows: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    row_counts: dict = field(default_factory=dict)
    excluded: dict = field(default_factory=dict)

    def add(self, issue_id, file, ref, issue, severity, resolution):
        self.issues.append(Issue(issue_id, file, ref, issue, severity, resolution))

    def bump(self, key, n=1):
        self.excluded[key] = self.excluded.get(key, 0) + n

    @property
    def issue_rows(self) -> list[dict]:
        return [
            {
                "issue_id": i.issue_id,
                "file": i.file,
                "row_or_id": i.row_or_id,
                "issue": i.issue,
                "severity": i.severity,
                "proposed_resolution": i.proposed_resolution,
            }
            for i in self.issues
        ]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------- validation
def validate(data_dir: Path, cfg: Config) -> ValidationResult:
    res = ValidationResult()

    products_raw = read_csv(data_dir / "products.csv")
    sales_raw = read_csv(data_dir / "sales.csv")
    inventory_raw = read_csv(data_dir / "inventory.csv")
    expenses_raw = read_csv(data_dir / "expenses.csv")
    materials_raw = read_csv(data_dir / "materials.csv")

    res.row_counts = {
        "products": len(products_raw),
        "sales": len(sales_raw),
        "inventory": len(inventory_raw),
        "expenses": len(expenses_raw),
        "materials": len(materials_raw),
        "distinct_materials": len({m.get("material_name", "") for m in materials_raw}),
    }

    # ---- products ----
    for r in products_raw:
        pid = (r.get("product_id") or "").strip()
        if not pid:
            res.add("PRD", "products.csv", "(blank product_id)", "missing product_id", "error", "exclude product")
            continue
        if pid in res.products:
            res.add("DUP", "products.csv", pid, "duplicate product_id", "error", "exclude all copies")
            res.products[pid] = None
            continue
        bad = False
        for col in ("unit_cost", "selling_price"):
            v = dec(r.get(col))
            if v is None or v < 0:
                res.add("PRD", "products.csv", pid, f"{col} missing or negative", "error", "exclude product from money metrics")
                bad = True
        for col in ("reorder_point", "pack_size", "lead_time_days"):
            v = integer(r.get(col))
            if v is None or v < 0 or (col == "pack_size" and v < 1):
                res.add("PRD", "products.csv", pid, f"{col} invalid", "error", "exclude product from stock metrics")
                bad = True
        res.products[pid] = {
            "product_id": pid,
            "product_name": r.get("product_name", ""),
            "unit_cost": dec(r.get("unit_cost")),
            "selling_price": dec(r.get("selling_price")),
            "reorder_point": integer(r.get("reorder_point")),
            "pack_size": integer(r.get("pack_size")),
            "lead_time_days": integer(r.get("lead_time_days")),
            "usable": not bad,
        }

    # ---- sales ----
    counts: dict[str, int] = {}
    for r in sales_raw:
        lid = (r.get("line_id") or "").strip()
        counts[lid] = counts.get(lid, 0) + 1
    dup_ids = {k for k, v in counts.items() if v > 1}

    for r in sales_raw:
        lid = (r.get("line_id") or "").strip()
        status = (r.get("status") or "").strip().lower()
        dt = iso_date(r.get("date"))
        qty = integer(r.get("quantity"))
        up = dec(r.get("unit_price"))
        disc = dec(r.get("discount_amount"))
        pid = (r.get("product_id") or "").strip()
        res.sales_rows.append(
            {"line_id": lid, "order_id": r.get("order_id", ""), "date": dt, "product_id": pid,
             "quantity": qty, "unit_price": up, "discount": disc, "status": status}
        )
        if lid in dup_ids:
            res.add("DUP", "sales.csv", lid, "duplicate line_id", "error", "exclude all copies; do not auto-pick one")
            res.bump("duplicate_line_id")
            continue
        if status not in VALID_STATUSES:
            res.add("VAL", "sales.csv", lid, f"unrecognised status '{r.get('status')}'", "error", "exclude line; fix export")
            res.bump("invalid_status")
            continue
        if dt is None:
            res.add("VAL", "sales.csv", lid, f"invalid date '{r.get('date')}'", "error", "exclude line; fix export")
            res.bump("invalid_date")
            continue
        if not (cfg.period_start <= dt <= cfg.period_end):
            res.bump("outside_reporting_period")
            continue
        if pid not in res.products or res.products.get(pid) is None:
            res.add("REF", "sales.csv", lid, f"unknown product_id '{pid}'", "error", "exclude line; add product or fix id")
            res.bump("unknown_product")
            continue
        if qty is None:
            res.add("VAL", "sales.csv", lid, "quantity blank or non-integer", "error", "exclude line")
            res.bump("invalid_quantity")
            continue
        if qty <= 0:
            res.add("VAL", "sales.csv", lid, f"quantity not > 0 ({qty})", "error", "exclude line")
            res.bump("invalid_quantity")
            continue
        if up is None or up < 0 or disc is None or disc < 0:
            res.add("VAL", "sales.csv", lid, "unit_price/discount missing or negative", "error", "exclude line")
            res.bump("invalid_money")
            continue
        if disc > q2(Decimal(qty) * up):
            res.add("VAL", "sales.csv", lid, "discount greater than gross line value", "error", "exclude line")
            res.bump("discount_exceeds_line")
            continue
        if status != "completed":
            res.bump(f"status_{status}")
            continue
        if up != res.products[pid]["selling_price"]:
            res.add("WARN", "sales.csv", lid, f"unit_price {up} differs from products.selling_price", "warning", "keep line; disclose")

    # ---- inventory ----
    inv_counts: dict[str, int] = {}
    for r in inventory_raw:
        pid = (r.get("product_id") or "").strip()
        inv_counts[pid] = inv_counts.get(pid, 0) + 1
    dup_inv = {k for k, v in inv_counts.items() if v > 1}

    for r in inventory_raw:
        pid = (r.get("product_id") or "").strip()
        if pid in dup_inv:
            res.add("DUP", "inventory.csv", pid, "duplicate current inventory record", "error",
                    "exclude product from stock metrics; recount")
            continue
        if pid not in res.products or res.products.get(pid) is None:
            res.add("REF", "inventory.csv", pid, "unknown product_id", "error", "exclude")
            continue
        soh = integer(r.get("stock_on_hand"))
        lcd = iso_date(r.get("last_count_date"))
        if soh is None or soh < 0:
            res.add("VAL", "inventory.csv", pid, "stock_on_hand invalid", "error", "exclude product from stock metrics")
            continue
        if lcd is None:
            res.add("VAL", "inventory.csv", pid, "invalid last_count_date", "error", "exclude product from stock metrics")
            continue
        age = (cfg.period_end - lcd).days
        stale = age > cfg.staleness_days
        if stale:
            res.add("STALE", "inventory.csv", pid,
                    f"stock count is {age} days old (threshold {cfg.staleness_days})", "warning",
                    "recount; do not compute replenishment")
        res.inventory[pid] = {"stock_on_hand": soh, "last_count_date": lcd, "age_days": age, "stale": stale}

    # ---- expenses ----
    for r in expenses_raw:
        eid = (r.get("expense_id") or "").strip()
        dt = iso_date(r.get("date"))
        amt = dec(r.get("amount"))
        ps = (r.get("paid_status") or "").strip().lower()
        if dt is None:
            res.add("VAL", "expenses.csv", eid, f"invalid date '{r.get('date')}'", "error", "exclude expense")
            continue
        if not (cfg.period_start <= dt <= cfg.period_end):
            continue
        if amt is None or amt < 0:
            res.add("VAL", "expenses.csv", eid, "amount missing or negative", "error", "exclude expense")
            continue
        if ps not in VALID_PAID_STATUS:
            res.add("VAL", "expenses.csv", eid, f"unrecognised paid_status '{r.get('paid_status')}'", "error", "exclude expense")
            continue
        if not (r.get("category") or "").strip():
            res.add("VAL", "expenses.csv", eid, "blank category", "error", "exclude expense")
            continue
        if not (r.get("description") or "").strip():
            res.add("WARN", "expenses.csv", eid, "blank description", "warning", "keep; disclose")
        res.expenses_rows.append({"expense_id": eid, "date": dt, "category": r.get("category", ""),
                                  "amount": amt, "description": r.get("description", ""), "paid_status": ps})

    # ---- materials ----
    for r in materials_raw:
        pid = (r.get("product_id") or "").strip()
        name = (r.get("material_name") or "").strip()
        qty = dec(r.get("quantity_per_unit"))
        if not name:
            res.add("VAL", "materials.csv", pid, "blank material_name", "error", "exclude material")
            continue
        if pid not in res.products:
            res.add("REF", "materials.csv", pid, f"unknown product_id '{pid}'", "error", "exclude material")
            continue
        if qty is None or qty <= 0:
            res.add("VAL", "materials.csv", f"{pid}/{name}", "quantity_per_unit invalid", "error", "exclude material")
            continue
        res.materials.append({"product_id": pid, "material_name": name,
                              "quantity_per_unit": qty, "unit": r.get("unit", "")})

    return res


# --------------------------------------------------------------------------- calculation
def eligible_lines(v: ValidationResult, cfg: Config) -> list[dict]:
    out = []
    for r in v.sales_rows:
        p = v.products.get(r["product_id"])
        if p is None or not p["usable"]:
            continue
        if r["status"] != "completed":
            continue
        if r["date"] is None or not (cfg.period_start <= r["date"] <= cfg.period_end):
            continue
        if r["quantity"] is None or r["quantity"] <= 0:
            continue
        if r["unit_price"] is None or r["unit_price"] < 0 or r["discount"] is None or r["discount"] < 0:
            continue
        if r["discount"] > q2(Decimal(r["quantity"]) * r["unit_price"]):
            continue
        lid = r["line_id"]
        if any(x["line_id"] == lid and x is not r for x in v.sales_rows):
            continue  # duplicate id -> already excluded
        out.append({**r, "net": q2(Decimal(r["quantity"]) * r["unit_price"] - r["discount"]),
                    "cogs": q2(Decimal(r["quantity"]) * p["unit_cost"])})
    return out


def _is_excluded(v: ValidationResult, row: dict, cfg: Config) -> bool:
    """True if the row was excluded for any reason (mirrors validate())."""
    counts: dict[str, int] = {}
    for r in v.sales_rows:
        counts[r["line_id"]] = counts.get(r["line_id"], 0) + 1
    lid = row["line_id"]
    if counts.get(lid, 0) > 1:
        return True
    if row["status"] not in VALID_STATUSES:
        return True
    if row["date"] is None or not (cfg.period_start <= row["date"] <= cfg.period_end):
        return True
    if row["product_id"] not in v.products or v.products.get(row["product_id"]) is None:
        return True
    if row["quantity"] is None or row["quantity"] <= 0:
        return True
    if row["unit_price"] is None or row["unit_price"] < 0 or row["discount"] is None or row["discount"] < 0:
        return True
    if row["discount"] > q2(Decimal(row["quantity"]) * row["unit_price"]):
        return True
    return row["status"] != "completed"


def calculate(v: ValidationResult, cfg: Config) -> dict:
    lines = eligible_lines(v, cfg)
    # duplicate ids excluded entirely
    counts: dict[str, int] = {}
    for r in v.sales_rows:
        counts[r["line_id"]] = counts.get(r["line_id"], 0) + 1
    lines = [l for l in lines if counts.get(l["line_id"], 0) == 1]

    net_rev = sum((l["net"] for l in lines), ZERO)
    cogs = sum((l["cogs"] for l in lines), ZERO)
    gp = net_rev - cogs
    margin = (gp / net_rev * 100) if net_rev > 0 else None
    units = sum(l["quantity"] for l in lines)

    exp_total = sum((e["amount"] for e in v.expenses_rows), ZERO)
    by_status: dict[str, Decimal] = {}
    for e in v.expenses_rows:
        by_status[e["paid_status"]] = by_status.get(e["paid_status"], ZERO) + e["amount"]

    per_product = {}
    for pid, p in v.products.items():
        if p is None:
            continue
        pl = [l for l in lines if l["product_id"] == pid]
        u = sum(l["quantity"] for l in pl)
        rev = sum((l["net"] for l in pl), ZERO)
        c = sum((l["cogs"] for l in pl), ZERO)
        g = rev - c
        per_product[pid] = {
            "product_name": p["product_name"],
            "units_sold": u,
            "net_revenue": money_str(rev),
            "cogs_estimate": money_str(c),
            "gross_profit_estimate": money_str(g),
            "gross_margin_pct": pct_str(g / rev * 100) if rev > 0 else None,
        }

    win_start = cfg.window_start
    win_units: dict[str, int] = {}
    for l in lines:
        if win_start <= l["date"] <= cfg.period_end:
            win_units[l["product_id"]] = win_units.get(l["product_id"], 0) + l["quantity"]

    stock_rows = {}
    for pid, p in v.products.items():
        if p is None:
            continue
        wu = win_units.get(pid, 0)
        adu = Decimal(wu) / Decimal(cfg.demand_window_days)
        row = {
            "product_name": p["product_name"],
            "window_units": wu,
            "average_daily_units": str(q6(adu)),
            "stock_on_hand": None,
            "days_of_stock": None,
            "coverage_note": None,
            "reorder_point": p["reorder_point"],
            "lead_time_days": p["lead_time_days"],
            "pack_size": p["pack_size"],
            "target_stock_units": None,
            "replenishment_units": None,
            "replenishment_note": None,
            "reorder_trigger": None,
            "marketing_trigger": False,
            "marketing_reason": None,
        }
        s = v.inventory.get(pid)
        if s is None:
            row["coverage_note"] = "stock not usable (missing, invalid or duplicated inventory record)"
            row["replenishment_note"] = "not computed - stock data not usable"
        else:
            row["stock_on_hand"] = s["stock_on_hand"]
            row["stock_age_days"] = s["age_days"]
            row["stock_stale"] = s["stale"]
            if adu <= 0:
                row["coverage_note"] = "cannot be estimated - zero eligible sales in the demand window"
                row["replenishment_note"] = "not computed - no recent demand"
                # G.9 marketing handoff: stock on hand AND zero eligible sales in the window.
                # A product sitting in stock with no recent demand is a promotion candidate.
                if s["stock_on_hand"] > 0:
                    row["marketing_trigger"] = True
                    row["marketing_reason"] = (
                        f"{s['stock_on_hand']} units in stock but zero eligible sales in the "
                        f"{cfg.demand_window_days}-day demand window "
                        f"({cfg.window_start}..{cfg.period_end}) - stock is not moving"
                    )
            else:
                row["days_of_stock"] = str(q2(Decimal(s["stock_on_hand"]) / adu))
                target = adu * Decimal(p["lead_time_days"] + cfg.safety_stock_days)
                row["target_stock_units"] = str(q2(target))
                if s["stale"]:
                    row["replenishment_note"] = f"not computed - stock count is stale ({s['age_days']} days); recount first"
                else:
                    raw = max(ZERO, target - Decimal(s["stock_on_hand"]))
                    if raw <= 0:
                        row["replenishment_units"] = 0
                        row["replenishment_note"] = "target stock below current stock - no replenishment"
                    else:
                        pack = p["pack_size"]
                        row["replenishment_units"] = int(math.ceil(raw / Decimal(pack))) * pack
                        row["replenishment_note"] = f"raw {q2(raw)} rounded up to pack_size {pack}"
                cover = Decimal(p["lead_time_days"] + cfg.safety_stock_days)
                row["reorder_trigger"] = bool(
                    s["stock_on_hand"] <= p["reorder_point"]
                    or Decimal(row["days_of_stock"]) <= cover
                )
                # Marketing handoff: over-stocked relative to demand
                threshold = cfg.overstock_multiple * cover
                if Decimal(row["days_of_stock"]) > threshold:
                    row["marketing_trigger"] = True
                    row["marketing_reason"] = (
                        f"{row['days_of_stock']} days of stock > {cfg.overstock_multiple} x "
                        f"(lead {p['lead_time_days']} + safety {cfg.safety_stock_days}) = {q2(threshold)} days"
                    )
        stock_rows[pid] = row

    return {
        "metrics": {
            "net_revenue": money_str(net_rev),
            "cogs_estimate": money_str(cogs),
            "gross_profit_estimate": money_str(gp),
            "gross_margin_pct": pct_str(margin),
            "units_sold": units,
            "recorded_expenses": money_str(exp_total),
            "recorded_expenses_by_status": {k: money_str(x) for k, x in by_status.items()},
            "expense_rows_counted": len(v.expenses_rows),
        },
        "per_product": per_product,
        "stock_and_replenishment": stock_rows,
        "eligible_lines": len(lines),
    }


def business_snapshot(v: ValidationResult, calc: dict, cfg: Config, run_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "currency": cfg.currency,
        "period_start": cfg.period_start.isoformat(),
        "period_end": cfg.period_end.isoformat(),
        "data_quality_status": "issues_found" if v.issues else "no_issues_detected",
        "metrics": calc["metrics"],
        "products": calc["per_product"],
        "assumptions": {
            "demand_window_days": cfg.demand_window_days,
            "safety_stock_days": cfg.safety_stock_days,
            "staleness_days": cfg.staleness_days,
            "excluded_statuses": list(cfg.excluded_statuses),
            "duplicate_policy": cfg.duplicate_policy,
            "cogs_basis": "products.unit_cost (owner estimate)",
        },
        "limitations": [
            "Synthetic demonstration data - not a real business.",
            "Gross profit is an estimate from the owner's unit costs; expenses are reported separately.",
            "Recorded expenses are not netted off gross profit; net profit is not claimed.",
        ],
        "row_counts": v.row_counts,
        "excluded_line_counts": v.excluded,
        "eligible_lines": calc["eligible_lines"],
    }
