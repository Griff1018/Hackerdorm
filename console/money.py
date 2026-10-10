"""Money Flow: every ringgit in and out of one business, in one ledger.

Money in  — online banking (DuitNow / FPX) and Touch 'n Go eWallet transfers from the payment feeds (SIMULATED,
            seeded when the owner connects them in Settings), cash/QR sales the owner recorded, completed customer
            orders, and manual entries.
Money out — ingredient purchases typed in by the owner, supplier purchase orders paid through BizFlow's
            automations (SIMULATED payments), and recorded expenses.

data/workspace/money.json holds manual entries and the payment-feed transactions. BizFlow never asks for or
stores bank logins, card numbers or e-wallet PINs; a "connection" is only a nickname.
"""
from __future__ import annotations

import csv
import hashlib
import json
import threading
import uuid
from collections import defaultdict
from datetime import date, timedelta

import automations as auto
import inbox
import settings as appset
import workspace as ws

STORE = ws.WS / "money.json"
LOCK = threading.Lock()
METHODS = {"bank": "Online banking (DuitNow / FPX)", "tng": "Touch 'n Go eWallet", "cash": "Cash", "qr": "DuitNow QR", "card": "Card", "other": "Other"}
OUT_CATEGORIES = ["Ingredients", "Packaging", "Rent / stall", "Transport", "Marketing", "Equipment", "Wages", "Other"]
IN_CATEGORIES = ["Sales", "Customer order", "Deposit", "Other"]


def _rows() -> list[dict]:
    return ws._read(STORE, [])


def _save(rows):
    ws._write(STORE, rows)


def add_entry(bid: str, e: dict) -> dict:
    """A manual money-in or money-out line. Optional material + qty also tops up Inventory."""
    direction = "in" if str(e.get("direction", "")).lower() in ("in", "income", "received") else "out"
    try:
        amount = round(float(e.get("amount")), 2)
    except (TypeError, ValueError):
        raise ValueError("Give the amount in MYR.")
    if amount <= 0:
        raise ValueError("The amount must be more than zero.")
    try:
        day = date.fromisoformat(str(e.get("date") or date.today().isoformat())[:10]).isoformat()
    except ValueError:
        day = date.today().isoformat()
    method = str(e.get("method") or "cash").lower()
    method = method if method in METHODS else next((k for k, v in METHODS.items() if v.lower().startswith(method[:4])), "other")
    row = {"id": "M" + uuid.uuid4().hex[:6], "business_id": bid, "date": day, "direction": direction, "amount": amount, "method": method,
           "category": str(e.get("category") or ("Ingredients" if direction == "out" else "Sales"))[:40],
           "party": str(e.get("party") or "")[:80], "note": str(e.get("note") or "")[:200], "source": "manual", "created_at": ws.now()}
    mat = str(e.get("material") or "").strip()
    if direction == "out" and mat and e.get("qty") not in (None, ""):
        try:
            q = float(e["qty"])
            cur = auto.stock_of(bid, mat) or {}
            auto.set_stock(bid, mat, {"qty": float(cur.get("qty") or 0) + q, "unit": e.get("unit") or cur.get("unit") or ""})
            row["material"], row["qty"], row["unit"] = mat, q, str(e.get("unit") or cur.get("unit") or "")
        except (TypeError, ValueError):
            pass
    with LOCK:
        rows = _rows()
        rows.append(row)
        _save(rows)
    return row


def delete_entry(mid: str) -> dict | None:
    with LOCK:
        rows = _rows()
        hit = next((r for r in rows if r["id"] == mid), None)
        if hit:
            rows.remove(hit)
            _save(rows)
        return hit


def restore_entry(row: dict):
    with LOCK:
        rows = [r for r in _rows() if r["id"] != row["id"]]
        rows.append(row)
        _save(rows)


# ---------------------------------------------------------------- payment feeds (simulated bank / e-wallet)

def seed_feed(bid: str, app: str):
    """When online banking or TNG is connected, pull in its recent incoming transfers once (SYNTHETIC):
    payments that match open customer orders by amount, plus a couple of plain transfers."""
    rows = _rows()
    if any(r.get("business_id") == bid and r.get("source") == "feed:" + app for r in rows):
        return
    method = "bank" if app == "bank" else "tng"
    orders = [o for o in inbox.orders(bid, None) if o.get("status") != "cancelled"]
    new = []
    for n, o in enumerate(orders):
        h = int(hashlib.md5(f"{bid}{app}{o['id']}".encode()).hexdigest(), 16)
        if (h + n) % 2 and app == "bank" or not (h + n) % 2 and app == "tng":  # split orders between the two feeds
            new.append({"id": "M" + uuid.uuid4().hex[:6], "business_id": bid, "date": str(o.get("created_at", ""))[:10], "direction": "in",
                        "amount": round(float(o.get("total") or 0), 2), "method": method, "category": "Customer order", "party": o.get("customer", ""),
                        "note": f"Payment for order {o['id']}", "order_id": o["id"], "source": "feed:" + app, "synthetic": True, "created_at": ws.now()})
    for k in range(2):
        h = int(hashlib.md5(f"{bid}{app}x{k}".encode()).hexdigest(), 16)
        new.append({"id": "M" + uuid.uuid4().hex[:6], "business_id": bid, "date": (date.today() - timedelta(days=1 + h % 6)).isoformat(), "direction": "in",
                    "amount": [12.0, 15.5, 8.0, 21.0, 6.5][h % 5], "method": method, "category": "Sales",
                    "party": ["Nurul", "Jia Hui", "Kumar", "Farah", "Daniel"][h % 5] + " (demo)", "note": ["kuih order", "snack box", "lunch pre-order", "bazaar sale", "pickup"][h % 5],
                    "source": "feed:" + app, "synthetic": True, "created_at": ws.now()})
    with LOCK:
        rows = _rows()
        rows.extend(x for x in new if x["amount"] > 0)
        _save(rows)


# ---------------------------------------------------------------- the ledger

def _sample_lines():
    """Campus Crumb's synthetic September: validated sales per day (in) and validated expenses (out)."""
    out = []
    try:
        import dashboard as dash
        lines, v, _cfg = dash._sales()
        day = defaultdict(float)
        for r in lines:
            day[r["date"].isoformat()] += float(r["net"])
        out += [{"id": "SALES-" + d, "date": d, "direction": "in", "amount": round(a, 2), "method": "cash", "category": "Sales",
                 "party": "Stall sales (daily total)", "note": "", "source": "sales records", "synthetic": True} for d, a in sorted(day.items())]
        for e in v.expenses_rows:
            if e.get("amount") is not None:
                out.append({"id": e.get("expense_id") or "E", "date": str(e.get("date"))[:10], "direction": "out", "amount": round(float(e["amount"]), 2),
                            "method": "bank" if e.get("paid_status") == "paid" else "other", "category": e.get("category") or "Other",
                            "party": "", "note": (e.get("description") or "") + ("" if e.get("paid_status") == "paid" else f" ({e.get('paid_status')})"),
                            "source": "expenses", "synthetic": True})
    except Exception:  # sample data unavailable — the ledger still works from the owner's own records
        pass
    return out


def _paid_pos(bid: str):
    if not (ws.business(bid) or {}).get("uses_sample_data"):
        return []
    d = ws._read(ws.ROOT / "data" / "output" / "purchase_orders.json", {})
    out = []
    for p in d.get("purchase_orders", []):
        if p.get("status") in ("paid", "received"):
            out.append({"id": p["order_id"], "date": str(p.get("paid_at") or "")[:10], "direction": "out", "amount": round(float(p.get("total") or 0), 2),
                        "method": "bank", "category": "Ingredients", "party": p.get("supplier_name", ""),
                        "note": "Supplier order: " + ", ".join(l["material"] for l in p.get("lines", [])), "source": "automation (simulated payment)"})
    return out


def _rows_for(bid: str) -> list[dict]:
    rows = [dict(r) for r in _rows() if r.get("business_id") == bid]
    paid_orders = {r.get("order_id") for r in rows if r.get("order_id")}
    for o in inbox.orders(bid, "done"):
        if o["id"] not in paid_orders and o.get("total"):
            rows.append({"id": o["id"], "date": str(o.get("updated_at") or o["created_at"])[:10], "direction": "in", "amount": round(float(o["total"]), 2),
                         "method": "cash", "category": "Customer order", "party": o.get("customer", ""), "note": f"Order {o['id']} ({o.get('channel')})",
                         "source": "completed order"})
    for s in appset.sales(bid):
        rows.append({"id": s["id"], "date": s["date"], "direction": "in", "amount": round(s["qty"] * s["price"], 2), "method": "cash", "category": "Sales",
                     "party": s.get("channel", ""), "note": f"{s['qty']}× {s['item']}", "source": "recorded sale"})
    if (ws.business(bid) or {}).get("uses_sample_data"):
        rows += _sample_lines()
    rows += _paid_pos(bid)
    return rows


def ledger(bid: str) -> dict:
    if bid == ws.ALL:
        rows = []
        for b in ws.businesses():
            rows += [dict(r, business_id=b["id"], business=b["name"]) for r in _rows_for(b["id"])]
    else:
        rows = _rows_for(bid)
    rows.sort(key=lambda r: (r["date"], r.get("created_at", "")), reverse=True)
    tin = round(sum(r["amount"] for r in rows if r["direction"] == "in"), 2)
    tout = round(sum(r["amount"] for r in rows if r["direction"] == "out"), 2)
    by_method, by_cat, by_day = defaultdict(float), defaultdict(float), defaultdict(lambda: {"in": 0.0, "out": 0.0})
    for r in rows:
        if r["direction"] == "in":
            by_method[METHODS.get(r["method"], r["method"])] += r["amount"]
        else:
            by_cat[r["category"]] += r["amount"]
        by_day[r["date"]][r["direction"]] += r["amount"]
    days = sorted(by_day)[-30:]
    return {"business_id": bid, "entries": rows, "totals": {"in": tin, "out": tout, "net": round(tin - tout, 2), "count": len(rows)},
            "in_by_method": sorted([{"method": k, "amount": round(v, 2)} for k, v in by_method.items()], key=lambda x: -x["amount"]),
            "out_by_category": sorted([{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()], key=lambda x: -x["amount"]),
            "daily": [{"date": d, "in": round(by_day[d]["in"], 2), "out": round(by_day[d]["out"], 2), "net": round(by_day[d]["in"] - by_day[d]["out"], 2)} for d in days],
            "methods": METHODS, "in_categories": IN_CATEGORIES, "out_categories": OUT_CATEGORIES,
            "feeds": {} if bid == ws.ALL else {c["id"]: c["connected"] for c in appset.connections(bid) if c["kind"] == "payments"}}
