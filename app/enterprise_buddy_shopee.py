"""Enterprise Buddy Shopee agent: five analysis modules + an approval queue for the connected Shopee shop.

Ported from ShopeeAgent's `agent/` (TypeScript). Each module returns {report, proposals}:
  orders    — ship-by deadlines, overdue orders, stalled tracking, failed deliveries, courier anomalies, buyer cancellations
  products  — stock cover vs supplier lead time, sales drops (Poisson test vs a 3-week baseline), pricing from unit
              economics (Shopee fees learned from payouts + the seller's cost sheet), price-change detection, listing quality
  reviews   — sentiment + complaint themes per review, recurring complaints, significant rating drops, evidence-based fixes
  service   — unread chat triage with order/tracking/product context, reply drafts, refund decisions on return requests
  sales     — daily/weekly sales and P&L after fees, refunds and COGS, product comparison (Promote/Improve/Investigate/
              Fix margin), anomalies that recognise campaign days and paydays, boost proposals

Numbers are always computed in code. Drafts (replies, listing copy) come from rules here; nothing is written to the
shop until the owner approves a proposal (or sets that action type to `auto`). On approval the action is re-checked
against live data, executed, read back to verify, and logged.

data/shopee/agent.json — settings (policies, thresholds), proposals and the action log.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shopee_mock"))
import sim  # noqa: E402

STORE = ROOT / "data" / "shopee" / "agent.json"
COSTS = ROOT / "data" / "shopee" / "seller-costs.csv"
HOUR, DAY = sim.HOUR, sim.DAY
SOURCE = "enterprise_buddy_agent"
LOCK = threading.RLock()

DEFAULT_SETTINGS = {
    "policy": {"ship_orders": "approval", "handle_buyer_cancellation": "approval", "update_price": "approval", "update_stock": "approval",
               "update_item": "approval", "boost_item": "approval", "unlist_item": "approval", "send_chat_message": "approval",
               "reply_comment": "approval", "accept_return": "approval", "offer_partial_refund": "approval", "dispute_return": "approval"},
    "lead_time_days": 7,
    "thresholds": {"ship_deadline_hours": 24, "stuck_tracking_hours": 48, "target_margin": 0.25, "min_margin": 0.1, "sales_drop_pct": 30,
                   "conversion_drop_pct": 30, "rating_drop": 0.3, "max_price_change_pct": 20},
}
MODULES = [
    {"id": "orders", "title": "Order & Fulfillment", "description": "Deadlines, logistics problems, cancellations and shipment actions"},
    {"id": "products", "title": "Product & Inventory", "description": "Stock risk, sales trends, pricing and listing quality"},
    {"id": "reviews", "title": "Review Intelligence", "description": "Sentiment, recurring complaints, rating trends and evidence-based fixes"},
    {"id": "service", "title": "Customer Service", "description": "Message triage, reply drafts, refunds and escalations"},
    {"id": "sales", "title": "Sales & Business Intelligence", "description": "Sales, profit, product comparison and anomaly detection"},
]
SEV = {"critical": 0, "warning": 1, "info": 2, "positive": 3}


# ---------------------------------------------------------------- formatting helpers

def r2(n):
    return round(n + 0.0, 2)


def pct(n, d=1):
    return f"{n * 100:.{d}f}%"


def rm(n):
    return f"RM{n:.2f}"


def spct(n):
    return f"{'+' if n >= 0 else ''}{n * 100:.0f}%"


short = sim.short


def charm(p):
    return r2(max(0, round(p - 0.9)) + 0.9)


def poisson_cdf(k, lam):
    if lam <= 0:
        return 1
    term = math.exp(-lam)
    s = term
    for i in range(1, int(k) + 1):
        term *= lam / i
        s += term
    return min(1, s)


def hours_label(h):
    if h < 0:
        return f"{abs(h):.0f}h overdue"
    if h < 1:
        return f"{round(h * 60)}m left"
    return f"{h:.0f}h left"


def first_name(full):
    if not full:
        return ""
    n = full.split(" ")[0]
    return " ".join(full.split(" ")[:2]) if len(n) <= 2 else n


def sort_findings(f):
    return sorted(f, key=lambda x: SEV[x["severity"]])


# ---------------------------------------------------------------- store (settings, proposals, log)

def _load():
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    s = d.get("settings") or {}
    d["settings"] = {**DEFAULT_SETTINGS, **s, "policy": {**DEFAULT_SETTINGS["policy"], **s.get("policy", {})},
                     "thresholds": {**DEFAULT_SETTINGS["thresholds"], **s.get("thresholds", {})}}
    d.setdefault("proposals", [])
    d.setdefault("log", [])
    d.setdefault("rejected", {})
    return d


def _save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    d["proposals"] = [p for p in d["proposals"] if p["status"] == "pending" or p.get("updated_at", 0) > time.time() - 14 * DAY][-600:]
    d["log"] = d["log"][-400:]
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def settings():
    with LOCK:
        return _load()["settings"]


def update_settings(patch):
    with LOCK:
        d = _load()
        s = d["settings"]
        for k in ("lead_time_days",):
            if patch.get(k) is not None:
                s[k] = max(1, min(60, int(patch[k])))
        for k, v in (patch.get("policy") or {}).items():
            if k in s["policy"] and v in ("approval", "auto", "disabled"):
                s["policy"][k] = v
        for k, v in (patch.get("thresholds") or {}).items():
            if k in s["thresholds"]:
                s["thresholds"][k] = float(v)
        _save(d)
        return s


def log(text, kind="info", **extra):
    with LOCK:
        d = _load()
        d["log"].append({"ts": time.time(), "sim_ts": sim.now(), "kind": kind, "text": text, **extra})
        _save(d)


# ---------------------------------------------------------------- data (the agent's read access to the shop)

def costs():
    out = {}
    try:
        with COSTS.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["model_sku"]] = {"unit_cost": float(r["unit_cost"]), "packaging": float(r["packaging_cost"])}
    except OSError:
        pass
    return out


class Data:
    """One consistent read of the shop for a module run (orders over the last 35 days)."""

    def __init__(self):
        self.now = sim.now()
        since = self.now - 35 * DAY
        self.items = sim.all_("SELECT * FROM items WHERE item_status != 'DELETED' ORDER BY item_id")
        models = sim.all_("SELECT * FROM models")
        for it in self.items:
            it["models"] = [m for m in models if m["item_id"] == it["item_id"]]
            it["attributes"] = sim.jl(it["attributes"], {})
            rt = sim.item_rating(it["item_id"])
            it["rating"], it["rating_count"] = rt["rating_star"], rt["rating_count"]
        self.item = {i["item_id"]: i for i in self.items}
        self.orders = sim.all_("SELECT * FROM orders WHERE create_time >= ? OR order_status NOT IN ('COMPLETED','CANCELLED') ORDER BY create_time", since)
        lines = sim.all_("SELECT oi.* FROM order_items oi JOIN orders o ON o.order_sn = oi.order_sn WHERE o.create_time >= ? OR o.order_status NOT IN ('COMPLETED','CANCELLED')", since)
        by = {}
        for ln in lines:
            by.setdefault(ln["order_sn"], []).append(ln)
        for o in self.orders:
            o["lines"] = by.get(o["order_sn"], [])
            o["recipient"] = sim.jl(o["recipient"], {})
        self.daily = sim.all_("SELECT * FROM item_daily_stats WHERE date >= ?", sim.date_key(self.now - 40 * DAY))
        self.comments = sim.all_("SELECT * FROM comments WHERE create_time >= ? ORDER BY create_time DESC", self.now - 60 * DAY)
        self.returns = sim.all_("SELECT * FROM returns WHERE create_time >= ? OR status IN ('REQUESTED','PROCESSING','JUDGING') ORDER BY create_time DESC", since)
        comm = {r["item_id"]: r["commission_rate"] for r in sim.all_("SELECT i.item_id, c.commission_rate FROM items i JOIN categories c ON c.category_id = i.category_id")}
        refunds = {r["order_sn"]: r["s"] for r in sim.all_("SELECT order_sn, SUM(refund_amount) s FROM returns WHERE status = 'REFUND_PAID' GROUP BY order_sn")}
        self.escrow = {o["order_sn"]: self._escrow(o, comm, refunds.get(o["order_sn"], 0) or 0) for o in self.orders}
        self.perf = sim.shop_performance()

    @staticmethod
    def _escrow(o, comm, refund):
        selling = commission = service = 0.0
        items = []
        for ln in o["lines"]:
            sell = ln["discounted_price"] * ln["quantity"]
            c = round(sell * comm.get(ln["item_id"], 0.09), 2)
            selling += sell
            commission += c
            service += min(30, sell * 0.05)
            items.append({"item_id": ln["item_id"], "sell": sell, "commission": c})
        transaction = (selling + o["buyer_shipping_fee"]) * 0.0378
        full = o["order_status"] == "CANCELLED" and refund == 0
        return {"selling": selling, "commission": 0 if full else commission, "service": 0 if full else service,
                "transaction": 0 if full else transaction, "refund": refund,
                "escrow": 0 if full else selling - commission - service - transaction - refund, "items": items}

    def tracking(self, sns):
        if not sns:
            return {}
        out = {}
        for i in range(0, len(sns), 400):
            chunk = sns[i:i + 400]
            for r in sim.all_(f"SELECT * FROM tracking_events WHERE order_sn IN ({','.join('?' * len(chunk))}) ORDER BY ts", *chunk):
                out.setdefault(r["order_sn"], []).append(r)
        return out

    def chats(self):
        convs = sim.all_("SELECT * FROM conversations WHERE last_message_time >= ? ORDER BY last_message_time DESC", self.now - 14 * DAY)
        for c in convs:
            c["messages"] = sim.all_("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_timestamp, message_id", c["conversation_id"])
            for m in c["messages"]:
                m["content"] = sim.jl(m["content"], {})
        return convs


LIVE = lambda o: o["order_status"] not in ("CANCELLED", "UNPAID")  # noqa: E731


def fee_rates(data):
    per, tf, ts = {}, 0.0, 0.0
    for o in data.orders:
        e = data.escrow[o["order_sn"]]
        if not LIVE(o) or not e["selling"]:
            continue
        order_level = e["service"] + e["transaction"]
        for it in e["items"]:
            share = it["sell"] / e["selling"]
            fees = it["commission"] + order_level * share
            cur = per.setdefault(it["item_id"], [0.0, 0.0])
            cur[0] += fees
            cur[1] += it["sell"]
            tf += fees
            ts += it["sell"]
    shop = tf / ts if ts else 0.17
    return lambda iid: per[iid][0] / per[iid][1] if iid in per and per[iid][1] > 50 else shop


def _sum(rows, frm, to, f):
    return sum(r[f] for r in rows if frm < r["date"] <= to)


def detect_price_change(item_id, orders, now):
    counts = {}
    for o in orders:
        for ln in o["lines"]:
            if ln["item_id"] == item_id:
                counts[ln["model_id"]] = counts.get(ln["model_id"], 0) + 1
    if not counts:
        return None
    main = max(counts.items(), key=lambda x: x[1])[0]
    by = {}
    for o in orders:
        for ln in o["lines"]:
            if ln["model_id"] == main:
                by.setdefault(sim.date_key(o["create_time"]), []).append(ln["discounted_price"])
    days = sorted(by)
    med = lambda a: sorted(a)[len(a) // 2]  # noqa: E731
    for i in range(len(days) - 1, 0, -1):
        cur, prev = med(by[days[i]]), med(by[days[i - 1]])
        if abs(cur - prev) / prev > 0.03:
            ago = round((now - sim.datetime.strptime(days[i], "%Y-%m-%d").replace(tzinfo=sim.TZ).timestamp()) / DAY)
            return {"date": days[i], "from": prev, "to": cur, "days_ago": ago}
    return None


def item_stats(data):
    now = data.now
    today, d7, d14, d28, d30 = (sim.date_key(now - k * DAY) for k in (0, 7, 14, 28, 30))
    rate = fee_rates(data)
    cost = costs()
    live = [o for o in data.orders if LIVE(o)]
    out = []
    for it in data.items:
        rows = [r for r in data.daily if r["item_id"] == it["item_id"]]
        fr = rate(it["item_id"])

        def mu(mid, since):
            return sum(ln["quantity"] for o in live if o["create_time"] >= since for ln in o["lines"] if ln["model_id"] == mid)
        models = []
        for m in it["models"]:
            u7, u14 = mu(m["model_id"], now - 7 * DAY), mu(m["model_id"], now - 14 * DAY)
            dr = max(u7 / 7, u14 / 14 * 0.9)
            c = cost.get(m["model_sku"])
            net = m["price"] * (1 - fr) - c["unit_cost"] - c["packaging"] if c else None
            models.append({"model_id": m["model_id"], "name": m["model_name"], "sku": m["model_sku"], "price": m["price"], "stock": m["stock"],
                           "units7": u7, "units14": u14, "daily_rate": dr, "days_cover": m["stock"] / dr if dr > 0 else math.inf,
                           "net": None if net is None else r2(net), "margin": None if net is None else net / m["price"]})
        weighted = sum(m["units14"] or 0.1 for m in models) or 1
        known = models and all(m["margin"] is not None for m in models)
        margin = sum(m["margin"] * (m["units14"] or 0.1) for m in models) / weighted if known else None
        npu = sum(m["net"] * (m["units14"] or 0.1) for m in models) / weighted if known else None
        views7, views_prev7 = _sum(rows, d7, today, "views"), _sum(rows, d14, d7, "views")
        orders7 = _sum(rows, d7, today, "orders")
        base_views, base_orders = _sum(rows, d28, d7, "views"), _sum(rows, d28, d7, "orders")
        units30 = _sum(rows, d30, today, "units")
        out.append({
            "item_id": it["item_id"], "name": it["item_name"], "sku": it["item_sku"], "status": it["item_status"], "boosted": it["boost_until"] > now,
            "description": it["description"] or "", "attributes": it["attributes"], "models": models,
            "price": min((m["price"] for m in models), default=0), "stock": sum(m["stock"] for m in models),
            "units7": _sum(rows, d7, today, "units"), "unitsPrev7": _sum(rows, d14, d7, "units"), "units30": units30,
            "views7": views7, "viewsPrev7": views_prev7, "orders7": orders7, "baseOrdersWeek": base_orders / 3,
            "cr7": orders7 / views7 if views7 else 0, "crBase": base_orders / base_views if base_views else 0,
            "revenue7": _sum(rows, d7, today, "sales"), "revenue30": _sum(rows, d30, today, "sales"),
            "fee_rate": fr, "margin": margin, "net_per_unit": npu, "rating": it["rating"], "rating_count": it["rating_count"],
            "series": [{"date": r["date"], "units": r["units"], "views": r["views"], "sales": r["sales"], "orders": r["orders"]} for r in sorted(rows, key=lambda r: r["date"]) if r["date"] > d30],
            "price_change": detect_price_change(it["item_id"], data.orders, now),
        })
    return out


def order_profit(o, e, cost):
    if not e or o["order_status"] == "CANCELLED":
        return {"revenue": 0, "fees": 0, "refund": 0, "cogs": 0, "profit": 0}
    cogs = sum(((cost.get(ln["model_sku"], {}).get("unit_cost") or ln["discounted_price"] * 0.45) + cost.get(ln["model_sku"], {}).get("packaging", 0)) * ln["quantity"]
               for ln in o["lines"])
    fees = e["commission"] + e["service"] + e["transaction"]
    return {"revenue": e["selling"], "fees": fees, "refund": e["refund"], "cogs": cogs, "profit": e["escrow"] - cogs}


def proposal(action_type, title, target, params, impact, rationale, evidence, risk, key, drafted_by="analysis", sensitive=False):
    return {"action_type": action_type, "title": title, "target": target, "params": params, "expected_impact": impact, "rationale": rationale,
            "evidence": evidence, "risk": risk, "dedupe_key": key, "drafted_by": drafted_by, "sensitive": sensitive}


def report(module, headline, summary, kpis, findings, n_props, tables, now, series=None):
    return {"module": module, "title": next(m["title"] for m in MODULES if m["id"] == module), "generated_at": time.time(), "sim_time": now,
            "headline": headline, "summary": summary, "summary_source": "rules", "kpis": kpis, "findings": findings, "proposals": n_props,
            "tables": tables, "series": series or {}}


# ---------------------------------------------------------------- module 1: orders & fulfilment

def run_orders(data, st):
    now, th = data.now, st["thresholds"]
    orders, perf = data.orders, data.perf
    by = lambda s: [o for o in orders if o["order_status"] == s]  # noqa: E731
    rts = sorted(by("READY_TO_SHIP"), key=lambda o: o["ship_by_date"])
    dl = th["ship_deadline_hours"] * HOUR
    overdue = [o for o in rts if o["ship_by_date"] < now]
    urgent = [o for o in rts if now <= o["ship_by_date"] < now + dl]
    later = [o for o in rts if o["ship_by_date"] - now >= dl]
    in_cancel, unpaid, processed, shipped = by("IN_CANCEL"), by("UNPAID"), by("PROCESSED"), by("SHIPPED")
    F, P = [], []
    hl = lambda o: hours_label((o["ship_by_date"] - now) / HOUR)  # noqa: E731
    th_h = int(th["ship_deadline_hours"])
    if overdue:
        F.append({"id": "overdue", "severity": "critical", "title": f"{len(overdue)} order{'s' if len(overdue) > 1 else ''} past ship-by date",
                  "detail": "Already counted as late shipments. Shopee auto-cancels unshipped orders 2 days after the ship-by date and adds a non-fulfilment penalty point for each.",
                  "evidence": [{"label": o["order_sn"], "value": f"{hl(o)} · {o['buyer_username']} · {rm(o['total_amount'])}"} for o in overdue[:6]]})
    if urgent:
        F.append({"id": "urgent", "severity": "warning", "title": f"{len(urgent)} order{'s' if len(urgent) > 1 else ''} must ship within {th_h}h",
                  "detail": f"Earliest deadline {hl(urgent[0])} ({urgent[0]['order_sn']}).",
                  "evidence": [{"label": o["order_sn"], "value": f"{hl(o)} · {o['shipping_carrier']}"} for o in urgent[:6]]})
    to_ship = overdue + urgent
    if to_ship:
        gmv = sum(o["total_amount"] for o in overdue)
        P.append(proposal("ship_orders", f"Arrange shipment for {len(to_ship)} order{'s' if len(to_ship) > 1 else ''} due within {th_h}h" + (f" ({len(overdue)} overdue)" if overdue else ""),
                          {"type": "orders", "id": ",".join(o["order_sn"] for o in to_ship), "label": f"{len(to_ship)} orders"},
                          {"order_sn_list": [o["order_sn"] for o in to_ship]},
                          f"Prevents {len(urgent)} additional late shipment(s)" + (f" and avoids up to {len(overdue)} auto-cancellation(s) (≈{rm(gmv)} GMV)" if overdue else "") +
                          f". Late-shipment rate is {perf['late_shipment_rate']}% (limit {perf['targets']['late_shipment_rate']}%).",
                          "These orders are paid and still waiting for shipment. Arranging pickup now books the next courier slot and generates tracking numbers.",
                          [{"label": o["order_sn"], "value": f"{hl(o)} · {o['shipping_carrier']} · {rm(o['total_amount'])}"} for o in to_ship[:8]], "low", "ship:urgent"))
    if later:
        P.append(proposal("ship_orders", f"Arrange shipment for {len(later)} other ready order{'s' if len(later) > 1 else ''}",
                          {"type": "orders", "id": ",".join(o["order_sn"] for o in later), "label": f"{len(later)} orders"},
                          {"order_sn_list": [o["order_sn"] for o in later]},
                          f"Keeps preparation time low (now {perf['preparation_time_days']} days, target < {perf['targets']['preparation_time_days']}) and gets parcels to buyers sooner.",
                          "Not urgent yet, but shipping early protects the preparation-time metric and reduces “when will you ship?” chats.",
                          [{"label": "Next deadline", "value": hl(later[0])}], "low", "ship:backlog"))
    for o in in_cancel:
        F.append({"id": f"cancel:{o['order_sn']}", "severity": "warning", "title": f"Buyer requested cancellation of {o['order_sn']}",
                  "detail": f"Reason: “{o['buyer_cancel_reason'] or 'not given'}”. Shopee auto-accepts if the seller does not respond within 24h; shipping is blocked meanwhile."})
        P.append(proposal("handle_buyer_cancellation", f"Accept cancellation request for {o['order_sn']}",
                          {"type": "order", "id": o["order_sn"], "label": f"{o['order_sn']} · {o['buyer_username']}"},
                          {"order_sn": o["order_sn"], "operation": "ACCEPT"},
                          f"Releases {sum(ln['quantity'] for ln in o['lines']) or 1} unit(s) back to stock and avoids a dispute; no penalty for buyer-initiated cancellations.",
                          f"The order has not shipped and the buyer gave a clear reason (“{o['buyer_cancel_reason']}”).",
                          [{"label": "Order value", "value": rm(o["total_amount"])}, {"label": "Items", "value": ", ".join(f"{short(ln['item_name'], 30)} ×{ln['quantity']}" for ln in o["lines"])}],
                          "low", f"cancel:{o['order_sn']}"))
    tracking = data.tracking([o["order_sn"] for o in shipped])
    problems = []
    for o in shipped:
        tr = tracking.get(o["order_sn"])
        if not tr:
            continue
        last = tr[-1]
        since = (now - last["ts"]) / HOUR
        base = {"order_sn": o["order_sn"], "buyer_user_id": o["buyer_user_id"], "buyer": o["buyer_username"], "name": o["recipient"].get("name") or o["buyer_username"],
                "carrier": o["shipping_carrier"], "last_event": last["description"], "location": last["location"], "value": o["total_amount"]}
        if last["logistics_status"] == "LOGISTICS_DELIVERY_FAILED":
            problems.append({**base, "kind": "failed", "hours": since})
        elif since > th["stuck_tracking_hours"]:
            problems.append({**base, "kind": "stuck", "hours": since})
        elif o["pickup_time"] and (now - o["pickup_time"]) / DAY > 6:
            problems.append({**base, "kind": "long_transit", "hours": (now - o["pickup_time"]) / HOUR})
    for o in processed:
        if o["ship_time"] and (now - o["ship_time"]) / HOUR > 24:
            problems.append({"order_sn": o["order_sn"], "buyer_user_id": o["buyer_user_id"], "buyer": o["buyer_username"], "name": o["recipient"].get("name", ""),
                             "carrier": o["shipping_carrier"], "kind": "pickup_delay", "hours": (now - o["ship_time"]) / HOUR, "last_event": "Awaiting courier pickup",
                             "location": "Shah Alam", "value": o["total_amount"]})
    stuck = sorted([p for p in problems if p["kind"] == "stuck"], key=lambda p: -p["hours"])
    if stuck:
        F.append({"id": "stuck", "severity": "critical" if any(s["hours"] > 96 for s in stuck) else "warning",
                  "title": f"{len(stuck)} parcel{'s' if len(stuck) > 1 else ''} with no tracking update for >{int(th['stuck_tracking_hours'])}h",
                  "detail": f"Longest: {stuck[0]['order_sn']} ({stuck[0]['carrier']}) silent for {stuck[0]['hours'] / 24:.1f} days at “{stuck[0]['location']}”. Stuck parcels drive “where is my order” chats, 1-star delivery reviews and lost-parcel refunds.",
                  "evidence": [{"label": s["order_sn"], "value": f"{s['carrier']} · {s['hours'] / 24:.1f}d · {s['location']}"} for s in stuck[:6]],
                  "recommendation": "Raise a courier ticket for parcels silent > 4 days and proactively update the buyers."})
    failed = [p for p in problems if p["kind"] == "failed"]
    if failed:
        F.append({"id": "failed", "severity": "warning", "title": f"{len(failed)} failed delivery attempt{'s' if len(failed) > 1 else ''}",
                  "detail": "Courier will re-attempt; buyers may need to confirm availability.", "evidence": [{"label": f["order_sn"], "value": f"{f['carrier']} · {f['location']}"} for f in failed]})
    pd = [p for p in problems if p["kind"] == "pickup_delay"]
    if pd:
        F.append({"id": "pickup", "severity": "warning", "title": f"{len(pd)} arranged shipment{'s' if len(pd) > 1 else ''} not picked up after 24h",
                  "detail": "Check the courier pickup booking or drop the parcels off.", "evidence": [{"label": p["order_sn"], "value": f"{p['carrier']} · {p['hours']:.0f}h"} for p in pd[:5]]})
    carriers = {}
    stuck_sns = {s["order_sn"] for s in stuck}
    for o in shipped:
        c = carriers.setdefault(o["shipping_carrier"], {"inflight": 0, "stuck": 0})
        c["inflight"] += 1
        c["stuck"] += o["order_sn"] in stuck_sns
    total_rate = len(stuck) / len(shipped) if shipped else 0
    for name, c in carriers.items():
        if c["inflight"] >= 5 and c["stuck"] / c["inflight"] > max(0.15, total_rate * 1.8):
            F.append({"id": f"carrier:{name}", "severity": "warning", "title": f"{name} has an unusual delay rate",
                      "detail": f"{c['stuck']} of {c['inflight']} in-flight {name} parcels ({pct(c['stuck'] / c['inflight'], 0)}) are stuck vs {pct(total_rate, 0)} across all couriers.",
                      "recommendation": f"Consider disabling {name} as a shipping option until the hub congestion clears."})
    for n in [s for s in stuck if s["hours"] > 72][:5]:
        text = (f"Hi {first_name(n['name'])}, this is UrbanNest 😊 We noticed your parcel {n['order_sn']} with {n['carrier']} hasn't had a tracking update for "
                f"{round(n['hours'] / 24)} days (last seen at {n['location']}). We're sorry for the wait — we have raised a ticket with {n['carrier']} and will update you within 24 hours. 🙏")
        P.append(proposal("send_chat_message", f"Proactively update {n['buyer']} about delayed parcel {n['order_sn']}",
                          {"type": "order", "id": n["order_sn"], "label": f"{n['order_sn']} · {n['buyer']}"},
                          {"to_id": n["buyer_user_id"], "conversation_id": None, "text": text, "category": "shipping_delay", "reply_to_message_id": None},
                          "Pre-empts a “where is my parcel” complaint and a likely low delivery rating; keeps chat response metrics healthy.",
                          f"No tracking movement for {n['hours'] / 24:.1f} days with {n['carrier']}.",
                          [{"label": "Last event", "value": n["last_event"]}, {"label": "Location", "value": n["location"]}], "low", f"delaymsg:{n['order_sn']}", "rules"))
    lost = [o for o in orders if o["order_status"] == "CANCELLED" and o["cancel_reason"] == "LOGISTICS_LOST" and o["update_time"] > now - 7 * DAY]
    if lost:
        F.append({"id": "lost", "severity": "info", "title": f"{len(lost)} parcel{'s' if len(lost) > 1 else ''} lost in transit this week",
                  "detail": "Shopee refunded the buyers; consider filing courier claims for the goods value.", "evidence": [{"label": o["order_sn"], "value": f"{o['shipping_carrier']} · {rm(o['total_amount'])}"} for o in lost]})
    auto_c = [o for o in orders if o["cancel_reason"] == "SELLER_DID_NOT_SHIP" and o["update_time"] > now - 7 * DAY]
    if auto_c:
        F.append({"id": "autocancel", "severity": "critical", "title": f"{len(auto_c)} order{'s' if len(auto_c) > 1 else ''} auto-cancelled for not shipping",
                  "detail": "Each added a penalty point and lost the sale.", "evidence": [{"label": o["order_sn"], "value": rm(o["total_amount"])} for o in auto_c]})
    if unpaid:
        F.append({"id": "unpaid", "severity": "info", "title": f"{len(unpaid)} unpaid order{'s' if len(unpaid) > 1 else ''}", "detail": "Shopee auto-cancels unpaid orders after 24h; stock is reserved meanwhile."})
    if not overdue and not urgent and not stuck:
        F.append({"id": "healthy", "severity": "positive", "title": "Fulfilment on track", "detail": "No overdue or at-risk shipments right now."})
    summary = (f"{len(to_ship)} orders need shipping within {th_h}h" + (f", including {len(overdue)} already overdue" if overdue else "") + ". "
               + (f"{len(stuck)} parcels have stalled tracking (longest {stuck[0]['hours'] / 24:.1f} days with {stuck[0]['carrier']}). " if stuck else "")
               + (f"{len(in_cancel)} buyer cancellation request(s) await a response." if in_cancel else "")) if to_ship else \
              (f"Fulfilment is on track: {len(rts)} orders queued, none at risk. " + (f"{len(stuck)} parcels have stalled tracking." if stuck else ""))
    kind_label = {"stuck": "Tracking stalled", "failed": "Delivery failed", "pickup_delay": "Pickup delayed", "long_transit": "Long transit"}
    attention = ([{"order_sn": o["order_sn"], "buyer": o["buyer_username"], "status": o["order_status"], "issue": "Overdue", "detail": hl(o), "carrier": o["shipping_carrier"], "value": o["total_amount"]} for o in overdue]
                 + [{"order_sn": o["order_sn"], "buyer": o["buyer_username"], "status": o["order_status"], "issue": "Ship soon", "detail": hl(o), "carrier": o["shipping_carrier"], "value": o["total_amount"]} for o in urgent]
                 + [{"order_sn": o["order_sn"], "buyer": o["buyer_username"], "status": o["order_status"], "issue": "Cancellation request", "detail": o["buyer_cancel_reason"] or "", "carrier": o["shipping_carrier"], "value": o["total_amount"]} for o in in_cancel]
                 + [{"order_sn": p["order_sn"], "buyer": p["buyer"], "status": "PROCESSED" if p["kind"] == "pickup_delay" else "SHIPPED", "issue": kind_label[p["kind"]],
                     "detail": f"{p['hours'] / 24:.1f}d · {p['location']}", "carrier": p["carrier"], "value": p["value"]} for p in problems])
    statuses = ["UNPAID", "READY_TO_SHIP", "PROCESSED", "SHIPPED", "TO_CONFIRM_RECEIVE", "COMPLETED", "IN_CANCEL", "TO_RETURN", "CANCELLED"]
    rep = report("orders", f"{len(overdue)} overdue · {len(urgent)} due soon" if overdue else f"{len(urgent)} orders due within {th_h}h" if urgent else "On track",
                 summary.strip(), [
                     {"label": "To ship", "value": str(len(rts)), "tone": "warn" if len(rts) > 40 else "neutral"},
                     {"label": "Overdue", "value": str(len(overdue)), "tone": "bad" if overdue else "good"},
                     {"label": f"Due < {th_h}h", "value": str(len(urgent)), "tone": "warn" if urgent else "good"},
                     {"label": "In transit", "value": str(len(shipped))},
                     {"label": "Stuck parcels", "value": str(len(stuck)), "tone": "warn" if stuck else "good"},
                     {"label": "Late shipment rate", "value": f"{perf['late_shipment_rate']}%", "tone": "bad" if perf["late_shipment_rate"] >= perf["targets"]["late_shipment_rate"] else "good"}],
                 sort_findings(F), len(P), {"attention": attention, "status": [{"status": s, "count": len(by(s))} for s in statuses],
                                             "carriers": [{"carrier": k, "in_flight": v["inflight"], "stuck": v["stuck"]} for k, v in carriers.items()]}, now)
    return rep, P


# ---------------------------------------------------------------- module 2: products & inventory

def _price_impact(s, new, el):
    p0, q0 = s["price"], max(s["units7"], 0.5)
    uc = p0 * (1 - s["fee_rate"]) - s["net_per_unit"] if s["net_per_unit"] is not None else p0 * 0.45
    q1 = q0 * (p0 / new) ** el
    return {"q0": q0, "q1": q1, "profit0": q0 * (p0 * (1 - s["fee_rate"]) - uc), "profit1": q1 * (new * (1 - s["fee_rate"]) - uc),
            "margin1": (new * (1 - s["fee_rate"]) - uc) / new, "unitCost": uc}


def _price_list(s, factor, absolute=None):
    same = all(m["price"] == s["models"][0]["price"] for m in s["models"])
    return [{"model_id": m["model_id"], "original_price": absolute if absolute is not None and same else charm(m["price"] * factor)} for m in s["models"]]


def _fallback_listing(s):
    attrs = list(s["attributes"].items())
    variants = [m["name"] for m in s["models"] if m["name"] != "Default"]
    words = [w for w in [s["name"].strip(), *[v for _, v in attrs[:3]], " ".join(variants)] if w]
    title = re.sub(r"\s+", " ", " | ".join(words))
    if len(title) > 120:
        title = re.sub(r"\s\S*$", "", title[:117]) + "…"
    lines = [f"✨ {s['name'].strip()}", "", *[f"✔ {k}: {v}" for k, v in attrs], f"✔ Available options: {' / '.join(variants)}" if variants else "", "",
             "📦 Ready stock, ships from Shah Alam within 24 hours.", "💬 Chat with us for any questions before ordering!"]
    desc = "\n".join(ln for i, ln in enumerate(lines) if ln or (i and lines[i - 1]))
    return {"item_name": title if len(title) >= 10 else f"{title} – UrbanNest", "description": desc,
            "changes": ["Added key attributes and variations to the title", "Structured description with specifications"]}


def run_products(data, st):
    now, th, lead = data.now, st["thresholds"], st["lead_time_days"]
    stats = [s for s in item_stats(data) if s["status"] == "NORMAL" or s["units30"] > 0]
    live = [s for s in stats if s["status"] == "NORMAL"]
    crs = sorted(s["cr7"] for s in live if s["views7"] > 100)
    med = crs[len(crs) // 2] if crs else 0
    F, P = [], []
    for s in live:
        target = {"type": "item", "id": str(s["item_id"]), "label": short(s["name"], 50)}
        low = [m for m in s["models"] if m["daily_rate"] > 0.2 and m["days_cover"] < lead + 3]
        out = [m for m in s["models"] if m["stock"] == 0 and m["units14"] > 0]
        risky = list({m["model_id"]: m for m in low + out}.values())
        if risky:
            worst = min(risky, key=lambda m: m["days_cover"])
            F.append({"id": f"stock:{s['item_id']}", "severity": "critical" if out or worst["days_cover"] < 3 else "warning",
                      "title": f"{short(s['name'], 40)}: {len(out)} variation(s) sold out" if out else f"{short(s['name'], 40)} will sell out in ~{worst['days_cover']:.1f} days",
                      "detail": f"Selling {s['units7'] / 7:.1f} units/day; supplier lead time is {lead} days. {rm(s['revenue7'])} weekly revenue at risk.",
                      "evidence": [{"label": m["name"], "value": f"{m['stock']} left · {m['daily_rate']:.1f}/day · " + (f"{m['days_cover']:.1f}d cover" if math.isfinite(m['days_cover']) else "no sales")} for m in risky],
                      "target": target})
            lst = [{"model_id": m["model_id"], "name": m["name"], "add": max(10, math.ceil((math.ceil(m["daily_rate"] * (lead + 21)) - m["stock"]) / 10) * 10)} for m in risky]
            pw = s["net_per_unit"] * s["units7"] if s["net_per_unit"] is not None else None
            P.append(proposal("update_stock", f"Restock {short(s['name'], 40)} (+{sum(x['add'] for x in lst)} units)", target, {"item_id": s["item_id"], "stock_list": lst},
                              f"Covers ~{lead + 21} days of demand and avoids a stock-out in {worst['days_cover']:.1f} days, protecting ≈{rm(s['revenue7'])}/week revenue" +
                              (f" (≈{rm(pw)}/week profit)" if pw is not None else "") + " and the listing's search ranking.",
                              f"Approve once the supplier delivery is received – this adds the new units on top of live stock. Reorder quantity = daily run-rate × (lead time {lead}d + 21d safety) − current stock.",
                              [{"label": x["name"], "value": f"{next(m['stock'] for m in s['models'] if m['model_id'] == x['model_id'])} in stock → +{x['add']}"} for x in lst], "medium", f"restock:{s['item_id']}"))
        change = (s["orders7"] - s["baseOrdersWeek"]) / s["baseOrdersWeek"] if s["baseOrdersWeek"] >= 6 else 0
        vchange = (s["views7"] - s["viewsPrev7"]) / s["viewsPrev7"] if s["viewsPrev7"] else 0
        crchange = (s["cr7"] - s["crBase"]) / s["crBase"] if s["crBase"] else 0
        pval = poisson_cdf(s["orders7"], s["baseOrdersWeek"])
        falling = change <= -th["sales_drop_pct"] / 100 and pval < 0.02
        if falling:
            driver = "traffic" if vchange < -0.2 and abs(crchange) < 0.25 else "conversion" if crchange <= -0.25 else "mixed"
            F.append({"id": f"falling:{s['item_id']}", "severity": "warning", "title": f"{short(s['name'], 40)} orders down {spct(change)} vs 3-week average",
                      "detail": f"{s['orders7']} orders in 7 days vs ~{s['baseOrdersWeek']:.0f}/week before (p = {pval:.3f}). Views {spct(vchange)}, conversion {pct(s['crBase'], 2)} → {pct(s['cr7'], 2)} ({spct(crchange)}). Primary driver: " +
                      {"traffic": "falling traffic (search ranking / competition)", "conversion": "falling conversion (price, reviews or listing)", "mixed": "both traffic and conversion"}[driver] + ".",
                      "target": target})
        if s["margin"] is None:
            continue
        pc = s["price_change"]
        if pc and pc["to"] > pc["from"] and pc["days_ago"] <= 21:
            d14 = (sim.datetime.strptime(pc["date"], "%Y-%m-%d") - sim.timedelta(days=14)).strftime("%Y-%m-%d")
            before = [r for r in s["series"] if d14 <= r["date"] < pc["date"]]
            after = [r for r in s["series"] if r["date"] >= pc["date"]]
            crb = sum(r["orders"] for r in before) / max(1, sum(r["views"] for r in before))
            cra = sum(r["orders"] for r in after) / max(1, sum(r["views"] for r in after))
            if crb > 0 and cra < crb * 0.75:
                el = max(0.5, math.log(crb / max(cra, 0.0001)) / math.log(pc["to"] / pc["from"]))
                rev = _price_impact(s, pc["from"], el)
                F.append({"id": f"pricehurt:{s['item_id']}", "severity": "warning", "title": f"Price increase on {short(s['name'], 36)} cut conversion {spct(cra / crb - 1)}",
                          "detail": f"Price raised {rm(pc['from'])} → {rm(pc['to'])} on {pc['date']}. Conversion {pct(crb, 2)} → {pct(cra, 2)} (implied price elasticity ≈ {el:.1f}).", "target": target})
                if rev["profit1"] > rev["profit0"]:
                    P.append(proposal("update_price", f"Revert {short(s['name'], 36)} price to {rm(pc['from'])}", target,
                                      {"item_id": s["item_id"], "price_list": _price_list(s, pc["from"] / pc["to"], pc["from"]), "previous": [{"model_id": m["model_id"], "price": m["price"]} for m in s["models"]]},
                                      f"Estimated weekly units {rev['q0']:.0f} → {rev['q1']:.0f} and weekly profit {rm(rev['profit0'])} → {rm(rev['profit1'])} ({spct(rev['profit1'] / max(rev['profit0'], 0.01) - 1)}). Margin {pct(s['margin'])} → {pct(rev['margin1'])}.",
                                      f"Demand for this item is price-sensitive (elasticity ≈ {el:.1f} measured from the {pc['date']} price change). The higher price lost more volume than it gained per unit.",
                                      [{"label": "Conversion before", "value": pct(crb, 2)}, {"label": "Conversion after", "value": pct(cra, 2)},
                                       {"label": "Units last 7d / prior 7d", "value": f"{s['units7']} / {s['unitsPrev7']}"}, {"label": "Unit cost incl. packaging", "value": rm(rev["unitCost"])}],
                                      "medium", f"price:{s['item_id']}"))
                continue
        if s["margin"] < th["min_margin"]:
            unit = s["price"] * (1 - s["fee_rate"]) - (s["net_per_unit"] or 0)
            tp = unit / (1 - s["fee_rate"] - th["target_margin"])
            newp = charm(min(tp, s["price"] * (1 + th["max_price_change_pct"] / 100)))
            imp = _price_impact(s, newp, 1.0)
            F.append({"id": f"margin:{s['item_id']}", "severity": "critical" if s["margin"] < 0 else "warning", "title": f"{short(s['name'], 40)} margin is {pct(s['margin'])} after Shopee fees",
                      "detail": f"Price {rm(s['price'])}, fees {pct(s['fee_rate'])} ({rm(s['price'] * s['fee_rate'])}), cost+packaging {rm(unit)} → {rm(s['net_per_unit'] or 0)} per unit on {s['units7']} units/week.", "target": target})
            P.append(proposal("update_price", f"Raise {short(s['name'], 36)} price {rm(s['price'])} → {rm(newp)}", target,
                              {"item_id": s["item_id"], "price_list": _price_list(s, newp / s["price"], newp), "previous": [{"model_id": m["model_id"], "price": m["price"]} for m in s["models"]]},
                              f"Margin {pct(s['margin'])} → {pct(imp['margin1'])}. Even if volume falls {pct(1 - imp['q1'] / imp['q0'], 0)} (unit-elastic assumption), weekly profit goes {rm(imp['profit0'])} → {rm(imp['profit1'])}.",
                              f"Below the {pct(th['min_margin'], 0)} minimum margin. Raise is capped at {th['max_price_change_pct']:.0f}% per step; target margin is {pct(th['target_margin'], 0)}. Conversion is {pct(s['cr7'], 2)} vs shop median {pct(med, 2)}.",
                              [{"label": "Current net / unit", "value": rm(s["net_per_unit"] or 0)}, {"label": "Fee rate (from payout data)", "value": pct(s["fee_rate"])},
                               {"label": "Conversion vs median", "value": f"{pct(s['cr7'], 2)} vs {pct(med, 2)}"}], "medium", f"price:{s['item_id']}"))
            continue
        if falling and vchange < -0.2 and s["margin"] > th["target_margin"] + 0.05:
            newp = charm(s["price"] * 0.9)
            imp = _price_impact(s, newp, 1.6)
            if imp["profit1"] > imp["profit0"] * 0.97:
                P.append(proposal("update_price", f"Cut {short(s['name'], 36)} price {rm(s['price'])} → {rm(newp)} to win back traffic", target,
                                  {"item_id": s["item_id"], "price_list": _price_list(s, newp / s["price"], newp), "previous": [{"model_id": m["model_id"], "price": m["price"]} for m in s["models"]]},
                                  f"Assuming elasticity ≈1.6: weekly units {imp['q0']:.0f} → {imp['q1']:.0f}, weekly profit {rm(imp['profit0'])} → {rm(imp['profit1'])}; margin stays healthy at {pct(imp['margin1'])}.",
                                  f"Traffic fell {spct(vchange)} while conversion held – consistent with a cheaper competitor. Margin ({pct(s['margin'])}) leaves room for a 10% cut. Re-check competitor prices before approving.",
                                  [{"label": "Units 7d vs prior", "value": f"{s['units7']} vs {s['unitsPrev7']}"}, {"label": "Views 7d vs prior", "value": f"{s['views7']} vs {s['viewsPrev7']}"}],
                                  "medium", f"price:{s['item_id']}"))
    for s in [s for s in live if len(s["name"].strip()) < 25 or len(s["description"].strip()) < 80][:3]:
        issues = []
        if len(s["name"].strip()) < 25:
            issues.append(f"title is only {len(s['name'].strip())} characters (no searchable keywords)")
        if len(s["description"].strip()) < 150:
            issues.append(f"description is only {len(s['description'].strip())} characters")
        if s["views7"] >= 150 and med and s["cr7"] < med * 0.65:
            issues.append(f"conversion {pct(s['cr7'], 2)} vs shop median {pct(med, 2)}")
        lst = _fallback_listing(s)
        lift = min(med / s["cr7"], 1.6) if med and s["cr7"] else 1.3
        target = {"type": "item", "id": str(s["item_id"]), "label": short(s["name"], 50)}
        F.append({"id": f"listing:{s['item_id']}", "severity": "warning", "title": f"Weak listing: {short(s['name'], 40)}",
                  "detail": f"{'; '.join(issues)}. {s['views7']} views last 7 days are converting poorly.", "target": target})
        P.append(proposal("update_item", f"Rewrite listing for “{short(s['name'], 40)}”", target, {"item_id": s["item_id"], "item_name": lst["item_name"], "description": lst["description"]},
                          f"Better search matching and buyer confidence. If conversion moves toward the shop median ({pct(med, 2)}), weekly orders could rise from {s['orders7']} to ~{round(s['orders7'] * lift)}.",
                          f"Issues: {'; '.join(issues)}. Changes: {'; '.join(lst['changes'])}.",
                          [{"label": "Current title", "value": s["name"]}, {"label": "Current description", "value": s["description"][:160] or "(empty)"},
                           {"label": "Views / conversion (7d)", "value": f"{s['views7']} / {pct(s['cr7'], 2)}"}], "low", f"listing:{s['item_id']}", "rules"))
    out_n = sum(1 for s in live for m in s["models"] if m["stock"] == 0)
    low_n = sum(1 for s in live for m in s["models"] if m["daily_rate"] > 0.2 and m["days_cover"] < lead + 3)
    known = [s for s in live if s["margin"] is not None]
    avg_m = sum(s["margin"] * s["revenue30"] for s in known) / max(1, sum(s["revenue30"] for s in known))
    falling_n = sum(1 for f in F if f["id"].startswith("falling:"))
    if not F:
        F.append({"id": "healthy", "severity": "positive", "title": "Catalogue healthy", "detail": "No stock, pricing or listing risks detected."})
    n_price = sum(1 for p in P if p["action_type"] == "update_price")
    summary = " ".join(x for x in [f"{low_n + out_n} variations need restocking." if low_n + out_n else "", f"{falling_n} product(s) show falling sales." if falling_n else "",
                                   f"{n_price} price change(s) recommended." if n_price else "", f"{sum(1 for p in P if p['action_type'] == 'update_item')} weak listing(s) drafted for improvement." if any(p["action_type"] == "update_item" for p in P) else ""] if x) or "Catalogue healthy."
    rep = report("products", f"{low_n + out_n} stock risks · {len(P)} actions" if low_n + out_n else f"{len(P)} recommendations", summary, [
        {"label": "Live products", "value": str(len(live))}, {"label": "Stock-out risk", "value": str(low_n), "tone": "warn" if low_n else "good"},
        {"label": "Sold out", "value": str(out_n), "tone": "bad" if out_n else "good"}, {"label": "Avg margin", "value": pct(avg_m), "tone": "warn" if avg_m < th["target_margin"] else "good"},
        {"label": "Falling sales", "value": str(falling_n), "tone": "warn" if falling_n else "good"}, {"label": "Median conversion", "value": pct(med, 2)}],
        sort_findings(F), len(P), {"products": sorted([{
            "item_id": s["item_id"], "name": s["name"], "price": s["price"], "stock": s["stock"],
            "days_cover": min((r2(m["days_cover"]) if math.isfinite(m["days_cover"]) else 999 for m in s["models"]), default=999), "units7": s["units7"], "units_prev7": s["unitsPrev7"],
            "views7": s["views7"], "cr7": r2(s["cr7"] * 100), "margin": None if s["margin"] is None else r2(s["margin"] * 100),
            "net_per_unit": None if s["net_per_unit"] is None else r2(s["net_per_unit"]), "fee_rate": r2(s["fee_rate"] * 100), "rating": s["rating"]} for s in live], key=lambda r: -r["units7"])}, now)
    return rep, P


# ---------------------------------------------------------------- module 3: review intelligence

THEMES = ["quality", "packaging", "sizing", "delivery", "accuracy", "value", "service"]
KEYWORDS = {
    "packaging": r"packaging (very |so |too )?thin|thin (layer|packaging)|poor packaging|improve (packing|packaging)|pack(ing)? (fragile|properly)|packing (terlalu )?nipis|box (was )?crush|crushed|dented|arrived (cracked|broken|damaged)|received (broken|cracked|damaged)|pecah|chipped|cracked|crack\b",
    "quality": r"quality not good|poor quality|bad quality|low quality|quality (very )?bad|rosak|spoil|defect|stopped working|stop working|not working|cannot (charge|work)|battery (drains|cannot|die|habis)|cepat habis|broke after|not durable|disconnect|no sound|shrink|leaks?\b|pilling|fabric thin|black dots|tak tahan|cracked after",
    "sizing": r"size (runs|not|tak)|runs small|too small|tight|kecik|kecil|fits like|not the oversized|tak oversized|size chart (not|wrong)|ukuran tak|doesn.t fit|does not fit|tak muat",
    "delivery": r"delivery (very |so )?slow|slow delivery|lambat|parcel stuck|stuck for|courier late|\blate\b|took \d+ days|waited (more|so|very)",
    "accuracy": r"different from|wrong (item|model|colour|color)|received wrong|not same|colour (not|more)|than picture|from picture|from photo",
    "value": r"too expensive|not worth|cheaper elsewhere|price increased|mahal sangat",
    "service": r"seller slow|no response|reply my chat|no reply",
}
PLAYBOOK = {
    "packaging": "Upgrade protective packaging for this SKU (double-wall carton, two layers of bubble wrap, corner protectors, FRAGILE sticker) and photograph packed parcels for dispute evidence.",
    "quality": "Quarantine the current stock batch, QC-test a sample, and raise a defect claim with the supplier; consider pausing the listing until QC passes.",
    "sizing": "Correct the size chart (measure actual garments), add a clear “runs small – size up” note in the title/description, and add model height/weight to photos.",
    "delivery": "Review courier performance for affected parcels; steer buyers to the most reliable channel and proactively message buyers when tracking stalls.",
    "accuracy": "Re-shoot product photos under neutral lighting, state the exact material/colour in the description, and double-check variation picking at packing.",
    "value": "Benchmark competitor prices and either justify the price in the listing (specs, warranty, bundle) or adjust it.",
    "service": "Tighten chat response SLAs (target < 1h) and use saved replies for common questions.",
}


def label_review(c):
    text = c.get("comment") or ""
    themes = [t for t in THEMES if re.search(KEYWORDS[t], text, re.I)]
    stars = c["rating_star"]
    sent = "positive" if stars >= 4 else "neutral" if stars == 3 else "negative"
    if sent == "positive" and themes and stars == 4:
        sent = "neutral"
    return {"sentiment": sent, "themes": [] if sent == "positive" else themes}


def run_reviews(data, st):
    now = data.now
    comments, items, returns, daily = data.comments, data.items, data.returns, data.daily
    labels = {c["comment_id"]: label_review(c) for c in comments}
    name = {i["item_id"]: i["item_name"] for i in items}
    F, P = [], []
    r30 = [c for c in comments if c["create_time"] > now - 30 * DAY]
    dist = {"positive": 0, "neutral": 0, "negative": 0}
    for c in r30:
        dist[labels[c["comment_id"]]["sentiment"]] += 1
    per = []
    for it in items:
        cs = [c for c in comments if c["item_id"] == it["item_id"]]
        recent = [c for c in cs if c["create_time"] > now - 14 * DAY]
        base = [c for c in cs if c["create_time"] <= now - 14 * DAY]
        c30 = [c for c in cs if c["create_time"] > now - 30 * DAY]
        avg = lambda a: sum(c["rating_star"] for c in a) / len(a) if a else 0  # noqa: E731
        tc = {}
        for c in c30:
            for t in labels[c["comment_id"]]["themes"]:
                tc.setdefault(t, []).append(c)
        per.append({"item_id": it["item_id"], "name": it["item_name"], "recentAvg": avg(recent), "recentN": len(recent), "baseAvg": avg(base), "baseN": len(base),
                    "recent": recent, "negShare": sum(1 for c in c30 if labels[c["comment_id"]]["sentiment"] == "negative") / len(c30) if c30 else 0, "n30": len(c30),
                    "themes": sorted([{"theme": t, "count": len(lst), "share": len(lst) / max(1, len(c30)),
                                       "quotes": [f"{c['rating_star']}★ “{c['comment'][:140]}”" for c in lst if c["comment"]][:3]} for t, lst in tc.items()], key=lambda x: -x["count"]),
                    "refunds30": sum(r["refund_amount"] for r in returns if r["item_id"] == it["item_id"] and r["create_time"] > now - 30 * DAY and r["status"] == "REFUND_PAID")})
    for r in per:
        drop = r["baseAvg"] - r["recentAvg"]
        n = r["recentN"]
        sd = math.sqrt(sum((c["rating_star"] - r["recentAvg"]) ** 2 for c in r["recent"]) / max(1, n - 1)) or 1
        z = drop / (sd / math.sqrt(max(1, n)))
        if n >= 6 and r["baseN"] >= 10 and drop >= st["thresholds"]["rating_drop"] and (z >= 2 or n >= 20):
            F.append({"id": f"rating:{r['item_id']}", "severity": "critical" if drop >= 0.7 else "warning", "title": f"Rating deteriorating: {short(r['name'], 40)}",
                      "detail": f"Last 14 days {r['recentAvg']:.2f}★ ({n} reviews) vs {r['baseAvg']:.2f}★ before ({r['baseN']}). Negative share last 30d: {pct(r['negShare'], 0)}.",
                      "evidence": [{"label": t["theme"], "value": q} for t in r["themes"][:2] for q in t["quotes"][:2]],
                      "target": {"type": "item", "id": str(r["item_id"]), "label": short(r["name"], 50)}})
    recurring = sorted([(r, t) for r in per for t in r["themes"] if t["count"] >= 4 and t["share"] >= 0.1], key=lambda x: -x[1]["count"])
    item_by = {i["item_id"]: i for i in items}
    for r, t in recurring[:8]:
        target = {"type": "item", "id": str(r["item_id"]), "label": short(r["name"], 50)}
        F.append({"id": f"theme:{r['item_id']}:{t['theme']}", "severity": "critical" if t["share"] >= 0.2 or (t["theme"] == "quality" and t["share"] >= 0.15) else "warning",
                  "title": f"Recurring {t['theme']} complaints: {short(r['name'], 38)}",
                  "detail": f"{t['count']} of {r['n30']} reviews in 30 days ({pct(t['share'], 0)}) mention {t['theme']}." + (f" {rm(r['refunds30'])} refunded on this product in 30 days." if r["refunds30"] else ""),
                  "evidence": [{"label": f"Review {i + 1}", "value": q} for i, q in enumerate(t["quotes"])], "recommendation": PLAYBOOK[t["theme"]], "target": target})
        if t["theme"] == "sizing":
            it = item_by[r["item_id"]]
            desc = it["description"] or ""
            if "SIZING TIP" not in desc and not re.search(r"size up", desc, re.I):
                P.append(proposal("update_item", f"Add sizing guidance to “{short(r['name'], 36)}”", target,
                                  {"item_id": r["item_id"], "description": "📏 SIZING TIP: Many buyers find this fits about ONE SIZE SMALLER than expected. We recommend sizing up (e.g. order L if you usually wear M). Chat us your height/weight for advice!\n\n" + desc},
                                  f"Addresses the #1 complaint ({t['count']} sizing reviews / 30d). Fewer wrong-size orders should cut sizing returns and lift the rating back toward {r['baseAvg']:.1f}★.",
                                  "Buyers repeatedly report the garment runs small; setting expectations in the listing is the fastest fix while the size chart is re-measured.",
                                  [{"label": f"Review {i + 1}", "value": q} for i, q in enumerate(t["quotes"])], "low", f"sizefix:{r['item_id']}", "rules"))
        if t["theme"] == "quality" and r["recentN"] >= 8 and r["negShare"] >= 0.3 and r["baseAvg"] - r["recentAvg"] >= 0.6:
            d7 = sim.date_key(now - 7 * DAY)
            wu = sum(d["units"] for d in daily if d["item_id"] == r["item_id"] and d["date"] >= d7)
            ws_ = sum(d["sales"] for d in daily if d["item_id"] == r["item_id"] and d["date"] >= d7)
            P.append(proposal("unlist_item", f"Pause listing “{short(r['name'], 36)}” pending batch QC", target, {"item_id": r["item_id"], "unlist": True},
                              f"Stops ~{wu} potentially defective units/week reaching buyers (≈{pct(t['share'], 0)} quality complaint rate), protecting shop rating and avoiding refunds ({rm(r['refunds30'])} already in 30d). Cost: ≈{rm(ws_)}/week revenue while paused.",
                              f"Rating fell {r['baseAvg']:.2f}★ → {r['recentAvg']:.2f}★ in 14 days with {t['count']} quality complaints – consistent with a defective stock batch.",
                              [{"label": f"Review {i + 1}", "value": q} for i, q in enumerate(t["quotes"])], "high", f"pause:{r['item_id']}", "analysis", True))
    to_reply = [c for c in comments if c["rating_star"] <= 3 and not c["reply"] and c["create_time"] > now - 14 * DAY][:10]
    replies = {"packaging": "We are truly sorry your item arrived damaged 🙏 We have upgraded our packaging for fragile items. Please chat with us so we can make this right for you.",
               "sizing": "Sorry the size did not fit as expected! We are updating our size chart to be more accurate. Please chat with us and we will help you with an exchange option.",
               "quality": "We are very sorry about the product issue. Our team is checking this batch with the supplier. Please chat with us with your order number so we can help you quickly.",
               "delivery": "Sorry for the delivery delay 🙏 We have escalated this with the courier to improve. Thank you for your patience and support!"}
    for c in to_reply:
        lab = labels[c["comment_id"]]
        theme = lab["themes"][0] if lab["themes"] else None
        text = replies.get(theme, "Thank you for your honest feedback. We are sorry it did not meet your expectations – please chat with us so we can help.")
        P.append(proposal("reply_comment", f"Reply to {c['rating_star']}★ review on “{short(name.get(c['item_id'], ''), 32)}”",
                          {"type": "comment", "id": str(c["comment_id"]), "label": f"{c['buyer_username']} · {c['rating_star']}★"},
                          {"comment_id": c["comment_id"], "comment": text, "review": c["comment"], "stars": c["rating_star"]},
                          "Public replies to negative reviews reassure future shoppers reading the reviews and show the issue is being handled.",
                          f"{lab['sentiment']} review" + (f" about {', '.join(lab['themes'])}" if lab["themes"] else "") + f", unanswered for {(now - c['create_time']) / DAY:.1f} days.",
                          [{"label": "Review", "value": c["comment"] or "(stars only)"}], "low", f"review_reply:{c['comment_id']}", "rules"))
    if not F:
        F.append({"id": "healthy", "severity": "positive", "title": "Reviews healthy", "detail": "No deteriorating products or recurring complaints detected."})
    top = sorted([{"theme": t, "count": sum(1 for c in r30 if t in labels[c["comment_id"]]["themes"])} for t in THEMES], key=lambda x: -x["count"])
    n = max(1, len(r30))
    summary = f"{dist['negative']} negative reviews in 30 days ({pct(dist['negative'] / n, 0)}). " + (
        f"Recurring issues: {'; '.join(f'{t['theme']} on {short(r['name'], 24)}' for r, t in recurring[:3])}." if recurring else "No recurring complaint themes.")
    rep = report("reviews", f"{dist['negative']} negative / {len(r30)} reviews (30d)", summary, [
        {"label": "Reviews (30d)", "value": str(len(r30))}, {"label": "Positive", "value": pct(dist["positive"] / n, 0), "tone": "good"},
        {"label": "Neutral", "value": pct(dist["neutral"] / n, 0)}, {"label": "Negative", "value": pct(dist["negative"] / n, 0), "tone": "bad" if dist["negative"] / n > 0.12 else "neutral"},
        {"label": "Deteriorating SKUs", "value": str(sum(1 for f in F if f["id"].startswith("rating:"))), "tone": "bad" if any(f["id"].startswith("rating:") for f in F) else "good"},
        {"label": "Awaiting reply", "value": str(len(to_reply)), "tone": "warn" if to_reply else "good"}],
        sort_findings(F), len(P), {
            "products": sorted([{"item_id": r["item_id"], "name": r["name"], "rating_14d": round(r["recentAvg"], 2), "n_14d": r["recentN"], "rating_before": round(r["baseAvg"], 2),
                                 "negative_share": round(r["negShare"] * 100), "top_theme": r["themes"][0]["theme"] if r["themes"] else "",
                                 "mentions": r["themes"][0]["count"] if r["themes"] else 0, "refunds_30d": r2(r["refunds30"])} for r in per if r["n30"]], key=lambda x: x["rating_14d"]),
            "themes": top,
            "recent": [{"comment_id": c["comment_id"], "product": short(name.get(c["item_id"], ""), 40), "stars": c["rating_star"], "sentiment": labels[c["comment_id"]]["sentiment"],
                        "themes": ", ".join(labels[c["comment_id"]]["themes"]), "text": c["comment"], "buyer": c["buyer_username"], "replied": bool(c["reply"])} for c in comments[:40]]}, now)
    return rep, P


# ---------------------------------------------------------------- module 4: customer service

SN_RE = re.compile(r"\b\d{6}[A-Z0-9]{8}\b")
THANKS_RE = re.compile(r"^((ok(ay)?|noted|alright|thanks?|thank you|terima kasih|tq|seller|dear)[\s,.!🙏]*)+$", re.I)
CAT_PRIORITY = ["return_refund", "complaint", "cancellation", "shipping_delay", "order_status", "product_question", "presale", "other", "no_reply_needed"]
STATUS_TEXT = {"UNPAID": "awaiting payment", "READY_TO_SHIP": "paid and being prepared for shipment", "PROCESSED": "packed and waiting for courier pickup",
               "SHIPPED": "in transit with the courier", "TO_CONFIRM_RECEIVE": "delivered", "COMPLETED": "completed", "IN_CANCEL": "pending cancellation",
               "CANCELLED": "cancelled", "TO_RETURN": "under return/refund"}


def rule_category(text):
    t = text.lower().strip()
    if THANKS_RE.match(t):
        return "no_reply_needed"
    if re.search(r"refund|pulang(kan)? duit|return|ganti|replace", t):
        return "return_refund"
    if re.search(r"broken|pecah|damaged|rosak|defect|cannot work|cannot charge|not working|disappointed|kecewa|1 star|worst|teruk|wrong item|too small|tight|different from|is lost\?\?", t):
        return "complaint"
    if "cancel" in t:
        return "cancellation"
    if re.search(r"not moving|stuck|tak bergerak|not received|haven.t received|is it lost|tracking", t):
        return "shipping_delay"
    if re.search(r"when.*ship|bila.*(pos|hantar|ship)|not shipped|belum ship|ship.*faster|ship my order", t):
        return "order_status"
    if re.search(r"stock|stok|voucher|discount|\bcod\b|ship today|original|buy 3", t):
        return "presale"
    if re.search(r"\?|can |boleh|got |ada |is it|does it|\bfit\b|size|compatible|warranty|how", t):
        return "product_question"
    return "other"


def rule_triage(texts, order, item, last_track, name):
    t = " ".join(texts).lower()
    hi = f"Hi {name or 'there'}"
    cats = [rule_category(x) for x in texts]
    cat = next((p for p in CAT_PRIORITY if p in cats), "other")
    if cat == "order_status":
        reply = (f"{hi}, thank you for your patience! Your order {order['order_sn']} is {STATUS_TEXT.get(order['order_status'], order['order_status'])}." +
                 (" We will arrange shipment today and you will receive the tracking number once it is picked up 🙏" if order["order_status"] == "READY_TO_SHIP" else "")) if order \
            else f"{hi}, thank you for your patience! Could you share your order number so we can check the status for you? 😊"
    elif cat == "shipping_delay":
        reply = (f"{hi}, so sorry for the delay 🙏 Your parcel {order['order_sn']} ({order['shipping_carrier']}) was last updated " +
                 (f"at “{last_track['location']}”" if last_track else "recently") + ". We have raised a ticket with the courier and will update you within 24 hours.") if order \
            else f"{hi}, sorry for the delay! Please share your order number and we will check with the courier right away."
    elif cat in ("complaint", "return_refund"):
        reply = f"{hi}, we are very sorry about this 🙏 Please submit a Return/Refund request in the Shopee app with photos of the item" + (f" for order {order['order_sn']}" if order else "") + ", and our team will review it as a priority."
    elif cat == "cancellation":
        reply = f"{hi}, noted – we have received your cancellation request for {order['order_sn']} and will process it shortly." if order and order["order_status"] == "IN_CANCEL" \
            else f"{hi}, noted! Please submit the cancellation request from your order page" + (f" ({order['order_sn']})" if order else "") + " and we will process it before shipping."
    elif cat == "presale":
        reply = f"{hi}! Yes, this item is ready stock" + (f" ({sum(m['stock'] for m in item['models'])} available)" if item else "") + " and we ship from Shah Alam within 24 hours. Free shipping for orders above RM30 😊"
    elif cat == "product_question":
        reply = f"{hi}! Thanks for your interest in {short(item['item_name'], 40)}. You can find the full specifications in the description section – let me check the details for you and get back shortly 😊" if item \
            else f"{hi}! Thanks for your question – let me check and get back to you shortly 😊"
    elif cat == "no_reply_needed":
        reply = ""
    else:
        reply = f"{hi}, thanks for reaching out! How can we help you today? 😊"
    sensitive = cat in ("complaint", "return_refund")
    return {"category": cat, "sentiment": "negative" if sensitive else "neutral", "needs_reply": cat != "no_reply_needed", "sensitive": sensitive,
            "escalate": sensitive and bool(re.search(r"1 star|report|scam|lawyer|police|very disappointed", t)),
            "escalation_reason": "Complaint / refund request" if sensitive else "", "reply": reply}


def run_service(data, st):
    now, perf = data.now, data.perf
    threads = data.chats()
    orders = data.orders
    order_by = {o["order_sn"]: o for o in orders}
    F, P, rows = [], [], []
    pending = []
    for th in threads:
        msgs = th["messages"]
        last_seller = max((i for i, m in enumerate(msgs) if m["sender"] == "seller"), default=-1)
        after = [m for m in msgs[last_seller + 1:] if m["sender"] == "buyer"]
        fresh = []
        for m in reversed(after):
            if fresh and fresh[0]["created_timestamp"] - m["created_timestamp"] > 24 * HOUR:
                break
            fresh.insert(0, m)
        while len(fresh) > 1 and fresh[0]["message_type"] == "text" and THANKS_RE.match(fresh[0]["content"].get("text", "")):
            fresh.pop(0)
        if any(m["message_type"] == "text" for m in fresh):
            pending.append((th, msgs, fresh))
    need_track = []
    for th, msgs, fresh in pending:
        buyer_id = th["buyer_user_id"]
        texts = [m["content"].get("text", "") for m in fresh if m["message_type"] == "text"]
        last = fresh[-1]
        ref_sn = next((m["content"].get("order_sn") for m in fresh if m["content"].get("order_sn")), None) or (SN_RE.search(" ".join(texts)) or [None])[0]
        ref_item = next((m["content"].get("item_id") for m in fresh if m["content"].get("item_id")), None)
        buyer_orders = sorted([o for o in orders if o["buyer_user_id"] == buyer_id], key=lambda o: -o["create_time"])
        order = (order_by.get(ref_sn) if ref_sn else None) or (None if ref_item else (buyer_orders[0] if buyer_orders else None))
        if order is None and ref_sn:
            order = sim.get_order(ref_sn)
            if order:
                order["recipient"] = sim.jl(order["recipient"], {})
        item = data.item.get(ref_item) if ref_item else None
        need_track.append((th, texts, last, fresh, order, item))
    tracks = data.tracking([x[4]["order_sn"] for x in need_track if x[4]])
    for th, texts, last, fresh, order, item in need_track:
        lt = tracks.get(order["order_sn"], [None])[-1] if order else None
        name = first_name((order or {}).get("recipient", {}).get("name")) or th["buyer_username"]
        tri = rule_triage(texts, order, item, lt, name)
        wait = (now - fresh[0]["created_timestamp"]) / HOUR
        rows.append({"conversation_id": th["conversation_id"], "buyer": th["buyer_username"], "category": tri["category"], "sentiment": tri["sentiment"], "sensitive": tri["sensitive"],
                     "escalate": tri["escalate"], "waiting_hours": round(wait, 1), "message": " / ".join(texts)[:200], "order_sn": (order or {}).get("order_sn", "")})
        if tri["escalate"]:
            F.append({"id": f"escalate:{th['conversation_id']}", "severity": "critical", "title": f"Escalation: {th['buyer_username']} ({tri['category'].replace('_', ' ')})",
                      "detail": f"{tri['escalation_reason'] or 'Needs owner attention'}. “{' '.join(texts)[:160]}”"})
        if not tri["needs_reply"] or not tri["reply"].strip():
            continue
        P.append(proposal("send_chat_message", f"{'Sensitive reply' if tri['sensitive'] else 'Reply'} to {th['buyer_username']} · {tri['category'].replace('_', ' ')}",
                          {"type": "conversation", "id": str(th["conversation_id"]), "label": th["buyer_username"]},
                          {"to_id": th["buyer_user_id"], "conversation_id": th["conversation_id"], "text": tri["reply"], "category": tri["category"],
                           "reply_to_message_id": last["message_id"], "buyer_messages": texts},
                          f"Buyer has waited {f'{round(wait * 60)} min' if wait < 1 else f'{wait:.1f}h'}. Replying within 12h counts toward chat response rate (now {perf['chat_response_rate']}%, target ≥ {perf['targets']['chat_response_rate']}%)." +
                          (" Complaint handling affects whether the buyer leaves a negative review or escalates to Shopee." if tri["sensitive"] else ""),
                          tri["category"].replace("_", " ") + (f" about order {order['order_sn']} ({STATUS_TEXT.get(order['order_status'], order['order_status'])})" if order else f" about {short(item['item_name'], 40)}" if item else "") + "." +
                          (f" Escalated: {tri['escalation_reason']}" if tri["escalate"] else ""),
                          [{"label": "Buyer wrote", "value": " / ".join(texts)[:300]}] + ([{"label": "Order", "value": f"{order['order_sn']} · {order['order_status']} · {rm(order['total_amount'])}"}] if order else []),
                          "medium" if tri["sensitive"] else "low", f"chat:{th['conversation_id']}:{last['message_id']}", "rules", tri["sensitive"]))
    open_r = [r for r in data.returns if r["status"] == "REQUESTED"]
    for r in open_r:
        order = order_by.get(r["order_sn"])
        it = data.item.get(r["item_id"])
        same = sum(1 for x in data.returns if x["item_id"] == r["item_id"] and x["reason"] == r["reason"] and x["return_sn"] != r["return_sn"] and x["create_time"] > now - 30 * DAY)
        due = (r["due_date"] - now) / HOUR
        partial = r["reason"] == "DIFFERENT_DESCRIPTION" and r["refund_amount"] > 20
        offer = round(r["refund_amount"] * 0.4, 2)
        F.append({"id": f"return:{r['return_sn']}", "severity": "critical" if due < 24 else "warning", "title": f"Return request {r['return_sn']} – {r['text_reason']}",
                  "detail": f"{r['buyer_username']} · {rm(r['refund_amount'])} · respond within {max(0, due):.0f}h or Shopee auto-refunds." + (f" {same} other “{r['reason']}” returns on this product in 30 days." if same else "")})
        target = {"type": "return", "id": r["return_sn"], "label": f"{r['return_sn']} · {r['buyer_username']}"}
        ev = [{"label": "Reason", "value": f"{r['reason']} – {r['text_reason']}"}, {"label": "Product", "value": short(it["item_name"], 60) if it else str(r["item_id"])},
              {"label": "Order", "value": f"{order['order_sn']} · {rm(order['total_amount'])} · {order['payment_method']}" if order else r["order_sn"]},
              {"label": "Same issue on this product (30d)", "value": str(same)}]
        if partial:
            P.append(proposal("offer_partial_refund", f"Offer {rm(offer)} partial refund for {r['return_sn']} (sizing)", target,
                              {"return_sn": r["return_sn"], "amount": offer, "refund_amount": r["refund_amount"]},
                              f"Buyer keeps the item; saves {rm(r['refund_amount'] - offer)} vs a full refund and avoids return shipping. ~65% of buyers accept partial offers; otherwise Shopee mediates.",
                              "Size mismatch is not a defect – a partial refund is a fair, common resolution. Our listing contributed (recurring sizing complaints), so a dispute would likely fail.",
                              ev, "medium", f"return:{r['return_sn']}", "analysis", True))
        else:
            P.append(proposal("accept_return", f"Approve {rm(r['refund_amount'])} refund for {r['return_sn']}", target, {"return_sn": r["return_sn"], "refund_amount": r["refund_amount"]},
                              f"Resolves the case before the {max(0, due):.0f}h deadline (Shopee auto-refunds anyway if ignored, but counts it against the shop). Cost {rm(r['refund_amount'])}.",
                              f"This matches a recurring problem on the product ({same} similar returns), so the claim is credible and a dispute would likely fail." if same
                              else "Low value – the cost of disputing exceeds the refund." if r["refund_amount"] <= 30 else "Buyer reports a fault on our side; accepting is the fastest resolution.",
                              ev, "medium", f"return:{r['return_sn']}", "analysis", True))
    waits = [r["waiting_hours"] for r in rows if r["category"] != "no_reply_needed"]
    sens = sum(1 for r in rows if r["sensitive"])
    if waits and max(waits) > 6:
        F.append({"id": "slow", "severity": "warning", "title": f"{sum(1 for w in waits if w > 6)} buyer(s) waiting more than 6 hours",
                  "detail": f"Oldest unanswered: {max(waits):.1f}h. Threads unanswered after 12h lower the chat response rate ({perf['chat_response_rate']}%)."})
    if perf["chat_response_rate"] < perf["targets"]["chat_response_rate"]:
        F.append({"id": "crr", "severity": "warning", "title": f"Chat response rate {perf['chat_response_rate']}% is below Shopee's {perf['targets']['chat_response_rate']}% target",
                  "detail": "Preferred Seller status requires ≥ 80% (measured over 30 days)."})
    if not F:
        F.append({"id": "healthy", "severity": "positive", "title": "Inbox under control", "detail": "No buyers waiting for a reply."})
    cats = [{"category": c, "count": n} for c in CAT_PRIORITY if (n := sum(1 for r in rows if r["category"] == c))]
    summary = f"{len(waits)} buyers need a reply" + (f", {sens} of them sensitive (complaints/refunds)" if sens else "") + ". " + (f"{len(open_r)} return request(s) need a decision." if open_r else "")
    rep = report("service", f"{len(waits)} to reply · {sens} sensitive · {len(open_r)} returns", summary.strip(), [
        {"label": "Need reply", "value": str(len(waits)), "tone": "warn" if len(waits) > 10 else "neutral"}, {"label": "Sensitive", "value": str(sens), "tone": "warn" if sens else "good"},
        {"label": "Escalations", "value": str(sum(1 for r in rows if r["escalate"])), "tone": "bad" if any(r["escalate"] for r in rows) else "good"},
        {"label": "Oldest wait", "value": f"{max(waits):.1f}h" if waits else "–"}, {"label": "Open returns", "value": str(len(open_r)), "tone": "warn" if open_r else "good"},
        {"label": "Chat response rate", "value": f"{perf['chat_response_rate']}%", "tone": "bad" if perf["chat_response_rate"] < perf["targets"]["chat_response_rate"] else "good"}],
        sort_findings(F), len(P), {"inbox": sorted(rows, key=lambda r: (-int(r["sensitive"]), -r["waiting_hours"])), "categories": cats}, now)
    return rep, P


# ---------------------------------------------------------------- module 5: sales & BI

def _is_campaign(date):
    _, m, d = (int(x) for x in date.split("-"))
    return m == d and m >= 9


def run_sales(data, st):
    now = data.now
    stats = item_stats(data)
    cost = costs()
    F, P = [], []
    today = sim.date_key(now)
    days = [sim.date_key(now - (29 - i) * DAY) for i in range(30)]
    pl = {d: {"date": d, "gmv": 0.0, "orders": 0, "units": 0, "views": 0, "fees": 0.0, "refunds": 0.0, "cogs": 0.0, "profit": 0.0} for d in days}
    for r in data.daily:
        d = pl.get(r["date"])
        if d:
            d["gmv"] += r["sales"]
            d["orders"] += r["orders"]
            d["units"] += r["units"]
            d["views"] += r["views"]
    item_profit = {}
    for o in data.orders:
        d = pl.get(sim.date_key(o["create_time"]))
        if not d or not LIVE(o):
            continue
        p = order_profit(o, data.escrow[o["order_sn"]], cost)
        for k in ("fees", "cogs", "profit"):
            d[k] += p[k]
        d["refunds"] += p["refund"]
        total = sum(ln["discounted_price"] * ln["quantity"] for ln in o["lines"]) or 1
        for ln in o["lines"]:
            item_profit[ln["item_id"]] = item_profit.get(ln["item_id"], 0) + p["profit"] * ln["discounted_price"] * ln["quantity"] / total
    series = [{**d, "gmv": r2(d["gmv"]), "fees": r2(d["fees"]), "refunds": r2(d["refunds"]), "cogs": r2(d["cogs"]), "profit": r2(d["profit"]),
               "cr": r2(d["orders"] / d["views"] * 100) if d["views"] else 0, "campaign": 1 if _is_campaign(d["date"]) else 0} for d in pl.values()]

    def ssum(a, b):
        rows = series[a:b]
        s = {k: sum(r[k] for r in rows) for k in ("gmv", "orders", "units", "views", "fees", "refunds", "cogs", "profit")}
        s.update(aov=s["gmv"] / s["orders"] if s["orders"] else 0, cr=s["orders"] / s["views"] if s["views"] else 0, margin=s["profit"] / s["gmv"] if s["gmv"] else 0)
        return s
    tday, yest, week, prev = ssum(29, 30), ssum(28, 29), ssum(22, 29), ssum(15, 22)
    weeks = [{"week": f"{series[22 - w * 7]['date']} → {series[28 - w * 7]['date']}", **ssum(22 - w * 7, 29 - w * 7)} for w in range(4)][::-1]
    progress = ((now + 8 * 3600) % DAY) / DAY
    payday = lambda a, b: any(int(d["date"][8:]) >= 25 or int(d["date"][8:]) <= 2 for d in series[a:b])  # noqa: E731
    F.append({"id": "weekly", "severity": "positive" if week["gmv"] >= prev["gmv"] else "info", "title": f"Last 7 days: {rm(week['gmv'])} sales, {rm(week['profit'])} est. profit",
              "detail": f"{week['orders']} orders ({spct(week['orders'] / max(1, prev['orders']) - 1)} vs prior week" + (", which included the month-end payday peak" if payday(15, 22) and not payday(22, 29) else "") +
              f"), AOV {rm(week['aov'])}, conversion {pct(week['cr'], 2)}, net margin {pct(week['margin'])} after {rm(week['fees'])} Shopee fees, {rm(week['refunds'])} refunds and {rm(week['cogs'])} COGS."})
    if _is_campaign(today):
        F.append({"id": "campaign", "severity": "positive", "title": f"Campaign day ({today[5:].replace('-', '.')}) – traffic elevated",
                  "detail": f"Today so far: {rm(tday['gmv'])} from {tday['orders']} orders with {round(progress * 100)}% of the day elapsed (yesterday: {rm(yest['gmv'])}). Expect a dip tomorrow – don't treat it as an anomaly."})
    base = [d for d in series[14:28] if not d["campaign"]]
    bm = sum(d["gmv"] for d in base) / max(1, len(base))
    bsd = math.sqrt(sum((d["gmv"] - bm) ** 2 for d in base) / max(1, len(base) - 1))
    y = series[28]
    if not y["campaign"] and bsd > 0 and (y["gmv"] - bm) / bsd < -2:
        F.append({"id": "shopdrop", "severity": "warning", "title": "Unusual drop in shop sales yesterday", "detail": f"{rm(y['gmv'])} vs a 14-day typical {rm(bm)} (z = {(y['gmv'] - bm) / bsd:.1f})."})
    live = [s for s in stats if s["status"] == "NORMAL"]
    for s in live:
        rows = s["series"]
        last3 = [r for r in rows if r["date"] < today][-3:]
        trailing = [r for r in rows if r["date"] < (last3[0]["date"] if last3 else today) and not _is_campaign(r["date"])][-14:]
        if len(last3) < 3 or len(trailing) < 10:
            continue
        mean = sum(r["units"] for r in trailing) / len(trailing)
        got = sum(r["units"] for r in last3)
        exp = mean * 3
        target = {"type": "item", "id": str(s["item_id"]), "label": short(s["name"], 50)}
        if exp >= 6 and poisson_cdf(got, exp) < 0.01:
            F.append({"id": f"drop:{s['item_id']}", "severity": "warning", "title": f"Unusual sales drop: {short(s['name'], 40)}",
                      "detail": f"{got} units in the last 3 days vs ~{exp:.0f} expected from the prior 2 weeks (p < 0.01). Views {spct(s['views7'] / max(1, s['viewsPrev7']) - 1)} w/w, conversion {pct(s['crBase'], 2)} → {pct(s['cr7'], 2)}.",
                      "target": target, "recommendation": "Conversion-driven – check recent price changes, new negative reviews or stock-outs on popular variations." if s["cr7"] < s["crBase"] * 0.75
                      else "Traffic-driven – check search ranking, competitor pricing or an ended promotion."})
        if s["views7"] >= 200 and s["crBase"] > 0 and s["cr7"] < s["crBase"] * (1 - st["thresholds"]["conversion_drop_pct"] / 100) and poisson_cdf(s["orders7"], s["views7"] * s["crBase"]) < 0.01 \
                and not any(f["id"] == f"drop:{s['item_id']}" for f in F):
            F.append({"id": f"cr:{s['item_id']}", "severity": "warning", "title": f"Conversion drop: {short(s['name'], 40)}",
                      "detail": f"Conversion {pct(s['crBase'], 2)} → {pct(s['cr7'], 2)} ({spct(s['cr7'] / s['crBase'] - 1)}) on {s['views7']} views.", "target": target})
    cr_med = sorted(s["cr7"] for s in live)[len(live) // 2] if live else 0
    v_med = sorted(s["views7"] for s in live)[len(live) // 2] if live else 0
    table = []
    for s in live:
        profit = item_profit.get(s["item_id"], 0)
        cover = min((m["days_cover"] if math.isfinite(m["days_cover"]) else 999 for m in s["models"]), default=999)
        trend = (s["orders7"] - s["baseOrdersWeek"]) / s["baseOrdersWeek"] if s["baseOrdersWeek"] else 0
        action = "Maintain"
        if (s["margin"] or 0) >= 0.35 and s["cr7"] >= cr_med and cover >= 14 and trend > -0.15:
            action = "Promote"
        elif s["views7"] >= v_med and s["cr7"] < cr_med * 0.7:
            action = "Improve"
        if any(f["id"] in (f"drop:{s['item_id']}", f"cr:{s['item_id']}") for f in F):
            action = "Investigate"
        if (s["margin"] if s["margin"] is not None else 1) < 0.1:
            action = "Fix margin"
        table.append({"item_id": s["item_id"], "name": s["name"], "revenue_30d": r2(s["revenue30"]), "profit_30d": r2(profit), "units_30d": s["units30"],
                      "margin": None if s["margin"] is None else r2(s["margin"] * 100), "views_7d": s["views7"], "cr_7d": r2(s["cr7"] * 100),
                      "trend": r2((s["units7"] - s["unitsPrev7"]) / s["unitsPrev7"] * 100) if s["unitsPrev7"] else 0, "rating": s["rating"], "days_cover": r2(cover),
                      "action": action, "boosted": s["boosted"]})
    table.sort(key=lambda r: -r["profit_30d"])
    tp = sum(r["profit_30d"] for r in table)
    top = table[:3]
    F.append({"id": "top", "severity": "info", "title": f"Top profit drivers: {', '.join(short(t['name'], 22) for t in top)}",
              "detail": f"These 3 products generated {pct(sum(t['profit_30d'] for t in top) / max(1, tp), 0)} of 30-day profit ({rm(sum(t['profit_30d'] for t in top))})."})
    losers = [t for t in table if t["profit_30d"] < 0 or (t["margin"] if t["margin"] is not None else 100) < 5]
    if losers:
        F.append({"id": "losers", "severity": "warning", "title": f"{len(losers)} product(s) barely profitable or loss-making",
                  "detail": "; ".join(f"{short(t['name'], 30)} ({t['margin']}% margin, {rm(t['profit_30d'])} in 30d)" for t in losers)})
    for t in [t for t in table if t["action"] == "Promote" and not t["boosted"]][:2]:
        s = next(x for x in live if x["item_id"] == t["item_id"])
        extra = s["views7"] / (7 * 24) * 4 * 1.8 * 1.2 * s["cr7"]
        P.append(proposal("boost_item", f"Boost “{short(s['name'], 36)}” for 4 hours", {"type": "item", "id": str(s["item_id"]), "label": short(s["name"], 50)},
                          {"item_id_list": [s["item_id"]]},
                          f"≈{max(1, round(extra))} extra orders during the boost window (≈{rm(extra * (s['net_per_unit'] or 0))} extra profit) – free to use, 5 boost slots available.",
                          f"Best combination of margin ({pct(s['margin'] or 0)}), conversion ({pct(s['cr7'], 2)} vs median {pct(cr_med, 2)}) and stock cover ({t['days_cover']:.0f} days).",
                          [{"label": "30-day profit", "value": rm(t["profit_30d"])}, {"label": "Rating", "value": f"{s['rating']:.1f}★"},
                           {"label": "Trend (units w/w)", "value": f"{'+' if t['trend'] >= 0 else ''}{t['trend']}%"}], "low", f"boost:{s['item_id']}:{today}"))
    improve = [t for t in table if t["action"] in ("Improve", "Investigate")]
    if improve:
        F.append({"id": "improve", "severity": "info", "title": f"Improve / investigate: {', '.join(short(t['name'], 24) for t in improve)}",
                  "detail": "High traffic but weak conversion, or an unusual drop – see the Products and Reviews modules for root causes."})
    promote = [t for t in table if t["action"] == "Promote" and not t["boosted"]][:2]
    summary = (f"Last 7 days: {rm(week['gmv'])} sales ({spct(week['gmv'] / max(1, prev['gmv']) - 1)} w/w) and {rm(week['profit'])} estimated profit ({pct(week['margin'])} margin). " +
               (f"Promote {' and '.join(short(p['name'], 24) for p in promote)}. " if promote else "") + (f"{len(improve)} product(s) need improvement or investigation." if improve else ""))
    rep = report("sales", f"{rm(week['gmv'])} / 7d · {pct(week['margin'])} margin", summary.strip(), [
        {"label": "Today (so far)", "value": rm(tday["gmv"]), "hint": f"{tday['orders']} orders"}, {"label": "Yesterday", "value": rm(yest["gmv"]), "hint": f"{yest['orders']} orders"},
        {"label": "Sales 7d", "value": rm(week["gmv"]), "hint": spct(week["gmv"] / max(1, prev["gmv"]) - 1) + " w/w", "tone": "good" if week["gmv"] >= prev["gmv"] else "warn"},
        {"label": "Est. profit 7d", "value": rm(week["profit"]), "hint": pct(week["margin"]) + " margin", "tone": "good" if week["margin"] > 0.2 else "warn"},
        {"label": "AOV 7d", "value": rm(week["aov"])}, {"label": "Conversion 7d", "value": pct(week["cr"], 2)}],
        sort_findings(F), len(P), {"products": table, "weeks": [{"week": w["week"], "gmv": r2(w["gmv"]), "orders": w["orders"], "profit": r2(w["profit"]),
                                                                 "margin": r2(w["margin"] * 100), "aov": r2(w["aov"]), "fees": r2(w["fees"]), "refunds": r2(w["refunds"])} for w in weeks]},
        now, {"daily": series})
    return rep, P


RUNNERS = {"orders": run_orders, "products": run_products, "reviews": run_reviews, "service": run_service, "sales": run_sales}


# ---------------------------------------------------------------- approvals: sync proposals, execute actions

SENSITIVE_TYPES = {"send_chat_message": lambda p: p.get("category") in ("complaint", "return_refund"), "accept_return": lambda p: True,
                   "offer_partial_refund": lambda p: True, "dispute_return": lambda p: True, "unlist_item": lambda p: True}
EDITABLE = {"send_chat_message": ["text"], "reply_comment": ["comment"], "update_item": ["item_name", "description"], "offer_partial_refund": ["amount"],
            "update_price": ["price"], "update_stock": ["add"], "dispute_return": ["reason"]}


def sync_proposals(module, drafts):
    """Dedupe by key, refresh pending ones (never overwriting the owner's edits), expire ones the module no longer emits,
    and respect rejections for the rest of the simulated day."""
    with LOCK:
        d = _load()
        day = sim.date_key(sim.now())
        keys = set()
        for dr in drafts:
            k = dr["dedupe_key"]
            keys.add(k)
            if d["rejected"].get(k) == day:
                continue
            if d["settings"]["policy"].get(dr["action_type"]) == "disabled":
                continue
            cur = next((p for p in d["proposals"] if p["dedupe_key"] == k and p["status"] == "pending"), None)
            if cur:
                keep = {f: cur["params"][f] for f in cur.get("edited_fields", []) if f in cur["params"]}
                cur.update({x: dr[x] for x in ("title", "target", "expected_impact", "rationale", "evidence", "risk", "drafted_by")})
                cur["params"] = {**dr["params"], **keep}
                cur["sensitive"] = bool(dr.get("sensitive"))
                cur["updated_at"] = time.time()
            elif not any(p["dedupe_key"] == k and p["status"] in ("executed", "running") and p.get("updated_at", 0) > time.time() - 600 for p in d["proposals"]):
                d["proposals"].append({**dr, "id": "SP" + uuid.uuid4().hex[:8], "module": module, "status": "pending", "created_at": time.time(),
                                       "updated_at": time.time(), "sim_created": sim.now(), "edited_fields": []})
        for p in d["proposals"]:
            if p["module"] == module and p["status"] == "pending" and p["dedupe_key"] not in keys:
                p["status"], p["updated_at"], p["result"] = "expired", time.time(), "No longer needed — the situation changed."
        _save(d)
    auto = [p for p in proposals("pending", module) if settings()["policy"].get(p["action_type"]) == "auto" and not p.get("sensitive")]
    for p in auto:
        try:
            decide(p["id"], "approve", by="auto policy")
        except Exception:
            pass


def proposals(status=None, module=None):
    with LOCK:
        d = _load()
    out = [p for p in d["proposals"] if (status is None or p["status"] == status) and (module is None or p["module"] == module)]
    return sorted(out, key=lambda p: ({"pending": 0}.get(p["status"], 1), -p.get("updated_at", 0)))


def _precheck(t, p):
    if t == "ship_orders":
        ok = [sn for sn in p["order_sn_list"] if (sim.get_order(sn) or {}).get("order_status") == "READY_TO_SHIP"]
        if not ok:
            return "None of these orders are ready to ship any more."
        p["order_sn_list"] = ok
    elif t == "handle_buyer_cancellation":
        if (sim.get_order(p["order_sn"]) or {}).get("order_status") != "IN_CANCEL":
            return "The cancellation request is no longer pending."
    elif t == "reply_comment":
        c = sim.get("SELECT reply FROM comments WHERE comment_id = ?", int(p["comment_id"]))
        if not c or c["reply"]:
            return "This review already has a reply."
    elif t in ("accept_return", "offer_partial_refund"):
        if (sim.get_return(p["return_sn"]) or {}).get("status") != "REQUESTED":
            return "The return request is no longer open."
    elif t == "send_chat_message" and p.get("conversation_id"):
        c = sim.get("SELECT awaiting_reply FROM conversations WHERE conversation_id = ?", int(p["conversation_id"]))
        last = sim.get("SELECT MAX(message_id) m FROM messages WHERE conversation_id = ? AND sender = 'buyer'", int(p["conversation_id"]))
        if not c or not c["awaiting_reply"] or (p.get("reply_to_message_id") and last and last["m"] and last["m"] > int(p["reply_to_message_id"]) + 1):
            return "The conversation moved on (already answered or new messages) — the draft is stale."
    return None


def _execute(t, p):
    if t == "ship_orders":
        done = [sim.ship_order(sn, SOURCE) for sn in p["order_sn_list"]]
        bad = [sn for sn in p["order_sn_list"] if sim.get_order(sn)["order_status"] != "PROCESSED"]
        return f"Arranged {len(done)} shipment(s); tracking numbers assigned." + (f" Not verified: {', '.join(bad)}" if bad else ""), not bad
    if t == "handle_buyer_cancellation":
        r = sim.handle_buyer_cancellation(p["order_sn"], p.get("operation", "ACCEPT"), SOURCE)
        return f"Order {p['order_sn']} is now {r['order_status']}.", r["order_status"] in ("CANCELLED", "READY_TO_SHIP")
    if t == "update_price":
        sim.update_price(int(p["item_id"]), p["price_list"], SOURCE)
        live = {m["model_id"]: m["price"] for m in sim.models_of(int(p["item_id"]))}
        ok = all(abs(live[int(x["model_id"])] - float(x["original_price"])) < 0.01 for x in p["price_list"])
        return "Prices now " + ", ".join(rm(live[int(x["model_id"])]) for x in p["price_list"][:4]) + ".", ok
    if t == "update_stock":
        before = {m["model_id"]: m["stock"] for m in sim.models_of(int(p["item_id"]))}
        sim.update_stock(int(p["item_id"]), [{"model_id": x["model_id"], "add": int(x["add"])} for x in p["stock_list"]], SOURCE)
        after = {m["model_id"]: m["stock"] for m in sim.models_of(int(p["item_id"]))}
        ok = all(after[int(x["model_id"])] >= before[int(x["model_id"])] + int(x["add"]) - 5 for x in p["stock_list"])
        return f"Added {sum(int(x['add']) for x in p['stock_list'])} units.", ok
    if t == "update_item":
        sim.update_item(int(p["item_id"]), {"item_name": p.get("item_name"), "description": p.get("description")}, SOURCE)
        it = sim.get_item(int(p["item_id"]))
        ok = (not p.get("item_name") or it["item_name"] == p["item_name"].strip()) and (not p.get("description") or it["description"] == p["description"].strip())
        return "Listing updated.", ok
    if t == "unlist_item":
        sim.update_item(int(p["item_id"]), {"item_status": "UNLIST"}, SOURCE)
        return "Listing paused.", sim.get_item(int(p["item_id"]))["item_status"] == "UNLIST"
    if t == "boost_item":
        for iid in p["item_id_list"]:
            sim.boost_item(int(iid), SOURCE)
        return "Boost started for 4 hours.", all(sim.get_item(int(i))["boost_until"] > sim.now() for i in p["item_id_list"])
    if t == "send_chat_message":
        cid = p.get("conversation_id") or sim.conversation_for(int(p["to_id"]))["conversation_id"]
        r = sim.seller_send(int(cid), p["text"], SOURCE)
        return "Message sent.", bool(sim.get("SELECT 1 x FROM messages WHERE message_id = ?", r["message_id"]))
    if t == "reply_comment":
        sim.reply_comment(int(p["comment_id"]), p["comment"], SOURCE)
        return "Reply posted.", bool(sim.get("SELECT reply FROM comments WHERE comment_id = ?", int(p["comment_id"]))["reply"])
    if t == "accept_return":
        r = sim.accept_return(p["return_sn"], SOURCE)
        return f"Refund {rm(r['refund_amount'])} approved.", sim.get_return(p["return_sn"])["status"] == "REFUND_PAID"
    if t == "offer_partial_refund":
        sim.offer_partial_refund(p["return_sn"], float(p["amount"]), SOURCE)
        return f"Partial refund {rm(float(p['amount']))} offered.", sim.get_return(p["return_sn"])["status"] == "PROCESSING"
    if t == "dispute_return":
        sim.dispute_return(p["return_sn"], p.get("reason") or "Item was sent in good condition", SOURCE)
        return "Dispute raised with Shopee.", sim.get_return(p["return_sn"])["status"] == "JUDGING"
    raise ValueError(f"unknown action {t}")


def decide(pid, decision, edits=None, by="owner"):
    """Approve (execute) or reject a pending proposal. Returns the updated proposal."""
    with LOCK:
        d = _load()
        p = next((x for x in d["proposals"] if x["id"] == pid), None)
        if not p:
            raise ValueError("unknown proposal")
        if p["status"] != "pending":
            raise ValueError(f"this proposal is already {p['status']}")
        if decision == "reject":
            p.update(status="rejected", updated_at=time.time(), decided_by=by)
            d["rejected"][p["dedupe_key"]] = sim.date_key(sim.now())
            d["log"].append({"ts": time.time(), "sim_ts": sim.now(), "kind": "reject", "text": f"Rejected: {p['title']}", "by": by})
            _save(d)
            return p
        if d["settings"]["policy"].get(p["action_type"]) == "disabled":
            raise ValueError("this action type is disabled in the Shopee agent settings")
        params = json.loads(json.dumps(p["params"]))
        for f, v in (edits or {}).items():
            if f not in EDITABLE.get(p["action_type"], []):
                continue
            if f == "price" and v not in (None, ""):
                params["price_list"] = [{"model_id": x["model_id"], "original_price": float(v)} for x in params["price_list"]]
            elif f == "add" and v not in (None, ""):
                params["stock_list"] = [dict(x, add=int(v)) for x in params["stock_list"]]
            elif v not in (None, ""):
                params[f] = v
            p.setdefault("edited_fields", []).append(f)
        p["params"] = params
        p["status"] = "running"
        _save(d)
    err = _precheck(p["action_type"], params)
    if err:
        status, result, ok = "expired", err, False
    else:
        try:
            result, ok = _execute(p["action_type"], params)
            status = "executed" if ok else "failed"
        except sim.ShopeeError as e:
            status, result, ok = "failed", f"Shopee rejected it: {e}", False
        except Exception as e:
            status, result, ok = "failed", f"Error: {e}", False
    with LOCK:
        d = _load()
        q = next(x for x in d["proposals"] if x["id"] == pid)
        q.update(status=status, result=result, verified=ok, updated_at=time.time(), decided_by=by, params=params, edited_fields=p.get("edited_fields", []))
        d["log"].append({"ts": time.time(), "sim_ts": sim.now(), "kind": status, "text": f"{q['title']} — {result}", "by": by, "action_type": q["action_type"]})
        _save(d)
        return q


# ---------------------------------------------------------------- run modules

_cache = {}


def run_module(module, sync=True):
    st = settings()
    data = Data()
    rep, props = RUNNERS[module](data, st)
    if sync:
        sync_proposals(module, props)
    rep["pending"] = proposals("pending", module)
    _cache[module] = rep
    return rep


def run_all():
    st = settings()
    data = Data()
    out = {}
    for m in RUNNERS:
        try:
            rep, props = RUNNERS[m](data, st)
            sync_proposals(m, props)
            out[m] = rep
            _cache[m] = rep
        except Exception as exc:
            print(f"[shopee agent] {m} failed: {exc}", flush=True)
    return out


def overview():
    perf = sim.shop_performance()
    pend = proposals("pending")
    by = {m["id"]: sum(1 for p in pend if p["module"] == m["id"]) for m in MODULES}
    return {"shop": sim.shop_info(), "performance": perf, "sim": sim.sim_state(), "modules": [dict(m, pending=by[m["id"]], headline=(_cache.get(m["id"]) or {}).get("headline", ""))
                                                                                            for m in MODULES],
            "pending": len(pend), "sensitive": sum(1 for p in pend if p.get("sensitive")), "log": list(reversed(_load()["log"][-40:]))}


def brief_text(module=None):
    """Plain-text report for the chat agent (read-only)."""
    mods = [module] if module else list(RUNNERS)
    lines = []
    data, st = Data(), settings()
    perf = data.perf
    lines.append(f"Shopee shop UrbanNest Lifestyle — simulated time {sim.local(data.now).strftime('%a %d %b %H:%M')}. Rating {perf['shop_rating']}★, "
                 f"chat response {perf['chat_response_rate']}%, late shipment {perf['late_shipment_rate']}%, preparation {perf['preparation_time_days']} days.")
    for m in mods:
        rep, props = RUNNERS[m](data, st)
        sync_proposals(m, props)
        lines.append(f"\n## {rep['title']} — {rep['headline']}\n{rep['summary']}")
        for k in rep["kpis"]:
            lines.append(f"- {k['label']}: {k['value']}")
        for f in rep["findings"][:6]:
            lines.append(f"- [{f['severity']}] {f['title']} — {f['detail']}")
    pend = proposals("pending", module)
    if pend:
        lines.append("\nPending proposals the owner can approve (use `shopee-approve <id>` as execute_command):")
        for p in pend[:15]:
            lines.append(f"- {p['id']} [{p['module']}{', sensitive' if p.get('sensitive') else ''}] {p['title']} — {p['expected_impact'][:160]}")
    lines.append("[evidence] data/shopee/shopee.db")
    return "\n".join(lines)
