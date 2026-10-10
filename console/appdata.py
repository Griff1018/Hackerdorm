"""Everything the chat agent can SEE and DO inside the BizFlow app.

- snapshot(bid)      → a compact text picture of the whole app for one business (or all), put into every prompt
- dataset(bid, name) → one table of real BizFlow data; the chat draws it as a chart or table (numbers never come from the AI)
- execute(bid, act)  → one in-app action the owner asked for (record a customer / sale / menu item, connect an app,
                       complete an order, set the goal). Each returns an undo record. Nothing here moves money,
                       posts, or messages anyone — those stay approval-only plan steps.

Customers (data/workspace/customers.json) and marketplace reviews (data/workspace/reviews.json) live here too.
Everything is SYNTHETIC demo data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
import uuid
from collections import defaultdict

import automations as auto
import dashboard as dash
import inbox
import money as mon
import settings as appset
import workspace as ws

CUSTOMERS = ws.WS / "customers.json"
REVIEWS = ws.WS / "reviews.json"
LOCK = threading.Lock()
MARKETPLACE_REVIEWS = ws.ROOT / "data" / "inbox" / "marketplace_reviews"

# name → (title, default chart, needs sales data)
DATASETS = {
    "kpis": ("Key numbers", "table"),
    "daily_revenue": ("Daily revenue", "line"),
    "weekday_revenue": ("Average revenue by weekday", "bar"),
    "product_sales": ("Sales by product", "hbar"),
    "product_profit": ("Profit by product", "hbar"),
    "orders_by_channel": ("Customer orders by channel", "hbar"),
    "expenses": ("Expenses by category", "hbar"),
    "stock_cover": ("Days of stock left per product", "hbar"),
    "orders": ("Customer orders", "table"),
    "customers": ("Customers", "table"),
    "sales_log": ("Sales you recorded", "table"),
    "reviews": ("Customer reviews", "table"),
    "review_ratings": ("Average rating by product", "hbar"),
    "shop_menu": ("Online shop menu", "table"),
    "connections": ("Connected apps", "table"),
    "businesses": ("Your businesses compared", "table"),
    "money_flow": ("Money in and out", "table"),
    "money_by_day": ("Money in per day", "line"),
    "money_out_by_category": ("Where the money goes", "hbar"),
    "money_in_by_method": ("How customers pay you", "hbar"),
    "inventory": ("Inventory — ingredients", "table"),
}
ACTIONS = {"record_customer", "update_customer", "delete_customer", "record_sale", "set_menu_item", "connect_app", "disconnect_app",
           "complete_order", "set_goal", "record_money", "add_ingredient", "set_stock", "remove_ingredient", "record_order", "set_autopost"}
CUSTOMER_FIELDS = ("name", "phone", "email", "notes", "tags", "birthday", "favourite")
FORBIDDEN = re.compile(r"\b(ic|nric|mykad|passport|bank|account no|card|cvv|password|pin|otp)\b", re.I)


def _read(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------- customers

def customers(bid: str) -> list[dict]:
    """Saved customers merged with people seen in orders (orders count, total spent, last order)."""
    saved = [c for c in _read(CUSTOMERS, []) if c.get("business_id") == bid]
    by = {c["name"].lower(): dict(c, orders=0, spent=0.0, last_order="") for c in saved}
    for o in inbox.orders(bid, None):
        if o.get("status") == "cancelled" or not o.get("customer"):
            continue
        key = str(o["customer"]).lower()
        c = by.setdefault(key, {"id": None, "business_id": bid, "name": o["customer"], "phone": o.get("phone", ""), "notes": "",
                                "tags": [], "source": "from orders", "orders": 0, "spent": 0.0, "last_order": ""})
        c["orders"] += 1
        c["spent"] = round(c["spent"] + float(o.get("total") or 0), 2)
        c["last_order"] = max(c["last_order"], str(o.get("created_at", ""))[:10])
        c.setdefault("channels", set()).add(o.get("channel", ""))
        if not c.get("phone") and o.get("phone"):
            c["phone"] = o["phone"]
    out = []
    for c in by.values():
        c["channels"] = ", ".join(sorted(x for x in c.pop("channels", set()) if x))
        out.append(c)
    return sorted(out, key=lambda c: (-c["spent"], c["name"]))


def _save_customers(rows):
    ws._write(CUSTOMERS, rows)


def add_customer(bid: str, data: dict) -> dict:
    name = str(data.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("A customer needs a name.")
    row = {"id": "C" + uuid.uuid4().hex[:6], "business_id": bid, "source": "chat", "created_at": ws.now()}
    for k in CUSTOMER_FIELDS:
        v = data.get(k)
        if k == "tags":
            row["tags"] = [str(t)[:30] for t in (v if isinstance(v, list) else str(v or "").split(",")) if str(t).strip()][:8]
        else:
            row[k] = str(v or "").strip()[:300]
    if FORBIDDEN.search(row.get("notes", "")):
        row["notes"] = "(removed: BizFlow does not store ID, bank, card or password details)"
    with LOCK:
        rows = _read(CUSTOMERS, [])
        old = next((c for c in rows if c.get("business_id") == bid and c["name"].lower() == name.lower()), None)
        if old:  # same name → update that customer instead of a duplicate
            before = dict(old)
            for k in CUSTOMER_FIELDS:
                if row.get(k):
                    old[k] = row[k]
            old["updated_at"] = ws.now()
            _save_customers(rows)
            return {"customer": old, "before": before}
        row["name"] = name
        rows.append(row)
        _save_customers(rows)
        return {"customer": row, "before": None}


def delete_customer(bid: str, cid_or_name: str) -> dict | None:
    with LOCK:
        rows = _read(CUSTOMERS, [])
        hit = next((c for c in rows if c.get("business_id") == bid and (c["id"] == cid_or_name or c["name"].lower() == str(cid_or_name).lower())), None)
        if hit:
            rows.remove(hit)
            _save_customers(rows)
        return hit


def restore_customer(row: dict):
    with LOCK:
        rows = [c for c in _read(CUSTOMERS, []) if c["id"] != row["id"]]
        rows.append(row)
        _save_customers(rows)


# ---------------------------------------------------------------- reviews (marketplace apps)

REVIEW_TEXT = {5: ["{i} was perfect, will order again!", "Fresh and nicely packed — {i} is my favourite.", "Fast pickup, {i} tasted homemade."],
               4: ["{i} was good, portion could be a bit bigger.", "Nice {i}, delivery took a little long.", "Tasty {i}, packaging ok."],
               3: ["{i} was okay, a bit too sweet for me.", "Average {i}, arrived slightly cold."],
               2: ["{i} arrived squashed, please pack better.", "Waited 40 minutes for {i}, too slow."]}


def seed_reviews(bid: str, app: str):
    """When a marketplace app is connected, pull its (synthetic) reviews once."""
    rows = _read(REVIEWS, [])
    if any(r["business_id"] == bid and r["platform"] == app for r in rows):
        return
    menu = [m["item"] for m in appset.shop_menu(bid)] or ["your item"]
    out = []
    for n in range(8):
        h = int(hashlib.md5(f"{bid}{app}{n}".encode()).hexdigest(), 16)
        rating = [5, 5, 4, 5, 4, 3, 5, 2][(h + n) % 8]
        item = menu[h % len(menu)]
        texts = REVIEW_TEXT[rating]
        out.append({"id": f"R{app[:2].upper()}{n + 1:02d}", "business_id": bid, "platform": app, "item": item, "rating": rating,
                    "text": texts[h % len(texts)].format(i=item), "date": f"2026-10-{1 + (h % 9):02d}", "customer": f"{app}_user{h % 900 + 100}",
                    "synthetic": True})
    with LOCK:
        rows = _read(REVIEWS, [])
        rows.extend(out)
        ws._write(REVIEWS, rows)


def reviews(bid: str) -> list[dict]:
    on = {c["id"] for c in appset.connections(bid) if c["connected"]}
    out = [r for r in _read(REVIEWS, []) if r["business_id"] == bid and r["platform"] in on]
    if (ws.business(bid) or {}).get("uses_sample_data"):
        names = {}
        try:
            with (ws.ROOT / "data" / "sample" / "products.csv").open(newline="", encoding="utf-8-sig") as f:
                names = {r["product_id"]: r["product_name"] for r in csv.DictReader(f)}
        except OSError:
            pass
        for p in sorted(MARKETPLACE_REVIEWS.glob("*.json")):
            r = _read(p, {})
            if r.get("rating"):
                out.append({"id": r["review_id"], "business_id": bid, "platform": "marketplace (demo)", "item": names.get(r.get("product_id"), r.get("product_id")),
                            "rating": r["rating"], "text": r.get("text", ""), "date": str(r.get("created_at", ""))[:10], "customer": r.get("external_order_id", ""),
                            "synthetic": True})
    return sorted(out, key=lambda r: r["date"], reverse=True)


# ---------------------------------------------------------------- datasets (what the chat can chart)

def _t(name, columns, rows, x=None, y=None, unit="", note="", chart=None):
    title, default = DATASETS[name]
    return {"dataset": name, "title": title, "chart": chart or default, "columns": columns, "rows": rows, "x": x, "y": y, "unit": unit,
            "note": note, "as_of": ws.now()}


def dataset(bid: str, name: str) -> dict:
    if name not in DATASETS:
        raise ValueError(f"unknown dataset {name}; choose one of {', '.join(DATASETS)}")
    if bid == ws.ALL and name in ("customers", "orders", "sales_log", "reviews", "shop_menu", "inventory", "money_flow"):
        rows, cols, title = [], None, DATASETS[name][0]
        for b in ws.businesses():
            d = dataset(b["id"], name)
            cols = cols or d["columns"]
            rows += [dict(r, business=b["name"]) for r in d["rows"]]
        return _t(name, [["business", "Business"]] + (cols or []), rows, note=f"{len(rows)} rows across {len(ws.businesses())} businesses")
    if bid == ws.ALL or name == "businesses":
        a = dash.all_dashboard()
        return _t("businesses", [["name", "Business"], ["revenue", "Revenue (MYR)"], ["gross_margin_pct", "Margin %"], ["orders_pending", "Orders waiting"],
                                 ["approvals_waiting", "To approve"], ["checkpoints", "Checkpoints"], ["critical", "Urgent problems"]],
                  [{k: r.get(k) for k in ("name", "revenue", "gross_margin_pct", "orders_pending", "approvals_waiting", "checkpoints", "critical")} for r in a["businesses"]],
                  x="name", y="revenue", unit="MYR")
    if name == "customers":
        rows = customers(bid)
        return _t(name, [["name", "Name"], ["phone", "Phone"], ["orders", "Orders"], ["spent", "Spent (MYR)"], ["last_order", "Last order"], ["notes", "Notes"],
                         ["tags", "Tags"], ["source", "Source"]], [dict(c, tags=", ".join(c.get("tags") or [])) for c in rows], x="name", y="spent", unit="MYR",
                  note=f"{len(rows)} customer(s)")
    if name == "orders":
        rows = inbox.orders(bid, None)
        return _t(name, [["id", "Order"], ["customer", "Customer"], ["channel", "Channel"], ["items", "Items"], ["total", "Total (MYR)"], ["status", "Status"],
                         ["when", "When"]], [{"id": o["id"], "customer": o.get("customer"), "channel": o.get("channel"), "status": o["status"], "when": o.get("when") or "",
                                              "total": float(o.get("total") or 0), "items": ", ".join(f"{i.get('qty')}× {i.get('item')}" for i in o.get("items") or [])}
                                             for o in sorted(rows, key=lambda o: o["created_at"], reverse=True)], x="id", y="total", unit="MYR")
    if name == "sales_log":
        rows = appset.sales(bid)
        return _t(name, [["date", "Date"], ["item", "Item"], ["qty", "Qty"], ["price", "Price"], ["cost", "Cost"], ["channel", "Where"]],
                  sorted(rows, key=lambda s: s["date"], reverse=True), x="date", y="price", unit="MYR")
    if name in ("reviews", "review_ratings"):
        rows = reviews(bid)
        if name == "reviews":
            avg = round(sum(r["rating"] for r in rows) / len(rows), 2) if rows else None
            return _t(name, [["date", "Date"], ["platform", "Platform"], ["item", "Item"], ["rating", "★"], ["text", "Review"]], rows, x="item", y="rating",
                      note=(f"{len(rows)} reviews · average {avg} ★" if rows else "No reviews — connect Shopee, GrabFood or foodpanda in Settings to pull them in."))
        agg = defaultdict(list)
        for r in rows:
            agg[r["item"]].append(r["rating"])
        return _t(name, [["item", "Item"], ["avg", "Average ★"], ["count", "Reviews"]],
                  sorted([{"item": k, "avg": round(sum(v) / len(v), 2), "count": len(v)} for k, v in agg.items()], key=lambda r: -r["avg"]), x="item", y="avg", unit="★")
    if name.startswith("money"):
        L = mon.ledger(bid)
        if name == "money_flow":
            return _t(name, [["date", "Date"], ["direction", "In/Out"], ["amount", "Amount (MYR)"], ["method", "Method"], ["category", "Category"], ["party", "From / to"],
                             ["note", "Note"], ["source", "Source"]], [dict(r, method=mon.METHODS.get(r["method"], r["method"]), source=r["source"].replace("feed:bank", "online banking feed").replace("feed:tng", "Touch 'n Go feed"))
                       for r in L["entries"][:120]],
                      note=f"In MYR {L['totals']['in']:.2f} · out MYR {L['totals']['out']:.2f} · net MYR {L['totals']['net']:.2f}")
        if name == "money_by_day":
            return _t(name, [["date", "Date"], ["in", "In (MYR)"], ["out", "Out (MYR)"], ["net", "Net (MYR)"]], L["daily"], x="date", y="in", unit="MYR")
        if name == "money_out_by_category":
            return _t(name, [["category", "Category"], ["amount", "Amount (MYR)"]], L["out_by_category"], x="category", y="amount", unit="MYR")
        return _t("money_in_by_method", [["method", "Method"], ["amount", "Amount (MYR)"]], L["in_by_method"], x="method", y="amount", unit="MYR")
    if name == "inventory":
        rows = [{"material": m, "qty": s_.get("qty"), "unit": s_.get("unit", ""), "threshold": s_.get("threshold"),
                 "state": "low" if float(s_.get("qty") or 0) <= float(s_.get("threshold") or -1) else "ok", "supplier": s_.get("supplier", "")}
                for m, s_ in auto.stock_all().get(bid, {}).items()]
        return _t(name, [["material", "Ingredient"], ["qty", "In stock"], ["unit", "Unit"], ["threshold", "Low level"], ["state", "State"], ["supplier", "Supplier"]],
                  sorted(rows, key=lambda r: (r["state"] != "low", r["material"])), x="material", y="qty",
                  note=f"{sum(r['state'] == 'low' for r in rows)} low of {len(rows)}")
    if name == "shop_menu":
        return _t(name, [["item", "Item"], ["price", "Price (MYR)"], ["cost", "Cost (MYR)"], ["note", "Note"]], appset.shop_menu(bid), x="item", y="price", unit="MYR")
    if name == "connections":
        return _t(name, [["name", "App"], ["kind", "Type"], ["status", "Status"], ["handle", "Account"]],
                  [{"name": c["name"], "kind": c["kind"], "status": ("connected" if c["connected"] else "not connected") + ("" if c["live"] else " (simulated)"),
                    "handle": c["handle"]} for c in appset.connections(bid)])
    d = dash.business_dashboard(bid)
    if name == "orders_by_channel":
        return _t(name, [["channel", "Channel"], ["orders", "Orders"], ["value", "Value (MYR)"]], d["orders"]["by_channel"], x="channel", y="value", unit="MYR")
    if not d.get("kpis"):
        return _t(name, [], [], note="No sales records yet for this business — record sales (➕ Record a sale) or complete orders first.")
    k = d["kpis"]
    if name == "kpis":
        rows = [{"metric": "Revenue", "value": k["revenue"]}, {"metric": "Gross profit", "value": k["gross_profit"]},
                {"metric": "Gross margin %", "value": k["gross_margin_pct"]}, {"metric": "Orders", "value": k["orders"]},
                {"metric": "Average order", "value": k["avg_order_value"]}, {"metric": "Expenses", "value": k["expenses"]},
                {"metric": "Kept after expenses", "value": k["operating_profit"]}, {"metric": "Last 7 days revenue", "value": k["last7_revenue"]},
                {"metric": "Previous 7 days revenue", "value": k["prev7_revenue"]}]
        return _t(name, [["metric", "Metric"], ["value", "Value"]], rows, note=f"Period {d['period']['start']} → {d['period']['end']}")
    if name == "daily_revenue":
        return _t(name, [["date", "Date"], ["revenue", "Revenue (MYR)"], ["orders", "Orders"], ["units", "Items"]], d["daily"], x="date", y="revenue", unit="MYR",
                  note=f"{d['period']['start']} → {d['period']['end']}")
    if name == "weekday_revenue":
        return _t(name, [["day", "Day"], ["avg_revenue", "Average (MYR)"], ["revenue", "Total (MYR)"], ["units", "Items"]], d["weekdays"], x="day", y="avg_revenue", unit="MYR")
    if name == "product_sales":
        return _t(name, [["name", "Product"], ["revenue", "Revenue (MYR)"], ["units", "Sold"]], sorted(d["products"], key=lambda p: -p["revenue"]),
                  x="name", y="revenue", unit="MYR")
    if name == "product_profit":
        return _t(name, [["name", "Product"], ["profit", "Profit (MYR)"], ["margin_pct", "Margin %"], ["profit_share_pct", "Share %"]],
                  sorted(d["products"], key=lambda p: -p["profit"]), x="name", y="profit", unit="MYR")
    if name == "expenses":
        return _t(name, [["category", "Category"], ["amount", "Amount (MYR)"]], d["expenses_by_category"], x="category", y="amount", unit="MYR")
    if name == "stock_cover":
        return _t(name, [["name", "Product"], ["days", "Days left"], ["on_hand", "On hand"], ["lead", "Delivery days"], ["state", "State"]],
                  [dict(s, days=s["days"] or 0) for s in d["stock"]], x="name", y="days", unit="days")
    return _t(name, [], [])


# ---------------------------------------------------------------- the snapshot every prompt gets

def snapshot(bid: str) -> str:
    L = []
    if bid == ws.ALL:
        a = dash.all_dashboard()
        L.append("Scope: ALL businesses. " + "; ".join(f"{r['name']} (id {r['id']}): revenue {r['revenue'] if r['revenue'] is not None else 'no sales data'}, "
                                                      f"{r['orders_pending']} orders waiting, {r['critical']} urgent" for r in a["businesses"]))
        L.append("Top problems: " + "; ".join(f"[{p['business']}] {p['title']}" for p in a["top_problems"][:5]))
        return "\n".join(L)
    b = ws.business(bid) or {}
    d = dash.business_dashboard(bid)
    L.append(f"Business id: {bid} — {b.get('name')} ({b.get('type')}), area {b.get('area')}. Goal: {b.get('goal') or 'not set'}.")
    k = d.get("kpis")
    if k:
        L.append(f"Numbers ({d['period']['start']} → {d['period']['end']}): revenue MYR {k['revenue']:.2f}, gross profit MYR {k['gross_profit']:.2f} "
                 f"({k['gross_margin_pct']}%), {k['orders']} orders, avg order MYR {k['avg_order_value']:.2f}, expenses MYR {k['expenses']:.2f}, "
                 f"kept after expenses MYR {k['operating_profit']:.2f}, last 7 days MYR {k['last7_revenue']:.2f} vs previous 7 MYR {k['prev7_revenue']:.2f}.")
        L.append("Products (revenue / profit / sold): " + "; ".join(f"{p['name']} {p['revenue']:.2f}/{p['profit']:.2f}/{p['units']}" for p in d["products"][:8]))
        wk = d["weekdays"]
        busy, quiet = max(wk, key=lambda w: w["avg_revenue"]), min(wk, key=lambda w: w["avg_revenue"])
        L.append("Weekdays (average revenue per day / total): " + "; ".join(f"{w['day']} {w['avg_revenue']:.2f}/{w['revenue']:.2f}" for w in wk) +
                 f". Busiest by average: {busy['day']} (MYR {busy['avg_revenue']:.2f}); quietest: {quiet['day']} (MYR {quiet['avg_revenue']:.2f}).")
        days = [x for x in d["daily"] if x["revenue"]]
        if days:
            hi, lo = max(days, key=lambda x: x["revenue"]), min(days, key=lambda x: x["revenue"])
            zero = [x["date"] for x in d["daily"] if not x["revenue"]]
            L.append(f"Best single day {hi['date']} MYR {hi['revenue']:.2f}; lowest selling day {lo['date']} MYR {lo['revenue']:.2f}; days with no sales: {', '.join(zero) or 'none'}.")
        if d.get("expenses_by_category"):
            L.append("Expenses by category: " + "; ".join(f"{e['category']} {e['amount']:.2f}" for e in d["expenses_by_category"]))
        if d.get("stock"):
            L.append("Stock (days left / state): " + "; ".join(f"{s_['name']} {s_['days'] if s_['days'] is not None else '?'}/{s_['state']}" for s_ in d["stock"]))
    else:
        L.append("No sales records yet.")
    o = d["orders"]
    L.append(f"Customer orders: {o['pending']} waiting (MYR {o['pending_value']:.2f}), {o['done']} done.")
    for x in inbox.orders(bid)[:6]:
        L.append(f"  - waiting order {x['id']}: {x.get('customer')} via {x.get('channel')}, MYR {x.get('total')}, " +
                 ", ".join(f"{i.get('qty')}× {i.get('item')}" for i in x.get("items") or []))
    cs = customers(bid)
    L.append(f"Customers on file: {len(cs)}" + (" — " + "; ".join(f"{c['name']} ({c['orders']} orders, MYR {c['spent']:.2f})" for c in cs[:6]) if cs else ""))
    rv = reviews(bid)
    if rv:
        L.append(f"Reviews: {len(rv)}, average {sum(r['rating'] for r in rv) / len(rv):.2f} ★; lowest: " +
                 "; ".join(f"{r['rating']}★ {r['item']} ({r['platform']}): {r['text']}" for r in sorted(rv, key=lambda r: r["rating"])[:2]))
    con = appset.connections(bid)
    L.append("Connected apps: " + ", ".join(c["name"] for c in con if c["connected"]) + ". Not connected: " + ", ".join(c["id"] for c in con if not c["connected"]) + ".")
    menu = appset.shop_menu(bid)
    L.append("Online shop menu: " + ("; ".join(f"{m['item']} MYR {m['price']:.2f}" + (f" (cost {m['cost']:.2f})" if m.get("cost") is not None else "") for m in menu) or "empty"))
    th = inbox.threads(bid)
    L.append(f"Online Requests: {th['unread']} unread message(s) across {len(th['threads'])} chat(s).")
    try:
        mf = mon.ledger(bid)
        L.append(f"Money Flow: in MYR {mf['totals']['in']:.2f}, out MYR {mf['totals']['out']:.2f}, net MYR {mf['totals']['net']:.2f}. In by method: " +
                 "; ".join(f"{x['method']} {x['amount']:.2f}" for x in mf["in_by_method"]) + ". Out by category: " +
                 "; ".join(f"{x['category']} {x['amount']:.2f}" for x in mf["out_by_category"][:6]) + ".")
    except Exception as exc:
        L.append(f"Money Flow unavailable: {exc}")
    inv = auto.stock_all().get(bid, {})
    low = [f"{m} {s_.get('qty')}{s_.get('unit', '')} (low level {s_.get('threshold')})" for m, s_ in inv.items() if float(s_.get("qty") or 0) <= float(s_.get("threshold") or -1)]
    L.append(f"Inventory: {len(inv)} ingredient(s)" + (f"; LOW: {'; '.join(low[:8])}" if low else "; none low") + ".")
    ap = auto.autopost(bid)
    L.append("Auto-post: " + (f"ON every {ap['every_days']} day(s) at {ap['time']} ({ap['focus']}), next {ap['next_at']}" if ap["enabled"] else "off") + ".")
    L.append("Top problems on the dashboard: " + "; ".join(p["title"] for p in d["problems"][:4]))
    pr = d["progress"]
    L.append(f"Roadmap: {pr['todos_done']}/{pr['todos_total']} plan steps done, {pr['checkpoints']} checkpoints, {pr['approvals_waiting']} supplier orders waiting for OK.")
    return "\n".join(L)


# ---------------------------------------------------------------- actions the chat can run

def execute(bid: str, act: dict) -> dict:
    """Run one in-app action. Returns {ok, text, undo?} — never raises for bad input."""
    t = act.get("type")
    try:
        if bid == ws.ALL and t != "show":
            return {"ok": False, "text": "Open a single business first — this action belongs to one business."}
        if t in ("record_customer", "update_customer"):
            r = add_customer(bid, act)
            c = r["customer"]
            return {"ok": True, "text": ("Updated" if r["before"] else "Saved") + f" customer {c['name']}" + (f" · {c['phone']}" if c.get("phone") else "") +
                    (f" · {c['notes']}" if c.get("notes") else ""), "undo": {"type": "restore_customer", "row": r["before"]} if r["before"] else {"type": "delete_customer", "id": c["id"]}}
        if t == "delete_customer":
            hit = delete_customer(bid, str(act.get("id") or act.get("name") or ""))
            return {"ok": bool(hit), "text": f"Removed customer {hit['name']}" if hit else "No saved customer with that name.",
                    "undo": {"type": "restore_customer", "row": hit} if hit else None}
        if t == "record_sale":
            s = appset.add_sale(bid, act)
            return {"ok": True, "text": f"Recorded sale: {s['qty']}× {s['item']} @ MYR {s['price']:.2f} on {s['date']}", "undo": {"type": "delete_sale", "id": s["id"]}}
        if t == "set_menu_item":
            before = appset.shop_menu(bid)
            rows = [dict(m) for m in before]
            name = str(act.get("item", "")).strip()
            hit = next((m for m in rows if m["item"].lower() == name.lower()), None)
            if act.get("remove"):
                rows = [m for m in rows if m is not hit]
            elif hit:
                for k in ("price", "cost", "note"):
                    if act.get(k) not in (None, ""):
                        hit[k] = act[k]
            else:
                rows.append({"item": name, "price": act.get("price"), "cost": act.get("cost"), "note": act.get("note", "")})
            appset.save_shop_menu(bid, rows)
            return {"ok": True, "text": ("Removed " if act.get("remove") else "Updated " if hit else "Added ") + f"{name} on your shop menu", "undo": {"type": "restore_menu", "rows": before}}
        if t in ("connect_app", "disconnect_app"):
            app = str(act.get("app", "")).lower().replace(" ", "")
            prev = next((c for c in appset.connections(bid) if c["id"] == app), None)
            if not prev:
                return {"ok": False, "text": f"BizFlow can't connect to '{act.get('app')}' yet."}
            c = appset.set_connection(bid, app, t == "connect_app", str(act.get("handle") or prev.get("handle") or ""))
            if t == "connect_app" and c["kind"] == "merchant" and app != "shop":
                seed_reviews(bid, app)
            if t == "connect_app" and c["kind"] == "payments":
                mon.seed_feed(bid, app)
            return {"ok": True, "text": f"{'Connected' if c['connected'] else 'Disconnected'} {c['name']}" + ("" if c["live"] else " (simulated link)") +
                    (f" as {c['handle']}" if c["connected"] and c["handle"] else ""),
                    "undo": {"type": "set_connection", "app": app, "connected": prev["connected"], "handle": prev["handle"]}}
        if t == "complete_order":
            oid = str(act.get("order_id", ""))
            o = inbox.set_order_status(oid, "done")
            return {"ok": True, "text": f"Marked order {oid} ({o.get('customer')}, MYR {o.get('total')}) as done", "undo": {"type": "order_status", "id": oid, "status": "pending"}}
        if t == "record_money":
            row = mon.add_entry(bid, act)
            return {"ok": True, "text": f"Recorded money {'in' if row['direction'] == 'in' else 'out'}: MYR {row['amount']:.2f} · {mon.METHODS.get(row['method'])} · {row['category']}" +
                    (f" · {row['note']}" if row.get("note") else "") + (f" (+{row['qty']:g} {row.get('unit', '')} {row['material']} to inventory)" if row.get("material") else ""),
                    "undo": {"type": "delete_money", "id": row["id"]}}
        if t in ("add_ingredient", "set_stock"):
            mat = str(act.get("material") or act.get("name") or "").strip()[:60]
            if not mat:
                return {"ok": False, "text": "Which ingredient?"}
            before = auto.stock_of(bid, mat)
            auto.set_stock(bid, mat, {"qty": act.get("qty") if act.get("qty") not in (None, "") else (None if before else 0),
                                      "threshold": act.get("threshold") if act.get("threshold") not in (None, "") else None,
                                      "unit": act.get("unit"), "supplier": act.get("supplier"), "phone": act.get("phone"),
                                      "planned_by": "agent" if act.get("_by") == "agent" else act.get("planned_by")})
            s_ = auto.stock_of(bid, mat)
            return {"ok": True, "text": f"{'Updated' if before else 'Added'} {mat} in Inventory: {s_.get('qty'):g} {s_.get('unit', '')}" +
                    (f", low level {s_.get('threshold'):g}" if s_.get("threshold") else ""),
                    "undo": {"type": "restore_stock", "material": mat, "row": before}}
        if t == "remove_ingredient":
            mat = str(act.get("material") or "").strip()
            hit = auto.remove_stock(bid, mat)
            return {"ok": bool(hit), "text": f"Removed {mat} from Inventory" if hit else f"No {mat} in Inventory.",
                    "undo": {"type": "restore_stock", "material": mat, "row": hit} if hit else None}
        if t == "record_order":
            items, total, unknown = [], 0.0, []
            menu = {m["item"].lower(): m for m in appset.shop_menu(bid)}
            for it in act.get("items") or []:
                name = str(it.get("item", "")).strip()
                q = max(1, int(it.get("qty") or 1))
                m = menu.get(name.lower()) or next((v for k, v in menu.items() if name.lower() in k or k in name.lower()), None) if name else None
                price = float(it["price"]) if it.get("price") not in (None, "") else (m["price"] if m else None)
                if price is None:
                    unknown.append(name)
                    continue
                total += price * q
                items.append({"item": m["item"] if m and it.get("price") in (None, "") else name, "qty": q, "price": f"{price:.2f}", "line_total": f"{price * q:.2f}"})
            if not items:
                return {"ok": False, "text": "No priced items — add the price or put the item on the shop menu." + (f" Unknown: {', '.join(unknown)}" if unknown else "")}
            if not str(act.get("customer", "")).strip():
                return {"ok": False, "text": "Whose order is it? Give a customer name."}
            o = inbox.add_order({"business_id": bid, "channel": str(act.get("channel") or "manual")[:20], "customer": str(act.get("customer"))[:60],
                                 "phone": str(act.get("phone") or "")[:20], "items": items, "total": f"{total:.2f}",
                                 "fulfilment": act.get("fulfilment") or "pickup", "when": str(act.get("when") or "")[:40], "notes": str(act.get("notes") or "")[:200],
                                 "source": "manual entry", "status": "done" if act.get("done") else "pending"})
            return {"ok": True, "text": f"Recorded order {o['id']} for {o['customer']}: " + ", ".join(f"{i['qty']}× {i['item']}" for i in items) +
                    f" = MYR {total:.2f}" + (f" (skipped unknown: {', '.join(unknown)})" if unknown else ""), "undo": {"type": "order_status", "id": o["id"], "status": "cancelled"}}
        if t == "set_autopost":
            before = auto.autopost(bid)
            cfg = auto.set_autopost(bid, act)
            return {"ok": True, "text": ("Auto-posting ON: every " + str(cfg["every_days"]) + f" day(s) at {cfg['time']} on {', '.join(cfg['platforms'])}, featuring "
                                         + {"rotate": "each menu item in turn", "best_seller": "your best seller", "slow_seller": "your slowest seller"}[cfg["focus"]] +
                                         f" — next post {str(cfg['next_at'])[:16].replace('T', ' ')}") if cfg["enabled"] else "Auto-posting turned off",
                    "undo": {"type": "autopost", "cfg": {k: before[k] for k in ("enabled", "every_days", "time", "focus", "platforms")}}}
        if t == "set_goal":
            prev = (ws.business(bid) or {}).get("goal", "")
            ws.set_goal(bid, str(act.get("goal", "")))
            return {"ok": True, "text": f"Goal set: {str(act.get('goal', ''))[:120]}", "undo": {"type": "set_goal", "goal": prev}}
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "text": f"Couldn't do '{t}': {exc}"}
    return {"ok": False, "text": f"Unknown action '{t}'."}


def undo(bid: str, u: dict) -> str:
    t = u.get("type")
    if t == "delete_customer":
        delete_customer(bid, u["id"])
    elif t == "restore_customer" and u.get("row"):
        restore_customer(u["row"])
    elif t == "delete_sale":
        appset.delete_sale(u["id"])
    elif t == "restore_menu":
        appset.save_shop_menu(bid, u["rows"])
    elif t == "set_connection":
        appset.set_connection(bid, u["app"], u["connected"], u.get("handle", ""))
    elif t == "order_status":
        inbox.set_order_status(u["id"], u["status"])
    elif t == "set_goal":
        ws.set_goal(bid, u.get("goal", ""))
    elif t == "delete_money":
        mon.delete_entry(u["id"])
    elif t == "restore_stock":
        if u.get("row"):
            auto.set_stock(bid, u["material"], u["row"])
            auto.set_stock(bid, u["material"], {"qty": u["row"].get("qty")})
        else:
            auto.remove_stock(bid, u["material"])
    elif t == "autopost":
        auto.set_autopost(bid, u["cfg"])
    else:
        raise ValueError("nothing to undo")
    return "undone"
