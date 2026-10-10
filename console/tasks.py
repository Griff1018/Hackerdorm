"""Repetitive tasks: everyday jobs and reports for a student seller or a small business.

Each task has a title and an editable prompt, and is either AI-automated (Enterprise Buddy runs the prompt through the
WorkBuddy CLI with read-only toolkit tools) or manual (the owner ticks it off). "Execute all AI-automated tasks"
runs every AI task, three at a time, and stores each result on its card.

Daily list: once a day (or on demand) Enterprise Buddy turns these routine cards plus the business's current state into today's
concrete checklist. The routine cards are the standing instructions for that generation.
"""
from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "workspace" / "tasks.json"
TZ = timezone(timedelta(hours=8))
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(3)

COMMON = [
    ("Daily sales & cash summary", "Give me today's short sales summary from my latest brief: revenue, best and worst seller, gross margin, and anything unusual.", "ai"),
    ("Low stock check", "Which ingredients and products are running low or below my low level? Read data/workspace/ingredient_stock.json and use the stock command. List what to reorder first.", "ai"),
    ("Unanswered customer messages", "Read data/workspace/inbox.json. List customer messages that still need a reply (last message from the customer), oldest first, with a one-line suggested reply using menu prices only.", "ai"),
    ("Supplier price watch", "Run python -m app.enterprise_buddy_cli prices and tell me which of my ingredients got cheaper or dearer and what that means for my costs. One bullet per change.", "ai"),
    ("Profit report", "Write my profit report from the latest brief and data/output/business_snapshot.json (period totals and per-product figures): revenue, cost of goods, gross profit and margin, top and bottom product by profit, and one action for next week. Do not add up sales rows yourself.", "ai"),
    ("Plan this week's social posts", "Suggest 3 social posts for this week (what to show, which day, which product) based on what is overstocked or selling slowly. Drafts only.", "ai"),
    ("Pay suppliers and bills", "Pay any approved purchase orders and unpaid expenses yourself (Enterprise Buddy never pays).", "manual"),
    ("Recount stock", "Count ingredients and products and update the counts in Automations → Ingredients.", "manual"),
]
STUDENT = [
    ("Fit selling around my classes", "I am a student. Suggest a selling schedule for this week that avoids lecture and exam times and keeps prep under 1 hour a day. If you do not know my timetable, give a template and tell me what to fill in.", "ai"),
    ("Study-business balance check", "Block study hours before tests and assignments; skip selling on exam days.", "manual"),
]
SMALL = [
    ("Monthly cash-flow check", "Check my recorded expenses (paid / unpaid) against revenue and tell me if cash will be tight this month. Use toolkit numbers only.", "ai"),
    ("Staff roster", "Confirm helper shifts for the week and food-handler certificates.", "manual"),
]


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def _all():
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STORE)


def _mk(title, prompt, mode):
    return {"id": "K" + uuid.uuid4().hex[:6], "title": title, "prompt": prompt, "mode": mode, "status": "idle", "result": "", "last_run": None}


def tasks(bid: str, owner_type: str | None) -> list[dict]:
    with LOCK:
        d = _all()
        typed = d.setdefault("_typed", {})
        if bid not in d:
            d[bid] = [_mk(*t) for t in COMMON]
        if owner_type and typed.get(bid) != owner_type:
            # add the student / small-business tasks once the owner has said which they are
            have = {t["title"] for t in d[bid]}
            d[bid] += [_mk(*t) for t in (STUDENT if owner_type == "student" else SMALL) if t[0] not in have]
            typed[bid] = owner_type
        _save(d)
        return d[bid]


def upsert(bid: str, task: dict) -> dict:
    with LOCK:
        d = _all()
        rows = d.setdefault(bid, [])
        t = next((x for x in rows if x["id"] == task.get("id")), None)
        if not t:
            t = _mk(str(task.get("title") or "New task")[:80], str(task.get("prompt") or "")[:1500], task.get("mode") if task.get("mode") in ("ai", "manual") else "ai")
            rows.append(t)
        else:
            for k in ("title", "prompt"):
                if task.get(k) is not None:
                    t[k] = str(task[k])[:1500 if k == "prompt" else 80]
            if task.get("mode") in ("ai", "manual"):
                t["mode"] = task["mode"]
            if task.get("status") in ("idle", "done"):
                t["status"] = task["status"]
                if task["status"] == "done" and t["mode"] == "manual":
                    t["last_run"] = now()
        _save(d)
        return t


def delete(bid: str, tid: str):
    with LOCK:
        d = _all()
        d[bid] = [x for x in d.get(bid, []) if x["id"] != tid]
        _save(d)


def _set(bid, tid, **kv):
    with LOCK:
        d = _all()
        for t in d.get(bid, []):
            if t["id"] == tid:
                t.update(kv)
        _save(d)


def run(bid: str, ids: list[str], runner) -> int:
    """Queue tasks; runner(task) -> (ok, text). Returns how many were queued."""
    rows = [t for t in _all().get(bid, []) if t["id"] in ids and t["mode"] == "ai" and t["status"] != "running"]
    for t in rows:
        _set(bid, t["id"], status="queued", result="")

    def work(t):
        _set(bid, t["id"], status="running")
        try:
            ok, text = runner(t)
        except Exception as exc:  # report on the card
            ok, text = False, f"Failed: {exc}"
        _set(bid, t["id"], status="done" if ok else "error", result=text, last_run=now())

    for t in rows:
        POOL.submit(work, t)
    return len(rows)


# ---------------------------------------------------------------- daily list (generated from the routine cards)

def today() -> str:
    return datetime.now(TZ).date().isoformat()


def daily(bid: str) -> dict:
    return _all().get("_daily", {}).get(bid) or {"date": None, "status": "idle", "items": []}


def _set_daily(bid: str, **kv) -> dict:
    with LOCK:
        d = _all()
        cur = d.setdefault("_daily", {}).setdefault(bid, {"date": None, "status": "idle", "items": []})
        cur.update(kv)
        _save(d)
        return cur


def generate_daily(bid: str, runner) -> bool:
    """Start generating today's list in the background; runner(prev_daily) -> list of task dicts. False if already running."""
    with LOCK:
        cur = daily(bid)
        if cur.get("status") == "running":
            return False
        _set_daily(bid, status="running", error="")

    def work():
        try:
            items = runner(cur)
        except Exception as exc:
            _set_daily(bid, status="error", error=str(exc)[:300], failed_on=today())
            return
        rows = [{"id": "Y" + uuid.uuid4().hex[:6], "title": str(t.get("title") or "")[:160], "detail": str(t.get("detail") or "")[:400],
                 "routine": str(t.get("routine") or "")[:80], "priority": "high" if t.get("priority") == "high" else "normal",
                 "ask": str(t.get("ask") or "")[:400], "done": False}
                for t in items if isinstance(t, dict) and t.get("title")][:12]
        if not rows:
            _set_daily(bid, status="error", error="The agent returned no tasks — press Regenerate to try again.", failed_on=today())
        else:
            _set_daily(bid, status="done", date=today(), items=rows, generated_at=now(), error="")

    POOL.submit(work)
    return True


def toggle_daily(bid: str, item_id: str, done: bool):
    with LOCK:
        d = _all()
        for t in d.get("_daily", {}).get(bid, {}).get("items", []):
            if t["id"] == item_id:
                t["done"] = bool(done)
        _save(d)
