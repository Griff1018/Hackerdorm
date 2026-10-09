"""Helpers shared by the lead, listing, admin and re-engagement services."""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .. import db, mailer
from ..config import settings

log = logging.getLogger(__name__)

STATUS_LABEL = {
    "INITIATED": "Initiated",
    "IN_PROGRESS": "In Progress",
    "QUALIFIED": "Qualified",
    "NEEDS_AGENT": "Needs Agent",
    "BANNED": "Banned",
}

# Tags Alex appends to replies, in priority order when several appear.
TAGS = ["IGNORE", "HANDOVER", "QUALIFIED", "UPDATE", "STANDBY"]
_TAG_RE = re.compile(r"\[(%s)\]" % "|".join(TAGS), re.IGNORECASE)


def split_tags(reply: str) -> tuple[str, str | None]:
    """Return (text without tags, highest-priority tag or None)."""
    found = {m.group(1).upper() for m in _TAG_RE.finditer(reply)}
    tag = next((t for t in TAGS if t in found), None)
    text = _TAG_RE.sub("", reply)
    text = re.sub(r"^\s*(AI|Alex)\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    return re.sub(r"[ \t]+\n", "\n", text).strip(), tag


def local_now() -> datetime:
    return datetime.now(settings.tz)


def fmt_local(value: str | datetime | None, with_time: bool = True) -> str:
    if not value:
        return "-"
    dt = db.from_iso(value) if isinstance(value, str) else value
    assert dt is not None
    dt = dt.astimezone(settings.tz)
    return dt.strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y")


def next_followup_at(anchor_iso: str | None, step: int) -> str | None:
    schedule = settings.followup_schedule_days
    if anchor_iso is None or step >= len(schedule):
        return None
    anchor = db.from_iso(anchor_iso)
    assert anchor is not None
    return db.to_iso(anchor + timedelta(days=schedule[step]))


def conversation_turn_values() -> dict[str, Any]:
    """Fields to reset whenever the lead and Alex have a real exchange."""
    now = db.now_iso()
    return {
        "last_contacted_at": now,
        "followup_anchor_at": now,
        "followup_step": 0,
        "next_followup_at": next_followup_at(now, 0),
    }


def normalize_phone(value: str | None) -> str | None:
    if not value or str(value).strip().lower() in ("null", "none", ""):
        return None
    raw = str(value).strip()
    digits = re.sub(r"\D", "", raw)
    international = raw.startswith("+") or raw.startswith("00")
    if raw.startswith("00"):
        digits = digits[2:]
    if len(digits) < 6:
        return None
    return ("+" if international else "") + digits


def normalize_lead_type(value: str | None) -> str:
    v = (value or "").strip().upper()
    return v if v in ("BUYER", "SELLER", "DUAL") else "UNKNOWN"


def clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in ("", "null", "none", "n/a") else text


def telegram_link(lead: sqlite3.Row) -> str | None:
    if not settings.telegram_bot_username:
        return None
    return f"https://t.me/{settings.telegram_bot_username}?start={lead['link_code']}"


def public_url(path: str) -> str:
    base = settings.public_base_url or "http://localhost:8000"
    return f"{base}{path}"


def agent_name() -> str:
    return db.get_agent_profile().get("agent_name") or "the agent"


async def send_email(to: list[str] | str, subject: str, body: str) -> bool:
    if not settings.smtp_enabled:
        log.warning("SMTP not configured; skipped email %r", subject)
        return False
    try:
        await asyncio.to_thread(mailer.send_email, to, subject, body)
        return True
    except Exception:
        log.exception("Failed to send email %r", subject)
        return False


def lead_contact(lead: sqlite3.Row) -> str:
    parts = [lead["phone"], lead["email"]]
    if lead["telegram_username"]:
        parts.append("@" + lead["telegram_username"])
    elif lead["telegram_chat_id"]:
        parts.append("Telegram linked")
    return " | ".join(p for p in parts if p) or "no contact"


def lead_card(lead: sqlite3.Row) -> str:
    score = f"{lead['score']}/10" if lead["score"] is not None else "unscored"
    qualified = {1: "YES", 0: "NO"}.get(lead["is_qualified"], "-")
    lines = [
        f"#{lead['id']} {lead['name'] or 'Unknown'} — {score} ({lead['lead_type'].title()})",
        f"{lead_contact(lead)} | Status: {STATUS_LABEL[lead['status']]} > {qualified}",
        lead["property_address"] or "No property yet",
    ]
    if lead["score_reason"]:
        lines.append(f"Reason: {lead['score_reason']}")
    return "\n".join(lines)
