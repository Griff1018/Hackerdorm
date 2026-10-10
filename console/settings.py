"""App settings, app connections, the demo online shop menu and the owner's own sales log.

data/workspace/settings.json  — {"app": {...}, "connections": {bid: {app_id: {...}}}, "shop_menu": {bid: [...]}}
data/workspace/sales_log.json — sales the owner records by hand (walk-in / bazaar / cash sales)

Connections are SIMULATED links: Enterprise Buddy only stores the public page or shop handle the owner types.
It never asks for or stores passwords, tokens, bank or card details.
"""
from __future__ import annotations

import csv
import threading
import uuid
from datetime import date

import workspace as ws

SETTINGS = ws.WS / "settings.json"
SALES = ws.WS / "sales_log.json"
LOCK = threading.Lock()

MODES = ("approve_at_end", "ask_me", "auto")
STYLES = ("smart", "plan")
DEFAULT_APP = {"mode": "approve_at_end", "answer_style": "smart", "owner_name": "", "currency": "MYR"}

# kind: social / merchant. live = a demo app in this project that really exchanges data with Enterprise Buddy.
APPS = [
    {"id": "instagram", "kind": "social", "name": "Instagram", "icon": "📸", "live": True, "portal": "/instagram/",
     "what": "Scheduled posts go out to your feed; DMs land in Messages."},
    {"id": "linkedin", "kind": "social", "name": "LinkedIn", "icon": "💼", "live": True, "portal": "/linkedin/",
     "what": "Job posts and Easy Apply candidates for hiring helpers."},
    {"id": "whatsapp", "kind": "social", "name": "WhatsApp Business", "icon": "💬", "live": True, "portal": "/whatsapp/",
     "what": "Customer chats land in Messages; auto-reply can take orders."},
    {"id": "facebook", "kind": "social", "name": "Facebook Page", "icon": "📘", "live": False, "portal": None,
     "what": "Share your posts to your page (simulated link)."},
    {"id": "tiktok", "kind": "social", "name": "TikTok", "icon": "🎵", "live": False, "portal": None,
     "what": "Post short videos from your campaign drafts (simulated link)."},
    {"id": "shop", "kind": "merchant", "name": "Enterprise Buddy Shop (your website)", "icon": "🛍️", "live": True, "portal": "/shop/",
     "what": "Your own online ordering page. Orders land in Orders and count in the Dashboard."},
    {"id": "shopee", "kind": "merchant", "name": "Shopee", "icon": "🧡", "live": True, "portal": "/shopee/",
     "what": "The demo Shopee shop (storefront + Seller Centre). Its orders, buyers, chats and reviews flow into Enterprise Buddy; the Shopee agent proposes actions you approve."},
    {"id": "grabfood", "kind": "merchant", "name": "GrabFood", "icon": "🟢", "live": False, "portal": None,
     "what": "Delivery orders from GrabFood (simulated link)."},
    {"id": "foodpanda", "kind": "merchant", "name": "foodpanda", "icon": "🩷", "live": False, "portal": None,
     "what": "Delivery orders from foodpanda (simulated link)."},
    {"id": "bank", "kind": "payments", "name": "Online banking (DuitNow / FPX)", "icon": "", "live": False, "portal": None,
     "what": "Incoming transfers appear in Money Flow and are matched to orders (simulated feed — no bank login is ever stored)."},
    {"id": "tng", "kind": "payments", "name": "Touch 'n Go eWallet", "icon": "", "live": False, "portal": None,
     "what": "eWallet payments appear in Money Flow and are matched to orders (simulated feed — no PIN or login is ever stored)."},
]
APP_IDS = {a["id"] for a in APPS}
DEFAULT_ON = {"instagram", "linkedin", "whatsapp", "shop"}


def _load() -> dict:
    d = ws._read(SETTINGS, {})
    d.setdefault("app", {})
    d["app"] = {**DEFAULT_APP, **d["app"]}
    d.setdefault("connections", {})
    d.setdefault("shop_menu", {})
    return d


def app() -> dict:
    return _load()["app"]


def save_app(patch: dict) -> dict:
    with LOCK:
        d = _load()
        if patch.get("mode") in MODES:
            d["app"]["mode"] = patch["mode"]
        if patch.get("answer_style") in STYLES:
            d["app"]["answer_style"] = patch["answer_style"]
        if "owner_name" in patch:
            d["app"]["owner_name"] = str(patch["owner_name"]).strip()[:60]
        ws._write(SETTINGS, d)
        return d["app"]


def connections(bid: str) -> list[dict]:
    saved = _load()["connections"].get(bid, {})
    out = []
    for a in APPS:
        c = saved.get(a["id"]) or {"connected": a["id"] in DEFAULT_ON, "handle": ""}
        out.append({**a, "connected": bool(c.get("connected")), "handle": c.get("handle", ""), "connected_at": c.get("at")})
    return out


def connected(bid: str, app_id: str) -> bool:
    return next((c["connected"] for c in connections(bid) if c["id"] == app_id), False)


def set_connection(bid: str, app_id: str, on: bool, handle: str = "") -> dict:
    if app_id not in APP_IDS:
        raise ValueError("unknown app")
    with LOCK:
        d = _load()
        d["connections"].setdefault(bid, {})[app_id] = {"connected": bool(on), "handle": str(handle).strip()[:80], "at": ws.now()}
        ws._write(SETTINGS, d)
    return next(c for c in connections(bid) if c["id"] == app_id)


# ---------------------------------------------------------------- LinkedIn company page (owner-edited fields)

LI_FIELDS = ("tagline", "industry", "location", "hq", "website", "size", "founded", "overview", "specialties", "industryTags", "followers")


def linkedin_profile(bid: str) -> dict:
    return _load().get("linkedin_profile", {}).get(bid, {})


def save_linkedin_profile(bid: str, patch: dict) -> dict:
    clean = {}
    for k in LI_FIELDS:
        if k not in patch:
            continue
        v = patch[k]
        if k in ("specialties", "industryTags"):
            v = [str(x).strip()[:40] for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()][:10]
        elif k in ("founded", "followers"):
            try:
                v = max(0, int(v))
            except (TypeError, ValueError):
                continue
        else:
            v = str(v).strip()[:1500 if k == "overview" else 160]
        clean[k] = v
    with LOCK:
        d = _load()
        d.setdefault("linkedin_profile", {}).setdefault(bid, {}).update(clean)
        ws._write(SETTINGS, d)
        return d["linkedin_profile"][bid]


# ---------------------------------------------------------------- shop menu (what the online shop sells)

def _sample_menu() -> list[dict]:
    try:
        with (ws.ROOT / "data" / "sample" / "menu.csv").open(newline="", encoding="utf-8-sig") as f:
            return [{"item": r["item_name"], "price": float(r["price"]), "note": r.get("allergens_note", "").replace("; synthetic note", "")}
                    for r in csv.DictReader(f) if r.get("available", "yes") == "yes"]
    except (OSError, ValueError, KeyError):
        return []


def shop_menu(bid: str) -> list[dict]:
    saved = _load()["shop_menu"].get(bid)
    if saved is not None:
        return saved
    return _sample_menu() if (ws.business(bid) or {}).get("uses_sample_data") else []


def save_shop_menu(bid: str, rows: list[dict]) -> list[dict]:
    clean = []
    for r in rows[:40]:
        name = str(r.get("item", "")).strip()[:80]
        try:
            price = round(float(r.get("price")), 2)
        except (TypeError, ValueError):
            continue
        if name and price >= 0:
            item = {"item": name, "price": price, "note": str(r.get("note", "")).strip()[:120]}
            try:
                item["cost"] = round(float(r["cost"]), 2) if r.get("cost") not in (None, "") else None
            except (TypeError, ValueError):
                item["cost"] = None
            clean.append(item)
    before = shop_menu(bid)
    with LOCK:
        d = _load()
        d["shop_menu"][bid] = clean
        ws._write(SETTINGS, d)
    try:  # auto-posting: new items and price changes get an announcement post (owner can abort it)
        import social
        social.menu_changed(bid, before, clean)
    except Exception:
        pass
    return clean


def price_cart(bid: str, cart: list[dict]) -> tuple[list[dict], float]:
    """Price a cart from the shop menu only (the customer's page never sets prices)."""
    menu = {m["item"]: m for m in shop_menu(bid)}
    lines, total = [], 0.0
    for c in cart or []:
        m = menu.get(str(c.get("item", "")))
        try:
            qty = max(0, min(99, int(c.get("qty") or 0)))
        except (TypeError, ValueError):
            qty = 0
        if m and qty:
            lt = round(m["price"] * qty, 2)
            total += lt
            lines.append({"item": m["item"], "qty": qty, "price": f"{m['price']:.2f}", "line_total": f"{lt:.2f}"})
    return lines, round(total, 2)


# ---------------------------------------------------------------- sales the owner records by hand

def sales(bid: str) -> list[dict]:
    return [s for s in ws._read(SALES, []) if s.get("business_id") == bid]


def add_sale(bid: str, s: dict) -> dict:
    try:
        qty = max(1, int(s.get("qty") or 1))
        price = round(float(s.get("price")), 2)
    except (TypeError, ValueError):
        raise ValueError("Give a quantity and a price per item.")
    item = str(s.get("item", "")).strip()[:80]
    if not item:
        raise ValueError("Which item did you sell?")
    try:
        day = date.fromisoformat(str(s.get("date") or date.today().isoformat())[:10]).isoformat()
    except ValueError:
        day = date.today().isoformat()
    cost = None
    if s.get("cost") not in (None, ""):
        try:
            cost = round(float(s["cost"]), 2)
        except (TypeError, ValueError):
            cost = None
    if cost is None:  # fall back to the cost saved on the shop menu
        cost = next((m.get("cost") for m in shop_menu(bid) if m["item"].lower() == item.lower()), None)
    row = {"id": "S" + uuid.uuid4().hex[:6], "business_id": bid, "date": day, "item": item, "qty": qty, "price": price,
           "cost": cost, "channel": str(s.get("channel") or "walk-in")[:30], "note": str(s.get("note", ""))[:200], "created_at": ws.now()}
    with LOCK:
        rows = ws._read(SALES, [])
        rows.append(row)
        ws._write(SALES, rows)
    return row


def delete_sale(sid: str) -> bool:
    with LOCK:
        rows = ws._read(SALES, [])
        keep = [s for s in rows if s["id"] != sid]
        ws._write(SALES, keep)
        return len(keep) != len(rows)
