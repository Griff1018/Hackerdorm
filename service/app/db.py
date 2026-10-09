"""SQLite access. All DB calls run on the event-loop thread; keep them short."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

LISTING_FIELDS = [
    "address", "property_type", "asking_price", "method_of_sale", "auction_date",
    "layout_specs", "aspect", "parking", "inclusions", "outdoor_features",
    "tenancy_income", "zoning", "easements", "strata_status", "strata_levies",
    "council_rates", "water_rates", "pet_policy", "rental_policy", "upgrades",
    "vendor_terms", "occupancy_access", "inspection_windows",
]

AGENT_FIELDS = [
    "agent_name", "agency", "service_areas", "working_hours", "phone_number",
    "include_phone", "commission_policy", "marketing_services", "mortgage_partner",
    "conveyancer_partner", "showing_style",
]

_conn: sqlite3.Connection | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def now_iso() -> str:
    return to_iso(utcnow())  # type: ignore[return-value]


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open (or reopen) the global connection and apply the schema."""
    global _conn
    if _conn is not None:
        _conn.close()
    if path is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        path = settings.db_path
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _conn = conn
    return conn


def conn() -> sqlite3.Connection:
    return _conn if _conn is not None else connect()


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    cur = conn().execute(sql, tuple(params))
    return cur.lastrowid or cur.rowcount


# Tables that carry an `updated_at` column. Most do, but some (e.g. pending_actions)
# deliberately do not — blindly injecting the column makes every write to those tables
# fail with "no such column: updated_at".
_TABLES_WITH_UPDATED_AT = {
    "leads", "listings", "messages", "agent_profile", "settings",
    "enquiries", "listing_matches",
}


def update(table: str, row_id: int, values: dict[str, Any]) -> None:
    if not values:
        return
    if table in _TABLES_WITH_UPDATED_AT:
        values = {**values, "updated_at": now_iso()}
    cols = ", ".join(f"{k} = ?" for k in values)
    execute(f"UPDATE {table} SET {cols} WHERE id = ?", [*values.values(), row_id])


def insert(table: str, values: dict[str, Any]) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))


# --- settings ---------------------------------------------------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT value FROM settings WHERE key = ?", [key])
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [key, value],
    )


def reengagement_enabled() -> bool:
    return get_setting("reengagement_enabled", "0") == "1"


# --- agent profile ------------------------------------------------------------

def get_agent_profile() -> dict[str, Any]:
    row = query_one("SELECT * FROM agent_profile WHERE id = 1")
    if row is None:
        return {f: (0 if f == "include_phone" else "") for f in AGENT_FIELDS}
    return dict(row)


def save_agent_profile(values: dict[str, Any]) -> None:
    data = {f: values.get(f, 0 if f == "include_phone" else "") for f in AGENT_FIELDS}
    data["updated_at"] = now_iso()
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    updates = ", ".join(f"{k} = excluded.{k}" for k in data)
    execute(
        f"INSERT INTO agent_profile (id, {cols}) VALUES (1, {marks}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        list(data.values()),
    )


# --- leads --------------------------------------------------------------------

def new_link_code() -> str:
    return secrets.token_urlsafe(9)


def create_lead(values: dict[str, Any]) -> sqlite3.Row:
    now = now_iso()
    data = {"link_code": new_link_code(), "created_at": now, "updated_at": now, **values}
    lead_id = insert("leads", data)
    return get_lead(lead_id)  # type: ignore[return-value]


def get_lead(lead_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM leads WHERE id = ?", [lead_id])


def lead_by_chat(chat_id: int | str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM leads WHERE telegram_chat_id = ?", [str(chat_id)])


def lead_by_link_code(code: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM leads WHERE link_code = ?", [code])


def find_lead_by_contact(email: str | None, phone: str | None) -> sqlite3.Row | None:
    if email:
        row = query_one(
            "SELECT * FROM leads WHERE lower(email) = lower(?) ORDER BY id DESC LIMIT 1", [email]
        )
        if row:
            return row
    if phone:
        return query_one("SELECT * FROM leads WHERE phone = ? ORDER BY id DESC LIMIT 1", [phone])
    return None


def add_message(lead_id: int, role: str, channel: str, content: str, kind: str = "chat") -> None:
    insert("messages", {
        "lead_id": lead_id, "role": role, "channel": channel, "kind": kind,
        "content": content, "created_at": now_iso(),
    })


def messages_for(lead_id: int) -> list[sqlite3.Row]:
    return query("SELECT * FROM messages WHERE lead_id = ? ORDER BY id", [lead_id])


_ROLE_LABEL = {"lead": "User", "ai": "AI", "agent": "Agent"}


def transcript(lead_id: int) -> str:
    """Chat history in the 'User: ... / AI: ...' shape the prompts were written for."""
    lines = []
    for m in messages_for(lead_id):
        label = "ORI Message" if m["kind"] == "enquiry" else _ROLE_LABEL[m["role"]]
        lines.append(f"{label}: {m['content']}")
    return "\n".join(lines)


# --- listings -----------------------------------------------------------------

def new_review_token() -> str:
    return secrets.token_urlsafe(18)


def get_listing(listing_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM listings WHERE id = ?", [listing_id])


def listing_by_token(token: str) -> sqlite3.Row | None:
    return query_one("SELECT * FROM listings WHERE review_token = ?", [token])


def selling_listings() -> list[sqlite3.Row]:
    return query("SELECT * FROM listings WHERE status = 'SELLING' ORDER BY id")


def _norm_address(text: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in text).split())


def match_listing(address: str) -> sqlite3.Row | None:
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


# --- Cloud-compatible domain queries (local SQLite implementations) -------------
# Every function here has a matching implementation in cloud_db.py (PostgREST). The
# cloud versions override these via `from .cloud_db import *` when use_cloud is True.
# Service code calls these by name so the same call sites work on both backends.

def processed_email_exists(message_id: str) -> bool:
    return query_one("SELECT 1 FROM processed_emails WHERE message_id = ?", [message_id]) is not None


def get_pending_action(action_id: int) -> sqlite3.Row | None:
    return query_one("SELECT * FROM pending_actions WHERE id = ?", [action_id])


def search_leads(text: str = "", status: str = "", lead_type: str = "",
                 min_score: int | None = None, qualified_only: bool = False,
                 limit: int = 10) -> list:
    where, params = ["1=1"], []
    if text:
        like = f"%{text}%"
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ? OR property_address LIKE ? "
                     "OR budget LIKE ? OR timeline LIKE ? OR notes LIKE ?)")
        params += [like] * 7
    if status:
        where.append("status = ?")
        params.append(str(status).upper())
    if lead_type:
        where.append("lead_type = ?")
        params.append(str(lead_type).upper())
    if min_score is not None:
        where.append("score >= ?")
        params.append(int(min_score))
    if qualified_only:
        where.append("is_qualified = 1")
    limit = max(1, min(int(limit), 30))
    return query(
        f"SELECT * FROM leads WHERE {' AND '.join(where)} "
        f"ORDER BY last_contacted_at DESC LIMIT {limit}", params,
    )


def recent_messages(lead_id: int, n: int = 20) -> list:
    n = max(1, min(int(n), 60))
    return query(
        "SELECT role, channel, content, created_at FROM messages WHERE lead_id = ? "
        "ORDER BY id DESC LIMIT ?", [lead_id, n],
    )


def list_listings(status: str = "") -> list:
    status = (status or "").upper()
    if status == "ALL":
        return query("SELECT id, address, asking_price, status, layout_specs FROM listings ORDER BY id")
    if status:
        return query("SELECT id, address, asking_price, status, layout_specs FROM listings "
                     "WHERE status = ?", [status])
    return query("SELECT id, address, asking_price, status, layout_specs FROM listings "
                 "WHERE status IN ('SELLING', 'DRAFT') ORDER BY id")


def stats() -> dict[str, Any]:
    row = query_one(
        "SELECT COUNT(*) total, SUM(is_qualified = 1) qualified, ROUND(AVG(score), 1) avg_score, "
        "SUM(status = 'NEEDS_AGENT') waiting_for_agent, SUM(status = 'IN_PROGRESS') in_progress, "
        "SUM(status = 'INITIATED') initiated, SUM(status = 'BANNED') banned, "
        "SUM(next_followup_at IS NOT NULL AND next_followup_at <= ?) followups_due FROM leads", [now_iso()],
    )
    return dict(row) if row else {}


def leads_since(dt_iso: str, limit: int = 10) -> list:
    return query("SELECT * FROM leads WHERE last_contacted_at >= ? ORDER BY last_contacted_at DESC LIMIT ?",
                 [dt_iso, int(limit)])


def top_qualified_since(since_iso: str, limit: int = 3) -> list:
    return query("SELECT * FROM leads WHERE is_qualified = 1 AND qualified_at >= ? "
                 "ORDER BY score DESC, qualified_at DESC LIMIT ?", [since_iso, int(limit)])


def summary_stats() -> dict[str, Any]:
    s = query_one(
        "SELECT COUNT(*) total, SUM(is_returning = 0) new, SUM(is_returning = 1) returning_count, "
        "SUM(is_qualified = 1) qualified, AVG(score) avg_score, SUM(status = 'NEEDS_AGENT') needs_agent, "
        "SUM(status = 'BANNED') banned FROM leads")
    return dict(s) if s else {}


def recent_qualified(limit: int = 5) -> list:
    return query("SELECT * FROM leads WHERE status = 'QUALIFIED' ORDER BY qualified_at DESC LIMIT ?",
                 [int(limit)])


def pending_actions(limit: int = 10) -> list:
    return query("SELECT * FROM pending_actions WHERE status = 'PENDING' ORDER BY id DESC LIMIT ?",
                 [int(limit)])


def active_listings() -> list:
    return query("SELECT id, address, status FROM listings WHERE status IN ('SELLING', 'DRAFT') ORDER BY id")


def match_candidates(listing_id: int, since_iso: str, max_candidates: int = 40) -> list:
    return query(
        "SELECT * FROM leads WHERE status != 'BANNED' AND lead_type IN ('BUYER', 'DUAL', 'UNKNOWN') "
        "AND (budget IS NOT NULL OR notes IS NOT NULL OR timeline IS NOT NULL) "
        "AND (listing_id IS NULL OR listing_id != ?) "
        "AND (telegram_chat_id IS NOT NULL OR email IS NOT NULL) "
        "AND id NOT IN (SELECT lead_id FROM listing_matches WHERE listing_id = ?) "
        "AND COALESCE(last_contacted_at, created_at) >= ? "
        "ORDER BY score IS NULL, score DESC, last_contacted_at DESC LIMIT ?",
        [listing_id, listing_id, since_iso, int(max_candidates)],
    )


def due_followups(max_step: int, now_iso: str) -> list:
    return query(
        "SELECT * FROM leads WHERE status IN ('INITIATED', 'IN_PROGRESS') "
        "AND followup_step < ? AND next_followup_at IS NOT NULL AND next_followup_at <= ? "
        "ORDER BY next_followup_at", [int(max_step), now_iso],
    )


def pending_followups(max_step: int) -> list:
    return query(
        "SELECT * FROM leads WHERE status IN ('INITIATED', 'IN_PROGRESS') "
        "AND followup_step < ? AND next_followup_at IS NOT NULL ORDER BY next_followup_at", [int(max_step)],
    )


def briefing_facts() -> dict[str, Any]:
    from .services import common
    now = utcnow()
    day_ago, three_days = to_iso(now - timedelta(days=1)), to_iso(now - timedelta(days=3))
    end_of_day = to_iso(common.local_now().replace(hour=23, minute=59, second=59))
    q = query

    def _brief(r: Any) -> dict[str, Any]:
        return {"id": r["id"], "name": r["name"], "type": r["lead_type"], "score": r["score"],
                "phone": r["phone"], "property": r["property_address"], "budget": r["budget"],
                "timeline": r["timeline"], "notes": r["notes"],
                "last_contact": common.fmt_local(r["last_contacted_at"])}

    return {
        "hot_qualified_recently": [_brief(r) for r in q(
            "SELECT * FROM leads WHERE status = 'QUALIFIED' AND score >= ? AND qualified_at >= ? "
            "ORDER BY score DESC LIMIT 8", [settings.hot_lead_score, three_days])],
        "other_qualified_recently": [_brief(r) for r in q(
            "SELECT * FROM leads WHERE status = 'QUALIFIED' AND (score < ? OR score IS NULL) "
            "AND qualified_at >= ? ORDER BY qualified_at DESC LIMIT 8", [settings.hot_lead_score, three_days])],
        "waiting_on_agent_handover": [_brief(r) for r in q(
            "SELECT * FROM leads WHERE status = 'NEEDS_AGENT' ORDER BY last_contacted_at LIMIT 8")],
        "new_leads_last_24h": [_brief(r) for r in q(
            "SELECT * FROM leads WHERE created_at >= ? AND status != 'BANNED' ORDER BY created_at DESC LIMIT 10",
            [day_ago])],
        "followups_due_today": (query_one(
            "SELECT COUNT(*) n FROM leads WHERE status IN ('INITIATED', 'IN_PROGRESS') "
            "AND next_followup_at IS NOT NULL AND next_followup_at <= ?", [end_of_day]) or {"n": 0})["n"],
        "reengagement_on": reengagement_enabled(),
        "draft_listings_to_review": [dict(r) for r in q("SELECT id, address FROM listings WHERE status = 'DRAFT'")],
        "pending_approvals": (query_one("SELECT COUNT(*) n FROM pending_actions WHERE status = 'PENDING'")
                              or {"n": 0})["n"],
        "pipeline": dict(query_one(
            "SELECT COUNT(*) total, SUM(status = 'IN_PROGRESS') chatting, "
            "SUM(status = 'QUALIFIED') qualified, SUM(status = 'NEEDS_AGENT') needs_agent FROM leads") or {}),
    }


def listing_addresses() -> set[str]:
    return {r["address"].lower() for r in query("SELECT address FROM listings") if r["address"]}


def selling_count() -> int:
    return (query_one("SELECT COUNT(*) n FROM listings WHERE status = 'SELLING'") or {"n": 0})["n"]


def table_rows(table: str, columns: str = "*") -> list:
    return query(f"SELECT {columns} FROM {table}")


# --- cloud delegation ---------------------------------------------------------
# When cloud is activated, the public API above is replaced by the PostgREST-backed
# implementation in cloud_db. Local SQLite behaviour is unchanged otherwise.
if settings.use_cloud:
    from .cloud_db import *  # noqa: F401,F403
