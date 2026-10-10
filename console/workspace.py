"""Businesses and saved conversations for the BizFlow console (JSON files, standard library only).

data/workspace/businesses.json        — the owner's businesses (Campus Crumb is the one with sample data)
data/workspace/conversations/<id>.json — one chat; each turn points at a console run (data/output/console_runs)
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "data" / "workspace"
BUSINESSES = WS / "businesses.json"
CONVS = WS / "conversations"
TZ = timezone(timedelta(hours=8))
ALL = "all"

DEFAULT_BUSINESS = {
    "id": "campus-crumb", "name": "Campus Crumb", "emoji": "🍪",
    "type": "Campus snack seller — cookies, muffins, buns, granola bars, iced lemon tea",
    "area": "Universiti Malaya, Kuala Lumpur",
    "description": "Student-run snack business (SYNTHETIC demo data: September sales, stock, suppliers, purchase orders).",
    "uses_sample_data": True,
}


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- businesses

def businesses() -> list[dict]:
    rows = _read(BUSINESSES, None)
    if not rows:
        rows = [dict(DEFAULT_BUSINESS, created_at=now(), collected=[])]
        _write(BUSINESSES, rows)
    return rows


def business(bid: str) -> dict | None:
    return next((b for b in businesses() if b["id"] == bid), None)


def add_business(name: str, btype: str, area: str, description: str = "", emoji: str = "🏪") -> dict:
    rows = businesses()
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "business"
    bid, n = base, 2
    while any(b["id"] == bid for b in rows) or bid == ALL:
        bid, n = f"{base}-{n}", n + 1
    b = {"id": bid, "name": name[:80], "emoji": (emoji or "🏪")[:4], "type": btype[:160], "area": area[:160],
         "description": description[:500], "uses_sample_data": False, "created_at": now(), "collected": []}
    rows.append(b)
    _write(BUSINESSES, rows)
    return b


def set_goal(bid: str, goal: str) -> dict | None:
    rows = businesses()
    hit = None
    for b in rows:
        if b["id"] == bid:
            b["goal"], b["goal_asked"] = goal.strip()[:300], True
            hit = b
    _write(BUSINESSES, rows)
    return hit


# ---------------------------------------------------------------- to-do list from approved plan steps

TODOS = WS / "todos.json"


def todos(bid: str) -> list[dict]:
    return [t for t in _read(TODOS, []) if bid == ALL or t.get("business_id") == bid]


def add_todos(bid: str, cid: str, items: list[dict]) -> list[dict]:
    rows = _read(TODOS, [])
    have = {(t.get("run_id"), t.get("item_id")) for t in rows}
    for it in items[:30]:
        key = (it.get("run_id"), it.get("item_id"))
        if key in have:
            continue
        rows.append({"id": "D" + uuid.uuid4().hex[:6], "business_id": bid, "conversation_id": cid, "run_id": it.get("run_id"),
                     "item_id": it.get("item_id"), "title": str(it.get("title", ""))[:200], "details": str(it.get("details", ""))[:600],
                     "department": str(it.get("department", ""))[:40], "category": str(it.get("category") or "")[:20], "guide_ids": it.get("guide_ids") or [], "done": False, "created_at": now()})
    _write(TODOS, rows)
    return todos(bid)


# ---------------------------------------------------------------- checkpoints (milestones the AI chose to record when a job was done)

CHECKPOINTS = WS / "checkpoints.json"


def checkpoints(bid: str) -> list[dict]:
    rows = [c for c in _read(CHECKPOINTS, []) if bid == ALL or c.get("business_id") == bid]
    return sorted(rows, key=lambda c: c.get("at", ""), reverse=True)


def add_checkpoint(bid: str, cp: dict) -> dict:
    rows = _read(CHECKPOINTS, [])
    c = {"id": "C" + uuid.uuid4().hex[:6], "business_id": bid, "at": now(),
         **{k: str(cp.get(k) or "")[:500] for k in ("title", "summary", "stage", "source", "ref", "icon", "by")}}
    rows.append(c)
    _write(CHECKPOINTS, rows)
    return c


def delete_checkpoint(cid: str):
    _write(CHECKPOINTS, [c for c in _read(CHECKPOINTS, []) if c["id"] != cid])


def toggle_todo(tid: str, done: bool | None = None, delete: bool = False):
    rows = _read(TODOS, [])
    if delete:
        rows = [t for t in rows if t["id"] != tid]
    for t in rows:
        if t["id"] == tid:
            t["done"] = (not t["done"]) if done is None else bool(done)
            t["done_at"] = now() if t["done"] else None
    _write(TODOS, rows)


def set_owner_type(bid: str, owner_type: str) -> dict | None:
    rows = businesses()
    hit = None
    for b in rows:
        if b["id"] == bid and owner_type in ("student", "small_business"):
            b["owner_type"] = owner_type
            hit = b
    _write(BUSINESSES, rows)
    return hit


SELL_FIELDS = ["product", "category", "style", "customers", "channel", "area", "budget", "price_range", "quantity",
               "start_when", "experience", "special"]


def set_selling_profile(bid: str, prof: dict) -> dict | None:
    rows = businesses()
    hit = None
    for b in rows:
        if b["id"] == bid:
            b["selling_profile"] = {k: str(prof.get(k) or "")[:300] for k in SELL_FIELDS} | {"updated_at": now()}
            hit = b
    _write(BUSINESSES, rows)
    return hit


def remember(bid: str, answers: dict) -> dict | None:
    """Save answers the owner gave to the agent's questions: owner_type, goal, or selling-profile fields (merged)."""
    rows = businesses()
    hit = None
    for b in rows:
        if b["id"] != bid:
            continue
        hit = b
        for key, value in answers.items():
            value = str(value or "").strip()[:300]
            if not value:
                continue
            if key == "owner_type" and value in ("student", "small_business"):
                b["owner_type"] = value
            elif key == "goal":
                b["goal"], b["goal_asked"] = value, True
            elif key in SELL_FIELDS:
                b["selling_profile"] = (b.get("selling_profile") or {}) | {key: value, "updated_at": now()}
    _write(BUSINESSES, rows)
    return hit


def selling_text(p: dict) -> str:
    labels = {"product": "What they sell", "category": "Category", "style": "Style / genre / type", "customers": "Target customers",
              "channel": "Sell online or offline", "area": "Where", "budget": "Starting budget (MYR)", "price_range": "Price range in mind",
              "quantity": "Expected quantity", "start_when": "When to start", "experience": "Skills / experience", "special": "Special requirements"}
    return "\n".join(f"- {labels[k]}: {p[k]}" for k in SELL_FIELDS if p.get(k))


def remove_business(bid: str) -> bool:
    rows = businesses()
    keep = [b for b in rows if b["id"] != bid or b.get("uses_sample_data")]
    if len(keep) == len(rows):
        return False
    _write(BUSINESSES, keep)
    for c in conversations(bid):
        delete(c["id"])
    return True


def add_collected(bid: str, paths: list[str]):
    rows = businesses()
    for b in rows:
        if b["id"] == bid:
            for p in paths:
                if p not in b.setdefault("collected", []):
                    b["collected"].append(p)
    _write(BUSINESSES, rows)


def business_context(bid: str) -> str:
    if bid == ALL:
        lines = ["The owner is asking about ALL their businesses together:"]
        for b in businesses():
            lines.append(f"- {b['name']} ({b['type']}), area: {b['area']}" + (" — has BizFlow sample data (brief/stock/po commands)" if b.get("uses_sample_data") else " — new, no sales data yet"))
        lines.append("Compare them, say which needs attention first, and only use toolkit numbers for the business that has sample data.")
        return "\n".join(lines)
    b = business(bid) or DEFAULT_BUSINESS
    ctx = [f"Business: {b['name']} — {b['type']}. Location/area: {b['area']}.", f"About: {b.get('description', '')}"]
    if b.get("owner_type") == "student":
        ctx.append("The owner is a STUDENT running this alongside their studies. Keep plans small, cheap and low-risk "
                   "(small test batches, little stock, no big spending), fit selling and prep around lectures, assignments and exam weeks, "
                   "mention the academic side where relevant (timetable, exam periods, campus rules, Student Affairs permission), "
                   "and suggest steps that take under about an hour a day. In any plan, include at least one item about fitting the "
                   "business around their timetable and exam weeks, and mention the academic trade-off in the Summary.")
    if b.get("goal"):
        ctx.append(f"OWNER'S GOAL: {b['goal']}. Every plan must move the business toward this goal; say how each step helps and how to "
                   "measure progress against it.")
    done = [t for t in todos(bid) if t.get("done")]
    if done:
        ctx.append("Already done by the owner (do not suggest again): " + "; ".join(t["title"] for t in done[-12:]) + ".")
    if b.get("selling_profile") and any(b["selling_profile"].get(k) for k in SELL_FIELDS):
        ctx.append("SELLING PROFILE from the owner's form (use it to make every plan specific — e.g. traditional costume → search "
                   "for traditional fabric suppliers such as songket/batik/kain sellers, not generic modern clothing; match budget, quantity "
                   "and channel; do not exceed the budget):\n" + selling_text(b["selling_profile"]))
    if b.get("owner_type") == "small_business":
        ctx.append("The owner runs this as a SMALL BUSINESS (their main work). Plan for steady operations: cash flow, "
                   "supplier reliability, staff, compliance and growth.")
    unknown = [label for key, label in (("owner_type", "whether the owner is a student or a small business"), ("goal", "the owner's goal"))
               if not b.get(key)]
    if not b.get("uses_sample_data") and not (b.get("selling_profile") or {}).get("product"):
        unknown.append("exactly what they will sell")
    if unknown:
        ctx.append("NOT KNOWN YET: " + "; ".join(unknown) + ". Ask about these ONLY if the current request needs them (see Step 0).")
    if b.get("uses_sample_data"):
        ctx.append("This is the business whose data the toolkit commands brief/stock/po list/suppliers/verify read.")
    else:
        ctx.append("This business is NEW: BizFlow has NO sales, stock or purchase-order data for it. Do NOT use brief, stock, "
                   "po list or verify (those belong to Campus Crumb). Use nearby (with this business's area), guide, scrape, "
                   "market, WebSearch and WebFetch; quote researched prices only with their source URL.")
    ctx.append(f"Default area for map lookups: \"{b['area']}\".")
    return "\n".join(ctx)


# ---------------------------------------------------------------- roadmap (step-by-step journey)

START_STEPS = [
    {"id": "idea", "icon": "💡", "title": "Decide what to sell and who will buy it",
     "detail": "Pick 2–3 items students want, that you can make well and cheaply.", "ask": "Help me decide what to sell to students near {area}. Suggest 3 options with reasons."},
    {"id": "competitors", "icon": "🧭", "title": "Check who already sells near you",
     "detail": "See real food places on the map, what they sell and where the gap is.", "ask": "Who are my competitors near {area} and what gap can I fill?", "tab": "map"},
    {"id": "menu", "icon": "💰", "title": "Set your menu and prices",
     "detail": "Price from your ingredient cost and what nearby sellers charge.", "ask": "Suggest a starter menu with prices, with sources for any prices you quote."},
    {"id": "ssm", "icon": "🧾", "title": "Register your business (SSM)", "detail": "Online at ezBiz; from RM30.", "guides": ["ssm-registration"]},
    {"id": "foodsafety", "icon": "🩺", "title": "Food handler course + typhoid jab", "detail": "Needed for you and every helper.", "guides": ["food-handler"]},
    {"id": "permit", "icon": "🏫", "title": "Get permission to sell (campus or council)", "detail": "Campus: Student Affairs. Outside: your council licence.", "guides": ["campus-permission", "council-licence"]},
    {"id": "suppliers", "icon": "📦", "title": "Find suppliers and compare prices",
     "detail": "Compare listed prices, online vs in-shop buying.", "ask": "Find suppliers for my ingredients near {area} and compare prices.", "tab": "suppliers"},
    {"id": "firstorder", "icon": "🛒", "title": "Buy your first stock", "detail": "Approve a purchase order; you pay the supplier yourself.", "guides": ["pay-supplier-po"], "tab": "automations"},
    {"id": "launch", "icon": "📣", "title": "Launch on social media", "detail": "Upload photos; BizFlow writes captions and hashtags and posts on schedule.", "tab": "automations", "guides": ["post-campaign"]},
    {"id": "autopilot", "icon": "🔁", "title": "Turn on auto-reorder and track sales",
     "detail": "Let BizFlow draft supplier orders when stock runs low — you approve payment.", "tab": "automations"},
]
RUN_STEPS = [
    {"id": "today", "icon": "📊", "title": "Check what needs attention today", "detail": "Low stock, stale counts, data problems.", "ask": "What needs my attention today?"},
    {"id": "recount", "icon": "🔢", "title": "Recount stale stock", "detail": "Counts older than 7 days block reorder maths.", "guides": ["recount-stock"]},
    {"id": "firstorder", "icon": "🛒", "title": "Restock low items", "detail": "Approve the purchase orders that cover low stock.", "ask": "Can I afford to restock everything this week?", "tab": "automations"},
    {"id": "autopilot", "icon": "🔁", "title": "Turn on auto-reorder", "detail": "Orders drafted when stock runs low or on a schedule; you approve payment.", "tab": "automations"},
    {"id": "competitors", "icon": "🧭", "title": "Know your competitors", "detail": "Real nearby food places on the map.", "ask": "Who are my competitors near {area} and what gap can I fill?", "tab": "map"},
    {"id": "launch", "icon": "📣", "title": "Promote slow sellers", "detail": "Post photos with SEO captions on a schedule.", "tab": "automations", "ask": "Draft a TikTok post for the granola bar."},
    {"id": "help", "icon": "👥", "title": "Get a part-time helper", "detail": "Job ad, interview kit, food-handler rules.", "guides": ["hire-helper", "food-handler"], "ask": "I need a part-time helper on Fridays."},
]


def roadmap(bid: str) -> dict:
    b = business(bid)
    if not b:
        return {"steps": []}
    steps = [dict(s) for s in (RUN_STEPS if b.get("uses_sample_data") else START_STEPS)]
    steps += b.get("roadmap_custom", [])
    status = b.get("roadmap_status", {})
    for s in steps:
        if s.get("ask"):
            s["ask"] = s["ask"].replace("{area}", b.get("area", "my area"))
        s["status"] = status.get(s["id"], s.get("status", "todo"))
    return {"business_id": bid, "journey": "Run and grow" if b.get("uses_sample_data") else "Start your business", "steps": steps}


def set_step(bid: str, step_id: str, state: str):
    rows = businesses()
    for b in rows:
        if b["id"] == bid:
            b.setdefault("roadmap_status", {})[step_id] = state if state in ("todo", "doing", "done") else "todo"
    _write(BUSINESSES, rows)


def add_steps(bid: str, items: list[dict]):
    rows = businesses()
    for b in rows:
        if b["id"] == bid:
            custom = b.setdefault("roadmap_custom", [])
            for it in items[:20]:
                custom.append({"id": "c" + uuid.uuid4().hex[:6], "icon": "📌", "title": str(it.get("title", ""))[:160],
                               "detail": str(it.get("detail", ""))[:400], "guides": [g for g in it.get("guides", []) if isinstance(g, str)][:3],
                               "from_chat": True})
    _write(BUSINESSES, rows)


# ---------------------------------------------------------------- pinned notes

PINS = WS / "pins.json"


def pins(bid: str) -> list[dict]:
    rows = _read(PINS, [])
    return [p for p in rows if bid == ALL or p.get("business_id") == bid][::-1]


def add_pin(p: dict) -> dict:
    rows = _read(PINS, [])
    pin = {"id": "N" + uuid.uuid4().hex[:6], "at": now(), **{k: str(p.get(k) or "")[:600] for k in
           ("business_id", "conversation_id", "run_id", "item_id", "kind", "title", "excerpt", "note")}}
    rows.append(pin)
    _write(PINS, rows)
    return pin


def edit_pin(pid: str, note: str | None = None, delete: bool = False):
    rows = _read(PINS, [])
    if delete:
        rows = [p for p in rows if p["id"] != pid]
    else:
        for p in rows:
            if p["id"] == pid:
                p["note"] = (note or "")[:600]
    _write(PINS, rows)


# ---------------------------------------------------------------- conversations

def conv_path(cid: str) -> Path:
    if not re.fullmatch(r"[\w-]{4,64}", cid or ""):
        raise ValueError("bad conversation id")
    return CONVS / f"{cid}.json"


def conversations(bid: str | None = None) -> list[dict]:
    out = []
    for f in CONVS.glob("*.json") if CONVS.exists() else []:
        c = _read(f, None)
        if c and (bid is None or c.get("business_id") == bid):
            out.append({k: c.get(k) for k in ("id", "business_id", "title", "created_at", "updated_at")} | {"turns": len(c.get("turns", []))})
    return sorted(out, key=lambda c: c.get("updated_at") or "", reverse=True)


def conversation(cid: str) -> dict | None:
    return _read(conv_path(cid), None)


def new_conversation(bid: str, title: str = "") -> dict:
    c = {"id": datetime.now(TZ).strftime("%m%d%H%M%S") + "-" + uuid.uuid4().hex[:4], "business_id": bid,
         "title": title or "New chat", "created_at": now(), "updated_at": now(), "turns": []}
    _write(conv_path(c["id"]), c)
    return c


def save_conversation(c: dict):
    c["updated_at"] = now()
    _write(conv_path(c["id"]), c)


def add_turn(cid: str, run_id: str, request: str):
    c = conversation(cid)
    if c is None:
        raise ValueError("unknown conversation")
    c["turns"].append({"run_id": run_id, "request": request, "at": now()})
    if c.get("title") in (None, "", "New chat"):
        c["title"] = request[:60] + ("…" if len(request) > 60 else "")
    save_conversation(c)


def rename(cid: str, title: str):
    c = conversation(cid)
    if c:
        c["title"] = title[:80] or c["title"]
        save_conversation(c)
    return c


def delete(cid: str):
    p = conv_path(cid)
    if p.exists():
        p.unlink()


def history_text(cid: str, runs: dict, limit=4) -> str:
    """Short memory of earlier turns, so follow-up questions have context."""
    c = conversation(cid)
    if not c or not c.get("turns"):
        return ""
    lines = ["Earlier in this conversation (most recent last):"]
    for t in c["turns"][-limit:]:
        r = runs.get(t["run_id"]) or {}
        plan = r.get("plan") or {}
        items = "; ".join(f"{i.get('item_id')} {i.get('title')} [{i.get('status')}]" for i in plan.get("plan_items", [])[:8])
        lines.append(f"- Owner asked: {t['request']}")
        if r.get("answer") or plan.get("understanding"):
            lines.append(f"  BizFlow answered: {(r.get('answer') or plan.get('understanding'))[:600]}")
        if items:
            lines.append(f"  Plan items: {items}")
        if plan.get("questions"):
            lines.append("  BizFlow asked the owner: " + "; ".join(q["question"] for q in plan["questions"]))
    return "\n".join(lines)
