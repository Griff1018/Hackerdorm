"""Interactive Enterprise Buddy toolkit CLI for WorkBuddy owner requests.

The CLI is a deterministic dispatcher. WorkBuddy supplies understanding/plan narration and, when
needed, live research evidence; this module executes the safe local operation and reports evidence
paths. It never posts, pays, contacts, or stores account credentials.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from enterprise_buddy_campaign_people import build_campaign, build_job_ad
from enterprise_buddy_customer import faq_answer, handle_order_message, simulate_refund, run_tier_b_demo, write_report
from enterprise_buddy_marketplace import process_inbox, write_review_summary
from enterprise_buddy_po_actions import list_pos, mark_paid, mark_received
from enterprise_buddy_tech import append_log, run_check, write_report as write_tech_report

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "output"
DATA = ROOT / "data" / "sample"
PYTHON = sys.executable


def announce(department: str, why: str):
    print(f"[department: {department}] {why}")


def evidence(path: Path, summary: str):
    print(f"[result] {summary}")
    print(f"[evidence] {path.relative_to(ROOT).as_posix()}")


def run_engine(extra: list[str], goal: str):
    announce("Orchestrator", "Run the deterministic pipeline because the request needs refreshed verified outputs.")
    cmd = [PYTHON, str(ROOT / "app" / "run_enterprise_buddy.py"), "--data", "data/sample", "--output", "data/output",
           "--po", "--tech", "--goal", goal] + extra
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    evidence(OUTPUT / "run_log.jsonl", f"pipeline exit code {result.returncode}")
    return result.returncode


def cmd_brief(_):
    announce("Reporting", "Read the latest verified daily brief to identify what needs owner attention.")
    evidence(OUTPUT / "daily_brief.md", "latest daily brief is available")
    print((OUTPUT / "daily_brief.md").read_text(encoding="utf-8"))


def cmd_stock(_):
    announce("Operations", "Read stock and replenishment findings to identify low-stock, stale-count, and overstock cases.")
    data = json.loads((OUTPUT / "ops_findings.json").read_text(encoding="utf-8"))
    for pid, row in data["stock_and_replenishment"].items():
        print(pid, row["product_name"], "stock", row.get("stock_on_hand"), "replenishment", row.get("replenishment_units"), row.get("replenishment_note"))
    evidence(OUTPUT / "ops_findings.json", "stock and replenishment findings read")


def cmd_suppliers(args):
    announce("Operations", f"Read scored supplier evidence for {args.material}; live web research must be supplied by WorkBuddy before this call when a refresh is required.")
    path = OUTPUT / "supplier_research.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8-sig")))
    selected = [r for r in rows if r["material_name"].lower() == args.material.lower()]
    if not selected:
        print(f"No saved supplier rows for {args.material}; obtain live quotations and save them before scoring.")
        return 2
    selected.sort(key=lambda r: (r.get("rank", "999")))
    report = OUTPUT / ("supplier_" + re.sub(r"[^a-z0-9]+", "_", args.material.lower()).strip("_") + ".md")
    lines = [f"# Supplier check — {args.material}", "", "Source-backed rows from the latest deterministic score; no price was invented.", "",
             "| supplier | score | rank | available | material match | recommended | source |", "|---|---:|---:|---|---|---|---|"]
    for r in selected:
        lines.append(f"| {r['supplier_name']} | {r['score'] or 'not comparable'} | {r['rank']} | {r.get('available') or 'not stated'} | {r.get('material_match') or 'not stated'} | {r['recommended']} | [{r['source_url']}]({r['source_url']}) |")
        lines.append(f"\n**Breakdown:** {r['score_breakdown']}\n\n**Notes:** {r['notes']}\n")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence(report, f"{len(selected)} supplier row(s) scored for {args.material}")


def cmd_po(args):
    if args.action == "list":
        announce("Operations", "Read purchase orders and their deterministic totals; nothing is paid or ordered.")
        doc = json.loads((OUTPUT / "purchase_orders.json").read_text(encoding="utf-8"))
        used = sum(float(po["total"]) for po in doc.get("purchase_orders", []) if po.get("status") in ("paid", "received"))
        for po in doc.get("purchase_orders", []):
            mats = ", ".join(f"{l['material']} x{l['packs']} ({l['pack_size']})" for l in po.get("lines", []))
            review = "; needs review: " + ", ".join(sorted({r for l in po.get("lines", []) for r in l.get("review_reasons", [])})) if any(l.get("needs_review") for l in po.get("lines", [])) else ""
            print(f"{po['order_id']} | {po['status']} | {po['supplier_name']} | total MYR {po['total']} | {mats}{' | OVER BUDGET' if po.get('over_budget') else ''}{review}")
        for row in doc.get("not_ordered", []):
            print("not ordered:", row if isinstance(row, str) else json.dumps(row))
        budget = float(doc["purchase_orders"][0]["purchasing_budget"]) if doc.get("purchase_orders") else 0.0
        print(f"purchasing budget MYR {budget:.2f}; already paid MYR {used:.2f}; remaining MYR {budget - used:.2f}")
        evidence(OUTPUT / "purchase_orders.json", "purchase orders listed")
        return 0
    if args.action == "draft":
        return run_engine([], "Prepare draft purchase orders and verify them.")
    try:
        if args.action == "mark-paid":
            announce("Owner / Transaction Controls", "Record the owner's simulated payment decision; no real money moves.")
            po = mark_paid(OUTPUT, args.po_id)
            evidence(OUTPUT / "purchase_orders.json", f"{args.po_id} marked paid (simulated)")
            return 0
        if args.action == "mark-received":
            announce("Operations", "Record receipt of a paid PO, append raw-material stock, and refresh the derived stock view.")
            po = mark_received(ROOT, args.po_id)
            evidence(OUTPUT / "purchase_stock_ledger.csv", f"{args.po_id} marked received; {len(po.get('lines', []))} material line(s) added")
            evidence(OUTPUT / "current_stock.csv", "derived current stock refreshed without editing data/sample/inventory.csv")
            return 0
    except ValueError as exc:
        print(f"[blocked] {exc}")
        return 2
    return 2


def cmd_order(args):
    announce("Customer Operations", "Parse the synthetic customer message against menu.csv; prices and totals come from configured files.")
    result = handle_order_message(DATA, OUTPUT / "customer_demo", args.message)
    evidence(OUTPUT / "customer_demo" / "chat_request_latest.json", f"order request status: {result['result']['status']}")
    print(json.dumps(result["result"], indent=2))


def cmd_faq(args):
    announce("Customer Support", "Answer only from business_policies.md; escalate if the question is unsafe or ambiguous.")
    answer = faq_answer(args.question, DATA / "business_policies.md", [])
    print(answer)
    evidence(DATA / "business_policies.md", "FAQ answer sourced from configured policy file")


def cmd_refund(args):
    announce("Transaction & Permission Controls", "Evaluate the simulated refund against the owner limit; never issue real money.")
    result = simulate_refund(OUTPUT, args.order_id, args.amount)
    print(json.dumps(result, indent=2))
    evidence(OUTPUT / "refunds_cli.jsonl", f"refund decision: {result['status']}")


def cmd_marketplace(_):
    announce("Marketplace Seller Operations", "Process synthetic marketplace inbox files, recompute totals, update status and fulfilment outputs.")
    result = process_inbox(ROOT)
    evidence(OUTPUT / "marketplace_status", f"processed {len(result['processed'])} inbox order(s); status {result['status']}")


def cmd_reviews(_):
    announce("Customer Support / Verifier", "Read completed synthetic reviews and produce exact-quote evidence with owner escalations.")
    write_review_summary(ROOT)
    evidence(OUTPUT / "review_summary.md", "review summary refreshed")


def cmd_campaign(args):
    announce("Sales & Marketing", f"Build an unsent one-week campaign draft for {args.product}; do not post automatically.")
    result = build_campaign(ROOT, OUTPUT)
    evidence(OUTPUT / "campaign_plan.md", f"campaign planner wrote {result['posts']} draft post(s)")


def cmd_jobad(_):
    announce("People", "Create a synthetic job ad and hiring kit from the owner-set pay range; do not post or collect applicants.")
    result = build_job_ad(ROOT, OUTPUT)
    evidence(OUTPUT / "job_ad_part_time_campus_snack_assistant.md", "job ad and hiring kit written")


def cmd_market(args):
    announce("Strategy", "Record the focused market question and require source-backed research before stating a conclusion.")
    path = OUTPUT / "market_question_latest.json"
    broad = any(x in args.question.lower() for x in ("start a", "what do i need", "feasibility", "business plan"))
    status = "out_of_scope_full_feasibility_requires_owner_questions_and_source_research" if broad else "needs_source_backed_research"
    path.write_text(json.dumps({"question": args.question, "status": status, "synthetic": True}, indent=2), encoding="utf-8")
    if broad:
        print("This request is broader than Enterprise Buddy's built one-question market check. I can record it and prepare a source-backed feasibility plan, but I will not invent market size, rent, legal requirements, demand, or startup costs.")
    evidence(path, "market question recorded; no unsupported conclusion invented")


def cmd_tech(_):
    announce("Technology", "Run the read-only health check and append a timestamped result.")
    result = run_check(ROOT)
    write_tech_report(OUTPUT / "tech_health_report.md", result)
    append_log(OUTPUT / "tech_health_log.csv", result, "interactive-techcheck")
    evidence(OUTPUT / "tech_health_report.md", f"Technology status {result['status']} ({result['counts']})")


def cmd_verify(_):
    announce("Verifier", "Read the latest verification report; if new numbers are needed, rerun the deterministic pipeline.")
    evidence(OUTPUT / "verification_report.md", "latest verification report read")
    print((OUTPUT / "verification_report.md").read_text(encoding="utf-8"))


def cmd_nearby(args):
    from enterprise_buddy_places import nearby, slug
    announce("Strategy", f"Look up real {args.kind} near '{args.place}' on OpenStreetMap for market investigation.")
    res = nearby(args.place, args.kind, args.radius, cache_dir=OUTPUT / "places")
    if res.get("error"):
        print(f"[blocked] {res['error']}")
        return 2
    print(f"{res['count']} {args.kind} within {args.radius} m of {res['center']['name']}")
    print("by category:", ", ".join(f"{k} {v}" for k, v in res["by_category"].items()))
    print(f"independent (no chain brand): {res['independent_count']}")
    for p in res["places"][:15]:
        print(f"- {p['name']} | {p['category']} | {p['distance_m']} m | {p['address'] or 'address not on map'}{' | hours ' + p['opening_hours'] if p['opening_hours'] else ''}")
    evidence(OUTPUT / "places" / f"{slug(args.place)}__{args.kind}__{args.radius}.json", f"{res['count']} real places from OpenStreetMap")


def cmd_scrape(args):
    from enterprise_buddy_scrape import scrape, scrape_suppliers
    if args.url:
        announce("Operations", "Read one public product page: image, item name, listed price, online/offline ordering signals.")
        r = scrape(args.url, OUTPUT / "supplier_images")
        if r.get("image_local"):
            r["image_local"] = Path(r["image_local"]).resolve().relative_to(ROOT).as_posix()
        print(json.dumps({k: v for k, v in r.items() if k not in ("evidence", "image_candidates")}, indent=2, ensure_ascii=False))
        print("signals:", json.dumps(r.get("evidence", {}), ensure_ascii=False))
        if r.get("ok"):
            import hashlib
            path = OUTPUT / "scraped" / (hashlib.sha1(args.url.encode()).hexdigest()[:12] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
            evidence(path, "listing saved for this business")
        return 0 if r.get("ok") else 2
    announce("Operations", "Refresh every saved supplier page: image, item name, current listed price, online/offline ordering.")
    doc = scrape_suppliers(ROOT, args.material)
    changed = [l for l in doc["listings"] if l["listed_price_now"] and l["saved_price"] and "unconfirmed" not in l["price_method"]
               and float(l["listed_price_now"]) != float(l["saved_price"])]
    print(f"{doc['scraped_ok']} of {doc['pages']} supplier pages read; {len(changed)} listed price(s) changed since research")
    for l in changed:
        print(f"- price changed: {l['material']} / {l['supplier']}: saved MYR {l['saved_price']} -> now MYR {l['listed_price_now']}")
    evidence(OUTPUT / "supplier_listings.json", "supplier listings refreshed")


def cmd_prices(_):
    announce("Operations", "Compare current listed supplier prices with the researched prices (no web fetch; unconfirmed prices ignored).")
    path = OUTPUT / "supplier_listings.json"
    if not path.exists():
        print("No supplier listings yet — run: python -m app.enterprise_buddy_cli scrape")
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for l in doc["listings"]:
        now, saved = l.get("listed_price_now"), l.get("saved_price")
        if not now or not saved or "unconfirmed" in (l.get("price_method") or ""):
            continue
        if float(now) != float(saved):
            n += 1
            print(f"- {l['material']} — {l['supplier']}: MYR {float(saved):.2f} -> MYR {float(now):.2f} ({'cheaper' if float(now) < float(saved) else 'dearer'}, per {l.get('price_unit') or 'pack'})")
    print(f"{n} confirmed price change(s) since research; listings read {doc.get('generated_at', '')}")
    evidence(path, f"{n} confirmed price change(s)")


def cmd_guide(args):
    announce("Guides", f"Find the how-to guide for '{args.topic}' (where to go, steps, what to prepare, official links).")
    doc = json.loads((ROOT / "data" / "guides" / "guides.json").read_text(encoding="utf-8"))
    topic = args.topic.lower()
    hits = [g for g in doc["guides"] if g["id"] == topic or any(k in topic for k in g["keywords"]) or topic in g["title"].lower()]
    if not hits:
        print("No saved guide matches; research official sources and label the answer 'general advice — not verified by Enterprise Buddy tools'.")
        print("Available:", ", ".join(g["id"] for g in doc["guides"]))
        return 2
    for g in hits:
        print(f"## {g['title']} [guide_id: {g['id']}]")
        print("Who:", g["who_needs_it"])
        for w in g["where"]:
            print(f"Where ({w['mode']}): {w['name']} {w['url']}")
        print("Prepare:", "; ".join(g["prepare"]))
        print("Cost:", g["cost"], "| Time:", g["time"])
    evidence(ROOT / "data" / "guides" / "guides.json", f"{len(hits)} guide(s) matched")


def cmd_full(_):
    return run_engine(["--customer-demo", "--marketplace", "--campaign", "--people"], "Run the full Enterprise Buddy pipeline for the owner's request.")


def cmd_appdata(args):
    """Read-only: any Enterprise Buddy app data (dashboard numbers, orders, customers, reviews, menu, connections) as a table."""
    sys.path.insert(0, str(ROOT / "console"))
    import appdata  # noqa: E402  (console module: workspace JSON + dashboard)
    if args.name == "summary":
        print(appdata.snapshot(args.business))
        return 0
    try:
        d = appdata.dataset(args.business, args.name)
    except ValueError as exc:
        print(exc)
        return 2
    print(f"{d['title']} — {args.business} (as of {d['as_of']}){' — ' + d['note'] if d['note'] else ''}")
    cols = d["columns"]
    if cols:
        print(" | ".join(c[1] for c in cols))
        for r in d["rows"][:80]:
            print(" | ".join(str(r.get(c[0], "")) for c in cols))
    print(f"[dataset] {args.name} — show it in chat with app_actions: {{\"type\": \"show\", \"dataset\": \"{args.name}\"}}")
    return 0


def cmd_shopee_report(args):
    """Read-only: the Shopee agent's analysis of the connected Shopee shop (orders, products, reviews, service, sales)."""
    import enterprise_buddy_shopee as shopee
    announce("Shopee", "Analyse the connected Shopee shop" + (f" ({args.module})" if args.module != "all" else " (all five modules)") + " from live marketplace data.")
    print(shopee.brief_text(None if args.module == "all" else args.module))
    return 0


def cmd_shopee_approve(args):
    """Approval-only: execute one pending Shopee proposal (re-checked against live data, then verified)."""
    import enterprise_buddy_shopee as shopee
    try:
        p = shopee.decide(args.proposal_id, "approve", by="owner via chat")
    except ValueError as exc:
        print(f"[blocked] {exc}")
        return 2
    print(f"[result] {p['title']} — {p['status']}: {p.get('result', '')}")
    print("[evidence] data/shopee/agent.json")
    return 0 if p["status"] == "executed" else 1


def build_parser():
    p = argparse.ArgumentParser(prog="python -m app.enterprise_buddy_cli", description="Enterprise Buddy WorkBuddy deterministic toolkit")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("brief").set_defaults(func=cmd_brief)
    sub.add_parser("stock").set_defaults(func=cmd_stock)
    q = sub.add_parser("suppliers"); q.add_argument("material"); q.set_defaults(func=cmd_suppliers)
    q = sub.add_parser("po"); q.add_argument("action", choices=["list", "draft", "mark-paid", "mark-received"]); q.add_argument("po_id", nargs="?"); q.set_defaults(func=cmd_po)
    q = sub.add_parser("order"); q.add_argument("message"); q.set_defaults(func=cmd_order)
    q = sub.add_parser("faq"); q.add_argument("question"); q.set_defaults(func=cmd_faq)
    q = sub.add_parser("refund"); q.add_argument("order_id"); q.add_argument("amount"); q.set_defaults(func=cmd_refund)
    sub.add_parser("marketplace").set_defaults(func=cmd_marketplace)
    sub.add_parser("reviews").set_defaults(func=cmd_reviews)
    q = sub.add_parser("campaign"); q.add_argument("product"); q.set_defaults(func=cmd_campaign)
    sub.add_parser("jobad").set_defaults(func=cmd_jobad)
    q = sub.add_parser("market"); q.add_argument("question"); q.set_defaults(func=cmd_market)
    sub.add_parser("techcheck").set_defaults(func=cmd_tech)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    q = sub.add_parser("nearby"); q.add_argument("place"); q.add_argument("--kind", choices=["competitors", "suppliers"], default="competitors")
    q.add_argument("--radius", type=int, default=2000); q.set_defaults(func=cmd_nearby)
    q = sub.add_parser("scrape"); q.add_argument("url", nargs="?"); q.add_argument("--material"); q.set_defaults(func=cmd_scrape)
    q = sub.add_parser("guide"); q.add_argument("topic"); q.set_defaults(func=cmd_guide)
    sub.add_parser("prices").set_defaults(func=cmd_prices)
    sub.add_parser("full").set_defaults(func=cmd_full)
    q = sub.add_parser("shopee-report"); q.add_argument("module", nargs="?", default="all", choices=["all", "orders", "products", "reviews", "service", "sales"])
    q.set_defaults(func=cmd_shopee_report)
    q = sub.add_parser("shopee-approve"); q.add_argument("proposal_id"); q.set_defaults(func=cmd_shopee_approve)
    q = sub.add_parser("appdata"); q.add_argument("name"); q.add_argument("--business", default="campus-crumb"); q.set_defaults(func=cmd_appdata)
    return p


def main():
    args = build_parser().parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
