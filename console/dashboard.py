"""Business analytics for the BizFlow dashboard — deterministic numbers + problems with actions.

Every figure comes from BizFlow files: the pipeline's validated sales lines (same filters as the brief),
products, expenses, stock findings, ingredient stock, customer orders from the inbox, automations, to-dos
and checkpoints. Each problem the dashboard raises carries a concrete action and a question the owner can
send to the agent with one click.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import automations as auto  # noqa: E402
import inbox  # noqa: E402
import settings as st  # noqa: E402
import workspace as ws  # noqa: E402

OUTPUT = ROOT / "data" / "output"
SAMPLE = ROOT / "data" / "sample"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _f(x) -> float:
    return float(x) if x not in (None, "") else 0.0


def _sales():
    """Validated sales lines from the pipeline (duplicates, refunds, cancellations, unknown products removed)."""
    import bizflow_core as core
    cfg = core.Config(data_dir=SAMPLE, output_dir=OUTPUT)
    v = core.validate(SAMPLE, cfg)
    return core.eligible_lines(v, cfg), v, cfg


def _orders_block(bid: str) -> dict:
    rows = inbox.orders(bid, None)
    pend = [o for o in rows if o["status"] == "pending"]
    done = [o for o in rows if o["status"] == "done"]
    by_ch = defaultdict(lambda: {"orders": 0, "value": 0.0})
    for o in pend + done:
        by_ch[o.get("channel", "other")]["orders"] += 1
        by_ch[o.get("channel", "other")]["value"] += _f(o.get("total"))
    return {"pending": len(pend), "pending_value": round(sum(_f(o.get("total")) for o in pend), 2),
            "done": len(done), "done_value": round(sum(_f(o.get("total")) for o in done), 2),
            "by_channel": [{"channel": k, **{kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}} for k, v in by_ch.items()],
            "oldest_pending": min((o["created_at"] for o in pend), default=None)}


def _progress_block(bid: str) -> dict:
    td = ws.todos(bid)
    cps = ws.checkpoints(bid)
    a = auto.load()
    pend_auto = [o for o in a["orders"] if o.get("business_id") == bid and o["status"] == "awaiting_approval"]
    posts = [p for p in a["posts"] if p.get("business_id", "campus-crumb") == bid]
    return {"todos_total": len(td), "todos_done": sum(1 for t in td if t.get("done")), "checkpoints": len(cps),
            "latest_checkpoint": cps[0]["title"] if cps else None, "approvals_waiting": len(pend_auto),
            "posts_published": sum(1 for p in posts if p["status"] == "posted_simulated"),
            "posts_scheduled": sum(1 for p in posts if p["status"] == "scheduled"),
            "auto_reorders_on": sum(1 for r in a["rules"] if r.get("business_id") == bid and r.get("enabled"))}


def _recorded_lines(bid: str) -> list[dict]:
    """Sales the owner logged by hand plus completed customer orders (online shop, chats)."""
    from datetime import date
    out = []
    for s in st.sales(bid):
        out.append({"date": date.fromisoformat(s["date"]), "item": s["item"], "qty": s["qty"], "net": s["qty"] * s["price"],
                    "cogs": s["qty"] * s["cost"] if s.get("cost") is not None else None, "order": s["id"], "channel": s.get("channel", "walk-in")})
    costs = {m["item"].lower(): m.get("cost") for m in st.shop_menu(bid)}
    for o in inbox.orders(bid, "done"):
        d = date.fromisoformat(str(o.get("updated_at") or o["created_at"])[:10])
        for it in o.get("items") or []:
            if it.get("line_total") in (None, ""):
                continue
            c = costs.get(str(it.get("item", "")).lower())
            q = int(it.get("qty") or 1)
            out.append({"date": d, "item": it["item"], "qty": q, "net": _f(it["line_total"]),
                        "cogs": c * q if c is not None else None, "order": o["id"], "channel": o.get("channel", "other")})
    return out


def _recorded_dashboard(bid: str, out: dict, lines: list[dict]):
    """Same charts as the sample business, computed from the owner's own records."""
    from datetime import date
    P = out["problems"]
    end = max(date.today(), max(r["date"] for r in lines))
    start = min(min(r["date"] for r in lines), end - timedelta(days=13))
    day_rev, day_units, day_orders = defaultdict(float), defaultdict(int), defaultdict(set)
    wk_rev, wk_units, wk_count = defaultdict(float), defaultdict(int), defaultdict(int)
    prod = defaultdict(lambda: {"revenue": 0.0, "cogs": 0.0, "units": 0, "cost_known": True})
    for r in lines:
        day_rev[r["date"]] += r["net"]; day_units[r["date"]] += r["qty"]; day_orders[r["date"]].add(r["order"])
        wk_rev[r["date"].weekday()] += r["net"]; wk_units[r["date"].weekday()] += r["qty"]
        pr = prod[r["item"]]; pr["revenue"] += r["net"]; pr["units"] += r["qty"]
        if r["cogs"] is None:
            pr["cost_known"] = False
        else:
            pr["cogs"] += r["cogs"]
    daily, d = [], start
    while d <= end:
        daily.append({"date": d.isoformat(), "revenue": round(day_rev.get(d, 0.0), 2), "units": day_units.get(d, 0), "orders": len(day_orders.get(d, ()))})
        wk_count[d.weekday()] += 1
        d += timedelta(days=1)
    revenue = sum(x["revenue"] for x in prod.values())
    known = [x for x in prod.values() if x["cost_known"]]
    gross = sum(x["revenue"] - x["cogs"] for x in known)
    known_rev = sum(x["revenue"] for x in known)
    n_orders = len({r["order"] for r in lines})
    products_out = []
    for name, x in sorted(prod.items(), key=lambda kv: -kv[1]["revenue"]):
        pf = round(x["revenue"] - x["cogs"], 2) if x["cost_known"] else None
        products_out.append({"id": name, "name": name, "revenue": round(x["revenue"], 2), "profit": pf if pf is not None else 0.0, "cost_known": x["cost_known"],
                             "units": x["units"], "margin_pct": round(pf / x["revenue"] * 100, 1) if pf is not None and x["revenue"] else 0.0,
                             "profit_share_pct": round(pf / gross * 100, 1) if pf is not None and gross else 0.0})
    weekdays = [{"day": DAYS[i], "revenue": round(wk_rev.get(i, 0.0), 2), "avg_revenue": round(wk_rev.get(i, 0.0) / wk_count[i], 2) if wk_count[i] else 0,
                 "units": wk_units.get(i, 0)} for i in range(7)]
    last7 = sum(x["revenue"] for x in daily[-7:]); prev7 = sum(x["revenue"] for x in daily[-14:-7])
    n_days = len({r["date"] for r in lines})
    out.update({
        "has_sales": True, "recorded": True, "period": {"start": start.isoformat(), "end": end.isoformat()},
        "kpis": {"revenue": round(revenue, 2), "gross_profit": round(gross, 2), "gross_margin_pct": round(gross / known_rev * 100, 2) if known_rev else 0,
                 "units": sum(x["units"] for x in prod.values()), "orders": n_orders, "avg_order_value": round(revenue / n_orders, 2) if n_orders else 0,
                 "expenses": 0.0, "expenses_unpaid": 0.0, "expenses_unknown": 0.0, "operating_profit": round(gross, 2),
                 "last7_revenue": round(last7, 2), "prev7_revenue": round(prev7, 2), "check_vs_snapshot": False,
                 "cost_coverage_pct": round(known_rev / revenue * 100) if revenue else 0},
        "daily": daily, "weekdays": weekdays, "products": products_out, "stock": [], "expenses_by_category": [], "ingredients_low": [],
        "sales_log": sorted(st.sales(bid), key=lambda s: s["created_at"], reverse=True)[:30],
        "sources": ["data/workspace/sales_log.json", "data/workspace/inbox.json (completed orders)", "data/workspace/settings.json (shop menu costs)"]})
    if out["kpis"]["cost_coverage_pct"] < 100:
        miss = [p["name"] for p in products_out if not p["cost_known"]]
        P.append({"level": "warning", "icon": "🧮", "title": f"Profit is missing for {len(miss)} product{'s' if len(miss) > 1 else ''}",
                  "detail": "Add what one " + ", ".join(miss[:3]) + " costs you to make (⚙️ Settings → Shop menu) so BizFlow can show real profit.",
                  "action": "Add costs", "drawer": "settings"})
    if len(products_out) > 1:
        top = products_out[0]
        P.append({"level": "good", "icon": "⭐", "title": f"{top['name']} is your best seller (MYR {top['revenue']:.2f})",
                  "detail": f"{top['units']} sold. Push it with a combo or a social post.", "action": "Sell more of it",
                  "ask": f"{top['name']} is my best seller ({top['units']} sold, MYR {top['revenue']:.2f}). How can I sell more of it next week?"})
    busy = max(weekdays, key=lambda w: w["avg_revenue"])
    if busy["avg_revenue"] and n_days >= 3:
        P.append({"level": "info", "icon": "📅", "title": f"{busy['day']} is your busiest day so far (avg MYR {busy['avg_revenue']:.2f})",
                  "detail": "Based on the sales you recorded. Keep logging every day to make this reliable.", "action": "Plan my week",
                  "ask": f"My busiest day so far is {busy['day']}. Plan my prep and stock for next week."})
    if n_days < 7:
        P.append({"level": "info", "icon": "📝", "title": f"{len(lines)} sale line{'s' if len(lines) != 1 else ''} recorded on {n_days} day{'s' if n_days != 1 else ''}",
                  "detail": "Record every sale for a week and BizFlow can show reliable best products and busy days.", "action": "Record a sale", "drawer": "sale"})


def business_dashboard(bid: str) -> dict:
    b = ws.business(bid) or {}
    out = {"business_id": bid, "name": b.get("name"), "emoji": b.get("emoji"), "goal": b.get("goal", ""),
           "has_sales": bool(b.get("uses_sample_data")), "orders": _orders_block(bid), "progress": _progress_block(bid), "problems": []}
    P = out["problems"]

    if b.get("uses_sample_data"):
        lines, v, cfg = _sales()
        snap = _read(OUTPUT / "business_snapshot.json", {})
        m = snap.get("metrics", {})
        products = {pid: p for pid, p in v.products.items() if p}
        # daily revenue (every day of the period, zero-filled)
        day_rev, day_units, orders_by_day = defaultdict(Decimal), defaultdict(int), defaultdict(set)
        wk_rev, wk_units = defaultdict(Decimal), defaultdict(int)
        prod = defaultdict(lambda: {"revenue": Decimal(0), "cogs": Decimal(0), "units": 0})
        for r in lines:
            d = r["date"]
            day_rev[d] += r["net"]; day_units[d] += r["quantity"]; orders_by_day[d].add(r["order_id"])
            wk_rev[d.weekday()] += r["net"]; wk_units[d.weekday()] += r["quantity"]
            pr = prod[r["product_id"]]; pr["revenue"] += r["net"]; pr["cogs"] += r["cogs"]; pr["units"] += r["quantity"]
        daily, d = [], cfg.period_start
        weekday_count = defaultdict(int)
        while d <= cfg.period_end:
            daily.append({"date": d.isoformat(), "revenue": float(day_rev.get(d, 0)), "units": day_units.get(d, 0), "orders": len(orders_by_day.get(d, ()))})
            weekday_count[d.weekday()] += 1
            d += timedelta(days=1)
        revenue = sum(float(x["revenue"]) for x in prod.values())
        cogs = sum(float(x["cogs"]) for x in prod.values())
        n_orders = len({r["order_id"] for r in lines})
        gross = revenue - cogs
        exp_total = _f(m.get("recorded_expenses"))
        exp_status = m.get("recorded_expenses_by_status", {})
        expenses = defaultdict(float)
        for e in v.expenses_rows:  # validated rows only (same 7 rows as "recorded expenses")
            if e.get("amount") is not None:
                expenses[e.get("category") or "Other"] += float(e["amount"])
        products_out = []
        for pid, x in sorted(prod.items(), key=lambda kv: -(kv[1]["revenue"] - kv[1]["cogs"])):
            rv, cg = float(x["revenue"]), float(x["cogs"])
            products_out.append({"id": pid, "name": products[pid]["product_name"] if pid in products else pid, "revenue": round(rv, 2),
                                 "profit": round(rv - cg, 2), "units": x["units"], "margin_pct": round((rv - cg) / rv * 100, 1) if rv else 0.0,
                                 "profit_share_pct": round((rv - cg) / gross * 100, 1) if gross else 0.0})
        weekdays = [{"day": DAYS[i], "revenue": round(float(wk_rev.get(i, 0)), 2), "avg_revenue": round(float(wk_rev.get(i, 0)) / weekday_count[i], 2) if weekday_count[i] else 0,
                     "units": wk_units.get(i, 0)} for i in range(7)]
        ops = _read(OUTPUT / "ops_findings.json", {}).get("stock_and_replenishment", {})
        stock = []
        for pid, s in ops.items():
            dos = _f(s.get("days_of_stock")) if s.get("days_of_stock") not in (None, "") else None
            lead = int(s.get("lead_time_days") or 0)
            state = "stale" if s.get("stock_stale") else "low" if s.get("reorder_trigger") else "over" if dos is not None and dos > 2 * (lead + cfg.safety_stock_days) else "ok"
            stock.append({"id": pid, "name": s["product_name"], "on_hand": s.get("stock_on_hand"), "days": dos, "lead": lead,
                          "reorder_units": s.get("replenishment_units"), "state": state, "age_days": s.get("stock_age_days")})
        ing = [{"material": k, **vv} for k, vv in auto.stock_all().get(bid, {}).items()]
        low_ing = [i for i in ing if _f(i.get("qty")) <= _f(i.get("threshold"))]
        last7 = sum(x["revenue"] for x in daily[-7:]); prev7 = sum(x["revenue"] for x in daily[-14:-7])
        out.update({
            "period": {"start": cfg.period_start.isoformat(), "end": cfg.period_end.isoformat()},
            "kpis": {"revenue": round(revenue, 2), "gross_profit": round(gross, 2), "gross_margin_pct": round(gross / revenue * 100, 2) if revenue else 0,
                     "units": sum(x["units"] for x in prod.values()), "orders": n_orders, "avg_order_value": round(revenue / n_orders, 2) if n_orders else 0,
                     "expenses": round(exp_total, 2), "expenses_unpaid": _f(exp_status.get("unpaid")), "expenses_unknown": _f(exp_status.get("unknown")),
                     "operating_profit": round(gross - exp_total, 2), "last7_revenue": round(last7, 2), "prev7_revenue": round(prev7, 2),
                     "check_vs_snapshot": abs(revenue - _f(m.get("net_revenue"))) < 0.01},
            "daily": daily, "weekdays": weekdays, "products": products_out, "stock": stock,
            "expenses_by_category": sorted([{"category": k, "amount": round(vv, 2)} for k, vv in expenses.items()], key=lambda e: -e["amount"]),
            "ingredients_low": [{"material": i["material"], "qty": i.get("qty"), "unit": i.get("unit"), "threshold": i.get("threshold")} for i in low_ing],
            "sources": ["data/sample/sales.csv (validated lines)", "data/output/business_snapshot.json", "data/output/ops_findings.json",
                        "data/sample/expenses.csv", "data/workspace/ingredient_stock.json", "data/workspace/inbox.json"]})

        # ---------------- problems → actions (deterministic rules)
        for s in sorted(stock, key=lambda x: x["days"] if x["days"] is not None else 99):
            if s["state"] == "low":
                P.append({"level": "critical", "icon": "⛔", "title": f"{s['name']} runs out in {s['days']:.1f} days",
                          "detail": f"Only {s['on_hand']} left and a new batch takes {s['lead']} days. Make or buy {s['reorder_units']} more now.",
                          "action": "Reorder now", "ask": f"{s['name']} runs out in {s['days']:.1f} days. What exactly should I buy or make, from which supplier, and how much will it cost?"})
            elif s["state"] == "stale":
                P.append({"level": "warning", "icon": "🔢", "title": f"{s['name']} stock count is {s['age_days']} days old",
                          "detail": "BizFlow can't tell when it will run out until you recount it.", "action": "Recount stock",
                          "ask": f"Help me recount {s['name']} and tell me what to do with the new number."})
            elif s["state"] == "over":
                P.append({"level": "warning", "icon": "📦", "title": f"Too much {s['name']} — {s['days']:.0f} days of stock",
                          "detail": "Cash is sitting on the shelf. Pause reordering and promote it this week.", "action": "Promote it",
                          "ask": f"I have {s['days']:.0f} days of {s['name']} in stock. Plan a promotion this week to sell it without cutting my margin too much."})
        if low_ing:
            P.append({"level": "warning", "icon": "🧺", "title": f"{len(low_ing)} ingredient{'s' if len(low_ing) > 1 else ''} below your low level",
                      "detail": ", ".join(f"{i['material']} {i['qty']:g} {i['unit']}" for i in low_ing[:5]), "action": "Open Inventory",
                      "tab": "inventory", "ask": "Which low ingredients should I reorder first and from which supplier?"})
        if products_out:
            weak = products_out[-1]
            if weak["profit_share_pct"] < 5:
                P.append({"level": "warning", "icon": "📉", "title": f"{weak['name']} earns only {weak['profit_share_pct']}% of your profit",
                          "detail": f"{weak['units']} sold this period (MYR {weak['profit']:.2f} profit). Bundle it, reprice it, or drop it to free time and cash.",
                          "action": "Fix or drop it", "ask": f"{weak['name']} earns only {weak['profit_share_pct']}% of my profit ({weak['units']} sold). Should I bundle, reprice or drop it? Give me a plan."})
            top = max(products_out, key=lambda x: x["margin_pct"])
            P.append({"level": "good", "icon": "⭐", "title": f"{top['name']} has your best margin ({top['margin_pct']}%)",
                      "detail": f"It brings MYR {top['profit']:.2f} profit ({top['profit_share_pct']}% of the total). Push it with a combo or social post.",
                      "action": "Sell more of it", "ask": f"{top['name']} has my best margin ({top['margin_pct']}%). How can I sell more of it next week?"})
        busy = max(weekdays, key=lambda w: w["avg_revenue"]); quiet = min(weekdays, key=lambda w: w["avg_revenue"])
        if busy["avg_revenue"]:
            P.append({"level": "info", "icon": "📅", "title": f"{busy['day']} is your busiest day (avg MYR {busy['avg_revenue']:.2f}); {quiet['day']} the quietest (avg MYR {quiet['avg_revenue']:.2f})",
                      "detail": f"Prep more stock and get help on {busy['day']}; try a small offer or rest on {quiet['day']}.", "action": "Plan my week",
                      "ask": f"My busiest day is {busy['day']} and quietest is {quiet['day']}. Plan my prep, stock and helper schedule for next week."})
        if exp_status.get("unpaid") or exp_status.get("unknown"):
            P.append({"level": "warning", "icon": "🧾", "title": f"MYR {_f(exp_status.get('unpaid')):.2f} of expenses unpaid, MYR {_f(exp_status.get('unknown')):.2f} unknown",
                      "detail": "Settle or confirm them so your profit numbers are real.", "action": "Sort my bills",
                      "ask": "Which expenses are unpaid or unknown, and what should I pay first?"})
        op = gross - exp_total
        P.append({"level": "good" if op > 0 else "critical", "icon": "💰" if op > 0 else "⚠️",
                  "title": f"After expenses you keep about MYR {op:.2f} ({op / revenue * 100:.0f}% of revenue)" if revenue else "No revenue yet",
                  "detail": f"Gross profit MYR {gross:.2f} − recorded expenses MYR {exp_total:.2f}. Biggest cost: {max(expenses, key=expenses.get) if expenses else 'n/a'}.",
                  "action": "Improve profit", "ask": f"I keep MYR {op:.2f} after expenses on MYR {revenue:.2f} revenue. Where can I cut costs or raise profit next month?"})
        if prev7:
            ch = (last7 - prev7) / prev7 * 100
            P.append({"level": "good" if ch >= 0 else "warning", "icon": "📈" if ch >= 0 else "📉",
                      "title": f"Sales {'up' if ch >= 0 else 'down'} {abs(ch):.0f}% in the last 7 days (MYR {last7:.2f} vs {prev7:.2f})",
                      "detail": "Compared with the 7 days before.", "action": "Why?",
                      "ask": f"My sales went {'up' if ch >= 0 else 'down'} {abs(ch):.0f}% in the last 7 days. What changed and what should I do?"})
    elif _recorded_lines(bid):
        _recorded_dashboard(bid, out, _recorded_lines(bid))
    else:
        out.update({"kpis": None, "sources": ["data/workspace/inbox.json", "data/workspace/todos.json", "data/workspace/checkpoints.json"]})
        P.append({"level": "info", "icon": "🧾", "title": "No sales records yet",
                  "detail": "Orders from Online Requests and your online shop are counted below. Record your first sales to unlock profit, best-product and busy-day analytics.",
                  "action": "Record a sale", "drawer": "sale", "ask": "How should I record my sales so BizFlow can show my profit, best products and busiest days?"})

    o = out["orders"]
    if o["pending"]:
        P.insert(0, {"level": "critical" if o["pending"] >= 3 else "warning", "icon": "📦", "title": f"{o['pending']} customer order{'s' if o['pending'] > 1 else ''} waiting (MYR {o['pending_value']:.2f})",
                     "detail": f"Oldest since {str(o['oldest_pending'])[:16].replace('T', ' ')}. Complete them before taking new stock decisions.", "action": "Open pending orders",
                     "drawer": "orders", "ask": "Which pending customer orders should I complete first and what do I need to prepare?"})
    pr = out["progress"]
    if pr["approvals_waiting"]:
        P.insert(0, {"level": "warning", "icon": "✋", "title": f"{pr['approvals_waiting']} supplier order{'s' if pr['approvals_waiting'] > 1 else ''} waiting for your OK",
                     "detail": "Auto-reorder prepared them because stock is low or a schedule fired.", "action": "Review in Inventory", "tab": "inventory"})
    if pr["todos_total"] and pr["todos_done"] < pr["todos_total"]:
        P.append({"level": "info", "icon": "📝", "title": f"{pr['todos_total'] - pr['todos_done']} plan step{'s' if pr['todos_total'] - pr['todos_done'] > 1 else ''} still to do",
                  "detail": f"{pr['todos_done']} of {pr['todos_total']} done · {pr['checkpoints']} checkpoint{'s' if pr['checkpoints'] != 1 else ''} reached.", "action": "Open Task Checklist", "tab": "roadmap"})
    rank = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    P.sort(key=lambda p: rank.get(p["level"], 9))
    return out


def all_dashboard() -> dict:
    rows = []
    for b in ws.businesses():
        d = business_dashboard(b["id"])
        k = d.get("kpis") or {}
        rows.append({"id": b["id"], "name": b["name"], "emoji": b.get("emoji", ""), "has_sales": d["has_sales"],
                     "revenue": k.get("revenue"), "gross_margin_pct": k.get("gross_margin_pct"), "operating_profit": k.get("operating_profit"),
                     "orders_pending": d["orders"]["pending"], "orders_value": round(d["orders"]["pending_value"] + d["orders"]["done_value"], 2),
                     "todos_done": d["progress"]["todos_done"], "todos_total": d["progress"]["todos_total"], "checkpoints": d["progress"]["checkpoints"],
                     "approvals_waiting": d["progress"]["approvals_waiting"],
                     "critical": sum(1 for p in d["problems"] if p["level"] == "critical"),
                     "problems": [dict(p, business_id=b["id"], business=b["name"], emoji=b.get("emoji", "")) for p in d["problems"] if p["level"] in ("critical", "warning")][:4]})
    top = sorted([p for r in rows for p in r["problems"]], key=lambda p: {"critical": 0, "warning": 1}.get(p["level"], 2))
    return {"businesses": rows, "top_problems": top[:10],
            "totals": {"revenue": round(sum(r["revenue"] or 0 for r in rows), 2), "orders_pending": sum(r["orders_pending"] for r in rows),
                       "approvals_waiting": sum(r["approvals_waiting"] for r in rows), "checkpoints": sum(r["checkpoints"] for r in rows),
                       "critical": sum(r["critical"] for r in rows)}}
