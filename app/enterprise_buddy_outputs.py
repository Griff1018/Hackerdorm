"""Enterprise Buddy output writers: action queue, reports, briefs, handoffs and purchase orders."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from enterprise_buddy_core import Config, ValidationResult, money_str, q2

ACTION_COLUMNS = ["action_id", "priority", "title", "reason", "evidence_refs", "metric_values",
                  "confidence", "suggested_next_step", "impact_estimate", "status"]


def _ref(*parts) -> str:
    return "; ".join(parts)


def build_actions(v: ValidationResult, calc: dict, cfg: Config) -> list[dict]:
    """Rule-based, deterministic. Priority: P1 urgent+supported, P2 high+supported,
    P3 routine improvement, INFO noteworthy but not actionable."""
    actions: list[dict] = []
    n = 0
    stock = calc["stock_and_replenishment"]

    for pid, s in stock.items():
        name = s["product_name"]
        repl = s.get("replenishment_units")
        if repl:
            n += 1
            dos = Decimal(s["days_of_stock"])
            urgent = dos <= Decimal(s["lead_time_days"])
            actions.append({
                "action_id": f"A-{n:03d}",
                "priority": "P1" if urgent else "P2",
                "title": f"Reorder {name} - {repl} units",
                "reason": (
                    f"stock {s['stock_on_hand']} is at or below the reorder point {s['reorder_point']} and "
                    f"coverage is {s['days_of_stock']} days, within lead {s['lead_time_days']} + safety "
                    f"{cfg.safety_stock_days} days"
                    + ("; stock would run out before a new delivery arrives" if urgent else "")
                ),
                "evidence_refs": _ref(f"inventory.csv:{pid}", f"products.csv:{pid}",
                                      f"sales.csv:{cfg.window_start}..{cfg.period_end} ({s['window_units']} units)"),
                "metric_values": (
                    f"stock={s['stock_on_hand']}; reorder_point={s['reorder_point']}; "
                    f"days_of_stock={s['days_of_stock']}; target={s['target_stock_units']}; "
                    f"avg_daily_units={s['average_daily_units']}; replenishment={repl} ({s['replenishment_note']})"
                ),
                "confidence": "high",
                "suggested_next_step": "approve a purchase order for the recommended supplier (draft only - you pay)",
                "impact_estimate": f"prevents a stockout of {name} within {s['days_of_stock']} days",
                "status": "proposed",
            })

        if s.get("stock_stale"):
            n += 1
            actions.append({
                "action_id": f"A-{n:03d}",
                "priority": "P2",
                "title": f"Recount stock for {name}",
                "reason": f"the last stock count is {s['stock_age_days']} days old (threshold {cfg.staleness_days}); "
                          f"no replenishment quantity is computed from a stale count",
                "evidence_refs": _ref(f"inventory.csv:{pid} last_count_date"),
                "metric_values": f"stock_age_days={s['stock_age_days']}; threshold={cfg.staleness_days}",
                "confidence": "high",
                "suggested_next_step": "physically recount and update inventory.csv, then re-run",
                "impact_estimate": "not estimated - the actual stock level is unknown until recounted",
                "status": "proposed",
            })

        if s.get("coverage_note") and "zero eligible sales" in s["coverage_note"] and s.get("stock_on_hand") is not None:
            n += 1
            actions.append({
                "action_id": f"A-{n:03d}",
                "priority": "P3",
                "title": f"Review {name} - no recent sales",
                "reason": "no eligible sales in the demand window, so demand and stock coverage cannot be estimated "
                          "from this data",
                "evidence_refs": _ref(f"sales.csv:{cfg.window_start}..{cfg.period_end} (0 eligible units)",
                                      f"inventory.csv:{pid}"),
                "metric_values": f"window_units=0; stock_on_hand={s['stock_on_hand']}",
                "confidence": "low",
                "suggested_next_step": "decide whether to promote, bundle or discontinue - a human decision",
                "impact_estimate": "insufficient data - impact cannot be estimated without a demand signal",
                "status": "proposed",
            })

        if s.get("marketing_trigger"):
            n += 1
            actions.append({
                "action_id": f"A-{n:03d}",
                "priority": "P3",
                "title": f"Promote {name}",
                "reason": f"over-stocked relative to demand: {s['marketing_reason']}",
                "evidence_refs": _ref(f"inventory.csv:{pid}", f"products.csv:{pid}",
                                      f"sales.csv:{cfg.window_start}..{cfg.period_end}"),
                "metric_values": f"days_of_stock={s['days_of_stock']}; window_units={s['window_units']}",
                "confidence": "medium",
                "suggested_next_step": "review the drafted promo post (draft only - never posted)",
                "impact_estimate": "not estimated - depends on campaign reach",
                "status": "proposed",
            })

    errors = [i for i in v.issues if i.severity == "error"]
    if errors:
        n += 1
        actions.append({
            "action_id": f"A-{n:03d}",
            "priority": "P2",
            "title": f"Fix {len(errors)} data-quality error(s) in the input files",
            "reason": "affected rows were excluded and are listed in data_quality_report.md; "
                      "metrics that depend on them are marked as affected",
            "evidence_refs": _ref("data_quality_report.md", *[f"{e.file}:{e.row_or_id}" for e in errors[:5]]),
            "metric_values": f"errors={len(errors)}; excluded_lines={sum(v.excluded.values())}",
            "confidence": "high",
            "suggested_next_step": "correct the listed rows in the source files and re-run",
            "impact_estimate": "not estimated - depends on how much revenue the excluded rows represent",
            "status": "proposed",
        })
    return actions


def write_action_queue(path: Path, actions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ACTION_COLUMNS, lineterminator="\n")
        w.writeheader()
        for a in actions:
            w.writerow({c: a.get(c, "") for c in ACTION_COLUMNS})


def write_data_quality_report(path: Path, v: ValidationResult, cfg: Config) -> None:
    errors = [i for i in v.issues if i.severity == "error"]
    warnings = [i for i in v.issues if i.severity == "warning"]
    L = ["# DATA QUALITY REPORT - Enterprise Buddy", ""]
    L.append(f"Period {cfg.period_start} .. {cfg.period_end} (inclusive). Currency {cfg.currency}.")
    L.append("")
    L.append("## Input files")
    L.append("")
    L.append("| file | rows |")
    L.append("|---|---|")
    for k, n in v.row_counts.items():
        L.append(f"| {k}.csv | {n} |")
    L.append("")
    L.append("## Rules performed")
    L.append("")
    L.append("missing required value · invalid date · unrecognised enum value · non-numeric or out-of-range "
             "value · duplicate id · unknown product reference · discount greater than the gross line value · "
             "unit price differing from the reference price · inventory count older than the staleness threshold · "
             "insufficient sales history for a demand estimate · rows outside the reporting period.")
    L.append("")
    L.append(f"## Issues: {len(v.issues)} ({len(errors)} error, {len(warnings)} warning)")
    L.append("")
    L.append("| # | file | row/id | issue | severity | proposed resolution |")
    L.append("|---|---|---|---|---|---|")
    if v.issues:
        for i in v.issues:
            L.append(f"| {i.issue_id} | {i.file} | {i.row_or_id} | {i.issue} | {i.severity} | {i.proposed_resolution} |")
    else:
        L.append("| - | - | - | no issues detected | - | - |")
    L.append("")
    L.append("## Excluded lines")
    L.append("")
    L.append("| reason | lines |")
    L.append("|---|---|")
    for k, n in v.excluded.items():
        L.append(f"| {k} | {n} |")
    L.append("")
    L.append("## Effect on metrics")
    L.append("")
    L.append("Excluded rows are never silently treated as valid. Metrics computed from the remaining rows are "
             "reported with the exclusion counts above; where a metric cannot be computed (for example stock "
             "coverage with no recent sales) it is reported as not available instead of zero.")
    L.append("")
    L.append("Duplicates are excluded, never auto-deduplicated (documented default).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_daily_brief(path: Path, snapshot: dict, actions: list[dict], v: ValidationResult, cfg: Config) -> None:
    m = snapshot["metrics"]
    margin = f"{m['gross_margin_pct']} %" if m["gross_margin_pct"] else "not applicable"
    top = [a for a in actions if a["priority"] in ("P1", "P2")][:5] or actions[:3]
    L = ["# DAILY BUSINESS BRIEF - Enterprise Buddy", ""]
    L.append(f"**SYNTHETIC DEMONSTRATION DATA - not a real business.**")
    L.append("")
    L.append(f"Period {cfg.period_start} .. {cfg.period_end} · currency {cfg.currency} · "
             f"run {snapshot['run_id']} · generated {snapshot['generated_at']}")
    L.append("")
    L.append("## Executive summary")
    L.append("")
    L.append(
        f"Net revenue {m['net_revenue']} from {m['units_sold']} units. Estimated gross profit "
        f"{m['gross_profit_estimate']} ({margin}). Recorded expenses {m['recorded_expenses']} "
        f"(reported separately, not deducted). "
        f"{len(v.issues)} data-quality finding(s) were detected; excluded rows are listed in the quality report."
    )
    L.append("")
    L.append("| metric | value |")
    L.append("|---|---|")
    L.append(f"| net revenue | {m['net_revenue']} |")
    L.append(f"| COGS estimate | {m['cogs_estimate']} |")
    L.append(f"| gross profit estimate | {m['gross_profit_estimate']} |")
    L.append(f"| gross margin | {margin} |")
    L.append(f"| units sold | {m['units_sold']} |")
    L.append(f"| recorded expenses | {m['recorded_expenses']} |")
    L.append("")
    L.append("## Top actions for the owner")
    L.append("")
    if top:
        for a in top:
            L.append(f"**{a['priority']} · {a['title']}**")
            L.append(f"- why: {a['reason']}")
            L.append(f"- evidence: {a['evidence_refs']}")
            L.append(f"- numbers: {a['metric_values']}")
            L.append(f"- confidence: {a['confidence']} · impact: {a['impact_estimate']}")
            L.append(f"- next step: {a['suggested_next_step']}")
            L.append("")
    else:
        L.append("No action was triggered by this run.")
        L.append("")
    L.append("## Data quality cautions")
    L.append("")
    if v.issues:
        for i in v.issues[:10]:
            L.append(f"- **{i.severity}** {i.file}:{i.row_or_id} — {i.issue} → {i.proposed_resolution}")
    else:
        L.append("- No issues detected.")
    L.append("")
    L.append("## Decisions that need your approval")
    L.append("")
    L.append("- Approve or reject each action above (nothing is ordered, paid or sent automatically).")
    L.append("- Approve a purchase order only when you have chosen the supplier and checked the total against your budget.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_market_brief(path: Path, material: dict, cfg: Config) -> None:
    L = ["# MARKET CHECK BRIEF - Enterprise Buddy (Strategy department)", ""]
    L.append("**Desk research only. Not validated with real customers.**")
    L.append("")
    L.append(f"Period {cfg.period_start} .. {cfg.period_end} · generated {material.get('generated_at','')}")
    L.append("")
    L.append(f"## Question")
    L.append("")
    L.append(material.get("question", ""))
    L.append("")
    L.append("## What we found")
    L.append("")
    L.append(material.get("answer", ""))
    L.append("")
    L.append("## Sources")
    L.append("")
    for s in material.get("sources", []):
        L.append(f"- {s.get('title','')} — {s.get('url','')} (retrieved {s.get('retrieved_at','')})")
    L.append("")
    L.append("## How to use this")
    L.append("")
    L.append(material.get("how_to_use", ""))
    L.append("")
    L.append("## Limits")
    L.append("")
    L.append("One focused question per run, public desk research only. No customer survey, no transaction data, "
             "and no claim that this reflects real demand.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_promo_draft(path: Path, product: dict, cfg: Config) -> None:
    L = ["# PROMO POST DRAFT - Sales & Marketing (handoff from Operations)", ""]
    L.append("**DRAFT ONLY - never posted automatically. The owner reviews and posts it themselves.**")
    L.append("")
    L.append(f"Product: **{product['product_name']}** · period {cfg.period_start} .. {cfg.period_end}")
    L.append("")
    L.append(f"Why this product: {product['reason']}")
    L.append("")
    L.append("## Suggested post")
    L.append("")
    L.append(product["post"])
    L.append("")
    L.append("## Facts used (from the verified run only)")
    L.append("")
    for f in product["facts"]:
        L.append(f"- {f}")
    L.append("")
    L.append("## Do not claim")
    L.append("")
    L.append("- No health, medical or 'best in town' claim.")
    L.append("- No price claim that is not in the verified data.")
    L.append("- No claim about demand that this run did not measure.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def build_po(order_id: str, cfg: Config, supplier: dict, lines: list[dict],
             profile: dict, budget_used: Decimal) -> dict:
    total = sum((Decimal(l["line_total"]) for l in lines), Decimal(0))
    budget = Decimal(str(profile.get("purchasing_budget", "0") or "0"))
    remaining = budget - budget_used
    over = total > remaining
    return {
        "order_id": order_id,
        "supplier_name": supplier.get("supplier_name", ""),
        "source_url": supplier.get("source_url", ""),
        "retrieved_at": supplier.get("retrieved_at", ""),
        "currency": cfg.currency,
        "payment_type": profile.get("preferred_payment_type", "not set"),
        "lines": lines,
        "total": f"{q2(total):.2f}",
        "purchasing_budget": f"{q2(budget):.2f}",
        "budget_already_used": f"{q2(budget_used):.2f}",
        "budget_remaining": f"{q2(remaining):.2f}",
        "over_budget": over,
        "status": "draft",
    }


def write_po(path: Path, po: dict) -> None:
    L = [f"# PURCHASE ORDER {po['order_id']} - DRAFT (ready to pay)", ""]
    L.append("**SIMULATED - no real money moves.** Enterprise Buddy never places or pays an order. This is a draft for "
             "the owner to pay the supplier directly.")
    L.append("")
    L.append(f"Supplier: **{po['supplier_name']}** · source: {po['source_url']} (retrieved {po['retrieved_at']})")
    L.append(f"Payment type on file: {po['payment_type']} · currency {po['currency']}")
    L.append("")
    L.append("| material | quantity | pack size | unit price | line total |")
    L.append("|---|---|---|---|---|")
    for l in po["lines"]:
        L.append(f"| {l['material']} | {l['quantity']} | {l['pack_size']} | {l['unit_price']} | {l['line_total']} |")
    L.append("")
    L.append(f"**Total: {po['total']} {po['currency']}**")
    L.append("")
    budget_label = po.get("purchasing_budget", po.get("monthly_budget", "0.00"))
    remaining_label = po.get("budget_remaining_after_this", po.get("budget_remaining", "0.00"))
    L.append(f"Purchasing budget {budget_label} · already committed {po['budget_already_used']} · "
             f"remaining {remaining_label}")
    if po["over_budget"]:
        L.append("")
        L.append("**This order exceeds the remaining purchasing budget. It is NOT approved automatically - "
                 "the owner must decide.**")
    L.append("")
    L.append("Status: draft → approved → ready to pay → paid (the owner pays). Quantities are rounded up to the "
             "supplier pack size.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def append_run_log(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()
