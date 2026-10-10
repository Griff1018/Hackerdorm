"""Mock Shopee marketplace (Python port of ShopeeAgent's `shopee/server`): one SQLite world with a simulated clock.

A time-stepped engine turns traffic into views → carts → orders (price elasticity, perceived rating, listing quality,
boosts, campaign days), and a schedule of future events drives payment, shipping, courier tracking, delivery, issues,
returns, reviews and buyer chats. The shop ("UrbanNest Lifestyle") has deliberately planted problems for the agent
to discover from data: a fragile mug with thin packaging, a tee that runs small, a defective earbuds batch, a cable
about to sell out, a board losing traffic to a competitor, a tumbler price hike, an underpriced lamp, a weak bedsheet
listing and a strong phone case worth promoting.

Every surface (storefront, Seller Centre, the Enterprise Buddy agent) calls the same service functions, so an action
has the same effect wherever it comes from. Timestamps are unix seconds of simulated time (Malaysia, UTC+8).

data/shopee/shopee_seed.db.gz  baseline world (60 days of history) — copied to data/shopee/shopee.db on first use / reset
data/shopee/sim_text.json      review / chat wording, couriers, payment methods (exported from the original TypeScript)
"""
from __future__ import annotations

import gzip
import json
import math
import random
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "shopee"
DB_PATH = DIR / "shopee.db"
SEED_GZ = DIR / "shopee_seed.db.gz"
TEXT = json.loads((DIR / "sim_text.json").read_text(encoding="utf-8"))

HOUR, DAY = 3600, 86400
TZ = timezone(timedelta(hours=8))
SHOP_ID = 880011
DEMO_BUYER = 1

LOCK = threading.RLock()
_conn: sqlite3.Connection | None = None


class ShopeeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise ShopeeError(code, message)


# ---------------------------------------------------------------- database

def _shift_world(c: sqlite3.Connection, days: int):
    """Move the whole world by whole days (so date keys stay valid) — used to line the seed up with today."""
    d = days * DAY
    cols = {
        "shop": ["joined_time"], "items": ["create_time", "update_time", "boost_until"], "price_history": ["changed_at"],
        "orders": ["create_time", "update_time", "pay_time", "ship_by_date", "ship_time", "pickup_time", "delivered_time", "complete_time"],
        "tracking_events": ["ts"], "returns": ["create_time", "update_time", "due_date"], "comments": ["create_time", "reply_time"],
        "conversations": ["last_message_time", "last_buyer_message_time"], "messages": ["created_timestamp"], "carts": ["added_time"],
        "sched": ["due"], "penalties": ["ts"], "events": ["ts"],
    }
    for t, cs in cols.items():
        for col in cs:
            c.execute(f"UPDATE {t} SET {col} = {col} + ? WHERE {col} IS NOT NULL AND {col} > 0", (d,))
    c.execute("CREATE TEMP TABLE ids AS SELECT item_id, date(date, ?) date, views, add_to_cart, orders, units, sales FROM item_daily_stats", (f"{days:+d} days",))
    c.execute("DELETE FROM item_daily_stats")
    c.execute("INSERT INTO item_daily_stats SELECT * FROM ids")
    c.execute("DROP TABLE ids")
    meta = dict(c.execute("SELECT key, value FROM meta"))
    for k in ("epoch", "sim_now"):
        c.execute("UPDATE meta SET value = ? WHERE key = ?", (str(int(json.loads(meta[k])) + d), k))
    mods = [dict(m, until=m["until"] + d) for m in json.loads(meta.get("modifiers", "[]"))]
    c.execute("UPDATE meta SET value = ? WHERE key = 'modifiers'", (json.dumps(mods),))
    dis = {k: v + d for k, v in json.loads(meta.get("disruption", "{}")).items()}
    c.execute("UPDATE meta SET value = ? WHERE key = 'disruption'", (json.dumps(dis),))


def install(force=False):
    """Create data/shopee/shopee.db from the seed, lined up so simulated 'now' is just before real now."""
    with LOCK:
        global _conn
        if DB_PATH.exists() and not force:
            return
        if _conn:
            _conn.close()
            _conn = None
        for p in (DB_PATH, DB_PATH.with_name("shopee.db-wal"), DB_PATH.with_name("shopee.db-shm")):
            p.unlink(missing_ok=True)
        tmp = DB_PATH.with_suffix(".tmp")
        with gzip.open(SEED_GZ, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        c = sqlite3.connect(tmp)
        sim_now = int(json.loads(c.execute("SELECT value FROM meta WHERE key='sim_now'").fetchone()[0]))
        days = math.floor((time.time() - sim_now) / DAY)
        _shift_world(c, days)
        c.execute("UPDATE meta SET value = '1' WHERE key = 'speed'")
        c.execute("UPDATE meta SET value = 'false' WHERE key = 'paused'")
        c.commit()
        c.close()
        tmp.replace(DB_PATH)
        clock.loaded = False


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if not DB_PATH.exists():
            install()
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=15)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.execute("PRAGMA synchronous = NORMAL")
        _conn.execute("PRAGMA busy_timeout = 15000")
    return _conn


def all_(sql, *p) -> list[dict]:
    with LOCK:
        return [dict(r) for r in db().execute(sql, p).fetchall()]


def get(sql, *p) -> dict | None:
    with LOCK:
        r = db().execute(sql, p).fetchone()
        return dict(r) if r else None


def run(sql, *p):
    with LOCK:
        return db().execute(sql, p)


class _Tx:
    depth = 0

    def __enter__(self):
        LOCK.acquire()
        if _Tx.depth == 0:
            db().execute("BEGIN IMMEDIATE")
        _Tx.depth += 1

    def __exit__(self, et, ev, tb):
        _Tx.depth -= 1
        try:
            if _Tx.depth == 0:
                db().execute("ROLLBACK" if et else "COMMIT")
        finally:
            LOCK.release()


def tx():
    return _Tx()


def jl(s, default):
    try:
        return json.loads(s) if s else default
    except (TypeError, json.JSONDecodeError):
        return default


def get_meta(key, default=None):
    r = get("SELECT value FROM meta WHERE key = ?", key)
    if not r:
        return default
    try:
        return json.loads(r["value"])
    except json.JSONDecodeError:
        return r["value"]


def set_meta(key, value):
    run("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", key, json.dumps(value))


# ---------------------------------------------------------------- clock, time helpers, randomness

class Clock:
    loaded = False
    now = 0
    speed = 1
    paused = False

    def load(self):
        if not self.loaded:
            self.now = int(get_meta("sim_now", int(time.time())))
            self.speed = float(get_meta("speed", 1))
            self.paused = bool(get_meta("paused", False))
            self.loaded = True

    def save(self):
        set_meta("sim_now", int(self.now))
        set_meta("speed", self.speed)
        set_meta("paused", self.paused)


clock = Clock()


def now() -> int:
    clock.load()
    return int(clock.now)


def local(ts):
    return datetime.fromtimestamp(ts, TZ)


def date_key(ts) -> str:
    return local(ts).strftime("%Y-%m-%d")


def yymmdd(ts) -> str:
    return local(ts).strftime("%y%m%d")


class Rng(random.Random):
    def chance(self, p):
        return self.random() < p

    def pick(self, arr):
        return arr[int(self.random() * len(arr))]

    def weighted(self, entries):
        total = sum(w for _, w in entries)
        r = self.random() * total
        for v, w in entries:
            r -= w
            if r <= 0:
                return v
        return entries[-1][0]

    def int_(self, lo, hi):
        return int(math.floor(lo + (hi - lo + 1) * self.random()))

    def poisson(self, lam):
        if lam <= 0:
            return 0
        if lam > 30:
            return max(0, round(self.gauss(lam, math.sqrt(lam))))
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            k += 1
            p *= self.random()
            if p <= L:
                return k - 1

    def binomial(self, n, p):
        if n > 60:
            return max(0, min(n, round(self.gauss(n * p, math.sqrt(max(1e-9, n * p * (1 - p)))))))
        return sum(1 for _ in range(n) if self.random() < p)

    def code(self, n, alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"):
        return "".join(alphabet[int(self.random() * len(alphabet))] for _ in range(n))


rng = Rng(int(time.time() * 1000) & 0xFFFFFFFF)


def fill(tpl, **v):
    return re.sub(r"\{(\w+)\}", lambda m: str(v.get(m.group(1), "")), tpl)


def short(s, n=42):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- events (activity feed)

def emit(etype, summary, payload=None):
    run("INSERT INTO events(ts, real_ts, type, summary, payload) VALUES(?,?,?,?,?)", now(), int(time.time() * 1000), etype, summary, json.dumps(payload or {}))


def events(since_id=0, limit=60):
    return all_("SELECT id, ts, type, summary FROM events WHERE id > ? ORDER BY id DESC LIMIT ?", since_id, limit)


# ---------------------------------------------------------------- products & ratings

def get_item(item_id):
    return get("SELECT * FROM items WHERE item_id = ?", item_id)


def get_model(model_id):
    return get("SELECT * FROM models WHERE model_id = ?", model_id)


def models_of(item_id):
    return all_("SELECT * FROM models WHERE item_id = ? ORDER BY model_id", item_id)


def _base_distribution(avg, count):
    p5 = min(0.95, max(0.3, (avg - 3.6) / 1.35))
    rest = 1 - p5
    w = [x * rest for x in (0.12, 0.08, 0.2, 0.6)]
    return [round(x * count) for x in (*w, p5)]


def item_rating(item_id):
    it = get("SELECT base_rating, base_rating_count FROM items WHERE item_id = ?", item_id)
    dist = _base_distribution(it["base_rating"], it["base_rating_count"]) if it else [0] * 5
    for r in all_("SELECT rating_star, COUNT(*) n FROM comments WHERE item_id = ? GROUP BY rating_star", item_id):
        dist[r["rating_star"] - 1] += r["n"]
    n = sum(dist)
    s = sum(c * (i + 1) for i, c in enumerate(dist))
    return {"rating_star": round(s / n, 2) if n else 0, "rating_count": n, "rating_count_by_star": dist}


def shop_rating():
    n = s = 0
    for r in all_("SELECT item_id FROM items WHERE item_status != 'DELETED'"):
        x = item_rating(r["item_id"])
        n += x["rating_count"]
        s += x["rating_star"] * x["rating_count"]
    return {"rating_star": round(s / n, 2) if n else 0, "rating_count": n}


def perceived_rating(item_id, since):
    life = item_rating(item_id)["rating_star"]
    rec = get("SELECT AVG(rating_star) avg, COUNT(*) n FROM comments WHERE item_id = ? AND create_time >= ?", item_id, since)
    if not rec or not rec["n"] or rec["avg"] is None:
        return life
    w = min(0.5, rec["n"] / 20)
    return life * (1 - w) + rec["avg"] * w


def listing_score(title, description):
    title, d = (title or "").strip(), (description or "").strip()
    tl, words = len(title), len(title.split())
    ts = 0.25 if tl < 15 else 0.55 if tl < 35 else (1 if words >= 6 else 0.8) if tl <= 120 else 0.8
    bullets = sum(1 for ln in d.split("\n") if re.match(r"^\s*([-•✔✅▪*]|\d+\.)", ln))
    specs = bool(re.search(r"\d+\s?(cm|mm|ml|g|kg|inch|\"|tc|gsm|mah|w)\b", d, re.I))
    ds = 0.25 if len(d) < 60 else 0.55 if len(d) < 200 else 0.85
    ds = min(1, ds + (0.1 if bullets >= 3 else 0) + (0.05 if specs else 0))
    return {"title": ts, "description": ds, "traffic": 0.65 + 0.35 * ts, "conversion": 0.5 + 0.5 * ds}


def bump_stats(item_id, ts, views=0, add_to_cart=0, orders=0, units=0, sales=0.0):
    run("""INSERT INTO item_daily_stats(item_id, date, views, add_to_cart, orders, units, sales) VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(item_id, date) DO UPDATE SET views = views + excluded.views, add_to_cart = add_to_cart + excluded.add_to_cart,
           orders = orders + excluded.orders, units = units + excluded.units, sales = sales + excluded.sales""",
        item_id, date_key(ts), views, add_to_cart, orders, units, sales)


def update_price(item_id, price_list, source):
    """price_list: [{model_id, original_price}] — the new selling price per model."""
    it = get_item(item_id) or fail("error_not_found", f"item {item_id} not found")
    t = now()
    with tx():
        for p in price_list:
            m = get_model(int(p["model_id"]))
            if not m or m["item_id"] != it["item_id"]:
                fail("error_param", f"model {p['model_id']} does not belong to item {item_id}")
            new = round(float(p["original_price"]), 2)
            if not (0.1 <= new <= 100000):
                fail("error_param", "price out of range")
            if abs(new - m["price"]) >= 0.005:
                run("INSERT INTO price_history(item_id, model_id, old_price, new_price, changed_at, source) VALUES(?,?,?,?,?,?)", item_id, m["model_id"], m["price"], new, t, source)
                run("UPDATE models SET price = ?, original_price = MAX(original_price, ?) WHERE model_id = ?", new, new, m["model_id"])
        run("UPDATE items SET update_time = ? WHERE item_id = ?", t, item_id)
    emit("product.price", f"Price updated on “{short(it['item_name'], 40)}” via {source}", {"item_id": item_id})
    return {"item_id": item_id, "models": [{"model_id": m["model_id"], "price": m["price"]} for m in models_of(item_id)]}


def update_stock(item_id, stock_list, source):
    """stock_list: [{model_id, add}] adds units on top of live stock, or [{model_id, stock}] sets it."""
    it = get_item(item_id) or fail("error_not_found", f"item {item_id} not found")
    with tx():
        for s in stock_list:
            m = get_model(int(s["model_id"]))
            if not m or m["item_id"] != it["item_id"]:
                fail("error_param", f"model {s['model_id']} does not belong to item {item_id}")
            new = m["stock"] + int(s["add"]) if "add" in s else int(s["stock"])
            run("UPDATE models SET stock = ? WHERE model_id = ?", max(0, new), m["model_id"])
        run("UPDATE items SET update_time = ? WHERE item_id = ?", now(), item_id)
    emit("product.stock", f"Stock updated on “{short(it['item_name'], 40)}” via {source}", {"item_id": item_id})
    return {"item_id": item_id, "models": [{"model_id": m["model_id"], "stock": m["stock"]} for m in models_of(item_id)]}


def update_item(item_id, fields, source):
    it = get_item(item_id) or fail("error_not_found", f"item {item_id} not found")
    sets = {}
    if fields.get("item_name") is not None:
        name = str(fields["item_name"]).strip()
        if not (10 <= len(name) <= 120):
            fail("error_param", "item_name must be 10–120 characters")
        sets["item_name"] = name
    if fields.get("description") is not None:
        desc = str(fields["description"]).strip()
        if not (20 <= len(desc) <= 3000):
            fail("error_param", "description must be 20–3000 characters")
        sets["description"] = desc
    if fields.get("item_status") in ("NORMAL", "UNLIST"):
        sets["item_status"] = fields["item_status"]
    if not sets:
        fail("error_param", "nothing to update")
    run(f"UPDATE items SET {', '.join(k + ' = ?' for k in sets)}, update_time = ? WHERE item_id = ?", *sets.values(), now(), item_id)
    what = "listed again" if sets.get("item_status") == "NORMAL" else "unlisted" if sets.get("item_status") == "UNLIST" else "listing updated"
    emit("product.updated", f"“{short(it['item_name'], 40)}” {what} via {source}", {"item_id": item_id})
    return get_item(item_id)


def boost_item(item_id, source, hours=4):
    it = get_item(item_id) or fail("error_not_found", f"item {item_id} not found")
    if it["item_status"] != "NORMAL":
        fail("error_item_not_available", "only live items can be boosted")
    active = get("SELECT COUNT(*) n FROM items WHERE boost_until > ?", now())["n"]
    if it["boost_until"] <= now() and active >= 5:
        fail("error_boost_limit", "all 5 boost slots are in use")
    until = now() + hours * HOUR
    run("UPDATE items SET boost_until = ? WHERE item_id = ?", until, item_id)
    schedule(until, "boost_end", str(item_id))
    emit("product.boost", f"Boosted “{short(it['item_name'], 40)}” for {hours}h via {source}", {"item_id": item_id})
    return {"item_id": item_id, "boost_until": until}


# ---------------------------------------------------------------- scheduler

def schedule(due, kind, ref, payload=None):
    run("INSERT INTO sched(due, kind, ref, payload) VALUES(?,?,?,?)", int(due), kind, str(ref), json.dumps(payload or {}))


# ---------------------------------------------------------------- orders & logistics

CARRIERS = TEXT["CARRIERS"]
PAYMENT_METHODS = [tuple(x) for x in TEXT["PAYMENT_METHODS"]]
ORIGIN_HUB = TEXT["ORIGIN_HUB"]
SELLER_CANCEL_REASONS = ["OUT_OF_STOCK", "CUSTOMER_REQUEST", "UNDELIVERABLE_AREA", "COD_NOT_SUPPORTED"]


def get_order(sn):
    return get("SELECT * FROM orders WHERE order_sn = ?", sn)


def order_lines(sn):
    return all_("SELECT * FROM order_items WHERE order_sn = ?", sn)


def set_status(o, status, extra=None, summary=None):
    extra = extra or {}
    run(f"UPDATE orders SET order_status = ?, update_time = ?{''.join(f', {k} = ?' for k in extra)} WHERE order_sn = ?",
        status, now(), *extra.values(), o["order_sn"])
    emit("order.status", summary or f"Order {o['order_sn']} → {status}", {"order_sn": o["order_sn"], "from": o["order_status"], "to": status})


def set_sim(sn, **patch):
    o = get_order(sn)
    if o:
        run("UPDATE orders SET sim = ? WHERE order_sn = ?", json.dumps({**jl(o["sim"], {}), **patch}), sn)


def add_tracking(sn, status, desc, loc="", ts=None):
    run("INSERT INTO tracking_events(order_sn, ts, logistics_status, description, location) VALUES(?,?,?,?,?)", sn, ts or now(), status, desc, loc)
    run("UPDATE orders SET logistics_status = ? WHERE order_sn = ?", status, sn)


def _carrier(name):
    return next((c for c in CARRIERS if c["name"] == name), CARRIERS[0])


def auto_ship_rate():
    return float(get_meta("auto_ship_rate", 0.6))


def create_order(buyer_user_id, lines, payment_method, source="sim", message="", carrier=None):
    buyer = get("SELECT * FROM buyers WHERE buyer_user_id = ?", buyer_user_id) or fail("error_param", "buyer not found")
    t = now()
    rows = []
    for ln in lines:
        m = get_model(int(ln["model_id"])) or fail("error_param", f"model {ln['model_id']} not found")
        it = get_item(m["item_id"])
        if it["item_status"] != "NORMAL":
            fail("error_item_not_available", f"{it['item_name']} is not available")
        q = max(1, int(ln.get("quantity", 1)))
        if m["stock"] < q:
            fail("error_out_of_stock", f"Only {m['stock']} left for {short(it['item_name'], 40)} ({m['model_name']})")
        rows.append((m, it, q))
    if not rows:
        fail("error_param", "empty order")
    car = next((c for c in CARRIERS if c["name"] == carrier), None) or rng.weighted([(c, c["w"]) for c in CARRIERS])
    east = buyer["region_group"] == "east"
    subtotal = round(sum(m["price"] * q for m, _, q in rows), 2)
    buyer_ship = 0 if subtotal >= 30 else (8.9 if east else 4.9)
    actual_ship = car["cost"][1 if east else 0]
    cod = 1 if payment_method == "Cash on Delivery" else 0
    while True:
        sn = yymmdd(t) + rng.code(8)
        if not get_order(sn):
            break
    days = (get("SELECT days_to_ship FROM shop LIMIT 1") or {}).get("days_to_ship", 2)
    recipient = {"name": buyer["name"], "phone": buyer["phone"], "full_address": f"{buyer['address']}, {buyer['zipcode']} {buyer['city']}, {buyer['state']}",
                 "city": buyer["city"], "state": buyer["state"], "zipcode": buyer["zipcode"], "region": "MY"}
    with tx():
        run("""INSERT INTO orders(order_sn, shop_id, buyer_user_id, buyer_username, order_status, create_time, update_time, pay_time,
               ship_by_date, days_to_ship, payment_method, cod, currency, subtotal, total_amount, buyer_shipping_fee, actual_shipping_fee,
               shipping_carrier, recipient, message_to_seller, logistics_status, sim) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            sn, SHOP_ID, buyer["buyer_user_id"], buyer["username"], "READY_TO_SHIP" if cod else "UNPAID", t, t, None, t + days * DAY, days,
            payment_method, cod, "MYR", subtotal, round(subtotal + buyer_ship, 2), buyer_ship, actual_ship, car["name"], json.dumps(recipient),
            message or "", "LOGISTICS_NOT_START", "{}")
        for m, it, q in rows:
            run("""INSERT INTO order_items(order_sn, item_id, model_id, item_name, model_name, item_sku, model_sku, quantity, original_price, discounted_price)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""", sn, it["item_id"], m["model_id"], it["item_name"], m["model_name"], it["item_sku"], m["model_sku"], q,
                m["original_price"], m["price"])
            run("UPDATE models SET stock = MAX(0, stock - ?) WHERE model_id = ?", q, m["model_id"])
            bump_stats(it["item_id"], t, orders=1, units=q, sales=m["price"] * q)
    o = get_order(sn)
    emit("order.created", f"New order {sn} from {buyer['username']} – RM{o['total_amount']:.2f} ({', '.join(short(it['item_name'], 28) for _, it, _ in rows)})",
         {"order_sn": sn, "total": o["total_amount"], "source": source})
    if cod:
        _on_ready_to_ship(o)
    elif source == "storefront":
        mark_paid(sn)
    else:
        roll = rng.random()
        if roll < 0.9:
            schedule(t + rng.int_(60, 3600), "pay", sn)
        elif roll < 0.975:
            schedule(t + rng.int_(HOUR, 12 * HOUR), "pay", sn)
        else:
            schedule(t + DAY, "unpaid_cancel", sn)
    return sn


def mark_paid(sn):
    o = get_order(sn)
    if not o or o["order_status"] != "UNPAID":
        return
    t = now()
    set_status(o, "READY_TO_SHIP", {"pay_time": t, "ship_by_date": t + o["days_to_ship"] * DAY}, f"Order {sn} paid via {o['payment_method']} – ready to ship")
    _on_ready_to_ship(get_order(sn))


def _on_ready_to_ship(o):
    t = now()
    if rng.chance(auto_ship_rate()):
        schedule(t + rng.int_(2 * HOUR, max(3 * HOUR, min(36 * HOUR, o["ship_by_date"] - t - HOUR))), "auto_ship", o["order_sn"])
    schedule(o["ship_by_date"], "ship_deadline", o["order_sn"])
    schedule(o["ship_by_date"] + 2 * DAY, "late_cancel", o["order_sn"])
    if rng.chance(0.025):
        schedule(t + rng.int_(HOUR, 20 * HOUR), "buyer_cancel_req", o["order_sn"])
    if rng.chance(0.25):
        schedule(t + rng.int_(26 * HOUR, 40 * HOUR), "buyer_msg", o["order_sn"], {"intent": "order_status"})


def ship_order(sn, by, mode="pickup"):
    o = get_order(sn) or fail("error_not_found", f"order {sn} not found")
    if o["order_status"] == "IN_CANCEL":
        fail("error_order_status", f"order {sn} has a pending buyer cancellation request – respond to it first")
    if o["order_status"] != "READY_TO_SHIP":
        fail("error_order_status", f"order {sn} is {o['order_status']}, cannot arrange shipment")
    car = _carrier(o["shipping_carrier"])
    tracking = car["prefix"] + rng.code(10, "0123456789") + ("MY" if car["prefix"] == "ER" else "")
    t = now()
    late = 1 if t > o["ship_by_date"] else o["late_flag"]
    set_status(o, "PROCESSED", {"tracking_number": tracking, "ship_time": t, "shipped_by": by, "late_flag": late},
               f"Order {sn} arranged for {mode} ({car['name']}) by {by}")
    add_tracking(sn, "LOGISTICS_REQUEST_CREATED", f"Seller has arranged shipment. {'Courier will pick up the parcel.' if mode == 'pickup' else 'Parcel will be dropped off.'}", "Shah Alam")
    schedule(t + rng.int_(3 * HOUR, 20 * HOUR), "pickup", sn)
    return {"order_sn": sn, "tracking_number": tracking}


def pickup(sn):
    o = get_order(sn)
    if not o or o["order_status"] != "PROCESSED":
        return
    car = _carrier(o["shipping_carrier"])
    until = get_meta("disruption", {}).get(car["name"], 0)
    stuck = car["stuck"] + (0.45 if until > now() else 0)
    roll = rng.random()
    plan = "lost" if roll < car["lost"] else "stuck" if roll < car["lost"] + stuck else "failed" if roll < car["lost"] + stuck + car["failed"] else "normal"
    set_status(o, "SHIPPED", {"pickup_time": now()}, f"Order {sn} picked up by {car['name']}")
    add_tracking(sn, "LOGISTICS_PICKUP_DONE", f"Parcel has been picked up by {car['name']}", "Shah Alam")
    set_sim(sn, plan=plan, step=0)
    schedule(now() + rng.int_(4 * HOUR, 12 * HOUR), "track", sn)


def tracking_route(o):
    r = jl(o["recipient"], {})
    city = r.get("city", "")
    return [
        {"status": "LOGISTICS_IN_TRANSIT", "desc": f"Parcel has arrived at sorting facility: {ORIGIN_HUB}", "loc": ORIGIN_HUB, "gap": [2, 8]},
        {"status": "LOGISTICS_IN_TRANSIT", "desc": f"Parcel has departed from sorting facility: {ORIGIN_HUB}", "loc": ORIGIN_HUB, "gap": [8, 30]},
        {"status": "LOGISTICS_IN_TRANSIT", "desc": f"Parcel has arrived at delivery hub: {city} Hub", "loc": f"{city} Hub", "gap": [6, 14]},
        {"status": "LOGISTICS_DELIVERY_ON_GOING", "desc": "Parcel is out for delivery", "loc": city, "gap": [2, 8]},
    ]


def deliver(sn):
    o = get_order(sn)
    if not o or o["order_status"] != "SHIPPED":
        return
    r = jl(o["recipient"], {})
    add_tracking(sn, "LOGISTICS_DELIVERY_DONE", f"Parcel has been delivered. Received by {(r.get('name') or 'recipient').split(' ')[0]}", r.get("city", ""))
    set_status(o, "TO_CONFIRM_RECEIVE", {"delivered_time": now()}, f"Order {sn} delivered to {o['buyer_username']}")


def _restore_stock(sn, restock=True):
    if restock:
        for ln in order_lines(sn):
            run("UPDATE models SET stock = stock + ? WHERE model_id = ?", ln["quantity"], ln["model_id"])


def mark_lost(sn):
    o = get_order(sn)
    if not o or o["order_status"] != "SHIPPED":
        return
    add_tracking(sn, "LOGISTICS_LOST", "Parcel is lost in transit. Buyer will be refunded by Shopee.", "")
    set_status(o, "CANCELLED", {"cancel_by": "system", "cancel_reason": "LOGISTICS_LOST"}, f"Order {sn} cancelled – parcel lost by {o['shipping_carrier']}")


def confirm_received(sn, by):
    o = get_order(sn)
    if not o or o["order_status"] != "TO_CONFIRM_RECEIVE":
        return False
    set_status(o, "COMPLETED", {"complete_time": now()}, f"Order {sn} completed ({'buyer confirmed receipt' if by == 'buyer' else 'auto-confirmed'})")
    return True


def seller_cancel(sn, reason, by):
    o = get_order(sn) or fail("error_not_found", f"order {sn} not found")
    if o["order_status"] not in ("UNPAID", "READY_TO_SHIP"):
        fail("error_order_status", f"order {sn} is {o['order_status']}, cannot be cancelled by seller")
    if reason not in SELLER_CANCEL_REASONS:
        fail("error_param", f"cancel_reason must be one of {', '.join(SELLER_CANCEL_REASONS)}")
    _restore_stock(sn, reason != "OUT_OF_STOCK")
    set_status(o, "CANCELLED", {"cancel_by": "seller", "cancel_reason": reason, "note": f"cancelled by {by}"}, f"Order {sn} cancelled by seller ({reason}) via {by}")
    if reason == "OUT_OF_STOCK":
        add_penalty(1, "Non-fulfilment: seller cancelled order (out of stock)", sn)
    return {"order_sn": sn, "order_status": "CANCELLED"}


def buyer_request_cancel(sn, reason):
    o = get_order(sn)
    if not o or o["order_status"] != "READY_TO_SHIP":
        return False
    set_status(o, "IN_CANCEL", {"buyer_cancel_reason": reason}, f"Buyer {o['buyer_username']} requested to cancel {sn}: “{reason}”")
    schedule(now() + DAY, "cancel_autoaccept", sn)
    return True


def handle_buyer_cancellation(sn, operation, by):
    o = get_order(sn) or fail("error_not_found", f"order {sn} not found")
    if o["order_status"] != "IN_CANCEL":
        fail("error_order_status", f"order {sn} has no pending cancellation (status {o['order_status']})")
    if operation == "ACCEPT":
        _restore_stock(sn)
        set_status(o, "CANCELLED", {"cancel_by": "buyer", "cancel_reason": "BUYER_REQUEST", "note": f"cancellation accepted by {by}"}, f"Cancellation of {sn} accepted via {by}")
    elif operation == "REJECT":
        set_status(o, "READY_TO_SHIP", {"note": f"cancellation rejected by {by}"}, f"Cancellation of {sn} rejected via {by} – order must ship")
    else:
        fail("error_param", "operation must be ACCEPT or REJECT")
    return {"order_sn": sn, "order_status": get_order(sn)["order_status"]}


def add_penalty(points, reason, sn=None):
    run("INSERT INTO penalties(ts, points, reason, order_sn) VALUES(?,?,?,?)", now(), points, reason, sn)
    emit("shop.penalty", f"Penalty +{points}: {reason}{f' ({sn})' if sn else ''}", {"points": points, "order_sn": sn})


# ---------------------------------------------------------------- returns

RETURN_REASONS = TEXT["RETURN_REASONS"]


def get_return(sn):
    return get("SELECT * FROM returns WHERE return_sn = ?", sn)


def _ret_update(r, status, extra, summary):
    run(f"UPDATE returns SET status = ?, update_time = ?{''.join(f', {k} = ?' for k in extra)} WHERE return_sn = ?", status, now(), *extra.values(), r["return_sn"])
    emit("return.updated", summary, {"return_sn": r["return_sn"], "status": status})


def request_return(order_sn, tag, text=None):
    o = get_order(order_sn)
    if not o or o["order_status"] not in ("TO_CONFIRM_RECEIVE", "COMPLETED"):
        return None
    if get("SELECT 1 x FROM returns WHERE order_sn = ?", order_sn):
        return None
    ln = order_lines(order_sn)[0]
    rr = RETURN_REASONS.get(tag, RETURN_REASONS["quality"])
    t = now()
    sn = order_sn[:6] + "R" + rng.code(8, "0123456789")
    amount = round(ln["discounted_price"] * ln["quantity"], 2)
    run("""INSERT INTO returns(return_sn, order_sn, buyer_user_id, buyer_username, item_id, model_id, reason, text_reason, status, refund_amount, create_time, update_time, due_date)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", sn, order_sn, o["buyer_user_id"], o["buyer_username"], ln["item_id"], ln["model_id"], rr["reason"], text or rr["text"],
        "REQUESTED", amount, t, t, t + 3 * DAY)
    set_status(o, "TO_RETURN", {}, f"Return/refund requested for {order_sn} by {o['buyer_username']}: {rr['text']}")
    emit("return.requested", f"Return request {sn} ({rr['reason']}) – RM{amount:.2f}", {"return_sn": sn})
    schedule(t + 3 * DAY, "return_autoaccept", sn)
    return sn


def _settle(r):
    o = get_order(r["order_sn"])
    if o and o["order_status"] == "TO_RETURN":
        set_status(o, "COMPLETED", {"complete_time": o["complete_time"] or now()}, f"Order {o['order_sn']} settled after return {r['return_sn']}")


def accept_return(sn, by):
    r = get_return(sn) or fail("error_not_found", f"return {sn} not found")
    if r["status"] not in ("REQUESTED", "PROCESSING"):
        fail("error_return_status", f"return {sn} is {r['status']}")
    _ret_update(r, "REFUND_PAID", {"resolution": "FULL_REFUND", "seller_note": f"accepted by {by}"}, f"Refund RM{r['refund_amount']:.2f} paid for {sn} (accepted via {by})")
    _settle(r)
    return {"return_sn": sn, "status": "REFUND_PAID", "refund_amount": r["refund_amount"]}


def offer_partial_refund(sn, amount, by):
    r = get_return(sn) or fail("error_not_found", f"return {sn} not found")
    if r["status"] != "REQUESTED":
        fail("error_return_status", f"return {sn} is {r['status']}; offers only allowed while REQUESTED")
    a = round(float(amount), 2)
    if not (0 < a < r["refund_amount"]):
        fail("error_param", f"offer must be between RM0.01 and RM{r['refund_amount'] - 0.01:.2f}")
    _ret_update(r, "PROCESSING", {"offered_amount": a, "seller_note": f"partial refund offered by {by}"}, f"Partial refund RM{a:.2f} offered for {sn} via {by}")
    schedule(now() + rng.int_(2 * HOUR, 12 * HOUR), "return_offer_reply", sn)
    return {"return_sn": sn, "status": "PROCESSING", "offered_amount": a}


def dispute_return(sn, reason, by):
    r = get_return(sn) or fail("error_not_found", f"return {sn} not found")
    if r["status"] not in ("REQUESTED", "PROCESSING"):
        fail("error_return_status", f"return {sn} is {r['status']}")
    _ret_update(r, "JUDGING", {"seller_note": f"dispute via {by}: {reason}"}, f"Return {sn} disputed via {by} – Shopee reviewing")
    schedule(now() + 2 * DAY, "return_judging", sn)
    return {"return_sn": sn, "status": "JUDGING"}


def _buyer_responds_to_offer(sn):
    r = get_return(sn)
    if not r or r["status"] != "PROCESSING" or r["offered_amount"] is None:
        return
    if rng.chance(0.65):
        _ret_update(r, "REFUND_PAID", {"refund_amount": r["offered_amount"], "resolution": "PARTIAL_REFUND"}, f"Buyer accepted partial refund RM{r['offered_amount']:.2f} for {sn}")
        _settle(r)
    else:
        _ret_update(r, "JUDGING", {}, f"Buyer rejected partial offer for {sn} – escalated to Shopee")
        schedule(now() + 2 * DAY, "return_judging", sn)


def _judge(sn):
    r = get_return(sn)
    if not r or r["status"] != "JUDGING":
        return
    if rng.chance(0.6):
        _ret_update(r, "REFUND_PAID", {"resolution": "SHOPEE_REFUND"}, f"Shopee ruled for buyer on {sn} – full refund RM{r['refund_amount']:.2f}")
    else:
        _ret_update(r, "CLOSED", {"refund_amount": 0, "resolution": "SELLER_WON"}, f"Shopee ruled for seller on {sn} – no refund")
    _settle(r)


def _auto_accept(sn):
    r = get_return(sn)
    if r and r["status"] == "REQUESTED":
        _ret_update(r, "REFUND_PAID", {"resolution": "AUTO_REFUND"}, f"Seller did not respond – Shopee auto-refunded RM{r['refund_amount']:.2f} for {sn}")
        _settle(r)


# ---------------------------------------------------------------- chat

def conversation_for(buyer_id):
    c = get("SELECT * FROM conversations WHERE buyer_user_id = ?", buyer_id)
    if not c:
        b = get("SELECT username FROM buyers WHERE buyer_user_id = ?", buyer_id) or fail("error_param", "buyer not found")
        cid = 7_000_000_000 + buyer_id * 13
        run("INSERT INTO conversations(conversation_id, buyer_user_id, buyer_username, last_message_time, unread_count, awaiting_reply) VALUES(?,?,?,?,0,0)",
            cid, buyer_id, b["username"], now())
        c = get("SELECT * FROM conversations WHERE conversation_id = ?", cid)
    return c


def buyer_send(buyer_id, text, intent=None, order_sn=None, item_id=None, source="sim", followup=False):
    c = conversation_for(buyer_id)
    t = now()
    if order_sn:
        run("INSERT INTO messages(conversation_id, sender, message_type, content, created_timestamp, source, ref_order_sn, intent) VALUES(?,?,?,?,?,?,?,?)",
            c["conversation_id"], "buyer", "order", json.dumps({"order_sn": order_sn}), t, source, order_sn, intent)
    elif item_id:
        run("INSERT INTO messages(conversation_id, sender, message_type, content, created_timestamp, source, ref_item_id, intent) VALUES(?,?,?,?,?,?,?,?)",
            c["conversation_id"], "buyer", "item", json.dumps({"item_id": item_id}), t, source, item_id, intent)
    cur = run("INSERT INTO messages(conversation_id, sender, message_type, content, created_timestamp, source, ref_order_sn, ref_item_id, intent) VALUES(?,?,?,?,?,?,?,?,?)",
              c["conversation_id"], "buyer", "text", json.dumps({"text": text}), t, source, order_sn, item_id, intent)
    run("UPDATE conversations SET last_message_time = ?, unread_count = unread_count + 1, last_buyer_message_time = ?, awaiting_reply = 1 WHERE conversation_id = ?",
        t, t, c["conversation_id"])
    mid = cur.lastrowid
    emit("chat.buyer_message", f"💬 {c['buyer_username']}: “{short(text, 80)}”", {"conversation_id": c["conversation_id"], "message_id": mid})
    if not followup and source != "storefront" and rng.chance(0.55):
        schedule(t + rng.int_(5 * HOUR, 9 * HOUR), "buyer_followup", c["conversation_id"], {"after": mid})
    return {"conversation_id": c["conversation_id"], "message_id": mid}


def seller_send(conversation_id, text, source):
    c = get("SELECT * FROM conversations WHERE conversation_id = ?", int(conversation_id)) or fail("error_not_found", f"conversation {conversation_id} not found")
    body = str(text or "").strip()
    if not body:
        fail("error_param", "message content is empty")
    if len(body) > 1000:
        fail("error_param", "message too long (max 1000 characters)")
    t = now()
    cur = run("INSERT INTO messages(conversation_id, sender, message_type, content, created_timestamp, source) VALUES(?,?,?,?,?,?)",
              c["conversation_id"], "seller", "text", json.dumps({"text": body}), t, source)
    run("UPDATE conversations SET last_message_time = ?, unread_count = 0, awaiting_reply = 0 WHERE conversation_id = ?", t, c["conversation_id"])
    emit("chat.seller_message", f"↩️ Reply to {c['buyer_username']} via {source}: “{short(body, 80)}”", {"conversation_id": c["conversation_id"]})
    if c["awaiting_reply"] and rng.chance(0.35):
        schedule(t + rng.int_(HOUR // 2, 3 * HOUR), "buyer_reply", c["conversation_id"])
    return {"message_id": cur.lastrowid, "created_timestamp": t}


def seller_message_buyer(buyer_id, text, source):
    """Start (or continue) a chat with a buyer — e.g. win-back messages to customers who have not bought for a while."""
    return seller_send(conversation_for(buyer_id)["conversation_id"], text, source)


def chat_response_rate():
    t = now()
    msgs = all_("SELECT conversation_id, sender, created_timestamp FROM messages WHERE created_timestamp >= ? AND message_type = 'text' ORDER BY conversation_id, created_timestamp",
                t - 30 * DAY)
    threads = answered = total = 0
    pending, conv = None, -1

    def close(reply):
        nonlocal threads, answered, total, pending
        if pending is None:
            return
        if reply is None and t - pending <= 12 * HOUR:
            pending = None
            return
        threads += 1
        if reply is not None and reply - pending <= 12 * HOUR:
            answered += 1
            total += reply - pending
        pending = None

    for m in msgs:
        if m["conversation_id"] != conv:
            close(None)
            conv = m["conversation_id"]
        if m["sender"] == "buyer" and pending is None:
            pending = m["created_timestamp"]
        elif m["sender"] == "seller" and pending is not None:
            close(m["created_timestamp"])
    close(None)
    return {"response_rate": answered / threads if threads else 1, "avg_response_seconds": round(total / answered) if answered else 0, "threads": threads}


# ---------------------------------------------------------------- reviews

def create_comment(item_id, model_id, order_sn, buyer_user_id, buyer_username, rating, text, tags):
    mx = get("SELECT MAX(comment_id) m FROM comments")["m"] or 50_000_000
    cid = mx + 7
    run("INSERT INTO comments(comment_id, item_id, model_id, order_sn, buyer_user_id, buyer_username, rating_star, comment, create_time, tags) VALUES(?,?,?,?,?,?,?,?,?,?)",
        cid, item_id, model_id, order_sn, buyer_user_id, buyer_username, rating, text, now(), json.dumps(tags))
    it = get_item(item_id) or {}
    emit("review.created", f"{'★' * rating}{'☆' * (5 - rating)} review on “{short(it.get('item_name', ''), 40)}” by {buyer_username}", {"comment_id": cid, "rating_star": rating})
    return cid


def reply_comment(comment_id, text, source):
    c = get("SELECT * FROM comments WHERE comment_id = ?", int(comment_id)) or fail("error_not_found", f"comment {comment_id} not found")
    if c["reply"]:
        fail("error_already_replied", f"comment {comment_id} already has a seller reply")
    body = str(text or "").strip()
    if not (2 <= len(body) <= 500):
        fail("error_param", "reply must be 2–500 characters")
    run("UPDATE comments SET reply = ?, reply_time = ?, reply_source = ? WHERE comment_id = ?", body, now(), source, int(comment_id))
    emit("review.replied", f"Seller replied to {c['rating_star']}★ review by {c['buyer_username']} via {source}", {"comment_id": int(comment_id)})
    return {"comment_id": int(comment_id)}


def review_rating(tags):
    if not tags:
        return rng.weighted([(5, 76), (4, 21), (3, 3)])
    if "quality" in tags or "packaging" in tags:
        return rng.weighted([(1, 45), (2, 30), (3, 20), (4, 5)])
    if "delivery" in tags or "value" in tags:
        return rng.weighted([(2, 10), (3, 35), (4, 45), (5, 10)])
    return rng.weighted([(2, 25), (3, 50), (4, 25)])


def review_text(key, tags, rating):
    if not tags:
        if rng.chance(0.22):
            return rng.pick(TEXT["SHORT_POS"])
        praise = TEXT["ITEM_PRAISE"].get(key, [])
        return rng.pick(praise) if praise and rng.chance(0.45) else rng.pick(TEXT["POSITIVE"])
    parts = []
    for t in tags:
        spec = TEXT["ISSUE_ITEM"].get(key, {}).get(t)
        parts.append(rng.pick(spec) if spec and rng.chance(0.8) else rng.pick(TEXT["ISSUE_GENERIC"][t]))
    if rating >= 4 and rng.chance(0.6):
        parts.insert(0, rng.pick(["Item ok overall.", "Product is fine.", "Barang ok."]))
    return " ".join(parts)


# ---------------------------------------------------------------- fees / payout

FEE_RATES = {"transaction": 0.0378, "service": 0.05, "service_cap_per_item": 30}


def compute_escrow(order_sn):
    o = get_order(order_sn)
    if not o:
        return None
    lines = all_("""SELECT oi.*, c.commission_rate FROM order_items oi JOIN items i ON i.item_id = oi.item_id
                    JOIN categories c ON c.category_id = i.category_id WHERE oi.order_sn = ?""", order_sn)
    refund = (get("SELECT SUM(refund_amount) s FROM returns WHERE order_sn = ? AND status = 'REFUND_PAID'", order_sn) or {}).get("s") or 0
    cancelled = o["order_status"] == "CANCELLED"
    selling = original = commission = service = 0.0
    items = []
    for ln in lines:
        sell = ln["discounted_price"] * ln["quantity"]
        comm = round(sell * ln["commission_rate"], 2)
        selling += sell
        original += ln["original_price"] * ln["quantity"]
        commission += comm
        service += min(FEE_RATES["service_cap_per_item"], sell * FEE_RATES["service"])
        items.append({"item_id": ln["item_id"], "model_id": ln["model_id"], "model_sku": ln["model_sku"], "item_name": ln["item_name"],
                      "quantity_purchased": ln["quantity"], "original_price": ln["original_price"], "discounted_price": ln["discounted_price"], "commission_fee": comm})
    transaction = (selling + o["buyer_shipping_fee"]) * FEE_RATES["transaction"]
    full_refund = cancelled and refund == 0
    escrow = 0 if full_refund else selling - commission - service - transaction - refund
    z = (lambda v: 0 if full_refund else round(v, 2))
    return {"order_sn": order_sn, "order_selling_price": round(selling, 2), "order_original_price": round(original, 2),
            "commission_fee": z(commission), "service_fee": z(service), "seller_transaction_fee": z(transaction),
            "seller_return_refund": -round(refund, 2), "escrow_amount": round(escrow, 2), "items": items,
            "is_final": o["order_status"] == "COMPLETED" or cancelled}


# ---------------------------------------------------------------- shop performance

def shop_info():
    return get("SELECT * FROM shop LIMIT 1")


def shop_performance():
    t = now()
    since = t - 30 * DAY
    shipped = get("SELECT COUNT(*) n, SUM(late_flag) late FROM orders WHERE ship_time >= ?", since)
    total = get("SELECT COUNT(*) n FROM orders WHERE create_time >= ? AND (pay_time IS NOT NULL OR cod = 1)", since)
    nonf = get("SELECT COUNT(*) n FROM orders WHERE create_time >= ? AND order_status = 'CANCELLED' AND (cancel_by = 'seller' OR cancel_reason = 'SELLER_DID_NOT_SHIP')", since)
    rets = get("SELECT COUNT(*) n FROM returns WHERE create_time >= ?", since)
    prep = get("SELECT AVG(ship_time - COALESCE(pay_time, create_time)) avg FROM orders WHERE ship_time >= ?", since)
    pts = get("SELECT SUM(points) p FROM penalties WHERE ts >= ?", t - 90 * DAY)
    chat = chat_response_rate()
    rating = shop_rating()
    return {
        "shop_rating": rating["rating_star"], "rating_count": rating["rating_count"],
        "chat_response_rate": round(chat["response_rate"] * 1000) / 10, "avg_chat_response_minutes": round(chat["avg_response_seconds"] / 60),
        "late_shipment_rate": round((shipped["late"] or 0) / shipped["n"] * 1000) / 10 if shipped["n"] else 0,
        "non_fulfilment_rate": round(nonf["n"] / total["n"] * 1000) / 10 if total["n"] else 0,
        "return_refund_rate": round(rets["n"] / total["n"] * 1000) / 10 if total["n"] else 0,
        "preparation_time_days": round(prep["avg"] / DAY * 100) / 100 if prep["avg"] else 0,
        "penalty_points": pts["p"] or 0,
        "targets": {"chat_response_rate": 80, "late_shipment_rate": 10, "non_fulfilment_rate": 10, "preparation_time_days": 1.5, "shop_rating": 4.6},
    }


# ---------------------------------------------------------------- demand model (engine)

_HF = [0.3, 0.18, 0.1, 0.08, 0.08, 0.15, 0.35, 0.6, 0.85, 1.0, 1.15, 1.3, 1.45, 1.35, 1.2, 1.1, 1.05, 1.1, 1.25, 1.45, 1.7, 1.85, 1.55, 0.9]
HOUR_FACTOR = [x / (sum(_HF) / 24) for x in _HF]


def day_factor(ts):
    d = local(ts)
    f = 1.12 if d.weekday() >= 5 else 1
    if d.day >= 25 or d.day <= 2:
        f *= 1.15  # payday
    if d.month == d.day and d.month >= 9:
        f *= 2.3  # 9.9, 10.10, 11.11, 12.12
    elif d.month == d.day + 1 and d.month >= 9:
        f *= 1.2
    return f


def is_campaign_day(ts):
    d = local(ts)
    return d.month == d.day and d.month >= 9


def active_modifiers():
    t = now()
    return [m for m in get_meta("modifiers", []) if m.get("until", 0) > t]


def add_modifier(m):
    set_meta("modifiers", active_modifiers() + [m])


def _trend(sim, ts, epoch):
    tr = sim.get("trend")
    if not tr:
        return 1
    d = (ts - epoch) / DAY
    if d <= tr["from"]:
        return 1
    if d >= tr["to"]:
        return tr["end"]
    return 1 + (d - tr["from"]) / (tr["to"] - tr["from"]) * (tr["end"] - 1)


def current_issues(item_id, sim, ts, epoch):
    issues = dict(sim.get("issues", {}))
    qs = sim.get("qualityShift")
    if qs and (ts - epoch) / DAY >= qs["from"]:
        issues.update(qs["issues"])
    for m in active_modifiers():
        if m.get("kind") == "quality" and m.get("item_id") == item_id and m.get("issues"):
            issues.update(m["issues"])
    return issues


_rating_cache = {"at": -1, "v": {}}
_buyer_pool = None


def _items_ctx(t):
    hb = t // HOUR
    if _rating_cache["at"] != hb:
        _rating_cache.update(at=hb, v={})
    out = []
    for r in all_("SELECT item_id, item_name, description, sim, boost_until FROM items WHERE item_status = 'NORMAL'"):
        rating = _rating_cache["v"].get(r["item_id"])
        if rating is None:
            rating = _rating_cache["v"][r["item_id"]] = perceived_rating(r["item_id"], t - 30 * DAY)
        sim = jl(r["sim"], {})
        out.append({"item_id": r["item_id"], "key": sim.get("key", ""), "sim": sim, "rating": rating, "boosted": r["boost_until"] > t,
                    "models": all_("SELECT model_id, price, stock, weight FROM models WHERE item_id = ?", r["item_id"]),
                    "listing": listing_score(r["item_name"], r["description"])})
    return out


def _pick_buyer():
    global _buyer_pool
    if _buyer_pool is None:
        ids, cum, c = [], [], 0.0
        for r in all_("SELECT buyer_user_id, loyalty FROM buyers WHERE buyer_user_id > 1"):
            c += 0.25 + r["loyalty"] ** 2 * 2
            ids.append(r["buyer_user_id"])
            cum.append(c)
        _buyer_pool = (ids, cum, c)
    ids, cum, total = _buyer_pool
    x = rng.random() * total
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return ids[lo]


def _traffic_step(t0, t1):
    dt = t1 - t0
    epoch = int(get_meta("epoch", t1))
    mods = active_modifiers()
    items = _items_ctx(t1)
    hf, df = HOUR_FACTOR[local(t1).hour], day_factor(t1)
    pending = []
    for it in items:
        s = it["sim"]
        tmult = rmult = 1.0
        for m in mods:
            if m.get("item_id") is not None and m["item_id"] != it["item_id"]:
                continue
            if m["kind"] == "traffic":
                tmult *= m.get("mult", 1)
            if m["kind"] == "refprice" and m.get("item_id") == it["item_id"]:
                rmult *= m.get("mult", 1)
        lam = s["views"] / 24 * hf * df * _trend(s, t1, epoch) * (2.2 if it["boosted"] else 1) * it["listing"]["traffic"] * tmult * (dt / HOUR)
        views = rng.poisson(lam)
        if not views:
            continue
        carts = rng.binomial(views, min(0.5, s["cart"] * math.sqrt(it["listing"]["conversion"])))
        in_stock = [m for m in it["models"] if m["stock"] > 0]
        orders = 0
        if carts and in_stock:
            avg = sum(m["price"] for m in in_stock) / len(in_stock)
            price_f = min(2.5, max(0.1, (s["refPrice"] * rmult / avg) ** s["elasticity"]))
            rating_f = min(1.15, max(0.45, 0.5 + (it["rating"] - 3.5) * 0.42))
            orders = rng.binomial(carts, min(0.9, s["buy"] * price_f * rating_f * math.sqrt(it["listing"]["conversion"])))
        bump_stats(it["item_id"], t1, views=views, add_to_cart=carts)
        for _ in range(orders):
            pending.append((t0 + int(rng.random() * dt), "order", it))
    for _ in range(rng.poisson(0.32 * hf * df * (dt / HOUR))):
        pending.append((t0 + int(rng.random() * dt), "question", None))
    pending.sort(key=lambda p: p[0])
    end = clock.now
    for at, kind, it in pending:
        clock.now = at
        try:
            if kind == "order":
                avail = [m for m in it["models"] if m["stock"] > 0]
                if not avail:
                    continue
                m = rng.weighted([(x, x["weight"] or 1) for x in avail])
                q = min(rng.weighted([(1, 80), (2, 15), (3, 5)]), m["stock"])
                lines = [{"model_id": m["model_id"], "quantity": q}]
                if rng.chance(0.08):
                    other = rng.pick(items)
                    om = next((x for x in other["models"] if x["stock"] > 0), None)
                    if om and other["item_id"] != it["item_id"]:
                        lines.append({"model_id": om["model_id"], "quantity": 1})
                msg = rng.pick(["Please pack nicely, it is a gift 🎁", "Tolong bungkus elok-elok ya", "Please send fast, thank you", "Leave at guard house"]) if rng.chance(0.06) else ""
                create_order(_pick_buyer(), lines, rng.weighted(PAYMENT_METHODS), "sim", msg)
                m["stock"] = max(0, m["stock"] - q)
            else:
                it = rng.weighted([(x, x["sim"]["views"]) for x in items])
                if rng.chance(0.7) and it["sim"].get("faqs"):
                    buyer_send(_pick_buyer(), rng.pick(it["sim"]["faqs"]), intent="product_question", item_id=it["item_id"])
                else:
                    buyer_send(_pick_buyer(), rng.pick(TEXT["PRESALE"]), intent="presale", item_id=it["item_id"])
        except ShopeeError:
            pass  # sold out meanwhile — shopper walks away
    clock.now = end


RETURN_CHANCE = {"packaging": 0.5, "quality": 0.42, "accuracy": 0.45, "sizing": 0.22}


def _after_delivery(sn):
    o = get_order(sn)
    if not o:
        return
    epoch = int(get_meta("epoch", now()))
    first = order_lines(sn)[0]
    it = get_item(first["item_id"]) or {}
    sim = jl(it.get("sim"), {})
    issues = [tag for tag, p in current_issues(first["item_id"], sim, now(), epoch).items() if rng.chance(p)]
    osim = jl(o["sim"], {})
    transit = (now() - (o["pickup_time"] or o["ship_time"] or o["create_time"])) / DAY
    if (osim.get("plan") not in (None, "normal")) or transit > 6 or o["late_flag"]:
        if rng.chance(0.55):
            issues.append("delivery")
    set_sim(sn, issues=issues)
    t = now()
    returnable = [i for i in issues if i in RETURN_CHANCE]
    will = next((i for i in returnable if rng.chance(RETURN_CHANCE[i])), None)
    if returnable and rng.chance(0.45):
        schedule(t + rng.int_(HOUR // 2, 20 * HOUR), "buyer_msg", sn, {"intent": "complaint", "tag": will or returnable[0]})
    if will:
        schedule(t + rng.int_(2 * HOUR, 2 * DAY), "return_request", sn, {"tag": will})
        return
    if rng.chance(0.62):
        schedule(t + rng.int_(3 * HOUR, 3 * DAY), "confirm", sn, {"by": "buyer"})
    else:
        schedule(t + 7 * DAY, "confirm", sn, {"by": "system"})


def _write_review(sn):
    o = get_order(sn)
    if not o:
        return
    ln = order_lines(sn)[0]
    key = jl((get_item(ln["item_id"]) or {}).get("sim"), {}).get("key", "")
    tags = jl(o["sim"], {}).get("issues", [])
    rating = review_rating(tags)
    create_comment(ln["item_id"], ln["model_id"], sn, o["buyer_user_id"], o["buyer_username"], rating, review_text(key, tags, rating), tags)


def _stuck_hub(sn):
    r = get("SELECT location FROM tracking_events WHERE order_sn = ? ORDER BY ts DESC LIMIT 1", sn)
    return (r or {}).get("location") or "sorting centre"


def _item_short(sn):
    ln = order_lines(sn)[0]
    return " ".join(((get_item(ln["item_id"]) or {}).get("item_name") or "item").split(" ")[:4])


def _h_unpaid_cancel(sn, p):
    o = get_order(sn)
    if o and o["order_status"] == "UNPAID":
        _restore_stock(sn)
        set_status(o, "CANCELLED", {"cancel_by": "system", "cancel_reason": "UNPAID"}, f"Order {sn} auto-cancelled (unpaid)")


def _h_auto_ship(sn, p):
    o = get_order(sn)
    if o and o["order_status"] == "READY_TO_SHIP":
        ship_order(sn, "warehouse_staff", "pickup" if rng.chance(0.8) else "dropoff")


def _h_ship_deadline(sn, p):
    o = get_order(sn)
    if not o or o["order_status"] != "READY_TO_SHIP":
        return
    run("UPDATE orders SET late_flag = 1 WHERE order_sn = ?", sn)
    emit("order.late", f"⚠️ Order {sn} missed its ship-by date – late shipment recorded", {"order_sn": sn})
    if rng.chance(0.5):
        _h_buyer_msg(sn, {"intent": "order_status"})


def _h_late_cancel(sn, p):
    o = get_order(sn)
    if not o or o["order_status"] != "READY_TO_SHIP":
        return
    _restore_stock(sn)
    set_status(o, "CANCELLED", {"cancel_by": "system", "cancel_reason": "SELLER_DID_NOT_SHIP"}, f"Order {sn} auto-cancelled – seller did not ship in time")
    add_penalty(1, "Non-fulfilment: order auto-cancelled because it was not shipped in time", sn)


def _h_buyer_cancel_req(sn, p):
    reason = rng.pick(TEXT["CANCEL_REASONS"])
    if buyer_request_cancel(sn, reason) and rng.chance(0.5):
        buyer_send(get_order(sn)["buyer_user_id"], fill(rng.pick(TEXT["CANCELLATION"]), sn=sn), intent="cancellation", order_sn=sn)


def _h_cancel_autoaccept(sn, p):
    o = get_order(sn)
    if o and o["order_status"] == "IN_CANCEL":
        handle_buyer_cancellation(sn, "ACCEPT", "system")


def _h_track(sn, p):
    o = get_order(sn)
    if not o or o["order_status"] != "SHIPPED":
        return
    osim = jl(o["sim"], {})
    step = osim.get("step", 0)
    route = tracking_route(o)
    rec = jl(o["recipient"], {})
    if osim.get("plan") in ("stuck", "lost") and step == 2:
        set_sim(sn, stuckSince=now())
        schedule(now() + rng.int_(4 * DAY, 7 * DAY), "stuck_resolve", sn)
        if rng.chance(0.75):
            schedule(now() + rng.int_(2 * DAY, 3 * DAY), "buyer_msg", sn, {"intent": "shipping_delay"})
        return
    if osim.get("plan") == "failed" and step == len(route):
        add_tracking(sn, "LOGISTICS_DELIVERY_FAILED", "Delivery attempt failed: recipient not available. Courier will re-attempt.", rec.get("city", ""))
        set_sim(sn, plan="normal", step=len(route) - 1)
        schedule(now() + rng.int_(18 * HOUR, 30 * HOUR), "track", sn)
        return
    if step < len(route):
        r = route[step]
        add_tracking(sn, r["status"], r["desc"], r["loc"])
        set_sim(sn, step=step + 1)
        nxt = route[step + 1]["gap"] if step + 1 < len(route) else [2, 8]
        extra = 24 if step == 1 and rec.get("state") in ("Sabah", "Sarawak") else 0
        schedule(now() + rng.int_((nxt[0] + extra) * HOUR, (nxt[1] + extra) * HOUR), "track", sn)
    else:
        deliver(sn)
        _after_delivery(sn)


def _h_stuck_resolve(sn, p):
    o = get_order(sn)
    if not o or o["order_status"] != "SHIPPED":
        return
    if jl(o["sim"], {}).get("plan") == "lost" or rng.chance(0.1):
        mark_lost(sn)
        if rng.chance(0.6):
            buyer_send(o["buyer_user_id"], f"Shopee says my parcel {sn} is lost?? I waited so long. Very disappointed with this shop.", intent="complaint", order_sn=sn)
        return
    set_sim(sn, plan="normal")
    add_tracking(sn, "LOGISTICS_IN_TRANSIT", "Parcel is in transit to the next facility (delay resolved)", _stuck_hub(sn))
    schedule(now() + rng.int_(8 * HOUR, 20 * HOUR), "track", sn)


def _h_confirm(sn, p):
    if confirm_received(sn, (p or {}).get("by", "buyer")):
        issues = jl(get_order(sn)["sim"], {}).get("issues", [])
        if rng.chance(0.7 if issues else 0.45):
            schedule(now() + rng.int_(2 * HOUR, 4 * DAY), "review", sn)


def _h_return_request(sn, p):
    if request_return(sn, (p or {}).get("tag", "quality")) and rng.chance(0.5):
        schedule(now() + rng.int_(3 * DAY, 6 * DAY), "review", sn)


def _h_buyer_msg(sn, p):
    o = get_order(sn)
    if not o:
        return
    intent = (p or {}).get("intent")
    if intent == "order_status" and o["order_status"] == "READY_TO_SHIP":
        buyer_send(o["buyer_user_id"], fill(rng.pick(TEXT["ORDER_STATUS"]), sn=sn), intent=intent, order_sn=sn)
    elif intent == "shipping_delay" and o["order_status"] == "SHIPPED":
        since = jl(o["sim"], {}).get("stuckSince") or now() - 3 * DAY
        buyer_send(o["buyer_user_id"], fill(rng.pick(TEXT["SHIPPING_DELAY"]), sn=sn, days=max(2, round((now() - since) / DAY)), hub=_stuck_hub(sn)),
                   intent=intent, order_sn=sn)
    elif intent == "complaint":
        tag = p.get("tag", "quality")
        tpl = rng.pick(TEXT["COMPLAINT"].get(tag) or TEXT["COMPLAINT"]["quality"])
        buyer_send(o["buyer_user_id"], fill(tpl, sn=sn, item=_item_short(sn)), intent="return_refund" if tag in ("packaging", "quality") else "complaint", order_sn=sn)


def _h_buyer_followup(cid, p):
    c = get("SELECT * FROM conversations WHERE conversation_id = ?", int(cid))
    if not c or not c["awaiting_reply"]:
        return
    if get("SELECT 1 x FROM messages WHERE conversation_id = ? AND sender = 'seller' AND message_id > ?", c["conversation_id"], (p or {}).get("after", 0)):
        return
    buyer_send(c["buyer_user_id"], rng.pick(TEXT["FOLLOWUP"]), intent="followup", followup=True)


def _h_buyer_reply(cid, p):
    c = get("SELECT * FROM conversations WHERE conversation_id = ?", int(cid))
    if c and not c["awaiting_reply"]:
        buyer_send(c["buyer_user_id"], rng.pick(TEXT["THANKS"]), intent="thanks", followup=True)


def _h_staff_reply(cid, p):
    c = get("SELECT awaiting_reply FROM conversations WHERE conversation_id = ?", int(cid))
    if c and c["awaiting_reply"]:
        seller_send(int(cid), rng.pick(TEXT["STAFF_REPLY"].get((p or {}).get("intent"), TEXT["STAFF_REPLY"]["other"])), "seller_staff")


def _h_staff_return(sn, p):
    r = get_return(sn)
    if r and r["status"] == "REQUESTED":
        if rng.chance(0.75):
            accept_return(sn, "seller_staff")
        else:
            offer_partial_refund(sn, round(r["refund_amount"] * 0.5, 2), "seller_staff")


def _h_boost_end(item_id, p):
    it = get("SELECT item_name, boost_until FROM items WHERE item_id = ?", int(item_id))
    if it and it["boost_until"] <= now():
        emit("product.boost_ended", f"Boost ended for “{short(it['item_name'], 40)}”", {"item_id": int(item_id)})


HANDLERS = {
    "pay": lambda sn, p: mark_paid(sn), "unpaid_cancel": _h_unpaid_cancel, "auto_ship": _h_auto_ship, "ship_deadline": _h_ship_deadline,
    "late_cancel": _h_late_cancel, "buyer_cancel_req": _h_buyer_cancel_req, "cancel_autoaccept": _h_cancel_autoaccept,
    "pickup": lambda sn, p: pickup(sn), "track": _h_track, "stuck_resolve": _h_stuck_resolve, "confirm": _h_confirm,
    "review": lambda sn, p: _write_review(sn), "return_request": _h_return_request, "return_autoaccept": lambda sn, p: _auto_accept(sn),
    "return_offer_reply": lambda sn, p: _buyer_responds_to_offer(sn), "return_judging": lambda sn, p: _judge(sn), "buyer_msg": _h_buyer_msg,
    "buyer_followup": _h_buyer_followup, "buyer_reply": _h_buyer_reply, "staff_reply": _h_staff_reply, "staff_return": _h_staff_return,
    "boost_end": _h_boost_end,
}


def _process_due(up_to):
    while True:
        rows = all_("SELECT * FROM sched WHERE due <= ? ORDER BY due, id LIMIT 400", up_to)
        if not rows:
            return
        for r in rows:
            run("DELETE FROM sched WHERE id = ?", r["id"])
            clock.now = max(clock.now, r["due"])
            try:
                h = HANDLERS.get(r["kind"])
                if h:
                    h(r["ref"], jl(r["payload"], {}))
            except ShopeeError:
                pass
            except Exception as exc:  # keep the world running
                print(f"[shopee sim] {r['kind']} {r['ref']} failed: {exc}", flush=True)


def advance_to(target, max_step=600):
    with LOCK:
        clock.load()
        while clock.now < target:
            t0 = clock.now
            t1 = min(target, t0 + max_step)
            with tx():
                _traffic_step(t0, t1)
                _process_due(t1)
                clock.now = t1
            clock.save()


# ---------------------------------------------------------------- scenarios (simulator controls)

def _item_by_key(key):
    for r in all_("SELECT item_id, item_name, sim FROM items"):
        if jl(r["sim"], {}).get("key") == key:
            return r
    return None


def _sc_angry(_):
    o = get("SELECT * FROM orders WHERE order_status IN ('TO_CONFIRM_RECEIVE','COMPLETED') ORDER BY update_time DESC LIMIT 1")
    if not o:
        return "No delivered order to complain about"
    buyer_send(o["buyer_user_id"], f"This is the worst!! Order {o['order_sn']} came broken and nobody replies. I will give 1 star and report this shop.",
               intent="complaint", order_sn=o["order_sn"])
    return f"{o['buyer_username']} sent an angry complaint"


def _sc_questions(_):
    for _ in range(6):
        it = rng.pick(_items_ctx(now()))
        buyer_send(_pick_buyer(), rng.pick(it["sim"].get("faqs") or TEXT["PRESALE"]), intent="product_question", item_id=it["item_id"])
    return "6 buyer questions arrived"


def _sc_cancel(_):
    o = get("SELECT * FROM orders WHERE order_status = 'READY_TO_SHIP' ORDER BY create_time DESC LIMIT 1")
    if not o or not buyer_request_cancel(o["order_sn"], rng.pick(TEXT["CANCEL_REASONS"])):
        return "No ready-to-ship order to cancel"
    return f"{o['buyer_username']} asked to cancel {o['order_sn']}"


def _sc_defect(item_id):
    it = get_item(item_id) if item_id else _item_by_key("lamp")
    add_modifier({"id": f"defect_{now()}", "kind": "quality", "item_id": it["item_id"], "issues": {"quality": 0.35}, "until": now() + 7 * DAY,
                  "label": f"Defective batch: {short(it['item_name'], 30)}"})
    return f"Defective batch on {short(it['item_name'], 30)} for 7 days"


def _sc_viral(item_id):
    it = get_item(item_id) if item_id else _item_by_key("case")
    add_modifier({"id": f"viral_{now()}", "kind": "traffic", "item_id": it["item_id"], "mult": 4, "until": now() + 3 * DAY, "label": f"Viral: {short(it['item_name'], 30)} ×4"})
    return f"{short(it['item_name'], 30)} traffic ×4 for 3 days"


def _sc_price_war(item_id):
    it = get_item(item_id) if item_id else _item_by_key("tumbler")
    add_modifier({"id": f"war_{now()}", "kind": "refprice", "item_id": it["item_id"], "mult": 0.8, "until": now() + 5 * DAY, "label": f"Price war: {short(it['item_name'], 30)}"})
    return f"Competitor price war on {short(it['item_name'], 30)} for 5 days"


def _sc_courier(_):
    d = get_meta("disruption", {})
    d["J&T Express"] = now() + 2 * DAY
    set_meta("disruption", d)
    return "J&T Express disrupted for 2 days"


def _sc_flash(_):
    add_modifier({"id": f"flash_{now()}", "kind": "traffic", "mult": 3, "until": now() + 6 * HOUR, "label": "Flash sale ×3 traffic"})
    return "Traffic ×3 for 6h"


SCENARIOS = [
    {"id": "flash_sale", "title": "Flash sale traffic spike", "description": "Shop-wide traffic ×3 for the next 6 simulated hours.", "run": _sc_flash},
    {"id": "courier_disruption", "title": "Courier disruption (J&T)", "description": "45% of new J&T pickups get stuck for days (next 2 days).", "run": _sc_courier},
    {"id": "viral_product", "title": "Product goes viral", "description": "A TikTok video drives ×4 traffic to the phone case for 3 days.", "run": _sc_viral},
    {"id": "defective_batch", "title": "Defective batch", "description": "35% of LED lamps delivered in the next week are faulty.", "run": _sc_defect},
    {"id": "price_war", "title": "Competitor price war", "description": "A competitor undercuts the tumbler by 20% for 5 days.", "run": _sc_price_war},
    {"id": "angry_customer", "title": "Angry customer", "description": "A buyer threatens a 1-star review and a report.", "run": _sc_angry},
    {"id": "question_burst", "title": "Burst of buyer questions", "description": "Six product questions arrive at once.", "run": _sc_questions},
    {"id": "cancellation", "title": "Cancellation request", "description": "A buyer asks to cancel a ready-to-ship order.", "run": _sc_cancel},
]

PLANTED = [
    {"key": "mug", "problem": "Ceramic mug arrives broken — packaging is too thin"},
    {"key": "tee", "problem": "Oversized tee runs one size small"},
    {"key": "buds", "problem": "New earbuds batch is defective"},
    {"key": "cable", "problem": "USB-C cable is about to sell out"},
    {"key": "board", "problem": "Bamboo board losing traffic to a cheaper competitor"},
    {"key": "tumbler", "problem": "Tumbler price hike cut conversion ~50%"},
    {"key": "lamp", "problem": "LED lamp has a near-zero margin after fees"},
    {"key": "sheet", "problem": "Bedsheet listing is weak (one-word title, empty description)"},
    {"key": "case", "problem": "Phone case is a strong product worth promoting"},
]


def run_scenario(sid, item_id=None):
    sc = next((s for s in SCENARIOS if s["id"] == sid), None) or fail("error_param", f"unknown scenario {sid}")
    with LOCK:
        msg = sc["run"](item_id)
    emit("sim.scenario", f"🎬 Scenario: {sc['title']} — {msg}", {"scenario": sid})
    return msg


# ---------------------------------------------------------------- live loop

_loop_started = False


def start_loop(interval=2.0, max_catch_up_days=7):
    """Advance the world in the background. After downtime it catches up (at most a week of simulated time)."""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def loop():
        install()
        with LOCK:
            clock.load()
            behind = time.time() - clock.now
            if clock.speed == 1 and behind > max_catch_up_days * DAY:
                clock.now = int(time.time() - max_catch_up_days * DAY)
        last = time.time()
        while True:
            time.sleep(interval)
            real = time.time()
            elapsed, last = real - last, real
            try:
                with LOCK:
                    clock.load()
                    if clock.paused:
                        continue
                    target = clock.now + elapsed * clock.speed
                    if clock.speed == 1 and clock.now < real - 60:  # catching up after downtime: a few hours per tick
                        target = min(real, clock.now + 6 * HOUR)
                advance_to(int(target), 600)
            except Exception as exc:
                print(f"[shopee sim] loop error: {exc}", flush=True)

    threading.Thread(target=loop, daemon=True).start()


def sim_state():
    clock.load()
    return {"now": clock.now, "now_text": local(clock.now).strftime("%a %d %b %Y, %H:%M"), "speed": clock.speed, "paused": clock.paused,
            "real_now": int(time.time()), "behind_seconds": int(time.time() - clock.now),
            "modifiers": active_modifiers(), "disruption": {k: v for k, v in get_meta("disruption", {}).items() if v > clock.now},
            "scenarios": [{k: s[k] for k in ("id", "title", "description")} for s in SCENARIOS], "planted": PLANTED}


def set_sim_controls(body):
    with LOCK:
        clock.load()
        if body.get("speed") is not None:
            clock.speed = max(0.0, min(3600.0, float(body["speed"])))
        if body.get("paused") is not None:
            clock.paused = bool(body["paused"])
        clock.save()
    if body.get("advance_hours"):
        h = max(0.0, min(72.0, float(body["advance_hours"])))
        advance_to(now() + int(h * HOUR), 600)
        emit("sim.advance", f"⏩ Fast-forwarded {h:g} simulated hours", {})
    if body.get("scenario"):
        run_scenario(str(body["scenario"]), body.get("item_id"))
    if body.get("reset"):
        global _buyer_pool
        install(force=True)
        _buyer_pool = None
        _rating_cache.update(at=-1, v={})
        emit("sim.reset", "♻️ Shop world reset to the 60-day demo history", {})
    return sim_state()
