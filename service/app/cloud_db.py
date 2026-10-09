"""Cloud-backed mirror of `db.py`'s public API, implemented on top of `cloud_client` (PostgREST).

This module is imported by `db.py` (via `from .cloud_db import *`) ONLY when `settings.use_cloud`
is True. It returns plain dicts (which support both `row["col"]` and `dict(row)`), so existing call
sites keep working. Touching `owner_id` is avoided — the database fills `DEFAULT auth.uid()` and RLS
enforces it, matching the cloud DB conventions.

NOTE: raw-SQL primitives (`query`, `query_one`, `execute`, `update`, `insert`) are NOT reimplemented
here because PostgREST cannot run arbitrary SQL. Code paths in `leads.py` / `dashboard.py` that call
those with literal SQL must be migrated to the domain functions below before `use_cloud` is enabled.
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from . import cloud_client as cc
from . import db as _local_db  # reuse datetime helpers (now_iso, to_iso, ...)
from .config import settings

# Re-export the datetime helpers so `db.now_iso()` etc. keep resolving after delegation.
utcnow = _local_db.utcnow
to_iso = _local_db.to_iso
now_iso = _local_db.now_iso
from_iso = _local_db.from_iso


# --- settings ---------------------------------------------------------------
def get_setting(key: str, default: str | None = None) -> str | None:
    row = cc.db_select_one("settings", filters={"key": key})
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    existing = cc.db_select_one("settings", filters={"key": key})
    if existing:
        cc.db_update("settings", existing["key"], {"value": value})
    else:
        cc.db_insert("settings", {"key": key, "value": value})


def reengagement_enabled() -> bool:
    return get_setting("reengagement_enabled", "0") == "1"


# --- agent profile ------------------------------------------------------------
AGENT_FIELDS = [
    "agent_name", "agency", "service_areas", "working_hours", "phone_number",
    "include_phone", "commission_policy", "marketing_services", "mortgage_partner",
    "conveyancer_partner", "showing_style",
]


def get_agent_profile() -> dict[str, Any]:
    row = cc.db_select_one("agent_profile", filters={"id": 1})
    if row is None:
        return {f: (0 if f == "include_phone" else "") for f in AGENT_FIELDS}
    return dict(row)


def save_agent_profile(values: dict[str, Any]) -> None:
    data = {f: values.get(f, 0 if f == "include_phone" else "") for f in AGENT_FIELDS}
    data["updated_at"] = now_iso()
    existing = cc.db_select_one("agent_profile", filters={"id": 1})
    if existing:
        cc.db_update("agent_profile", 1, data)
    else:
        data["id"] = 1
        cc.db_insert("agent_profile", data)


# --- leads --------------------------------------------------------------------
def new_link_code() -> str:
    return secrets.token_urlsafe(9)


def create_lead(values: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    data = {"link_code": new_link_code(), "created_at": now, "updated_at": now, **values}
    return cc.db_insert("leads", data)


def get_lead(lead_id: int) -> dict[str, Any] | None:
    return cc.db_select_one("leads", filters={"id": lead_id})


def lead_by_chat(chat_id: int | str) -> dict[str, Any] | None:
    return cc.db_select_one("leads", filters={"telegram_chat_id": str(chat_id)})


def lead_by_link_code(code: str) -> dict[str, Any] | None:
    return cc.db_select_one("leads", filters={"link_code": code})


def find_lead_by_contact(email: str | None, phone: str | None) -> dict[str, Any] | None:
    if email:
        row = cc.db_select_one("leads", raw_filters={"email": f"ilike.{email}"})
        if row:
            return row
    if phone:
        return cc.db_select_one("leads", filters={"phone": phone})
    return None


def add_message(lead_id: int, role: str, channel: str, content: str, kind: str = "chat") -> None:
    cc.db_insert("messages", {
        "lead_id": lead_id, "role": role, "channel": channel, "kind": kind,
        "content": content, "created_at": now_iso(),
    })


def messages_for(lead_id: int) -> list[dict[str, Any]]:
    return cc.db_select("messages", filters={"lead_id": lead_id}, order="id")


_ROLE_LABEL = {"lead": "User", "ai": "AI", "agent": "Agent"}


def transcript(lead_id: int) -> str:
    lines = []
    for m in messages_for(lead_id):
        label = "ORI Message" if m["kind"] == "enquiry" else _ROLE_LABEL[m["role"]]
        lines.append(f"{label}: {m['content']}")
    return "\n".join(lines)


# --- listings -----------------------------------------------------------------
def new_review_token() -> str:
    return secrets.token_urlsafe(18)


def get_listing(listing_id: int) -> dict[str, Any] | None:
    return cc.db_select_one("listings", filters={"id": listing_id})


def listing_by_token(token: str) -> dict[str, Any] | None:
    return cc.db_select_one("listings", filters={"review_token": token})


def selling_listings() -> list[dict[str, Any]]:
    return cc.db_select("listings", filters={"status": "SELLING"}, order="id")


def _norm_address(text: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in text).split())


def match_listing(address: str) -> dict[str, Any] | None:
    """Best SELLING listing for an address mentioned by a lead (containment either way)."""
    target = _norm_address(address or "")
    if len(target) < 4:
        return None
    best, best_len = None, 0
    for row in selling_listings():
        cand = _norm_address(row["address"])
        if not cand:
            continue
        if cand in target or target in cand:
            overlap = min(len(cand), len(target))
            if overlap > best_len:
                best, best_len = row, overlap
    return best


# --- generic write primitives (mirror db.insert / db.update) --------------------
def insert(table: str, values: dict[str, Any]) -> int:
    row = cc.db_insert(table, values)
    return row.get("id") or 0


def update(table: str, row_id: int, values: dict[str, Any]) -> None:
    cc.db_update(table, row_id, values)


# Raw-SQL primitives are intentionally NOT supported on cloud (PostgREST has no SQL).
# Any leftover `db.query/query_one/execute` call under `use_cloud` fails loudly so the
# offending call site gets migrated to a domain function. Dashboard analytics below
# replace the old raw-SQL endpoints.
def query(sql: str, params: Any = ()) -> list[dict[str, Any]]:
    raise NotImplementedError("Raw SQL is not supported on cloud; use a domain function instead.")


def query_one(sql: str, params: Any = ()) -> dict[str, Any] | None:
    raise NotImplementedError("Raw SQL is not supported on cloud; use a domain function instead.")


def execute(sql: str, params: Any = ()) -> int:
    raise NotImplementedError("Raw SQL is not supported on cloud; use a domain function instead.")


# --- analytics (cloud equivalents of the dashboard's old raw-SQL queries) -------
def cloud_overview() -> dict[str, Any]:
    leads = cc.db_select("leads")
    scores = [l["score"] for l in leads if l.get("score") is not None]
    by_status = {
        s: sum(1 for l in leads if l["status"] == s)
        for s in ("INITIATED", "IN_PROGRESS", "QUALIFIED", "NEEDS_AGENT", "BANNED")
    }
    pending = len(cc.db_select("pending_actions", filters={"status": "PENDING"}))
    now = now_iso()
    followups_due = sum(
        1 for l in leads
        if l["status"] in ("INITIATED", "IN_PROGRESS")
        and l.get("next_followup_at") and l["next_followup_at"] <= now
    )
    draft_listings = cc.db_select("listings", columns="id,address", filters={"status": "DRAFT"})
    since = to_iso(utcnow() - timedelta(days=7))
    hot = sorted(
        [l for l in leads
         if l["status"] == "QUALIFIED" and (l.get("score") or 0) >= settings.hot_lead_score
         and l.get("qualified_at") and l["qualified_at"] >= since],
        key=lambda l: l.get("score") or 0, reverse=True,
    )[:5]
    return {
        "totals": {
            "total": len(leads),
            "qualified": sum(1 for l in leads if l.get("is_qualified") == 1),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "needs_agent": by_status["NEEDS_AGENT"], "banned": by_status["BANNED"],
        },
        "by_status": by_status,
        "pending_approvals": pending, "followups_due": followups_due,
        "reengagement_on": get_setting("reengagement_enabled", "0") == "1",
        "briefing_on": get_setting("briefing_enabled", "1") == "1",
        "reengagement_hour": settings.reengagement_hour,
        "briefing_hour": settings.briefing_hour,
        "hot_lead_score": settings.hot_lead_score,
        "draft_listings": [dict(d) for d in draft_listings],
        "hot_leads": [dict(d) for d in hot],
    }


def cloud_list_leads(status: str = "", lead_type: str = "", q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    leads = cc.db_select("leads")
    if status:
        leads = [l for l in leads if l["status"] == status]
    if lead_type:
        leads = [l for l in leads if l["lead_type"] == lead_type.upper()]
    if q:
        ql = q.lower()
        leads = [l for l in leads if
                 (l.get("name") or "").lower().find(ql) >= 0 or
                 (l.get("email") or "").lower().find(ql) >= 0 or
                 (l.get("phone") or "").find(ql) >= 0 or
                 (l.get("property_address") or "").lower().find(ql) >= 0 or
                 (l.get("notes") or "").lower().find(ql) >= 0]
    leads.sort(key=lambda l: l.get("last_contacted_at") or l.get("created_at") or "", reverse=True)
    return [dict(l) for l in leads[:limit]]


def cloud_list_listings(status: str = "") -> list[dict[str, Any]]:
    rows = cc.db_select("listings", filters={"status": status} if status else None, order="id")
    return [dict(r) for r in rows]


def cloud_approvals() -> list[dict[str, Any]]:
    rows = cc.db_select("pending_actions", filters={"status": "PENDING"}, order="id.desc", limit=50)
    return [
        {"id": r["id"], "kind": r["kind"], "summary": r["summary"],
         "source": r["source"], "created_at": r["created_at"]}
        for r in rows
    ]


# --- cloud-compatible domain queries (PostgREST / Python-side) -------------------
# These override the local SQLite versions in db.py when use_cloud is True. The dataset
# is a single agent's pipeline, so fetching a table and filtering in Python is simple and
# avoids bespoke PostgREST query-string building. `owner_id` stays untouched: RLS fills it.

def _all_leads() -> list[dict[str, Any]]:
    return cc.db_select("leads")


def _all_listings() -> list[dict[str, Any]]:
    return cc.db_select("listings")


def _is_true(v: Any) -> bool:
    return v in (1, True)


def processed_email_exists(message_id: str) -> bool:
    return cc.db_select_one("processed_emails", filters={"message_id": message_id}) is not None


def get_pending_action(action_id: int) -> dict[str, Any] | None:
    return cc.db_select_one("pending_actions", filters={"id": action_id})


def search_leads(text: str = "", status: str = "", lead_type: str = "",
                 min_score: int | None = None, qualified_only: bool = False,
                 limit: int = 10) -> list[dict[str, Any]]:
    ql = (text or "").lower()
    out = []
    for r in _all_leads():
        if status and r["status"] != str(status).upper():
            continue
        if lead_type and r["lead_type"] != str(lead_type).upper():
            continue
        if min_score is not None and (r.get("score") or 0) < int(min_score):
            continue
        if qualified_only and not _is_true(r.get("is_qualified")):
            continue
        if ql:
            hay = " ".join(str(r.get(k) or "") for k in
                           ("name", "email", "phone", "property_address", "budget", "timeline", "notes")).lower()
            if ql not in hay:
                continue
        out.append(r)
    out.sort(key=lambda r: r.get("last_contacted_at") or r.get("created_at") or "", reverse=True)
    return out[: max(1, min(int(limit), 30))]


def recent_messages(lead_id: int, n: int = 20) -> list[dict[str, Any]]:
    n = max(1, min(int(n), 60))
    rows = cc.db_select("messages", filters={"lead_id": lead_id}, order="id.desc", limit=n)
    return [{"role": r["role"], "channel": r["channel"], "content": r["content"], "created_at": r["created_at"]}
            for r in rows]


def list_listings(status: str = "") -> list[dict[str, Any]]:
    status = (status or "").upper()
    cols = "id,address,asking_price,status,layout_specs"
    if status == "ALL":
        rows = cc.db_select("listings", columns=cols, order="id")
    elif status:
        rows = cc.db_select("listings", columns=cols, filters={"status": status}, order="id")
    else:
        rows = [r for r in cc.db_select("listings", columns=cols, order="id") if r["status"] in ("SELLING", "DRAFT")]
    return [dict(r) for r in rows]


def stats() -> dict[str, Any]:
    leads = _all_leads()
    scores = [l["score"] for l in leads if l.get("score") is not None]
    return {
        "total": len(leads),
        "qualified": sum(1 for l in leads if _is_true(l.get("is_qualified"))),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "waiting_for_agent": sum(1 for l in leads if l["status"] == "NEEDS_AGENT"),
        "in_progress": sum(1 for l in leads if l["status"] == "IN_PROGRESS"),
        "initiated": sum(1 for l in leads if l["status"] == "INITIATED"),
        "banned": sum(1 for l in leads if l["status"] == "BANNED"),
        "followups_due": sum(1 for l in leads
                             if l["status"] in ("INITIATED", "IN_PROGRESS")
                             and l.get("next_followup_at") and l["next_followup_at"] <= now_iso()),
    }


def leads_since(dt_iso: str, limit: int = 10) -> list[dict[str, Any]]:
    out = [r for r in _all_leads() if (r.get("last_contacted_at") or "") >= dt_iso]
    out.sort(key=lambda r: r.get("last_contacted_at") or "", reverse=True)
    return out[: max(1, int(limit))]


def top_qualified_since(since_iso: str, limit: int = 3) -> list[dict[str, Any]]:
    out = [r for r in _all_leads()
           if _is_true(r.get("is_qualified")) and (r.get("qualified_at") or "") >= since_iso]
    out.sort(key=lambda r: ((r.get("score") or 0), (r.get("qualified_at") or "")), reverse=True)
    return out[: max(1, int(limit))]


def summary_stats() -> dict[str, Any]:
    leads = _all_leads()
    scores = [l["score"] for l in leads if l.get("score") is not None]
    return {
        "total": len(leads),
        "new": sum(1 for l in leads if not _is_true(l.get("is_returning"))),
        "returning_count": sum(1 for l in leads if _is_true(l.get("is_returning"))),
        "qualified": sum(1 for l in leads if _is_true(l.get("is_qualified"))),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "needs_agent": sum(1 for l in leads if l["status"] == "NEEDS_AGENT"),
        "banned": sum(1 for l in leads if l["status"] == "BANNED"),
    }


def recent_qualified(limit: int = 5) -> list[dict[str, Any]]:
    out = [r for r in _all_leads() if r["status"] == "QUALIFIED"]
    out.sort(key=lambda r: r.get("qualified_at") or "", reverse=True)
    return out[: max(1, int(limit))]


def pending_actions(limit: int = 10) -> list[dict[str, Any]]:
    rows = cc.db_select("pending_actions", filters={"status": "PENDING"}, order="id.desc",
                        limit=max(1, int(limit)))
    return [dict(r) for r in rows]


def active_listings() -> list[dict[str, Any]]:
    rows = [r for r in cc.db_select("listings", columns="id,address,status", order="id")
            if r["status"] in ("SELLING", "DRAFT")]
    return [dict(r) for r in rows]


def match_candidates(listing_id: int, since_iso: str, max_candidates: int = 40) -> list[dict[str, Any]]:
    existing = {m["lead_id"] for m in cc.db_select("listing_matches", columns="lead_id",
                                                   filters={"listing_id": listing_id})}
    out = []
    for r in _all_leads():
        if r["status"] == "BANNED":
            continue
        if r["lead_type"] not in ("BUYER", "DUAL", "UNKNOWN"):
            continue
        if not (r.get("budget") or r.get("notes") or r.get("timeline")):
            continue
        if r.get("listing_id") and r["listing_id"] == listing_id:
            continue
        if not (r.get("telegram_chat_id") or r.get("email")):
            continue
        if r["id"] in existing:
            continue
        anchor = r.get("last_contacted_at") or r.get("created_at") or ""
        if anchor < since_iso:
            continue
        out.append(r)
    out.sort(key=lambda r: r.get("last_contacted_at") or r.get("created_at") or "", reverse=True)
    out.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    return out[: max(1, int(max_candidates))]


def due_followups(max_step: int, now_iso: str) -> list[dict[str, Any]]:
    out = [r for r in _all_leads()
           if r["status"] in ("INITIATED", "IN_PROGRESS")
           and (r.get("followup_step") or 0) < int(max_step)
           and r.get("next_followup_at") and r["next_followup_at"] <= now_iso]
    out.sort(key=lambda r: r.get("next_followup_at") or "")
    return out


def pending_followups(max_step: int) -> list[dict[str, Any]]:
    out = [r for r in _all_leads()
           if r["status"] in ("INITIATED", "IN_PROGRESS")
           and (r.get("followup_step") or 0) < int(max_step)
           and r.get("next_followup_at")]
    out.sort(key=lambda r: r.get("next_followup_at") or "")
    return out


def briefing_facts() -> dict[str, Any]:
    from .services import common
    leads = _all_leads()
    hot = settings.hot_lead_score
    now = utcnow()
    three_days = to_iso(now - timedelta(days=3))
    day_ago = to_iso(now - timedelta(days=1))
    end_of_day = to_iso(common.local_now().replace(hour=23, minute=59, second=59))

    def _brief(r: dict[str, Any]) -> dict[str, Any]:
        return {"id": r["id"], "name": r["name"], "type": r["lead_type"], "score": r["score"],
                "phone": r["phone"], "property": r["property_address"], "budget": r["budget"],
                "timeline": r["timeline"], "notes": r["notes"],
                "last_contact": common.fmt_local(r.get("last_contacted_at"))}

    hot_q = [r for r in leads if r["status"] == "QUALIFIED" and (r.get("score") or 0) >= hot
             and (r.get("qualified_at") or "") >= three_days]
    other_q = [r for r in leads if r["status"] == "QUALIFIED"
               and ((r.get("score") or 0) < hot or r.get("score") is None)
               and (r.get("qualified_at") or "") >= three_days]
    waiting = [r for r in leads if r["status"] == "NEEDS_AGENT"]
    new24 = [r for r in leads if (r.get("created_at") or "") >= day_ago and r["status"] != "BANNED"]
    followups_due = sum(1 for r in leads if r["status"] in ("INITIATED", "IN_PROGRESS")
                        and r.get("next_followup_at") and r["next_followup_at"] <= end_of_day)
    drafts = [{"id": r["id"], "address": r["address"]}
              for r in cc.db_select("listings", columns="id,address", filters={"status": "DRAFT"})]
    pending = len(cc.db_select("pending_actions", filters={"status": "PENDING"}))
    return {
        "hot_qualified_recently": sorted([_brief(r) for r in hot_q],
                                         key=lambda r: r.get("score") or 0, reverse=True)[:8],
        "other_qualified_recently": sorted([_brief(r) for r in other_q],
                                           key=lambda r: r.get("qualified_at") or "", reverse=True)[:8],
        "waiting_on_agent_handover": [_brief(r) for r in waiting][:8],
        "new_leads_last_24h": sorted([_brief(r) for r in new24],
                                     key=lambda r: r.get("created_at") or "", reverse=True)[:10],
        "followups_due_today": followups_due,
        "reengagement_on": get_setting("reengagement_enabled", "0") == "1",
        "draft_listings_to_review": drafts,
        "pending_approvals": pending,
        "pipeline": {
            "total": len(leads),
            "chatting": sum(1 for r in leads if r["status"] == "IN_PROGRESS"),
            "qualified": sum(1 for r in leads if r["status"] == "QUALIFIED"),
            "needs_agent": sum(1 for r in leads if r["status"] == "NEEDS_AGENT"),
        },
    }


def listing_addresses() -> set[str]:
    return {r["address"].lower() for r in cc.db_select("listings", columns="address") if r.get("address")}


def selling_count() -> int:
    return len([r for r in cc.db_select("listings", columns="id", filters={"status": "SELLING"})])


def table_rows(table: str, columns: str = "*") -> list[dict[str, Any]]:
    return cc.db_select(table, columns)
