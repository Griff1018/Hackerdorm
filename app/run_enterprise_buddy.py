#!/usr/bin/env python3
"""Enterprise Buddy end-to-end run (deterministic part).

Called by the WorkBuddy agent, which supplies the goal, the research results and the approvals.
This script never orders, pays, posts or contacts anyone; it only reads inputs and writes outputs.

    python app/run_enterprise_buddy.py --data data/sample --output data/output
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enterprise_buddy_core import Config, business_snapshot, calculate, q2, validate  # noqa: E402
from enterprise_buddy_outputs import (append_run_log, build_actions, now_iso, write_action_queue,  # noqa: E402
                             write_daily_brief, write_data_quality_report,
                             write_market_brief, write_promo_draft)
from enterprise_buddy_supplier import RESEARCH_COLUMNS, score_material  # noqa: E402
from enterprise_buddy_verify import verify, write_report as write_verification  # noqa: E402
from enterprise_buddy_tech import append_log as tech_append_log, run_check, write_report as write_tech  # noqa: E402
from enterprise_buddy_profile import load_profile  # noqa: E402
from enterprise_buddy_purchase import (materials_needed, build_purchase_plan, write_purchase_plan,  # noqa: E402
                              write_po, write_po_json)
from enterprise_buddy_customer import run_tier_b_demo, write_report as write_customer_report  # noqa: E402
from enterprise_buddy_marketplace import process_inbox as process_marketplace  # noqa: E402
from enterprise_buddy_campaign_people import build_campaign, build_job_ad  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/sample")
    p.add_argument("--output", default="data/output")
    p.add_argument("--period-start", default="2026-09-01")
    p.add_argument("--period-end", default="2026-09-30")
    p.add_argument("--currency", default="MYR")
    p.add_argument("--mode", default="auto", choices=["auto", "ask", "approve"])
    p.add_argument("--goal", default="")
    p.add_argument("--tech", action="store_true", help="also run the Technology health check")
    p.add_argument("--tech-trigger", default="run")
    p.add_argument("--profile", default="data/business_profile.json",
                   help="business profile (never stores card/account numbers)")
    p.add_argument("--market-check", default="data/market_check.json",
                   help="Strategy department research record (one focused question per run)")
    p.add_argument("--po", action="store_true", help="build draft purchase orders from the scored research")
    p.add_argument("--customer-demo", action="store_true", help="run the synthetic FR-01 Tier B customer/order flow")
    p.add_argument("--marketplace", action="store_true", help="process synthetic FR-06 marketplace inbox files")
    p.add_argument("--campaign", action="store_true", help="write the FR-03 campaign planner drafts")
    p.add_argument("--people", action="store_true", help="write the FR-04 job ad and hiring kit")
    return p.parse_args()


def d(s: str) -> date:
    return date.fromisoformat(s)


def run_supplier_scoring(outdir: Path, calc: dict, cfg: Config, v) -> list[dict]:
    """Score the research the agent collected (data/output/supplier_research_input.csv)."""
    src = outdir / "supplier_research_input.csv"
    if not src.exists():
        return []
    with src.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    adu = {pid: s["average_daily_units"] for pid, s in calc["stock_and_replenishment"].items()}
    unit_by_material: dict[str, str] = {}
    per_product_qty: dict[str, dict] = {}
    for m in v.materials:
        per_product_qty.setdefault(m["material_name"], {})[m["product_id"]] = m["quantity_per_unit"]
        unit_by_material[m["material_name"]] = (m["unit"] or "").strip().lower()

    by_material: dict[str, list] = {}
    for r in rows:
        by_material.setdefault(r["material_name"], []).append(r)

    out = []
    for name, mrows in by_material.items():
        tier = (mrows[0].get("tier") or "light").strip().lower()
        unit = unit_by_material.get(name, "")
        # expected use in the material's own unit, per 4 weeks (28 d) and 3 months (90 d)
        per_day = Decimal(0)
        for pid, qty in per_product_qty.get(name, {}).items():
            if pid in adu:
                per_day += Decimal(str(qty)) * Decimal(str(adu[pid]))
        use_4w, use_3m = per_day * 28, per_day * 90
        out.extend(score_material(mrows, tier, use_4w, use_3m, unit))
    out.sort(key=lambda r: (r["material_name"], r["rank"]))
    return out


def main() -> int:
    a = parse_args()
    data_dir = (ROOT / a.data).resolve()
    outdir = (ROOT / a.output).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    cfg = Config(data_dir=data_dir, output_dir=outdir, currency=a.currency,
                 period_start=d(a.period_start), period_end=d(a.period_end))
    run_id = f"run-{date.today().isoformat()}-{uuid.uuid4().hex[:6]}"

    log: list[dict] = []

    def step(stage, detail, status="ok"):
        log.append({"run_id": run_id, "at": now_iso(), "stage": stage, "detail": detail, "status": status})
        print(f"[{stage}] {detail}")

    step("intake", f"goal={a.goal or '(default)'} mode={a.mode}")
    step("plan", f"validate -> calculate -> actions -> reports -> verify (data={data_dir.name})")

    v = validate(data_dir, cfg)
    step("inspect", f"row counts {v.row_counts}")
    step("validate", f"{len(v.issues)} issue rows ({sum(1 for i in v.issues if i.severity=='error')} error)")

    calc = calculate(v, cfg)
    snap = business_snapshot(v, calc, cfg, run_id)
    step("calculate", f"net revenue {calc['metrics']['net_revenue']}, {calc['eligible_lines']} eligible lines")

    actions = build_actions(v, calc, cfg)
    step("prioritise", f"{len(actions)} actions")

    (outdir / "business_snapshot.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
    write_action_queue(outdir / "action_queue.csv", actions)
    write_data_quality_report(outdir / "data_quality_report.md", v, cfg)
    write_daily_brief(outdir / "daily_brief.md", snap, actions, v, cfg)
    step("report", "business_snapshot.json, action_queue.csv, data_quality_report.md, daily_brief.md written")

    # department handoff files
    (outdir / "ops_findings.json").write_text(json.dumps({
        "run_id": run_id,
        "stock_and_replenishment": calc["stock_and_replenishment"],
        "replenishment_list": [
            {"product_id": pid, "product_name": s["product_name"], "units": s["replenishment_units"]}
            for pid, s in calc["stock_and_replenishment"].items() if s.get("replenishment_units")
        ],
        "recount_checklist": [
            {"product_id": pid, "product_name": s["product_name"], "reason": s["replenishment_note"]}
            for pid, s in calc["stock_and_replenishment"].items() if s.get("stock_stale")
        ],
        "materials": [{"product_id": m["product_id"], "material_name": m["material_name"],
                       "quantity_per_unit": str(m["quantity_per_unit"]), "unit": m["unit"]}
                      for m in v.materials],
    }, indent=2), encoding="utf-8")

    # G.9 marketing handoff: pick the qualifying product. Prefer a product whose trigger is
    # "zero eligible sales in the window" (clearest promotion case), then the one with the most
    # days of stock. This makes P005 (stock on hand, no recent sales) the promoted product.
    triggered = [(pid, s) for pid, s in calc["stock_and_replenishment"].items()
                 if s.get("marketing_trigger")]
    if triggered:
        def _promo_key(item):
            pid, s = item
            zero_sales = 1 if s.get("window_units", 0) == 0 else 0
            dos = (Decimal(s["days_of_stock"]) if s.get("days_of_stock") is not None
                   else Decimal("0"))
            return (zero_sales, dos)
        triggered.sort(key=_promo_key, reverse=True)
        promo_pid = triggered[0][0]
    else:
        promo_pid = None
    (outdir / "marketing_handoff.json").write_text(json.dumps({
        "run_id": run_id,
        "trigger_product_id": promo_pid,
        "trigger_product_name": (calc["stock_and_replenishment"].get(promo_pid or "", {}) or {}).get("product_name"),
        "reason": (calc["stock_and_replenishment"].get(promo_pid or "", {}) or {}).get("marketing_reason"),
        "facts_available": (calc["per_product"].get(promo_pid or "", {}) or {}),
        "constraint": "draft only - never posted automatically",
    }, indent=2), encoding="utf-8")
    step("operations", f"ops_findings.json written; marketing handoff -> {promo_pid}")

    # ---- Strategy: one focused light market check, public desk research only -------
    mk_path = ROOT / a.market_check
    if mk_path.exists():
        mk = json.loads(mk_path.read_text(encoding="utf-8"))
        mk["generated_at"] = now_iso()
        write_market_brief(outdir / "market_brief.md", mk, cfg)
        step("strategy", f"market_brief.md written for: {mk.get('question','')[:70]}...")
    else:
        step("strategy", f"no market check supplied at {a.market_check} - skipped", status="skipped")

    # ---- Sales & Marketing: draft only, never posted ------------------------------
    if promo_pid:
        facts = calc["per_product"].get(promo_pid, {})
        write_promo_draft(outdir / "promo_draft.md", {
            "product_name": facts.get("product_name", promo_pid),
            "reason": (calc["stock_and_replenishment"].get(promo_pid, {}) or {}).get("marketing_reason", ""),
            "post": (f"{facts.get('product_name', promo_pid)} - see our menu for details.\n\n"
                     "Message us to ask about today's availability and order."),
            "facts": [
                f"Units sold {cfg.period_start}..{cfg.period_end}: {facts.get('units_sold')}",
                f"Eligible sales in demand window {cfg.window_start}..{cfg.period_end}: "
                f"{(calc['stock_and_replenishment'].get(promo_pid, {}) or {}).get('window_units', 0)}",
                f"Net revenue: {cfg.currency} {facts.get('net_revenue')}",
                f"Gross margin: {facts.get('gross_margin_pct')}%",
                "G.9 trigger: " +
                str((calc['stock_and_replenishment'].get(promo_pid, {}) or {}).get('marketing_reason', '')),
            ],
        }, cfg)
        step("marketing", f"promo_draft.md written for {promo_pid} (draft only - not posted)")
    else:
        step("marketing", "no product crossed the marketing handoff threshold - no promo draft",
             status="skipped")

    # ---- Operations: score the supplier research (before POs, which depend on it) --
    scored = run_supplier_scoring(outdir, calc, cfg, v)
    if scored:
        with (outdir / "supplier_research.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=RESEARCH_COLUMNS, lineterminator="\n")
            w.writeheader()
            for r in scored:
                w.writerow({c: r.get(c, "") for c in RESEARCH_COLUMNS})

        by_mat: dict[str, list] = {}
        for r in scored:
            by_mat.setdefault(r["material_name"], []).append(r)
        # Section G.11: never imply a full comparison when fewer than 3 real options exist.
        coverage = {
            m: {
                "tier": rows[0]["tier"],
                "suppliers_found": len(rows),
                "suppliers_with_a_price": sum(1 for r in rows if r.get("comparable_price")),
                "eligible_suppliers_with_a_price": sum(
                    1 for r in rows if r.get("comparable_price") and r["recommended"] == "yes"),
                "unavailable_listings": sum(1 for r in rows if r.get("available") == "no"),
                "substitutes_only": bool(rows) and all(r.get("material_match") == "no" for r in rows),
                "recommended": sum(1 for r in rows if r["recommended"] == "yes"),
            }
            for m, rows in by_mat.items()
        }
        gaps = sorted(m for m, c in coverage.items() if c["suppliers_with_a_price"] == 0)
        no_eligible = sorted(m for m, c in coverage.items() if c["eligible_suppliers_with_a_price"] == 0)
        (outdir / "supplier_coverage.json").write_text(json.dumps({
            "run_id": run_id,
            "materials_researched": len(by_mat),
            "materials_with_at_least_one_priced_supplier": len(by_mat) - len(gaps),
            "materials_with_no_priced_supplier": gaps,
            "materials_with_no_eligible_supplier": no_eligible,
            "coverage": coverage,
            "rule": "top 3 priced, available listings matching the specified material are recommended; "
                    "unavailable listings and substitutes are never recommended; unpriced rows are never recommended",
        }, indent=2), encoding="utf-8")

        step("operations",
             f"supplier_research.csv: {len(scored)} rows across {len(by_mat)} materials (scored by code)")
        no_eligible = sorted(m for m, rows in by_mat.items()
                             if not any(r.get("recommended") == "yes" and r.get("score") for r in rows))
        step("operations",
             f"supplier coverage: {len(by_mat) - len(gaps)}/{len(by_mat)} materials have at least one "
             f"priced listing; no priced listings for: {', '.join(gaps) if gaps else 'none'}")
        if no_eligible:
            step("operations",
                 f"no eligible supplier for: {', '.join(no_eligible)} "
                 "(unavailable listings and substitutes are not recommendations)", status="gap")
        if gaps:
            step("operations",
                 f"{len(gaps)} material(s) have no published comparable price and need a quotation - "
                 "recorded as an open gap, not filled with an estimate", status="gap")

    # ---- Ready-to-pay purchase orders (draft only, never sent or paid) ------------
    profile = load_profile(ROOT / a.profile)
    if a.po:
        if not profile:
            step("purchase", f"no business profile at {a.profile} - purchase orders skipped",
                 status="skipped")
        elif not scored:
            step("purchase", "no scored supplier research - purchase orders skipped", status="skipped")
        else:
            budget_used = Decimal(str(profile.get("purchasing_budget_used", "0") or "0"))
            pos, skipped = build_purchase_plan(scored, materials_needed(v, calc), cfg,
                                               profile, budget_used)
            podir = outdir / "po"
            for p in pos:
                write_po(podir / f"{p['order_id']}.md", p)
            write_purchase_plan(outdir / "purchase_plan.md", pos, skipped, cfg)
            write_po_json(outdir / "purchase_orders.json", pos, skipped)
            over = [p for p in pos if p["over_budget"]]
            step("purchase", f"{len(pos)} draft PO(s) written to po/ "
                             f"(purchasing budget {profile.get('purchasing_budget')} {cfg.currency})")
            if over:
                step("purchase", f"{len(over)} PO(s) exceed the remaining budget - "
                                 "NOT approved automatically, owner decides", status="blocked")
            if skipped:
                step("purchase", f"{len(skipped)} material(s) not ordered - see purchase_plan.md for "
                     "availability/material-match/quotation reasons", status="gap")

    result = verify(data_dir, cfg, snap, actions, v.issue_rows)
    write_verification(outdir / "verification_report.md", result)
    if result["status"] == "failed":
        # dynamic adaptation: one re-run, then show the mismatch
        calc = calculate(v, cfg)
        snap = business_snapshot(v, calc, cfg, run_id)
        (outdir / "business_snapshot.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
        result = verify(data_dir, cfg, snap, actions, v.issue_rows)
        write_verification(outdir / "verification_report.md", result)
        step("verify", "first verification failed - re-ran once", "retry")
    step("verify", f"verification {result['status']} ({len(result['checks'])} checks)")

    if a.tech:
        res = run_check(ROOT)
        write_tech(outdir / "tech_health_report.md", res)
        tech_append_log(outdir / "tech_health_log.csv", res, a.tech_trigger)
        step("technology", f"health check {res['status']} logged")

    # ---- Feature Update 01 outputs: all synthetic and explicit opt-in flags --------
    if a.customer_demo:
        customer_out = outdir / "customer_demo"
        customer_result = run_tier_b_demo(data_dir, customer_out)
        write_customer_report(customer_out / "customer_operations_report.md", customer_result)
        step("customer_ops", f"FR-01 Tier B {customer_result['status']} ({len(customer_result['checks'])} checks)")
    if a.marketplace:
        marketplace_result = process_marketplace(ROOT)
        step("marketplace", f"FR-06 processed {len(marketplace_result['processed'])} synthetic inbox order(s)")
    if a.campaign:
        campaign_result = build_campaign(ROOT, outdir)
        step("marketing", f"FR-03 campaign planner wrote {campaign_result['posts']} draft post(s)")
    if a.people:
        people_result = build_job_ad(ROOT, outdir)
        step("people", "FR-04 job ad and hiring kit written (draft only)")

    for e in log:
        append_run_log(outdir / "run_log.jsonl", e)

    print("\nRun", run_id, "->", outdir)
    print("net revenue", calc["metrics"]["net_revenue"], "| actions", len(actions),
          "| issues", len(v.issues), "| verification", result["status"])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
