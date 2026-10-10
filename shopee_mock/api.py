"""HTTP routes for the mock Shopee app (storefront, Seller Centre, simulator), served by the Enterprise Buddy console.

handle(method, path, qs, body) -> (payload, status) or None when the path is not a Shopee route.
The storefront buyer is the demo account (buyer 1, "demo_buyer"). All routes go through the same services as the
simulation engine and the Enterprise Buddy agent.
"""
from __future__ import annotations

import re

import sim

PREFIX = "/api/shopee"
STATUS_GROUPS = {
    "unpaid": ["UNPAID"], "to_ship": ["READY_TO_SHIP", "IN_CANCEL"], "shipping": ["PROCESSED", "SHIPPED"], "completed": ["TO_CONFIRM_RECEIVE", "COMPLETED"],
    "cancelled": ["CANCELLED"], "return": ["TO_RETURN"],
}


def _item_card(it):
    models = sim.models_of(it["item_id"])
    rt = sim.item_rating(it["item_id"])
    sold = (sim.get("SELECT SUM(units) s FROM item_daily_stats WHERE item_id = ?", it["item_id"]) or {}).get("s") or 0
    prices = [m["price"] for m in models] or [0]
    return {"item_id": it["item_id"], "name": it["item_name"], "emoji": it["emoji"], "color": it["color"], "status": it["item_status"], "brand": it["brand"],
            "price_min": min(prices), "price_max": max(prices), "original_max": max([m["original_price"] for m in models] or [0]),
            "stock": sum(m["stock"] for m in models), "sold": int((it["base_sold"] or 0) + sold), "rating": rt["rating_star"], "rating_count": rt["rating_count"],
            "boosted": it["boost_until"] > sim.now(), "category_id": it["category_id"]}


def _order_view(o, with_tracking=False):
    lines = sim.order_lines(o["order_sn"])
    out = {k: o[k] for k in ("order_sn", "buyer_user_id", "buyer_username", "order_status", "create_time", "update_time", "pay_time", "ship_by_date", "payment_method",
                             "total_amount", "subtotal", "buyer_shipping_fee", "shipping_carrier", "tracking_number", "logistics_status", "message_to_seller",
                             "buyer_cancel_reason", "cancel_reason", "late_flag")}
    out["recipient"] = sim.jl(o["recipient"], {})
    out["items"] = [{"item_id": ln["item_id"], "model_id": ln["model_id"], "name": ln["item_name"], "model": ln["model_name"], "qty": ln["quantity"],
                     "price": ln["discounted_price"], "emoji": (sim.get_item(ln["item_id"]) or {}).get("emoji", "📦")} for ln in lines]
    out["hours_to_ship"] = round((o["ship_by_date"] - sim.now()) / 3600, 1) if o["order_status"] in ("READY_TO_SHIP", "IN_CANCEL") else None
    if with_tracking:
        out["tracking"] = sim.all_("SELECT ts, logistics_status, description, location FROM tracking_events WHERE order_sn = ? ORDER BY ts DESC", o["order_sn"])
        out["return"] = sim.get("SELECT * FROM returns WHERE order_sn = ?", o["order_sn"])
        out["reviewed"] = bool(sim.get("SELECT 1 x FROM comments WHERE order_sn = ?", o["order_sn"]))
    return out


def _conv_view(c, full=False):
    msgs = sim.all_("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_timestamp, message_id", c["conversation_id"])
    for m in msgs:
        m["content"] = sim.jl(m["content"], {})
    last = next((m for m in reversed(msgs) if m["message_type"] == "text"), None)
    out = {"conversation_id": c["conversation_id"], "buyer_user_id": c["buyer_user_id"], "buyer": c["buyer_username"], "unread": c["unread_count"],
           "awaiting_reply": bool(c["awaiting_reply"]), "last_time": c["last_message_time"],
           "last": (last or {}).get("content", {}).get("text", ""), "last_from": (last or {}).get("sender", "")}
    if full:
        out["messages"] = msgs[-80:]
    return out


def handle(method, path, qs, body):
    if not path.startswith(PREFIX + "/"):
        return None
    p = path[len(PREFIX):]
    try:
        return _route(method, p, qs, body), 200
    except sim.ShopeeError as e:
        return {"error": str(e), "code": e.code}, 400
    except (KeyError, ValueError, TypeError) as e:
        return {"error": f"bad request: {e}"}, 400


def _route(method, p, qs, body):
    now = sim.now
    # ------------------------------------------------ shared
    if p == "/state" and method == "GET":
        shop = sim.shop_info()
        return {"shop": shop, "sim": sim.sim_state(), "events": sim.events(int(qs.get("since", 0) or 0), 40)}
    if p == "/sim" and method == "POST":
        return sim.set_sim_controls(body)
    # ------------------------------------------------ storefront (buyer = demo_buyer)
    if p == "/store/home":
        cats = sim.all_("SELECT category_id, name, icon FROM categories WHERE parent_id = 0")
        items = [_item_card(i) for i in sim.all_("SELECT * FROM items WHERE item_status = 'NORMAL' ORDER BY item_id")]
        q = (qs.get("q") or "").lower().strip()
        if q:
            items = [i for i in items if q in i["name"].lower()]
        return {"shop": sim.shop_info(), "rating": sim.shop_rating(), "categories": cats, "items": items}
    m = re.fullmatch(r"/store/item/(\d+)", p)
    if m:
        it = sim.get_item(int(m.group(1))) or sim.fail("error_not_found", "item not found")
        card = _item_card(it)
        card.update(description=it["description"], attributes=sim.jl(it["attributes"], {}), tiers=sim.jl(it["tier_variation"], []),
                    models=[{k: x[k] for k in ("model_id", "model_name", "price", "original_price", "stock")} for x in sim.models_of(it["item_id"])],
                    rating_by_star=sim.item_rating(it["item_id"])["rating_count_by_star"],
                    reviews=sim.all_("SELECT comment_id, buyer_username, rating_star, comment, create_time, reply, model_id FROM comments WHERE item_id = ? ORDER BY create_time DESC LIMIT 30", it["item_id"]))
        return card
    if p == "/store/checkout" and method == "POST":
        lines = [{"model_id": int(x["model_id"]), "quantity": int(x.get("quantity", 1))} for x in body.get("lines", [])]
        sn = sim.create_order(sim.DEMO_BUYER, lines, body.get("payment_method") or "ShopeePay", "storefront", str(body.get("message") or "")[:200])
        return _order_view(sim.get_order(sn), True)
    if p == "/store/orders":
        rows = sim.all_("SELECT * FROM orders WHERE buyer_user_id = ? ORDER BY create_time DESC LIMIT 40", sim.DEMO_BUYER)
        return {"orders": [_order_view(o, True) for o in rows]}
    m = re.fullmatch(r"/store/order/(\w+)/(confirm|review|return|cancel)", p)
    if m and method == "POST":
        sn, act = m.groups()
        o = sim.get_order(sn) or sim.fail("error_not_found", "order not found")
        if o["buyer_user_id"] != sim.DEMO_BUYER:
            sim.fail("error_permission", "not your order")
        if act == "confirm":
            sim.confirm_received(sn, "buyer") or sim.fail("error_order_status", "order is not waiting for confirmation")
        elif act == "review":
            if sim.get("SELECT 1 x FROM comments WHERE order_sn = ?", sn):
                sim.fail("error_already_reviewed", "you already reviewed this order")
            if o["order_status"] not in ("COMPLETED", "TO_CONFIRM_RECEIVE"):
                sim.fail("error_order_status", "you can review after delivery")
            ln = sim.order_lines(sn)[0]
            rating = max(1, min(5, int(body.get("rating", 5))))
            sim.create_comment(ln["item_id"], ln["model_id"], sn, sim.DEMO_BUYER, "demo_buyer", rating, str(body.get("comment") or "")[:500], [])
        elif act == "return":
            sim.request_return(sn, body.get("tag") or "quality", str(body.get("text") or "") or None) or sim.fail("error_order_status", "this order cannot be returned now")
        elif act == "cancel":
            if o["order_status"] == "UNPAID":
                sim.seller_cancel(sn, "CUSTOMER_REQUEST", "buyer")
            else:
                sim.buyer_request_cancel(sn, body.get("reason") or "Change of mind") or sim.fail("error_order_status", "this order can no longer be cancelled")
        return _order_view(sim.get_order(sn), True)
    if p == "/store/chat":
        c = sim.conversation_for(sim.DEMO_BUYER)
        if method == "POST":
            text = str(body.get("text") or "").strip()
            if not text:
                sim.fail("error_param", "empty message")
            sim.buyer_send(sim.DEMO_BUYER, text[:1000], intent=None, item_id=body.get("item_id"), order_sn=body.get("order_sn"), source="storefront")
        return _conv_view(sim.conversation_for(sim.DEMO_BUYER), True)
    # ------------------------------------------------ Seller Centre
    if p == "/seller/dashboard":
        t = now()
        counts = {k: sim.get(f"SELECT COUNT(*) n FROM orders WHERE order_status IN ({','.join('?' * len(v))})", *v)["n"] for k, v in STATUS_GROUPS.items()}
        today = sim.date_key(t)
        day = sim.get("SELECT SUM(sales) s, SUM(orders) o, SUM(views) v FROM item_daily_stats WHERE date = ?", today)
        series = sim.all_("SELECT date, SUM(sales) sales, SUM(orders) orders FROM item_daily_stats WHERE date > ? GROUP BY date ORDER BY date", sim.date_key(t - 14 * sim.DAY))
        return {"shop": sim.shop_info(), "performance": sim.shop_performance(), "counts": counts,
                "today": {"sales": round(day["s"] or 0, 2), "orders": day["o"] or 0, "views": day["v"] or 0}, "series": series,
                "overdue": sim.get("SELECT COUNT(*) n FROM orders WHERE order_status = 'READY_TO_SHIP' AND ship_by_date < ?", t)["n"],
                "unread_chats": sim.get("SELECT COUNT(*) n FROM conversations WHERE awaiting_reply = 1")["n"],
                "open_returns": sim.get("SELECT COUNT(*) n FROM returns WHERE status = 'REQUESTED'")["n"],
                "unreplied_reviews": sim.get("SELECT COUNT(*) n FROM comments WHERE reply IS NULL AND rating_star <= 3 AND create_time > ?", t - 14 * sim.DAY)["n"],
                "events": sim.events(0, 25)}
    if p == "/seller/orders":
        grp = STATUS_GROUPS.get(qs.get("status") or "to_ship", STATUS_GROUPS["to_ship"])
        order = "ship_by_date ASC" if (qs.get("status") or "to_ship") == "to_ship" else "update_time DESC"
        rows = sim.all_(f"SELECT * FROM orders WHERE order_status IN ({','.join('?' * len(grp))}) ORDER BY {order} LIMIT 120", *grp)
        return {"orders": [_order_view(o) for o in rows]}
    m = re.fullmatch(r"/seller/order/(\w+)", p)
    if m and method == "GET":
        return _order_view(sim.get_order(m.group(1)) or sim.fail("error_not_found", "order not found"), True)
    m = re.fullmatch(r"/seller/order/(\w+)/(ship|cancel|cancellation)", p)
    if m and method == "POST":
        sn, act = m.groups()
        if act == "ship":
            sim.ship_order(sn, "seller_centre", body.get("mode") or "pickup")
        elif act == "cancel":
            sim.seller_cancel(sn, body.get("reason") or "OUT_OF_STOCK", "seller_centre")
        else:
            sim.handle_buyer_cancellation(sn, body.get("operation") or "ACCEPT", "seller_centre")
        return _order_view(sim.get_order(sn), True)
    if p == "/seller/ship-all" and method == "POST":
        rows = sim.all_("SELECT order_sn FROM orders WHERE order_status = 'READY_TO_SHIP' ORDER BY ship_by_date LIMIT ?", int(body.get("limit") or 50))
        for r in rows:
            sim.ship_order(r["order_sn"], "seller_centre")
        return {"shipped": len(rows)}
    if p == "/seller/products":
        items = sim.all_("SELECT * FROM items WHERE item_status != 'DELETED' ORDER BY item_id")
        out = []
        d7 = sim.date_key(now() - 7 * sim.DAY)
        for it in items:
            card = _item_card(it)
            card["models"] = [{k: x[k] for k in ("model_id", "model_name", "model_sku", "price", "original_price", "stock")} for x in sim.models_of(it["item_id"])]
            s = sim.get("SELECT SUM(views) v, SUM(orders) o, SUM(units) u, SUM(sales) s FROM item_daily_stats WHERE item_id = ? AND date > ?", it["item_id"], d7)
            card.update(views7=s["v"] or 0, orders7=s["o"] or 0, units7=s["u"] or 0, sales7=round(s["s"] or 0, 2), description=it["description"])
            out.append(card)
        return {"products": out}
    m = re.fullmatch(r"/seller/product/(\d+)", p)
    if m and method == "POST":
        iid = int(m.group(1))
        if body.get("prices"):
            sim.update_price(iid, [{"model_id": int(k), "original_price": float(v)} for k, v in body["prices"].items()], "seller_centre")
        if body.get("stock"):
            sim.update_stock(iid, [{"model_id": int(k), "stock": int(v)} for k, v in body["stock"].items()], "seller_centre")
        fields = {k: body[k] for k in ("item_name", "description", "item_status") if body.get(k) is not None}
        if fields:
            sim.update_item(iid, fields, "seller_centre")
        if body.get("boost"):
            sim.boost_item(iid, "seller_centre")
        return _item_card(sim.get_item(iid))
    if p == "/seller/reviews":
        f = qs.get("filter") or "all"
        where = {"all": "1=1", "unreplied": "reply IS NULL AND rating_star <= 3", "negative": "rating_star <= 2", "positive": "rating_star >= 4"}.get(f, "1=1")
        rows = sim.all_(f"SELECT c.*, i.item_name, i.emoji FROM comments c JOIN items i ON i.item_id = c.item_id WHERE {where} ORDER BY create_time DESC LIMIT 80")
        return {"reviews": rows, "rating": sim.shop_rating()}
    m = re.fullmatch(r"/seller/review/(\d+)/reply", p)
    if m and method == "POST":
        return sim.reply_comment(int(m.group(1)), body.get("text"), "seller_centre")
    if p == "/seller/chats":
        rows = sim.all_("SELECT * FROM conversations ORDER BY awaiting_reply DESC, last_message_time DESC LIMIT 80")
        return {"chats": [_conv_view(c) for c in rows]}
    m = re.fullmatch(r"/seller/chat/(\d+)", p)
    if m:
        cid = int(m.group(1))
        if method == "POST":
            sim.seller_send(cid, body.get("text"), "seller_centre")
        c = sim.get("SELECT * FROM conversations WHERE conversation_id = ?", cid) or sim.fail("error_not_found", "conversation not found")
        sim.run("UPDATE conversations SET unread_count = 0 WHERE conversation_id = ?", cid)
        v = _conv_view(c, True)
        recent = sim.all_("SELECT * FROM orders WHERE buyer_user_id = ? ORDER BY create_time DESC LIMIT 3", c["buyer_user_id"])
        v["orders"] = [_order_view(o) for o in recent]
        return v
    if p == "/seller/returns":
        rows = sim.all_("SELECT r.*, i.item_name, i.emoji FROM returns r JOIN items i ON i.item_id = r.item_id ORDER BY (r.status = 'REQUESTED') DESC, r.create_time DESC LIMIT 60")
        return {"returns": rows}
    m = re.fullmatch(r"/seller/return/(\w+)/(accept|offer|dispute)", p)
    if m and method == "POST":
        sn, act = m.groups()
        if act == "accept":
            return sim.accept_return(sn, "seller_centre")
        if act == "offer":
            return sim.offer_partial_refund(sn, float(body.get("amount")), "seller_centre")
        return sim.dispute_return(sn, body.get("reason") or "Item was sent in good condition", "seller_centre")
    sim.fail("error_not_found", f"unknown Shopee route {p}")
