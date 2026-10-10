"""Online Requests inbox (WhatsApp / Instagram DM / LinkedIn) and the recruiting matcher.

Channels plug in through a tiny HTTP contract (see docs/DEMO_CHANNELS_API.md):
  POST /api/channels/<channel>/incoming   {"contact": {"handle", "name"}, "text", "business_id"?}
  GET  /api/channels/<channel>/thread?handle=...  -> the thread, so the demo app can show BizFlow's replies
  POST /api/channels/linkedin/candidates  [candidate, ...]   (demo LinkedIn pushes profiles)
The owner reads and replies in BizFlow. Nothing here contacts a real person.

Recruiting: the owner sets a role (skills, days, pay, area). The engine re-scores every candidate it can see
(pushed by the demo LinkedIn, fetched from LINKEDIN_DEMO_URL, or the labelled synthetic seed) with a fixed,
explainable score out of 100 and lists new matches.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "workspace" / "inbox.json"
TZ = timezone(timedelta(hours=8))
LOCK = threading.RLock()
CHANNELS = {"whatsapp": "WhatsApp", "instagram": "Instagram", "linkedin": "LinkedIn", "shop": "Online shop"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

SEED_CANDIDATES = [  # SYNTHETIC people for the demo until the demo LinkedIn pushes real demo profiles
    {"handle": "nurul-izzah-demo", "name": "Nurul Izzah (synthetic)", "headline": "Food Science student, UM · part-time barista",
     "skills": ["customer service", "food handling", "cashier", "barista"], "availability": ["Wed", "Fri", "Sat"],
     "location": "Universiti Malaya, Kuala Lumpur", "expected_pay": 13, "certs": ["food handler", "typhoid"]},
    {"handle": "jason-tan-demo", "name": "Jason Tan (synthetic)", "headline": "Accounting student · weekend market helper",
     "skills": ["cashier", "inventory", "social media"], "availability": ["Sat", "Sun"], "location": "Petaling Jaya, Selangor",
     "expected_pay": 12, "certs": []},
    {"handle": "priya-r-demo", "name": "Priya R. (synthetic)", "headline": "Culinary diploma · baking assistant",
     "skills": ["baking", "food handling", "packing", "customer service"], "availability": ["Mon", "Fri"],
     "location": "Bangsar, Kuala Lumpur", "expected_pay": 15, "certs": ["food handler"]},
    {"handle": "amir-h-demo", "name": "Amir Hakimi (synthetic)", "headline": "Engineering student, UM · delivery rider",
     "skills": ["delivery", "customer service"], "availability": ["Tue", "Thu", "Fri"], "location": "Universiti Malaya, Kuala Lumpur",
     "expected_pay": 14, "certs": ["typhoid"]},
    {"handle": "mei-ling-demo", "name": "Lim Mei Ling (synthetic)", "headline": "Marketing student · TikTok content creator",
     "skills": ["social media", "photography", "customer service"], "availability": ["Fri", "Sat"], "location": "Kuala Lumpur",
     "expected_pay": 18, "certs": []},
]

SEED_THREADS = [
    {"channel": "whatsapp", "contact": {"handle": "60120000101", "name": "Hafiz (demo customer)"},
     "messages": [{"from": "them", "text": "Hi Campus Crumb! Can I order 2 chocolate chip cookies and 1 iced lemon tea for pickup at 3pm today?"}]},
]


def now():
    return datetime.now(TZ).isoformat(timespec="seconds")


def load():
    with LOCK:
        try:
            d = json.loads(STORE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            d = None
        if d is None:
            d = {"threads": [], "jobs": [], "candidates": [], "matches": [], "log": []}
            for t in SEED_THREADS:
                _thread(d, "campus-crumb", t["channel"], t["contact"])["messages"].extend(
                    [dict(m, id="m" + uuid.uuid4().hex[:6], at=now()) for m in t["messages"]])
            for th in d["threads"]:
                th["unread"] = len(th["messages"])
            d["candidates"] = [dict(c, source="synthetic seed", profile_url=f"/linkedin/in/{c['handle']}") for c in SEED_CANDIDATES]
            save(d)
        return d


def save(d):
    with LOCK:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STORE)


def _thread(d, bid, channel, contact):
    handle = str(contact.get("handle") or contact.get("name") or "unknown")[:80]
    th = next((t for t in d["threads"] if t["channel"] == channel and t["contact"]["handle"] == handle and t["business_id"] == bid), None)
    if not th:
        th = {"id": "T" + uuid.uuid4().hex[:7], "business_id": bid, "channel": channel,
              "contact": {"handle": handle, "name": str(contact.get("name") or handle)[:80]}, "messages": [], "unread": 0, "updated_at": now()}
        d["threads"].append(th)
    return th


def incoming(channel: str, contact: dict, text: str, bid: str = "campus-crumb") -> dict:
    if channel not in CHANNELS:
        raise ValueError("unknown channel")
    text = str(text).strip()[:2000]
    if not text:
        raise ValueError("empty message")
    with LOCK:
        d = load()
        th = _thread(d, bid, channel, contact)
        th["messages"].append({"id": "m" + uuid.uuid4().hex[:6], "from": "them", "text": text, "at": now()})
        th["unread"] = th.get("unread", 0) + 1
        th["updated_at"] = now()
        save(d)
        return th


def reply(tid: str, text: str, by: str = "owner") -> dict:
    with LOCK:
        d = load()
        th = next((t for t in d["threads"] if t["id"] == tid), None)
        if not th:
            raise ValueError("unknown thread")
        th["messages"].append({"id": "m" + uuid.uuid4().hex[:6], "from": "me", "text": str(text).strip()[:2000], "at": now(), "by": by})
        th["updated_at"] = now()
        save(d)
        return th


def threads(bid: str) -> dict:
    d = load()
    rows = [t for t in d["threads"] if bid == "all" or t["business_id"] == bid]
    rows.sort(key=lambda t: t["updated_at"], reverse=True)
    out = [{k: t[k] for k in ("id", "business_id", "channel", "contact", "unread", "updated_at")} |
           {"last": (t["messages"][-1] if t["messages"] else None), "auto_reply": t.get("auto_reply", False)} for t in rows]
    return {"threads": out, "unread": sum(t.get("unread", 0) for t in rows),
            "by_channel": {c: sum(t.get("unread", 0) for t in rows if t["channel"] == c) for c in CHANNELS}}


def thread(tid: str, mark_read=True) -> dict | None:
    with LOCK:
        d = load()
        th = next((t for t in d["threads"] if t["id"] == tid), None)
        if th and mark_read and th.get("unread"):
            th["unread"] = 0
            save(d)
        return th


def thread_for(channel: str, handle: str, bid: str = "campus-crumb") -> dict | None:
    d = load()
    return next((t for t in d["threads"] if t["channel"] == channel and t["contact"]["handle"] == handle and t["business_id"] == bid), None)


# ---------------------------------------------------------------- auto-reply + pending orders

def set_auto(tid: str, on: bool) -> dict:
    with LOCK:
        d = load()
        th = next((t for t in d["threads"] if t["id"] == tid), None)
        if not th:
            raise ValueError("unknown thread")
        th["auto_reply"] = bool(on)
        save(d)
        return th


def set_draft(tid: str, draft: dict):
    with LOCK:
        d = load()
        for t in d["threads"]:
            if t["id"] == tid:
                t["order_draft"] = draft
        save(d)


def add_order(o: dict) -> dict:
    with LOCK:
        d = load()
        d.setdefault("orders", [])
        if o.get("thread_id"):  # one open order per conversation: update it instead of duplicating
            old = next((x for x in d["orders"] if x.get("thread_id") == o["thread_id"] and x["status"] == "pending"), None)
            if old:
                old.update({k: v for k, v in o.items() if v not in (None, "", [])}, updated_at=now())
                save(d)
                return old
        o = {"id": "O" + uuid.uuid4().hex[:6], "status": "pending", "created_at": now(), **o}
        d["orders"].append(o)
        d["log"].append({"at": now(), "text": f"New pending order {o['id']} from {o.get('customer')} ({o.get('channel')}) — MYR {o.get('total')}"})
        save(d)
        return o


def orders(bid: str, status: str | None = "pending") -> list[dict]:
    d = load()
    rows = [o for o in d.get("orders", []) if (bid == "all" or o.get("business_id") == bid) and (status is None or o["status"] == status)]
    return sorted(rows, key=lambda o: o.get("when_sort") or o["created_at"])


def set_order_status(oid: str, status: str) -> dict:
    with LOCK:
        d = load()
        o = next((x for x in d.get("orders", []) if x["id"] == oid), None)
        if not o:
            raise ValueError("unknown order")
        o["status"], o["updated_at"] = status if status in ("pending", "done", "cancelled") else "pending", now()
        save(d)
        return o


# ---------------------------------------------------------------- recruiting

def add_candidates(cands: list[dict], source="demo LinkedIn") -> int:
    with LOCK:
        d = load()
        n = 0
        for c in cands[:200]:
            if not isinstance(c, dict) or not c.get("handle"):
                continue
            c = {k: c.get(k) for k in ("handle", "name", "headline", "skills", "availability", "location", "expected_pay", "certs", "profile_url", "about")}
            c["source"] = source
            d["candidates"] = [x for x in d["candidates"] if x["handle"] != c["handle"]] + [c]
            n += 1
        save(d)
        return n


def fetch_remote():
    url = os.environ.get("LINKEDIN_DEMO_URL")
    if not url:
        return 0
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        return add_candidates(data if isinstance(data, list) else data.get("candidates", []), "demo LinkedIn")
    except Exception:
        return 0


def score(job: dict, c: dict) -> dict:
    want = [s.strip().lower() for s in job.get("skills", []) if s.strip()]
    have = [s.lower() for s in (c.get("skills") or [])]
    hit = [s for s in want if any(s in h or h in s for h in have)]
    s_skill = round(40 * len(hit) / len(want)) if want else 20
    days = job.get("days") or []
    dhit = [x for x in days if x in (c.get("availability") or [])]
    s_days = round(25 * len(dhit) / len(days)) if days else 12
    pay = c.get("expected_pay")
    lo, hi = float(job.get("pay_min") or 0), float(job.get("pay_max") or 999)
    s_pay = 15 if pay is not None and lo <= float(pay) <= hi else (7 if pay is not None and float(pay) <= hi + 2 else 0)
    area_words = [w for w in re.split(r"[ ,]+", (job.get("area") or "").lower()) if len(w) > 3]
    loc = (c.get("location") or "").lower()
    s_loc = 10 if any(w in loc for w in area_words) else (5 if "kuala lumpur" in loc or "selangor" in loc else 0)
    certs = [x.lower() for x in (c.get("certs") or [])]
    s_cert = (5 if "food handler" in certs else 0) + (5 if "typhoid" in certs else 0)
    total = s_skill + s_days + s_pay + s_loc + s_cert
    why = [f"skills {len(hit)}/{len(want)} ({', '.join(hit) or 'none'}) → {s_skill}/40",
           f"available on {', '.join(dhit) or 'none of your days'} → {s_days}/25",
           f"expects MYR {pay}/h vs your MYR {lo:.0f}–{hi:.0f} → {s_pay}/15",
           f"location {c.get('location')} → {s_loc}/10",
           f"food handler/typhoid: {', '.join(certs) or 'none yet'} → {s_cert}/10"]
    return {"score": total, "why": why}


def save_job(job: dict) -> dict:
    with LOCK:
        d = load()
        job = {"id": job.get("id") or "J" + uuid.uuid4().hex[:5], "business_id": job.get("business_id") or "campus-crumb",
               "title": str(job.get("title") or "Part-time helper")[:80],
               "skills": [s.strip() for s in (job.get("skills") or []) if str(s).strip()][:12],
               "days": [x for x in (job.get("days") or []) if x in DAYS], "pay_min": job.get("pay_min") or 12, "pay_max": job.get("pay_max") or 15,
               "area": str(job.get("area") or "")[:120], "min_score": int(job.get("min_score") or 60), "active": bool(job.get("active", True)),
               "created_at": job.get("created_at") or now(), "last_scan": None}
        d["jobs"] = [j for j in d["jobs"] if j["id"] != job["id"]] + [job]
        d["log"].append({"at": now(), "text": f"Recruiting: searching for '{job['title']}'"})
        save(d)
    scan()
    return job


def scan() -> list[dict]:
    """Re-score all candidates for every active job; remember new matches."""
    fetch_remote()
    with LOCK:
        d = load()
        new = []
        for job in d["jobs"]:
            if not job.get("active"):
                continue
            for c in d["candidates"]:
                sc = score(job, c)
                m = next((x for x in d["matches"] if x["job_id"] == job["id"] and x["handle"] == c["handle"]), None)
                if sc["score"] >= job.get("min_score", 60):
                    if not m:
                        m = {"job_id": job["id"], "handle": c["handle"], "found_at": now(), "status": "new"}
                        d["matches"].append(m)
                        new.append(m)
                        d["log"].append({"at": now(), "text": f"Recruiting: new match {c['name']} ({sc['score']}/100) for {job['title']}"})
                    m.update(score=sc["score"], why=sc["why"])
                elif m and m["status"] == "new":
                    d["matches"].remove(m)
            job["last_scan"] = now()
        d["log"] = d["log"][-300:]
        save(d)
        return new


def recruiting(bid: str) -> dict:
    d = load()
    jobs = [j for j in d["jobs"] if bid == "all" or j["business_id"] == bid]
    ids = {j["id"] for j in jobs}
    cands = {c["handle"]: c for c in d["candidates"]}
    matches = sorted([dict(m, candidate=cands.get(m["handle"], {})) for m in d["matches"] if m["job_id"] in ids], key=lambda m: -m.get("score", 0))
    sources = sorted({c.get("source", "") for c in d["candidates"]})
    return {"jobs": jobs, "matches": matches, "candidates_seen": len(d["candidates"]), "sources": sources,
            "remote": bool(os.environ.get("LINKEDIN_DEMO_URL"))}


def contact_candidate(job_id: str, handle: str, text: str, bid: str) -> dict:
    with LOCK:
        d = load()
        c = next((x for x in d["candidates"] if x["handle"] == handle), None)
        if not c:
            raise ValueError("unknown candidate")
        th = _thread(d, bid, "linkedin", {"handle": handle, "name": c["name"]})
        th["messages"].append({"id": "m" + uuid.uuid4().hex[:6], "from": "me", "text": text.strip()[:2000], "at": now(), "by": "owner"})
        th["updated_at"] = now()
        for m in d["matches"]:
            if m["job_id"] == job_id and m["handle"] == handle:
                m["status"] = "contacted"
                m["thread_id"] = th["id"]
        save(d)
        return th
