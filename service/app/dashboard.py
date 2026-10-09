"""Admin web console: a browser alternative to the Telegram bot.

Exposes a JSON API under /api/admin/* plus the static console at /admin. Every action
reuses the existing service layer (leads, listings, actions, matching, reengagement,
briefing, copilot) so the web console behaves exactly like the bot.

Optional shared-secret gate: set ADMIN_DASHBOARD_KEY in .env. When set, every
/api/admin/* call (except login / auth-status) must carry the header
`X-Admin-Key: <key>`. The console shows a login screen in that case.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse

from . import db
from .config import settings
from .services import actions, briefing, common, copilot, leads, listings, matching, reengagement
from .export import build_workbook

WEBROOT = Path(__file__).resolve().parent.parent / "webroot"

STATUS_LABEL = {
    "INITIATED": "Initiated", "IN_PROGRESS": "In Progress", "QUALIFIED": "Qualified",
    "NEEDS_AGENT": "Needs Agent", "BANNED": "Banned",
}


def _lead_public(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"], "name": r["name"], "email": r["email"], "phone": r["phone"],
        "telegram_chat_id": r["telegram_chat_id"], "telegram_username": r["telegram_username"],
        "lead_type": r["lead_type"], "status": r["status"], "status_label": STATUS_LABEL.get(r["status"], r["status"]),
        "is_qualified": r["is_qualified"], "score": r["score"],
        "property_address": r["property_address"], "listing_id": r["listing_id"],
        "budget": r["budget"], "timeline": r["timeline"], "pre_approval": r["pre_approval"],
        "notes": r["notes"], "source": r["source"], "is_returning": r["is_returning"],
        "created_at": r["created_at"], "last_contacted_at": r["last_contacted_at"],
    }


# --- auth --------------------------------------------------------------------

def _require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    # Backdoor: a configured static key always works (and is the only option when cloud is off).
    if settings.admin_dashboard_key and x_admin_key == settings.admin_dashboard_key:
        return
    if settings.use_cloud:
        from . import cloud_client
        if not x_admin_key or not cloud_client.auth_user_me(x_admin_key):
            raise HTTPException(status_code=401, detail="unauthorized")
        return
    if settings.admin_dashboard_key:
        raise HTTPException(status_code=401, detail="unauthorized")
    # No key configured and cloud off -> open access.


def _body_key(payload: dict[str, Any]) -> str:
    return str(payload.get("key", "") or "")


# Public routes: static console + auth handshake (no admin key required).
public_router = APIRouter()


@public_router.get("/admin")
async def admin_page() -> FileResponse:
    return FileResponse(WEBROOT / "admin.html")


@public_router.get("/admin.css")
async def admin_css() -> FileResponse:
    return FileResponse(WEBROOT / "admin.css", media_type="text/css")


@public_router.get("/admin.js")
async def admin_js() -> FileResponse:
    return FileResponse(WEBROOT / "admin.js", media_type="application/javascript")


@public_router.get("/api/admin/auth-status")
async def auth_status() -> dict[str, Any]:
    # Cloud mode uses email+password (the console shows a login form); static key is the fallback.
    return {"required": bool(settings.admin_dashboard_key) or settings.use_cloud,
            "cloud": settings.use_cloud}


@public_router.post("/api/admin/login")
async def login(payload: dict[str, Any]) -> dict[str, Any]:
    if settings.use_cloud:
        from . import cloud_client
        email = str(payload.get("email") or "")
        password = str(payload.get("password") or "")
        try:
            sess = cloud_client.auth_signin(email, password)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail=f"cloud auth failed: {exc}")
        return {"ok": True, "token": sess.get("access_token")}
    key = settings.admin_dashboard_key
    if not key:
        return {"ok": True, "note": "open access"}
    if _body_key(payload) != key:
        raise HTTPException(status_code=401, detail="wrong key")
    return {"ok": True}


# Protected routes: every endpoint requires the admin key when one is configured.
dashboard_router = APIRouter(dependencies=[Depends(_require_admin)])


# --- overview / stats --------------------------------------------------------

@dashboard_router.get("/api/admin/overview")
async def overview() -> dict[str, Any]:
    if settings.use_cloud:
        return db.cloud_overview()
    s = db.query_one(
        "SELECT COUNT(*) total, SUM(is_qualified = 1) qualified, ROUND(AVG(score),1) avg_score, "
        "SUM(status = 'NEEDS_AGENT') needs_agent, SUM(status = 'BANNED') banned "
        "FROM leads"
    )
    by_status = db.query_one(
        "SELECT SUM(status='INITIATED') initiated, SUM(status='IN_PROGRESS') in_progress, "
        "SUM(status='QUALIFIED') qualified, SUM(status='NEEDS_AGENT') needs_agent, "
        "SUM(status='BANNED') banned FROM leads"
    )
    pending = db.query_one("SELECT COUNT(*) n FROM pending_actions WHERE status='PENDING'")["n"]
    followups_due = db.query_one(
        "SELECT COUNT(*) n FROM leads WHERE status IN ('INITIATED','IN_PROGRESS') "
        "AND next_followup_at IS NOT NULL AND next_followup_at <= ?", [db.now_iso()]
    )["n"]
    draft_listings = db.query("SELECT id, address FROM listings WHERE status='DRAFT'")
    since = db.to_iso(db.utcnow() - timedelta(days=7))
    hot = db.query(
        "SELECT * FROM leads WHERE status='QUALIFIED' AND score >= ? AND qualified_at >= ? "
        "ORDER BY score DESC LIMIT 5", [settings.hot_lead_score, since]
    )
    return {
        "totals": dict(s), "by_status": dict(by_status),
        "pending_approvals": pending, "followups_due": followups_due,
        "reengagement_on": db.reengagement_enabled(),
        "briefing_on": db.get_setting("briefing_enabled", "1") == "1",
        "reengagement_hour": settings.reengagement_hour,
        "briefing_hour": settings.briefing_hour,
        "hot_lead_score": settings.hot_lead_score,
        "draft_listings": [dict(r) for r in draft_listings],
        "hot_leads": [_lead_public(r) for r in hot],
    }


# --- leads -------------------------------------------------------------------

@dashboard_router.get("/api/admin/leads")
async def list_leads(status: str = "", lead_type: str = "", q: str = "", limit: int = 100) -> list[dict[str, Any]]:
    where, params = ["1=1"], []
    if status:
        where.append("status = ?")
        params.append(status)
    if lead_type:
        where.append("lead_type = ?")
        params.append(lead_type.upper())
    if q:
        like = f"%{q}%"
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR property_address LIKE ? OR notes LIKE ?)")
        params += [like] * 5
    limit = max(1, min(limit, 500))
    if settings.use_cloud:
        return [_lead_public(r) for r in db.cloud_list_leads(status, lead_type, q, limit)]
    rows = db.query(
        f"SELECT * FROM leads WHERE {' AND '.join(where)} "
        f"ORDER BY COALESCE(last_contacted_at, created_at) DESC LIMIT {limit}", params
    )
    return [_lead_public(r) for r in rows]


@dashboard_router.get("/api/admin/leads/{lead_id}")
async def lead_detail(lead_id: int) -> dict[str, Any]:
    lead = db.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="no such lead")
    msgs = db.messages_for(lead_id)
    transcript = [
        {"role": m["role"], "channel": m["channel"], "kind": m["kind"],
         "content": m["content"], "at": m["created_at"]}
        for m in msgs
    ]
    return {"lead": _lead_public(lead), "transcript": transcript}


@dashboard_router.post("/api/admin/leads/{lead_id}/reply")
async def reply_lead(lead_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty message")
    result = await leads.agent_reply(lead_id, text)
    return {"ok": True, "message": result}


@dashboard_router.post("/api/admin/leads/{lead_id}/status")
async def status_lead(lead_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").upper()
    if status not in actions.LEAD_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    result = leads.set_status(lead_id, status)
    return {"ok": True, "message": result}


# --- listings ----------------------------------------------------------------

@dashboard_router.get("/api/admin/listings")
async def list_listings(status: str = "") -> list[dict[str, Any]]:
    if settings.use_cloud:
        return db.cloud_list_listings(status)
    if status:
        rows = db.query("SELECT * FROM listings WHERE status = ? ORDER BY id", [status.upper()])
    else:
        rows = db.query("SELECT * FROM listings ORDER BY id")
    return [dict(r) for r in rows]


@dashboard_router.get("/api/admin/listings/{listing_id}")
async def listing_detail(listing_id: int) -> dict[str, Any]:
    listing = db.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="no such listing")
    return {"listing": dict(listing)}


@dashboard_router.post("/api/admin/listings/{listing_id}/status")
async def status_listing(listing_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").upper()
    if status not in actions.LISTING_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    result = listings.set_status(listing_id, status)
    return {"ok": True, "message": result}


@dashboard_router.post("/api/admin/match/{listing_id}")
async def match_listing(listing_id: int) -> dict[str, Any]:
    found = await matching.find_matches(listing_id, notify=False)
    return {"ok": True, **found}


# --- approvals ---------------------------------------------------------------

@dashboard_router.get("/api/admin/approvals")
async def approvals() -> list[dict[str, Any]]:
    if settings.use_cloud:
        return db.cloud_approvals()
    rows = db.query("SELECT * FROM pending_actions WHERE status='PENDING' ORDER BY id DESC LIMIT 50")
    return [
        {"id": r["id"], "kind": r["kind"], "summary": r["summary"],
         "source": r["source"], "created_at": r["created_at"]}
        for r in rows
    ]


@dashboard_router.post("/api/admin/approvals/{action_id}/decide")
async def decide_approval(action_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    approve = bool(payload.get("approve"))
    result = await actions.decide(action_id, approve)
    return {"ok": True, "message": result}


# --- settings / control ------------------------------------------------------

@dashboard_router.get("/api/admin/settings")
async def settings_get() -> dict[str, Any]:
    return {
        "reengagement_on": db.reengagement_enabled(),
        "briefing_on": db.get_setting("briefing_enabled", "1") == "1",
        "reengagement_hour": settings.reengagement_hour,
        "briefing_hour": settings.briefing_hour,
        "timezone": settings.timezone,
        "mail_enabled": settings.mail_enabled,
        "telegram_enabled": settings.telegram_enabled,
        "llm_configured": bool(settings.llm_api_key),
    }


@dashboard_router.post("/api/admin/settings/reengagement")
async def set_reengagement(payload: dict[str, Any]) -> dict[str, Any]:
    db.set_setting("reengagement_enabled", "1" if payload.get("enabled") else "0")
    return {"ok": True, "reengagement_on": bool(payload.get("enabled"))}


@dashboard_router.post("/api/admin/settings/briefing")
async def set_briefing(payload: dict[str, Any]) -> dict[str, Any]:
    db.set_setting("briefing_enabled", "1" if payload.get("enabled") else "0")
    return {"ok": True, "briefing_on": bool(payload.get("enabled"))}


@dashboard_router.post("/api/admin/run_followups")
async def run_followups() -> dict[str, Any]:
    result = await reengagement.run(force=True)
    return {"ok": True, "message": result}


@dashboard_router.post("/api/admin/briefing")
async def briefing_now() -> dict[str, Any]:
    text = await briefing.build()
    return {"ok": True, "text": text}


@dashboard_router.get("/api/admin/profile")
async def profile_get() -> dict[str, Any]:
    return {"profile": db.get_agent_profile(), "fields": db.AGENT_FIELDS}


@dashboard_router.post("/api/admin/profile")
async def profile_post(payload: dict[str, Any]) -> dict[str, Any]:
    field = str(payload.get("field") or "")
    value = payload.get("value")
    if field not in db.AGENT_FIELDS:
        raise HTTPException(status_code=400, detail="invalid field")
    profile = db.get_agent_profile()
    if field == "include_phone":
        profile[field] = 1 if str(value).strip().lower() in ("1", "yes", "true", "on") else 0
    else:
        profile[field] = str(value)
    db.save_agent_profile(profile)
    return {"ok": True}


# --- copilot -----------------------------------------------------------------

@dashboard_router.post("/api/admin/copilot")
async def copilot_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="empty message")
    result = await copilot.handle_web("web-admin", message)
    return {"ok": True, "answer": result.get("answer", ""), "proposals": result.get("proposals", [])}


@dashboard_router.post("/api/admin/copilot/reset")
async def copilot_reset() -> dict[str, Any]:
    copilot.reset("web-admin")
    return {"ok": True}


# --- export ------------------------------------------------------------------

@dashboard_router.get("/api/admin/export")
async def export_xlsx() -> Response:
    content = build_workbook()
    stamp = common.local_now().strftime("%Y%m%d-%H%M")
    return Response(
        content,
        headers={"Content-Disposition": f"attachment; filename=lead-database-{stamp}.xlsx"},
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
