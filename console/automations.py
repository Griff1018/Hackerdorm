"""Enterprise Buddy automations: auto-reorder from suppliers and scheduled social posting.

Auto-reorder: rules fire on a schedule (weekday + time, or every N days) or when stock runs low
(product stock at/below its reorder point, from ops_findings.json). Each firing creates an order draft
with the quantity, a plain-English "why this amount" chain and the sources, plus the message to the
supplier. PAYMENT ALWAYS WAITS FOR THE OWNER'S APPROVAL. On approval the PO is marked paid
(SIMULATED — no money moves) and a payment-confirmation message is prepared.

Messaging: WhatsApp messages are prepared as wa.me click-to-chat links (the owner taps Send). If
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, the owner's confirmation summary is also sent to Telegram.

Social posting: media + context -> agent-written caption/hashtags/SEO -> post now or schedule. Posts go to
the SIMULATED social feed; real Facebook/Instagram publishing needs a Meta Business account + Graph API token.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "output"
STORE = ROOT / "data" / "workspace" / "automations.json"
MEDIA = OUTPUT / "media"
TZ = timezone(timedelta(hours=8))
LOCK = threading.RLock()
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def now():
    return datetime.now(TZ)


def iso(dt=None):
    return (dt or now()).isoformat(timespec="seconds")


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


DEFAULT_RULES = [
    {"id": "R1", "business_id": "campus-crumb", "name": "Chocolate chips — reorder when cookies run low",
     "po_id": "PO-2026-09-30-02", "material": "Chocolate chips",
     "trigger": {"type": "low_stock", "product_id": "P001"},
     "contact": {"channel": "whatsapp", "name": "Healthy Baker Malaysia (demo contact)", "phone": "60110000001"},
     "enabled": True, "last_fired": None},
    {"id": "R2", "business_id": "campus-crumb", "name": "Flour — weekly order every Monday 09:00",
     "po_id": "PO-2026-09-30-04", "material": "Flour",
     "trigger": {"type": "schedule", "weekday": "Mon", "time": "09:00"},
     "contact": {"channel": "whatsapp", "name": "PJ Grocer Sdn Bhd (demo contact)", "phone": "60110000002"},
     "enabled": True, "last_fired": None},
    {"id": "R3", "business_id": "campus-crumb", "name": "Wax paper — every 14 days",
     "po_id": "PO-2026-09-30-03", "material": "Wax paper",
     "trigger": {"type": "every_days", "days": 14, "time": "10:00"},
     "contact": {"channel": "telegram", "name": "Image Magic (demo contact)", "phone": "60110000003"},
     "enabled": False, "last_fired": None},
]


def load():
    with LOCK:
        d = _read_json(STORE, None)
        if d is None:
            d = {"rules": DEFAULT_RULES, "orders": [], "outbox": [], "posts": [], "log": []}
            save(d)
        return d


def save(d):
    with LOCK:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STORE)


def log(d, text, kind="info", **extra):
    d["log"].append({"at": iso(), "kind": kind, "text": text, **extra})
    d["log"] = d["log"][-400:]


# ---------------------------------------------------------------- reorder: why this amount

def _po(po_id):
    doc = _read_json(OUTPUT / "purchase_orders.json", {})
    return next((p for p in doc.get("purchase_orders", []) if p.get("order_id") == po_id), None)


def _materials():
    try:
        with (ROOT / "data" / "sample" / "materials.csv").open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


# ---------------------------------------------------------------- ingredient stock (owner counts + low levels)

STOCKF = ROOT / "data" / "workspace" / "ingredient_stock.json"
# SYNTHETIC starting counts in recipe units (materials.csv) — the owner edits them to real counts.
SEED_STOCK = {"Flour": (6000, 5000), "Butter": (1500, 2000), "Chocolate chips": (400, 1000), "Paper cookie bag": (30, 50),
              "Tea bag": (160, 100), "Sugar": (3000, 2000), "Lemon syrup": (1800, 1000), "Plastic cup 500ml": (120, 100),
              "Banana": (8, 12), "Muffin cup": (150, 100), "Chicken filling": (1500, 1000), "Spice mix": (300, 200),
              "Wax paper": (80, 50), "Rolled oats": (2500, 2000), "Honey": (900, 500), "Peanut butter": (600, 300),
              "Granola bar wrapper": (70, 50)}


def stock_all() -> dict:
    with LOCK:
        d = _read_json(STOCKF, None)
        if d is None:
            units = {}
            try:
                with (ROOT / "data" / "sample" / "materials.csv").open(newline="", encoding="utf-8-sig") as f:
                    for r in csv.DictReader(f):
                        units[r["material_name"]] = r["unit"]
            except OSError:
                pass
            d = {"campus-crumb": {m: {"qty": q, "unit": units.get(m, ""), "threshold": t, "counted_at": iso(), "synthetic": True}
                                  for m, (q, t) in SEED_STOCK.items()}}
            STOCKF.parent.mkdir(parents=True, exist_ok=True)
            STOCKF.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        return d


def stock_of(bid: str, material: str) -> dict | None:
    return stock_all().get(bid, {}).get(material)


def set_stock(bid: str, material: str, patch: dict) -> dict:
    with LOCK:
        d = stock_all()
        s = d.setdefault(bid, {}).setdefault(material, {"qty": 0, "unit": "", "threshold": 0})
        if patch.get("qty") is not None:
            s["qty"], s["counted_at"], s["synthetic"] = max(0, float(patch["qty"])), iso(), False
        if patch.get("threshold") is not None:
            s["threshold"] = max(0, float(patch["threshold"]))
        for k in ("supplier_url", "phone", "unit", "supplier", "planned_by", "price_note"):
            if patch.get(k) is not None:
                s[k] = str(patch[k])[:500]
        s.setdefault("added_at", iso())
        STOCKF.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        return s


def topup_packs(stock: dict, pack: str) -> tuple[int, str] | None:
    """Packs needed to bring stock back to 2 x the low level (deterministic)."""
    from enterprise_buddy_supplier import parse_amount_unit
    import math
    parsed = parse_amount_unit(pack or "")
    if not parsed or parsed[2] is None or not stock or parsed[1] != stock.get("unit"):
        return None
    need = 2 * float(stock.get("threshold", 0)) - float(stock.get("qty", 0))
    if need <= 0:
        return 1, "already above 2 × low level — ordering 1 pack"
    packs = max(1, math.ceil(need / float(parsed[2])))
    return packs, (f"top up to 2 × low level: 2 × {stock['threshold']:g} − {stock['qty']:g} = {need:g} {stock['unit']} "
                   f"→ {packs} pack(s) of {pack} ({float(parsed[2]):g} {stock['unit']} each)")


def _listing_po(rule):
    """A purchase-order-shaped view of a rule that buys from a supplier listing (no Enterprise Buddy PO)."""
    L = rule["listing"]
    packs = int(L.get("packs", 1))
    tp = topup_packs(stock_of(rule["business_id"], rule["material"]), L.get("pack")) if rule["trigger"].get("type") == "low_stock" else None
    if tp:
        packs = tp[0]
    price = float(L["unit_price"])
    line = {"material": rule["material"], "quantity_needed": "set by you", "packs": str(packs), "pack_size": L.get("pack", "pack"),
            "unit_price": f"{price:.2f}", "line_total": f"{price * packs:.2f}", "needs_review": False, "review_reasons": []}
    return {"order_id": "LST-" + rule["id"], "supplier_name": L["supplier"], "source_url": L.get("source_url", ""),
            "retrieved_at": L.get("retrieved_at", ""), "lines": [line], "total": line["line_total"], "status": "draft"}


def explain(rule) -> dict:
    """Quantity, cost and the reasoning chain, all from Enterprise Buddy files (no model arithmetic)."""
    po = _po(rule["po_id"]) if rule.get("po_id") else _listing_po(rule) if rule.get("listing") else None
    ops = _read_json(OUTPUT / "ops_findings.json", {}).get("stock_and_replenishment", {})
    if not po:
        return {"ok": False, "why": [f"Purchase order {rule['po_id']} not found — run the Enterprise Buddy pipeline first."]}
    line = next((l for l in po["lines"] if l["material"].lower() == rule["material"].lower()), po["lines"][0])
    users = [m for m in _materials() if m["material_name"].lower() == line["material"].lower()]
    why, sources = [], [f"data/output/purchase_orders.json ({po['order_id']})", "data/output/ops_findings.json", "data/sample/materials.csv"]
    st = stock_of(rule["business_id"], line["material"])
    if st:
        why.append(f"{line['material']}: {st['qty']:g} {st['unit']} left, your 'low' level is {st['threshold']:g} {st['unit']}"
                   + (" (synthetic starting count)" if st.get("synthetic") else f" (counted {str(st.get('counted_at', ''))[:10]})") + ".")
        sources.append("data/workspace/ingredient_stock.json")
        if rule.get("listing"):
            tp = topup_packs(st, line["pack_size"])
            if tp and rule["trigger"].get("type") == "low_stock":
                why.append("Amount: " + tp[1] + ".")
    for m in users:
        s = ops.get(m["product_id"]) or {}
        if s:
            why.append(f"{s['product_name']}: stock {s['stock_on_hand']}, reorder point {s['reorder_point']}, sells ~{float(s['average_daily_units']):.1f}/day "
                       f"→ {s['days_of_stock']} days left vs lead time {s['lead_time_days']} days; plan to make {s['replenishment_units']} more ({s['replenishment_note']}).")
            why.append(f"Recipe: {m['quantity_per_unit']} {m['unit']} of {line['material']} per unit (materials.csv).")
    if rule.get("listing"):
        if not (st and rule["trigger"].get("type") == "low_stock" and topup_packs(st, line["pack_size"])):
            why.append(f"You order {line['packs']} pack(s) of {line['pack_size']} each time (change it in the rule).")
    else:
        why.append(f"Total {line['material']} needed: {line['quantity_needed']} → {line['packs']} pack(s) of {line['pack_size']}.")
    why.append(f"Price: MYR {line['unit_price']} per pack listed by {po['supplier_name']} (retrieved {po.get('retrieved_at', '')[:10]}) → MYR {line['line_total']}.")
    if line.get("needs_review"):
        why.append("Check before paying: " + ", ".join(line.get("review_reasons", [])) + ".")
    sources.append(po.get("source_url", ""))
    return {"ok": True, "po": po, "line": line, "total": po["total"], "why": why, "sources": [s for s in sources if s]}


def low_stock(rule) -> tuple[bool, str]:
    st = stock_of(rule["business_id"], rule["material"])
    if st and st.get("threshold"):
        low = float(st["qty"]) <= float(st["threshold"])
        return low, f"{rule['material']} {st['qty']:g} {st['unit']} vs low level {st['threshold']:g} {st['unit']}"
    pid = rule["trigger"].get("product_id")
    s = _read_json(OUTPUT / "ops_findings.json", {}).get("stock_and_replenishment", {}).get(pid) or {}
    if not s:
        return False, "no stock data"
    low = int(s.get("stock_on_hand", 0)) <= int(s.get("reorder_point", 0)) or bool(s.get("reorder_trigger"))
    return low, f"{s['product_name']} stock {s['stock_on_hand']} vs reorder point {s['reorder_point']}"


def due(rule, t: datetime) -> tuple[bool, str]:
    trig, last = rule["trigger"], rule.get("last_fired")
    last_dt = datetime.fromisoformat(last) if last else None
    if trig["type"] == "low_stock":
        low, why = low_stock(rule)
        if not low:
            return False, why
        po = (_po(rule["po_id"]) if rule.get("po_id") else None) or {}
        if po.get("status") == "paid":
            return False, why + " — already paid, waiting for delivery"
        return True, "stock is low: " + why
    hh, mm = map(int, trig.get("time", "09:00").split(":"))
    slot = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if trig["type"] == "schedule":
        if DAYS[t.weekday()] != trig.get("weekday", "Mon") or t < slot:
            return False, f"next run {trig.get('weekday')} {trig.get('time')}"
        return (last_dt is None or last_dt < slot), f"scheduled {trig.get('weekday')} {trig.get('time')}"
    if trig["type"] == "every_days":
        if last_dt is None:
            return t >= slot, f"every {trig.get('days')} days at {trig.get('time')}"
        return t >= last_dt + timedelta(days=int(trig.get("days", 7))), f"every {trig.get('days')} days"
    return False, "unknown trigger"


def supplier_message(rule, ex, business_name="Campus Crumb") -> str:
    l = ex["line"]
    return (f"Hi {rule['contact']['name'].split(' (')[0]}, this is {business_name}. "
            f"I'd like to order {l['packs']} x {l['pack_size']} {l['material']} "
            f"(MYR {l['unit_price']} each, total MYR {l['line_total']}) as listed on your page. "
            f"Could you confirm stock, delivery date and payment details? Order ref {ex['po']['order_id']}. Thank you!")


def wa_link(phone: str, text: str) -> str:
    return f"https://wa.me/{''.join(ch for ch in phone if ch.isdigit())}?text={urllib.parse.quote(text)}"


def tg_send(text: str) -> str:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return "not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to send for real)"
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=15).read()
        return "sent"
    except Exception as exc:  # report, never crash the engine
        return f"failed: {exc}"


def outbox_add(d, order_id, to, channel, phone, text, purpose):
    msg = {"id": "M" + uuid.uuid4().hex[:6], "order_id": order_id, "at": iso(), "to": to, "channel": channel,
           "purpose": purpose, "text": text, "status": "ready — tap to send"}
    if channel == "whatsapp":
        msg["link"] = wa_link(phone, text)
    elif channel == "telegram":
        msg["link"] = f"https://t.me/share/url?url=&text={urllib.parse.quote(text)}"
    d["outbox"].append(msg)
    return msg


def fire(d, rule, reason) -> dict | None:
    if any(o for o in d["orders"] if o["rule_id"] == rule["id"] and o["status"] == "awaiting_approval"):
        return None  # one open order per rule
    ex = explain(rule)
    rule["last_fired"] = iso()
    if not ex["ok"]:
        log(d, f"{rule['name']}: could not prepare order — {ex['why'][0]}", "error", rule_id=rule["id"])
        return None
    order = {"id": "AO-" + now().strftime("%m%d%H%M%S"), "rule_id": rule["id"], "business_id": rule["business_id"],
             "created_at": iso(), "trigger": reason, "material": ex["line"]["material"], "supplier": ex["po"]["supplier_name"],
             "po_id": ex["po"]["order_id"], "quantity": f"{ex['line']['packs']} x {ex['line']['pack_size']}",
             "total_myr": ex["total"], "why": ex["why"], "sources": ex["sources"], "status": "awaiting_approval",
             "supplier_message": supplier_message(rule, ex), "contact": rule["contact"]}
    d["orders"].append(order)
    outbox_add(d, order["id"], rule["contact"]["name"], rule["contact"]["channel"], rule["contact"].get("phone", ""),
               order["supplier_message"], "order request (send now; payment waits for your approval)")
    log(d, f"Auto-reorder fired: {rule['name']} — {reason}. Order {order['id']} MYR {order['total_myr']} waiting for your payment approval.",
        "order", rule_id=rule["id"], order_id=order["id"])
    return order


def check(force_rule: str | None = None) -> list[dict]:
    with LOCK:
        d, t, made = load(), now(), []
        for r in d["rules"]:
            if force_rule and r["id"] != force_rule:
                continue
            if not r.get("enabled") and not force_rule:
                continue
            ok, reason = (True, "run manually by the owner") if force_rule else due(r, t)
            if ok:
                o = fire(d, r, reason)
                if o:
                    made.append(o)
        if force_rule is None:
            d["last_check"] = iso()
        save(d)
        return made


def decide(order_id: str, approve: bool, mark_paid=None) -> dict:
    with LOCK:
        d = load()
        o = next((x for x in d["orders"] if x["id"] == order_id), None)
        if not o or o["status"] != "awaiting_approval":
            raise ValueError("order not found or already decided")
        if not approve:
            o["status"], o["decided_at"] = "rejected", iso()
            log(d, f"Owner rejected {o['id']} ({o['material']}). Nothing paid.", "reject", order_id=o["id"])
            save(d)
            return o
        note = ""
        if mark_paid and not o["po_id"].startswith("LST-"):
            try:
                mark_paid(o["po_id"])
            except Exception as exc:
                note = f" (PO state: {exc})"
        o["status"], o["decided_at"] = "paid_simulated", iso()
        conf = (f"Payment confirmation (SIMULATED): {o['supplier']} — {o['quantity']} {o['material']}, MYR {o['total_myr']}, ref {o['po_id']}. "
                f"Please confirm delivery date. Thank you!")
        outbox_add(d, o["id"], o["contact"]["name"], o["contact"]["channel"], o["contact"].get("phone", ""), conf, "payment confirmation to supplier")
        summary = (f"Enterprise Buddy: you approved {o['po_id']} — {o['quantity']} {o['material']} from {o['supplier']}, MYR {o['total_myr']} (simulated payment).\n"
                   "Why: " + " ".join(o["why"][:3]) + "\nVerify: " + ", ".join(o["sources"][-2:]))
        tg = tg_send(summary)
        d["outbox"].append({"id": "M" + uuid.uuid4().hex[:6], "order_id": o["id"], "at": iso(), "to": "Owner (you)", "channel": "telegram",
                            "purpose": "owner payment summary", "text": summary, "status": "telegram " + tg})
        log(d, f"Owner approved payment for {o['id']} — MYR {o['total_myr']} (simulated){note}. Confirmation prepared; Telegram {tg}.", "paid", order_id=o["id"])
        save(d)
        return o


def create_rule(business_id: str, material: str, listing: dict | None, product_id: str | None) -> dict:
    """Turn on auto-reorder for an ingredient: reuse its Enterprise Buddy purchase order if one exists, else its best listing."""
    with LOCK:
        d = load()
        existing = next((r for r in d["rules"] if r["business_id"] == business_id and r["material"].lower() == material.lower()), None)
        if existing:
            existing["enabled"] = True
            save(d)
            return existing
        doc = _read_json(OUTPUT / "purchase_orders.json", {})
        po = next((p for p in doc.get("purchase_orders", []) if any(l["material"].lower() == material.lower() for l in p["lines"])), None)
        if po and listing and listing.get("source_url") and po.get("source_url") != listing["source_url"]:
            po = None  # the owner chose a different supplier than the drafted PO
        rid = "R" + uuid.uuid4().hex[:5]
        rule = {"id": rid, "business_id": business_id, "name": f"{material} — auto-reorder", "material": material,
                "trigger": {"type": "low_stock", "product_id": product_id} if product_id else {"type": "schedule", "weekday": "Mon", "time": "09:00"},
                "contact": {"channel": "whatsapp", "name": ((po or {}).get("supplier_name") or (listing or {}).get("supplier", "Supplier")) + " (demo contact)", "phone": "60110000009"},
                "enabled": True, "last_fired": None}
        if po:
            rule["po_id"] = po["order_id"]
        elif listing and listing.get("unit_price"):
            rule["listing"] = {k: listing.get(k) for k in ("supplier", "source_url", "unit_price", "pack", "retrieved_at")} | {"packs": 1}
        else:
            raise ValueError("No supplier with a listed price for this ingredient yet — ask for a quote first.")
        d["rules"].append(rule)
        log(d, f"Auto-reorder turned on for {material}", "info", rule_id=rid)
        save(d)
        return rule


def remove_stock(bid: str, material: str) -> dict | None:
    with LOCK:
        d = stock_all()
        hit = d.get(bid, {}).pop(material, None)
        STOCKF.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        return hit


# ---------------------------------------------------------------- auto-posting (AI writes and posts on a schedule)

AUTOPOST_DEFAULT = {"enabled": True, "every_days": 2, "time": "12:30", "focus": "rotate", "platforms": ["Instagram"], "last_at": None, "count": 0}


def autopost(bid: str) -> dict:
    d = load()
    cfg = {**AUTOPOST_DEFAULT, **d.get("autopost", {}).get(bid, {})}
    nxt = sorted(s["at"] for s in d.get("autopost_plan", {}).get(bid, []) if s["status"] == "planned" and s["at"] >= now().isoformat(timespec="minutes"))
    cfg["next_at"] = (nxt[0] if nxt else _autopost_next(cfg)) if cfg["enabled"] else None
    return cfg


def _autopost_next(cfg) -> str | None:
    if not cfg.get("enabled"):
        return None
    hh, mm = (int(x) for x in str(cfg.get("time") or "12:30").split(":")[:2])
    base = datetime.fromisoformat(cfg["last_at"]) + timedelta(days=int(cfg.get("every_days") or 1)) if cfg.get("last_at") else now()
    nxt = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if not cfg.get("last_at") and nxt < now():
        nxt += timedelta(days=1)
    return iso(nxt)


def set_autopost(bid: str, patch: dict) -> dict:
    with LOCK:
        d = load()
        cfg = {**AUTOPOST_DEFAULT, **d.setdefault("autopost", {}).get(bid, {})}
        if "enabled" in patch:
            cfg["enabled"] = bool(patch["enabled"])
        if patch.get("every_days") not in (None, ""):
            cfg["every_days"] = max(1, min(14, int(patch["every_days"])))
        if patch.get("time"):
            cfg["time"] = str(patch["time"])[:5]
        if patch.get("focus") in ("rotate", "best_seller", "slow_seller"):
            cfg["focus"] = patch["focus"]
        if isinstance(patch.get("platforms"), list):
            cfg["platforms"] = [p for p in patch["platforms"] if p in ("Instagram", "Facebook", "TikTok")] or ["Instagram"]
        for k in ("last_at", "count", "last_post_id", "last_error"):
            if k in patch:
                cfg[k] = patch[k]
        d["autopost"][bid] = cfg
        log(d, f"Auto-post {'on' if cfg['enabled'] else 'off'} for {bid}: every {cfg['every_days']} day(s) at {cfg['time']}", "post")
        save(d)
    return autopost(bid)


def autopost_due() -> list[str]:
    out = []
    for bid in list(load().get("autopost", {})):
        cfg = autopost(bid)
        if cfg["enabled"] and cfg["next_at"] and datetime.fromisoformat(cfg["next_at"]) <= now():
            out.append(bid)
    return out


def publish_now(post_id: str) -> dict:
    with LOCK:
        d = load()
        p = next((x for x in d["posts"] if x["id"] == post_id), None)
        if not p:
            raise ValueError("unknown post")
        if p["status"] == "scheduled":
            p["status"], p["posted_at"] = "posted_simulated", iso()
            log(d, f"Posted now (ignoring schedule) to {', '.join(p.get('platforms', []))}", "post", post_id=p["id"])
            save(d)
        return p


def update_rule(rule_id: str, patch: dict) -> dict:
    with LOCK:
        d = load()
        r = next((x for x in d["rules"] if x["id"] == rule_id), None)
        if not r:
            raise ValueError("unknown rule")
        if "enabled" in patch:
            r["enabled"] = bool(patch["enabled"])
        if isinstance(patch.get("contact"), dict):
            for k in ("channel", "name", "phone"):
                if k in patch["contact"]:
                    r["contact"][k] = str(patch["contact"][k])[:80]
        if patch.get("packs") and r.get("listing"):
            r["listing"]["packs"] = max(1, min(int(patch["packs"]), 999))
        if isinstance(patch.get("trigger"), dict):
            t = patch["trigger"]
            if t.get("type") in ("low_stock", "schedule", "every_days"):
                r["trigger"] = {k: v for k, v in t.items() if k in ("type", "product_id", "weekday", "time", "days")}
        log(d, f"Rule {r['name']} updated", "info", rule_id=r["id"])
        save(d)
        return r


# ---------------------------------------------------------------- social posting

def save_media(name: str, data: bytes, context: str, business_id: str) -> dict:
    ext = Path(name).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"):
        raise ValueError("Upload a photo (jpg/png/webp) or a short video (mp4/mov/webm).")
    MEDIA.mkdir(parents=True, exist_ok=True)
    mid = "MD" + uuid.uuid4().hex[:8]
    path = MEDIA / (mid + ext)
    path.write_bytes(data)
    rec = {"id": mid, "file": path.relative_to(ROOT).as_posix(), "name": name[:120], "kind": "video" if ext in (".mp4", ".mov", ".webm") else "image",
           "context": context[:1000], "business_id": business_id, "uploaded_at": iso()}
    with LOCK:
        d = load()
        d.setdefault("media", []).append(rec)
        save(d)
    return rec


def add_post(post: dict) -> dict:
    with LOCK:
        d = load()
        post = {"id": "SP" + uuid.uuid4().hex[:6], "created_at": iso(), **post}
        post["status"] = "scheduled" if post.get("scheduled_for") else "posted_simulated"
        if post["status"] == "posted_simulated":
            post["posted_at"] = iso()
            log(d, f"Posted (simulated) to {', '.join(post.get('platforms', []))}: {post.get('caption', '')[:60]}…", "post", post_id=post["id"])
        else:
            log(d, f"Scheduled post for {post['scheduled_for']} on {', '.join(post.get('platforms', []))}", "post", post_id=post["id"])
        d["posts"].append(post)
        save(d)
        return post


def publish_due():
    with LOCK:
        d, t, changed = load(), now(), False
        for p in d["posts"]:
            if p["status"] == "scheduled" and datetime.fromisoformat(p["scheduled_for"]) <= t:
                p["status"], p["posted_at"], changed = "posted_simulated", iso(), True
                log(d, f"Scheduled post published (simulated) to {', '.join(p.get('platforms', []))}", "post", post_id=p["id"])
        if changed:
            save(d)


def engine_loop(stop: threading.Event, interval=30):
    while not stop.wait(interval):
        try:
            check()
            publish_due()
        except Exception as exc:  # keep the engine alive
            with LOCK:
                d = load()
                log(d, f"automation engine error: {exc}", "error")
                save(d)
