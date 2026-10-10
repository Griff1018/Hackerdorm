"""BizFlow Verifier: an INDEPENDENT re-check of the run.

It re-reads the source CSVs itself and recomputes the headline totals with its own arithmetic,
so it does not reuse the objects produced by the analysis stage. It can reject a run.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from bizflow_core import Config, q2


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def recompute(data_dir: Path, cfg: Config) -> dict:
    """Independent pass: raw files -> totals. Deliberately separate from bizflow_core.calculate."""
    products = {r["product_id"]: r for r in _read(data_dir / "products.csv")}
    sales = _read(data_dir / "sales.csv")
    expenses = _read(data_dir / "expenses.csv")

    ids: dict[str, int] = {}
    for r in sales:
        ids[r["line_id"]] = ids.get(r["line_id"], 0) + 1

    net = Decimal("0")
    cogs = Decimal("0")
    units = 0
    for r in sales:
        if ids.get(r["line_id"], 0) != 1:
            continue
        if r["status"].strip().lower() != "completed":
            continue
        try:
            d = datetime.strptime(r["date"].strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (cfg.period_start <= d <= cfg.period_end):
            continue
        if r["product_id"] not in products:
            continue
        try:
            q = int(r["quantity"])
            up = Decimal(r["unit_price"])
            disc = Decimal(r["discount_amount"])
        except (ValueError, ArithmeticError):
            continue
        if q <= 0 or up < 0 or disc < 0 or disc > q2(q * up):
            continue
        net += q2(q * up - disc)
        cogs += q2(q * Decimal(products[r["product_id"]]["unit_cost"]))
        units += q

    exp = Decimal("0")
    for r in expenses:
        try:
            d = datetime.strptime(r["date"].strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (cfg.period_start <= d <= cfg.period_end):
            continue
        if r["paid_status"].strip().lower() not in ("paid", "unpaid", "unknown"):
            continue
        if not r["category"].strip():
            continue
        try:
            amt = Decimal(r["amount"])
        except (ValueError, ArithmeticError):
            continue
        if amt < 0:
            continue
        exp += amt

    return {"net_revenue": f"{q2(net):.2f}", "cogs_estimate": f"{q2(cogs):.2f}",
            "gross_profit_estimate": f"{q2(net - cogs):.2f}", "units_sold": units,
            "recorded_expenses": f"{q2(exp):.2f}"}


def verify(data_dir: Path, cfg: Config, snapshot: dict, actions: list[dict], issues: list) -> dict:
    ind = recompute(data_dir, cfg)
    m = snapshot["metrics"]
    checks = []

    def add(name, expected, actual):
        checks.append({"check": name, "expected": expected, "actual": actual,
                       "result": "pass" if str(expected) == str(actual) else "FAIL"})

    add("net_revenue", m["net_revenue"], ind["net_revenue"])
    add("cogs_estimate", m["cogs_estimate"], ind["cogs_estimate"])
    add("gross_profit_estimate", m["gross_profit_estimate"], ind["gross_profit_estimate"])
    add("units_sold", m["units_sold"], ind["units_sold"])
    add("recorded_expenses", m["recorded_expenses"], ind["recorded_expenses"])

    # every quantitative action must carry evidence
    missing_evidence = [a["action_id"] for a in actions
                        if not a.get("evidence_refs") or not a.get("metric_values")]
    checks.append({"check": "actions_have_evidence",
                   "expected": f"0 of {len(actions)} without evidence",
                   "actual": f"{len(missing_evidence)} of {len(actions)} without evidence",
                   "result": "pass" if not missing_evidence else "FAIL"})

    # a run with errors must not be presented as clean
    errs = [i for i in issues if i["severity"] == "error"]
    status_ok = snapshot["data_quality_status"] == ("issues_found" if errs else "no_issues_detected")
    checks.append({"check": "data_quality_status_consistent",
                   "expected": "issues_found" if errs else "no_issues_detected",
                   "actual": snapshot["data_quality_status"],
                   "result": "pass" if status_ok else "FAIL"})

    failed = [c for c in checks if c["result"] == "FAIL"]
    return {"verified_at": datetime.now().astimezone().isoformat(),
            "status": "failed" if failed else "passed",
            "independent_values": ind,
            "checks": checks,
            "failed_checks": failed}


def write_report(path: Path, result: dict) -> None:
    L = ["# VERIFICATION REPORT - BizFlow (Verifier department)", ""]
    L.append(f"Verified at {result['verified_at']} · status **{result['status'].upper()}**")
    L.append("")
    L.append("The Verifier re-read the source files and recomputed the headline totals with its own "
             "arithmetic. It does not reuse the analysis stage's numbers.")
    L.append("")
    L.append("| check | expected (analysis) | actual (independent) | result |")
    L.append("|---|---|---|---|")
    for c in result["checks"]:
        L.append(f"| {c['check']} | {c['expected']} | {c['actual']} | {c['result']} |")
    L.append("")
    if result["failed_checks"]:
        L.append("**This run FAILED verification.** Per the workflow the affected calculation is re-run once; "
                 "if it still disagrees the run is marked failed and the mismatch is shown - it is never "
                 "quietly corrected.")
    else:
        L.append("All checks passed.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
