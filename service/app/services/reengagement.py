"""Daily follow-ups for leads who went quiet (port of "Lead Reengagement").

Schedule: FOLLOWUP_SCHEDULE_DAYS (default 3,5,7,30,90) days after the last real
conversation turn. The last step is an email; earlier steps go to Telegram when the
lead has linked it, otherwise by email.
"""
from __future__ import annotations

import logging
import sqlite3

from .. import db, llm, prompts, telegram_api as tg
from ..config import settings
from . import common

log = logging.getLogger(__name__)


def due_leads() -> list[sqlite3.Row]:
    return db.due_followups(len(settings.followup_schedule_days), db.now_iso())


def pending_leads() -> list[sqlite3.Row]:
    return db.pending_followups(len(settings.followup_schedule_days))


def _split_subject(text: str) -> tuple[str, str]:
    first, _, rest = text.strip().partition("\n")
    if first.lower().startswith("subject:"):
        return first.split(":", 1)[1].strip() or "Quick question regarding your property plans", rest.strip()
    return "Quick question regarding your property plans", text.strip()


async def send_followup(lead: sqlite3.Row) -> str | None:
    step = lead["followup_step"]
    is_email_step = step == len(settings.followup_schedule_days) - 1
    raw = await llm.complete(
        prompts.render(prompts.FOLLOWUP, agent=common.agent_name(), lead_name=lead["name"] or "there",
                       lead_type=lead["lead_type"], step=step, chat_history=db.transcript(lead["id"])),
        temperature=0.7, max_tokens=300,
    )
    text = common.split_tags(raw)[0].strip('"')

    channel = None
    if lead["telegram_chat_id"] and not (is_email_step and lead["email"]):
        await tg.send_message(lead["telegram_chat_id"], text)
        channel = "telegram"
        stored = text
    elif lead["email"]:
        subject, body = _split_subject(text) if is_email_step else ("Following up on your property enquiry", text)
        link = common.telegram_link(lead)
        signoff = f"\n\nKind regards,\n{settings.mail_from_name}\n{common.agent_name()}'s team"
        if link:
            signoff += f"\n\nChat with us on Telegram: {link}"
        if await common.send_email(lead["email"], subject, body + signoff):
            channel = "email"
        stored = body

    next_step = step + 1
    db.update("leads", lead["id"], {
        "followup_step": next_step,
        "next_followup_at": common.next_followup_at(lead["followup_anchor_at"], next_step) if channel else None,
        "last_contacted_at": db.now_iso() if channel else lead["last_contacted_at"],
    })
    if channel:
        db.add_message(lead["id"], "ai", channel, stored, kind="followup")
    return channel


async def run(force: bool = False) -> str:
    if not force and not db.reengagement_enabled():
        return "Re-engagement is OFF."
    sent, failed, unreachable = 0, 0, 0
    for lead in due_leads():
        try:
            if await send_followup(lead):
                sent += 1
            else:
                unreachable += 1
        except Exception:
            failed += 1
            log.exception("Follow-up failed for lead %s", lead["id"])
    summary = f"🔁 Re-engagement run: {sent} follow-up(s) sent"
    if unreachable:
        summary += f", {unreachable} lead(s) unreachable (no Telegram/email)"
    if failed:
        summary += f", {failed} failed (see logs)"
    return summary
