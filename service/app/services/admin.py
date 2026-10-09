"""Telegram commands for the agent/admin chat (port of the Hybrid Bot's admin branch)."""
from __future__ import annotations

import logging
from datetime import timedelta

from .. import db, telegram_api as tg
from ..config import settings
from ..export import build_workbook
from . import actions, briefing, common, copilot, leads, listings, matching, reengagement

log = logging.getLogger(__name__)

COMMANDS = [
    ("leads", "Today's leads"),
    ("top", "Top 3 qualified leads this week"),
    ("summary", "All-time stats"),
    ("recent", "Last 5 qualified leads"),
    ("pending", "Leads queued for re-engagement"),
    ("lead", "<id> — lead details + chat"),
    ("reply", "<id> <text> — message a lead"),
    ("resume", "<id> — hand a lead back to Alex"),
    ("unban", "<id> — un-ban a lead"),
    ("briefing", "Morning briefing now"),
    ("approvals", "Actions waiting for your approval"),
    ("match", "<listing id> — find past buyers who fit a listing"),
    ("listing", "How to add a listing + current listings"),
    ("sold", "<id> — mark a listing sold"),
    ("profile", "Show agent profile"),
    ("setprofile", "<field> <value> — edit agent profile"),
    ("reengagement_on", "Start daily follow-ups"),
    ("reengagement_off", "Stop daily follow-ups"),
    ("run_followups", "Send due follow-ups now"),
    ("export", "Download the database as Excel"),
    ("briefing_on", "Daily morning briefing on"),
    ("briefing_off", "Daily morning briefing off"),
    ("reset", "Clear the copilot's conversation memory"),
    ("help", "Show this menu"),
]

DIVIDER = "------------------------------"


def help_text() -> str:
    lines = ["🤖 AVAILABLE COMMANDS", "", "Tap on blue-coloured text to command:"]
    lines += [f"/{c} — {d}" for c, d in COMMANDS]
    lines += ["", "💬 Or just type a request, e.g. \"which buyers fit Help Street?\" or "
              "\"tell David the inspection moved to 11am\" — anything that changes data or messages a lead "
              "comes back with Approve / Cancel buttons."]
    if settings.support_contact:
        lines += ["", settings.support_contact]
    return "\n".join(lines)


def _cards(rows: list) -> str:
    return f"\n{DIVIDER}\n".join(common.lead_card(r) for r in rows)


def _today_start_utc() -> str:
    start = common.local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.to_iso(start)  # type: ignore[return-value]


def _int_arg(arg: str) -> int | None:
    token = arg.strip().split(" ")[0].lstrip("#")
    return int(token) if token.isdigit() else None


async def handle(chat_id: str, text: str) -> None:
    text = text.strip()
    if text and not text.startswith("/"):
        try:
            await copilot.handle(chat_id, text)
        except Exception as exc:
            log.exception("Copilot failed: %s", text)
            await tg.send_message(chat_id, f"⚠️ Copilot error: {exc}")
        return
    command, _, arg = text.partition(" ")
    command = command.split("@")[0].lower().lstrip("/")
    try:
        reply = await _dispatch(chat_id, command, arg.strip())
    except Exception as exc:
        log.exception("Admin command failed: %s", text)
        reply = f"⚠️ Command failed: {exc}"
    if reply:
        await tg.send_message(chat_id, reply)


async def _dispatch(chat_id: str, command: str, arg: str) -> str | None:
    if command in ("start", "help", ""):
        return help_text()

    if command == "leads":
        rows = db.leads_since(_today_start_utc(), 10)
        return f"📋 TODAY'S LEADS\n\n{_cards(rows)}" if rows else "No leads yet today."

    if command == "top":
        since = db.to_iso(db.utcnow() - timedelta(days=7))
        rows = db.top_qualified_since(since, 3)
        return f"🏆 TOP QUALIFIED LEADS THIS WEEK\n\n{_cards(rows)}" if rows else "No leads found in the last 7 days yet."

    if command == "summary":
        s = db.summary_stats()
        if not s:
            return "📊 DATABASE SUMMARY\n\nNo data yet."
        avg = f"{s['avg_score']:.1f}/10" if s.get("avg_score") is not None else "-"
        return (f"📊 DATABASE SUMMARY\n\nTotal leads: {s['total']}\nNew leads: {s.get('new') or 0}\n"
                f"Returning leads: {s.get('returning_count') or 0}\nQualified: {s.get('qualified') or 0}\n"
                f"Needs agent: {s.get('needs_agent') or 0}\nBanned: {s.get('banned') or 0}\nAvg score: {avg}\n\n"
                "Type /top for best leads.\nType /recent for latest activity.")

    if command == "recent":
        rows = db.recent_qualified(5)
        return (f"🕐 RECENT QUALIFIED LEADS (Last 5)\n\n{_cards(rows)}\n\nType /help for all commands."
                if rows else "No recent leads yet.")

    if command == "pending":
        rows = reengagement.pending_leads()
        if not rows:
            return "No stale leads here."
        state = "ON" if db.reengagement_enabled() else "OFF — /reengagement_on to start"
        days = ", ".join(str(d) for d in settings.followup_schedule_days)
        lines = [f"#{r['id']} {r['name'] or 'Unknown'} — step {r['followup_step'] + 1} on "
                 f"{common.fmt_local(r['next_followup_at'], with_time=False)}" for r in rows[:30]]
        return (f"Pending Re-engagement [{state}]\n[Sends every day at {settings.reengagement_hour}:00]\n\n"
                + "\n".join(lines)
                + f"\n\nFollow-ups go out on day {days} of inactivity (the last one by email).")

    if command in ("reengagement_on", "reengagement_off"):
        on = command.endswith("on")
        db.set_setting("reengagement_enabled", "1" if on else "0")
        return (f"✅ Lead re-engagement is now ON. Daily follow-ups will fire at {settings.reengagement_hour}:00."
                if on else "⏸ Lead re-engagement paused. No follow-ups will be sent.")

    if command == "briefing":
        return await briefing.build()

    if command in ("briefing_on", "briefing_off"):
        on = command.endswith("on")
        db.set_setting("briefing_enabled", "1" if on else "0")
        return (f"☀️ Morning briefing ON — daily at {settings.briefing_hour}:00." if on
                else "Morning briefing OFF.")

    if command == "match":
        listing_id = _int_arg(arg)
        if not listing_id:
            return "Usage: /match <listing id>  (see /listing for ids)"
        result = await matching.find_matches(listing_id, notify=True)
        return f"⚠️ {result['error']}" if result.get("error") else None

    if command == "approvals":
        rows = db.pending_actions(10)
        if not rows:
            return "Nothing waiting for approval."
        for r in rows:
            await tg.send_message(chat_id, r["summary"], actions.buttons(r["id"]))
        return None

    if command == "reset":
        copilot.reset(chat_id)
        return "Copilot memory cleared."

    if command == "run_followups":
        return await reengagement.run(force=True)

    if command == "lead":
        lead_id = _int_arg(arg)
        lead = db.get_lead(lead_id) if lead_id else None
        if lead is None:
            return "Usage: /lead <id>"
        extra = [
            f"Timeline: {lead['timeline'] or '-'}", f"Budget: {lead['budget'] or '-'}",
            f"Finance/Motivation: {lead['pre_approval'] or '-'}", f"Notes: {lead['notes'] or '-'}",
            f"Source: {lead['source'].title()}  Last contact: {common.fmt_local(lead['last_contacted_at'])}",
        ]
        chat = db.transcript(lead["id"])
        return f"{common.lead_card(lead)}\n" + "\n".join(extra) + f"\n\n💬 CHAT\n{chat[-3000:] or '(none)'}"

    if command == "reply":
        lead_id = _int_arg(arg)
        message = arg.partition(" ")[2].strip()
        if not lead_id or not message:
            return "Usage: /reply <id> <message>"
        return await leads.agent_reply(lead_id, message)

    if command == "resume":
        lead_id = _int_arg(arg)
        return leads.set_status(lead_id, "IN_PROGRESS") if lead_id else "Usage: /resume <id>"

    if command == "unban":
        lead_id = _int_arg(arg)
        return leads.set_status(lead_id, "IN_PROGRESS") if lead_id else "Usage: /unban <id>"

    if command in ("listing", "listings"):
        rows = db.active_listings()
        current = "\n".join(f"#{r['id']} {r['address']}" + (" (draft — awaiting review)" if r["status"] == "DRAFT" else "")
                            for r in rows) or "(none)"
        senders = ", ".join(settings.listing_senders) or "(set LISTING_SENDERS)"
        return (f"Add a Property Listing (Est. 4 min):\n\nFrom {senders}, email ONE Contract of Sale PDF "
                f"(max 25MB) to:\n{settings.gmail_address or '(set GMAIL_ADDRESS)'}\n"
                "Body content: ONE Domain/REA listing URL\n\n"
                f"Current listings:\n{current}\n\nMark sold: /sold <id>")

    if command == "sold":
        listing_id = _int_arg(arg)
        return listings.set_status(listing_id, "SOLD") if listing_id else "Usage: /sold <id>"

    if command == "profile":
        profile = db.get_agent_profile()
        return "👤 AGENT PROFILE\n\n" + "\n".join(f"{f}: {profile.get(f, '')}" for f in db.AGENT_FIELDS) + \
            "\n\nEdit: /setprofile <field> <value>"

    if command == "setprofile":
        field, _, value = arg.partition(" ")
        if field not in db.AGENT_FIELDS:
            return "Usage: /setprofile <field> <value>\nFields: " + ", ".join(db.AGENT_FIELDS)
        profile = db.get_agent_profile()
        if field == "include_phone":
            profile[field] = 1 if value.strip().lower() in ("1", "yes", "true", "on") else 0
        else:
            profile[field] = value.strip()
        db.save_agent_profile(profile)
        return f"Updated {field}."

    if command in ("export", "gs"):
        content = build_workbook()
        stamp = common.local_now().strftime("%Y%m%d-%H%M")
        await tg.send_document(chat_id, f"lead-database-{stamp}.xlsx", content, caption="📎 Lead database export")
        return None

    return "Unknown command. " + help_text()
