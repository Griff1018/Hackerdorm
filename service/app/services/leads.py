"""Lead intake (email + Telegram), Alex's qualification chat, scoring and alerts.

Ports the Make.com "Gmail Hook" and the lead branch of "TLG Hybrid Bot Model".
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

from .. import db, llm, prompts, telegram_api as tg
from ..config import settings
from ..mailer import InboundEmail, strip_quoted
from . import common
from .common import STATUS_LABEL

log = logging.getLogger(__name__)

# Per-lead debounce state: a version counter bumped on every inbound message,
# plus a lock so only one reply is generated at a time per lead.
_versions: dict[int, int] = {}
_locks: dict[int, asyncio.Lock] = {}
_tasks: set[asyncio.Task[Any]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# --- Email intake ------------------------------------------------------------------

async def intake_email(em: InboundEmail) -> str:
    """Handle one inbound enquiry email. Returns a short result for processed_emails."""
    known = db.find_lead_by_contact(em.sender, None) if em.sender else None
    if known is not None and em.is_reply:
        return await _handle_email_reply(known, em)

    data = await llm.complete_json(
        prompts.render(prompts.EMAIL_EXTRACTION, sender=f"{em.sender_name} <{em.sender}>",
                       subject=em.subject, body=em.text[:15000]),
        max_tokens=600,
    )
    if data.get("is_property_enquiry") is False:
        return "skipped: not a property enquiry"

    name = common.clean_value(data.get("lead_name")) or em.sender_name or ""
    email = common.clean_value(data.get("lead_email"))
    if not email and em.sender and not _looks_automated(em.sender):
        email = em.sender
    phone = common.normalize_phone(data.get("lead_phone"))
    lead_type = common.normalize_lead_type(data.get("buyer_or_seller"))
    address = common.clean_value(data.get("property_address")) or ""
    message = common.clean_value(data.get("message")) or ""

    listing = db.match_listing(address)
    lead = db.find_lead_by_contact(email, phone)
    if lead is not None and lead["status"] == "BANNED":
        await tg.notify_admins(f"🚫 Ignored email enquiry from banned lead #{lead['id']} {lead['name']}.")
        return f"skipped: banned lead {lead['id']}"

    returning = lead is not None
    fields = {
        "lead_type": lead_type if lead_type != "UNKNOWN" or not returning else lead["lead_type"],
        "property_address": address or (lead["property_address"] if returning else ""),
        "listing_id": listing["id"] if listing else (lead["listing_id"] if returning else None),
        "status": "INITIATED",
    }
    if returning:
        assert lead is not None
        db.update("leads", lead["id"], {
            **fields,
            "is_returning": 1,
            "name": lead["name"] or name,
            "email": lead["email"] or email,
            "phone": lead["phone"] or phone,
        })
        lead_id = lead["id"]
    else:
        lead_id = db.create_lead({**fields, "name": name, "email": email, "phone": phone, "source": "EMAIL"})["id"]

    db.insert("enquiries", {
        "lead_id": lead_id, "property_address": address, "lead_type": fields["lead_type"],
        "message": message, "email_subject": em.subject, "email_from": em.sender,
        "received_at": db.now_iso(),
    })
    db.add_message(lead_id, "lead", "email", message or em.subject, kind="enquiry")

    opener = await llm.complete(
        prompts.render(prompts.OPENER_SYSTEM, new_or_returning="returning" if returning else "new"),
        prompts.render(prompts.OPENER_USER, name=name, lead_type=fields["lead_type"].title(),
                       property_address=fields["property_address"], message=message),
        temperature=0.8, max_tokens=200,
    )
    opener = common.split_tags(opener)[0].strip('"')
    lead = db.get_lead(lead_id)
    assert lead is not None
    delivered = await _deliver_opener(lead, opener, em.subject)
    db.update("leads", lead_id, common.conversation_turn_values())

    await tg.notify_admins(
        f"📩 {'Returning' if returning else 'New'} email lead #{lead_id}\n"
        f"👤 {name or 'Unknown'} — {fields['lead_type'].title()}\n"
        f"📧 {email or '-'}  📞 {phone or '-'}\n"
        f"🏠 {fields['property_address'] or '-'}"
        f"{' (listing #%d)' % listing['id'] if listing else ''}\n\n"
        f"Opener ({delivered}):\n{opener}"
    )
    return f"lead {lead_id} ({'returning' if returning else 'new'})"


async def _handle_email_reply(lead: sqlite3.Row, em: InboundEmail) -> str:
    """A known lead answered by email instead of Telegram: continue the same conversation."""
    text = strip_quoted(em.text) or em.text.strip()
    if lead["status"] == "BANNED":
        return f"skipped: banned lead {lead['id']}"
    db.add_message(lead["id"], "lead", "email", text)
    if lead["status"] == "NEEDS_AGENT":
        await tg.notify_admins(
            f"📧 {lead['name'] or 'Lead'} (#{lead['id']}) replied by email:\n{text}\n\n"
            f"Reply: /reply {lead['id']} <message>\nHand back to Alex: /resume {lead['id']}"
        )
        return f"reply from lead {lead['id']} forwarded to agent"
    lock = _locks.setdefault(lead["id"], asyncio.Lock())
    async with lock:
        await generate_reply(lead["id"], channel="email", subject=em.subject)
    return f"reply from lead {lead['id']} answered by email"


def _looks_automated(address: str) -> bool:
    local = address.split("@")[0]
    return any(k in local for k in ("noreply", "no-reply", "donotreply", "notification", "mailer"))


async def _deliver_opener(lead: sqlite3.Row, opener: str, subject: str) -> str:
    channels = []
    if lead["telegram_chat_id"]:
        try:
            await tg.send_message(lead["telegram_chat_id"], opener)
            db.add_message(lead["id"], "ai", "telegram", opener, kind="opener")
            channels.append("Telegram")
        except Exception:
            log.exception("Telegram opener failed for lead %s", lead["id"])
    if lead["email"]:
        link = common.telegram_link(lead)
        body = opener
        if link:
            body += (f"\n\nFor the fastest reply, continue the chat with us on Telegram:\n{link}"
                     "\n\nOr simply reply to this email.")
        body += f"\n\nKind regards,\n{settings.mail_from_name}\n{common.agent_name()}'s team"
        if await common.send_email(lead["email"], f"Re: {subject}" if subject else "Your property enquiry", body):
            if not channels:
                db.add_message(lead["id"], "ai", "email", opener, kind="opener")
            channels.append("email")
    return " + ".join(channels) if channels else "NOT delivered — no reachable contact"


# --- Telegram messages from leads -----------------------------------------------------

async def handle_telegram_message(message: dict[str, Any]) -> None:
    chat_id = str(message["chat"]["id"])
    user = message.get("from") or {}
    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        await tg.send_message(chat_id, "Sorry, I can only read text messages here.")
        return

    if text.startswith("/start"):
        await _handle_start(chat_id, user, text.partition(" ")[2].strip())
        return

    lead = db.lead_by_chat(chat_id)
    if lead is None:
        lead = _create_telegram_lead(chat_id, user)
    if lead["status"] == "BANNED":
        # Still acknowledge, so the user is never left staring at a silent bot.
        await tg.send_message(chat_id, "This conversation has been closed. Have a good day.")
        return

    db.add_message(lead["id"], "lead", "telegram", text)
    if lead["status"] == "NEEDS_AGENT":
        db.update("leads", lead["id"], {"last_contacted_at": db.now_iso()})
        # The lead must at least receive an acknowledgement while the human is away.
        await tg.send_message(
            chat_id,
            f"Thanks — I've passed this to {common.agent_name()}, who will reply to you here shortly.",
        )
        await tg.notify_admins(
            f"💬 {lead['name'] or 'Lead'} (#{lead['id']}) is waiting for you:\n{text}\n\n"
            f"Reply: /reply {lead['id']} <message>\nHand back to Alex: /resume {lead['id']}"
        )
        return

    version = _versions.get(lead["id"], 0) + 1
    _versions[lead["id"]] = version
    _spawn(_debounced_reply(lead["id"], version))


async def _handle_start(chat_id: str, user: dict[str, Any], code: str) -> None:
    linked = db.lead_by_link_code(code) if code else None
    if linked is not None and linked["telegram_chat_id"] not in (None, chat_id):
        linked = None  # code already used by someone else
    if linked is not None:
        previous = db.lead_by_chat(chat_id)
        if previous is not None and previous["id"] != linked["id"]:
            db.update("leads", previous["id"], {"telegram_chat_id": None})
        db.update("leads", linked["id"], {
            "telegram_chat_id": chat_id,
            "telegram_username": user.get("username"),
            "name": linked["name"] or _telegram_name(user),
        })
        lead = db.get_lead(linked["id"])
        assert lead is not None
        msgs = db.messages_for(lead["id"])
        last_ai = next((m for m in reversed(msgs) if m["role"] == "ai"), None)
        greeting = last_ai["content"] if last_ai else _default_greeting(lead)
        await tg.send_message(chat_id, greeting)
        db.add_message(lead["id"], "ai", "telegram", greeting, kind="opener")
        await tg.notify_admins(f"🔗 Lead #{lead['id']} {lead['name']} linked their Telegram.")
        return

    lead = db.lead_by_chat(chat_id) or _create_telegram_lead(chat_id, user)
    if lead["status"] == "BANNED":
        # Never leave the user with silence, even on a closed conversation.
        await tg.send_message(chat_id, "This conversation has been closed. Have a good day.")
        return

    # `/start` must ALWAYS produce a reply. A lead who qualified earlier and comes
    # back should not be greeted with the generic opener as if we had never spoken,
    # and must not be silently ignored.
    if lead["status"] == "QUALIFIED":
        first = (lead["name"] or "").split(" ")[0]
        hello = f"Hi {first}," if first else "Hi,"
        greeting = (f"{hello} great to hear from you again. {common.agent_name()} has your details "
                    "and will be in touch about next steps. Anything you want to add, just type it here.")
    elif lead["status"] == "NEEDS_AGENT":
        greeting = (f"Hi {lead['name'] or 'there'}, {common.agent_name()} is handling your enquiry "
                    "personally and will reply here shortly. Feel free to add anything below.")
        await tg.send_message(chat_id, greeting)
        db.update("leads", lead["id"], {"last_contacted_at": db.now_iso()})
        await tg.notify_admins(
            f"💬 {lead['name'] or 'Lead'} (#{lead['id']}) sent /start while waiting for you.\n\n"
            f"Reply: /reply {lead['id']} <message>\nHand back to Alex: /resume {lead['id']}"
        )
        return
    else:
        greeting = _default_greeting(lead)

    await tg.send_message(chat_id, greeting)
    db.add_message(lead["id"], "ai", "telegram", greeting, kind="opener")
    if lead["status"] == "INITIATED":
        db.update("leads", lead["id"], common.conversation_turn_values())
    else:
        db.update("leads", lead["id"], {"last_contacted_at": db.now_iso()})


def _telegram_name(user: dict[str, Any]) -> str:
    return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)


def _create_telegram_lead(chat_id: str, user: dict[str, Any]) -> sqlite3.Row:
    lead = db.create_lead({
        "name": _telegram_name(user),
        "telegram_chat_id": chat_id,
        "telegram_username": user.get("username"),
        "source": "TELEGRAM",
    })
    _spawn(tg.notify_admins(f"🆕 New Telegram lead #{lead['id']} {lead['name'] or ''} started a chat."))
    return lead


def _default_greeting(lead: sqlite3.Row) -> str:
    first = (lead["name"] or "").split(" ")[0]
    hello = f"Hi {first}, thanks" if first else "Hi, thanks"
    if lead["property_address"]:
        return f"{hello} for your enquiry about {lead['property_address']}. Are you looking to move in the next 1-3 months or just keeping an eye on the market?"
    return f"{hello} for reaching out to {common.agent_name()}'s team. Are you looking to buy or sell a property?"


async def _debounced_reply(lead_id: int, version: int) -> None:
    await asyncio.sleep(settings.reply_debounce_seconds)
    if _versions.get(lead_id) != version:
        return  # a newer message arrived; its task will reply to everything
    lock = _locks.setdefault(lead_id, asyncio.Lock())
    async with lock:
        try:
            await generate_reply(lead_id)
        except Exception as exc:
            log.exception("Reply generation failed for lead %s", lead_id)
            await tg.notify_admins(f"⚠️ Alex could not reply to lead #{lead_id}: {exc}")


# --- Alex --------------------------------------------------------------------------

def _property_block(listing: sqlite3.Row | None) -> str:
    if listing is None:
        return ("No matching listing on file. Do not invent property facts; "
                "use the Soft Deferral rule for property questions.")
    labels = [
        ("Address", "address"), ("Type", "property_type"), ("Listing Asking Price", "asking_price"),
        ("Method of Sale", "method_of_sale"), ("Auction Date & Time", "auction_date"),
        ("Layout & Specs", "layout_specs"), ("Aspect / Orientation", "aspect"), ("Parking", "parking"),
        ("Furnishing & Inclusions", "inclusions"), ("Outdoor & Amenities", "outdoor_features"),
        ("Tenancy & Rental Income", "tenancy_income"), ("School Catchments & Zoning", "zoning"),
        ("Title & Easements", "easements"), ("Strata Status", "strata_status"),
        ("Strata Levies", "strata_levies"), ("Council Rates", "council_rates"),
        ("Water Rates", "water_rates"), ("Pet Policy", "pet_policy"), ("Rental Policy", "rental_policy"),
        ("Upgrades", "upgrades"), ("Vendor Terms", "vendor_terms"), ("Showing Access", "occupancy_access"),
        ("Preferred Inspection Windows", "inspection_windows"),
    ]
    return "\n".join(f"{label}: {listing[key] or '-'}" for label, key in labels)


def build_alex_prompt(lead: sqlite3.Row) -> str:
    agent = db.get_agent_profile()
    listing = db.get_listing(lead["listing_id"]) if lead["listing_id"] else None
    name = agent["agent_name"] or "the agent"
    if agent["include_phone"] and agent["phone_number"]:
        phone_rule = (f"Include {name}'s number {agent['phone_number']} next to {name}'s name ONLY if it "
                      "does not already exist in CHAT HISTORY.")
        phone_inclusion = f"YES {agent['phone_number']}"
    else:
        phone_rule = f"Never share a phone number for {name}."
        phone_inclusion = "NO"
    return prompts.render(
        prompts.ALEX_SYSTEM,
        agent=name,
        now=common.local_now().strftime("%A %d %b %Y %H:%M"),
        lead_name=lead["name"] or "Unknown",
        lead_type=lead["lead_type"],
        lead_status=lead["status"],
        agency=agent["agency"], service_areas=agent["service_areas"],
        working_hours=agent["working_hours"], phone_inclusion=phone_inclusion,
        commission_policy=agent["commission_policy"], marketing_services=agent["marketing_services"],
        mortgage_partner=agent["mortgage_partner"], conveyancer_partner=agent["conveyancer_partner"],
        showing_style=agent["showing_style"],
        property_data=_property_block(listing),
        asking_price=listing["asking_price"] if listing else "unknown",
        inspection_windows=listing["inspection_windows"] if listing else "by appointment",
        occupancy_access=listing["occupancy_access"] if listing else "by appointment",
        phone_rule=phone_rule,
        chat_history=db.transcript(lead["id"]),
    )


async def generate_reply(lead_id: int, channel: str = "telegram", subject: str = "") -> None:
    lead = db.get_lead(lead_id)
    if lead is None or lead["status"] in ("BANNED", "NEEDS_AGENT"):
        return
    if channel == "telegram" and not lead["telegram_chat_id"]:
        return
    if channel == "email" and not lead["email"]:
        return
    msgs = db.messages_for(lead_id)
    last = msgs[-1] if msgs else None
    if last is None or last["role"] != "lead":
        return  # nothing new to answer

    if channel == "telegram":
        await tg.send_typing(lead["telegram_chat_id"])
    raw = await llm.complete(build_alex_prompt(lead), model=settings.llm_model_chat,
                             temperature=0.8, max_tokens=300)
    text, tag = common.split_tags(raw)
    msgs = db.messages_for(lead_id)
    last_lead = next((m for m in reversed(msgs) if m["role"] == "lead"), None)
    last_lead_text = last_lead["content"] if last_lead else ""

    if text:
        if channel == "telegram":
            await tg.send_message(lead["telegram_chat_id"], text)
        else:
            subject = subject if subject.lower().startswith("re:") else f"Re: {subject or 'Your property enquiry'}"
            body = f"{text}\n\nKind regards,\n{settings.mail_from_name}\n{common.agent_name()}'s team"
            link = common.telegram_link(lead)
            if link:
                body += f"\n\nPrefer chat? Continue on Telegram: {link}"
            if not await common.send_email(lead["email"], subject, body):
                raise RuntimeError("email reply failed to send")
        db.add_message(lead_id, "ai", channel, text)

    if tag == "QUALIFIED":
        await _qualify(lead_id)
    elif tag == "HANDOVER":
        db.update("leads", lead_id, {"status": "NEEDS_AGENT", "last_contacted_at": db.now_iso(),
                                     "next_followup_at": None})
        await tg.notify_admins(
            f"⚠️ HANDOVER REQUIRED: {lead['name'] or 'Lead'} (#{lead_id}) — {common.lead_contact(lead)}\n"
            f"They asked or said something that needs you. Alex has paused for this lead.\n\n"
            f"Message:\n{last_lead_text}\n\n"
            f"Reply: /reply {lead_id} <message>\nHand back to Alex: /resume {lead_id}"
        )
    elif tag == "IGNORE":
        db.update("leads", lead_id, {"status": "BANNED", "last_contacted_at": db.now_iso(),
                                     "next_followup_at": None})
        await tg.notify_admins(
            f"🚨 SPAM/TROLL ALERT 🚨\nAlex triggered the [IGNORE] protocol and banned lead #{lead_id} "
            f"({lead['name'] or 'unknown'}, {common.lead_contact(lead)}).\n"
            f'Last message: "{last_lead_text}"\n\nUndo with /unban {lead_id}'
        )
    elif tag in ("STANDBY", "UPDATE"):
        # A qualified lead still talking to us must never go silent: refresh the
        # follow-up clock so the re-engagement run keeps checking on them, and make
        # sure the agent sees messages that carry new information.
        values: dict[str, Any] = {"last_contacted_at": db.now_iso()}
        if lead["status"] == "QUALIFIED":
            values.update(common.conversation_turn_values())
        db.update("leads", lead_id, values)
        if tag == "UPDATE":
            await tg.notify_admins(f"📝 Additional message from {lead['name'] or 'lead'} (#{lead_id}):\n{last_lead_text}")
    else:
        values = common.conversation_turn_values()
        if lead["status"] == "INITIATED":
            values["status"] = "IN_PROGRESS"
        if lead["status"] == "QUALIFIED":
            values["next_followup_at"] = None
        db.update("leads", lead_id, values)


async def _qualify(lead_id: int) -> None:
    lead = db.get_lead(lead_id)
    assert lead is not None
    result = await llm.complete_json(
        prompts.render(prompts.SCORING, lead_type=lead["lead_type"],
                       property_address=lead["property_address"] or "None",
                       chat_history=db.transcript(lead_id)),
        max_tokens=600,
    )
    try:
        score = max(0, min(10, int(float(result.get("lead_score", 0)))))
    except (TypeError, ValueError):
        score = 0
    address = common.clean_value(result.get("extracted_address"))
    lead_type = common.normalize_lead_type(result.get("final_lead_type"))
    values: dict[str, Any] = {
        "status": "QUALIFIED",
        "lead_type": lead_type if lead_type != "UNKNOWN" else lead["lead_type"],
        "timeline": common.clean_value(result.get("timeline")),
        "budget": common.clean_value(result.get("budget")),
        "pre_approval": common.clean_value(result.get("pre_approval")),
        "score": score,
        "score_reason": common.clean_value(result.get("score_reason")),
        "is_qualified": 1 if str(result.get("is_qualified", "")).upper().startswith("Y") else 0,
        "notes": common.clean_value(result.get("notes")),
        "qualified_at": db.now_iso(),
        "last_contacted_at": db.now_iso(),
        "next_followup_at": None,
    }
    if address:
        values["property_address"] = address
        if not lead["listing_id"]:
            listing = db.match_listing(address)
            if listing:
                values["listing_id"] = listing["id"]
    db.update("leads", lead_id, values)
    lead = db.get_lead(lead_id)
    assert lead is not None
    await send_qualified_alerts(lead)


async def send_qualified_alerts(lead: sqlite3.Row) -> None:
    hot = (lead["score"] or 0) >= settings.hot_lead_score
    qualified = "YES" if lead["is_qualified"] else "NO"
    header = "🔔 NEW HOT LEAD QUALIFIED - CALL NOW! 📢🔥" if hot else "🔔 NEW LEAD QUALIFIED"
    await tg.notify_admins(
        f"{header}\n\n"
        f"👤 {lead['name'] or 'Unknown'} — {lead['lead_type'].title()} (#{lead['id']})\n"
        f"📧 {lead['email'] or '-'}\n📞 {lead['phone'] or '-'}\n"
        f"🏠 {lead['property_address'] or '-'}\n"
        f"💰 Budget / Price: {lead['budget'] or '-'}\n⏰ Timeline: {lead['timeline'] or '-'}\n"
        f"💳 Pre-approval/Motivation: {lead['pre_approval'] or '-'}\n📝 Notes: {lead['notes'] or '-'}\n\n"
        f"🤖 AI Score: {lead['score']}/10\n💡 Reason: {lead['score_reason'] or '-'}\n✅ Qualified: {qualified}\n\n"
        f"⚡ Automated Telegram qualification completed."
    )
    transcript = db.transcript(lead["id"])
    kind = "NEW" if not lead["is_returning"] else "RETURNING"
    line = "━━━━━━━━━━━━━━━━━━━━━━"
    details = (
        f"{line}\nLEAD DETAILS\n{line}\nName:     {lead['name']}\nEmail:    {lead['email'] or '-'}\n"
        f"Phone:    {lead['phone'] or '-'}\nType:     {lead['lead_type'].title()}\n\n"
        f"{line}\nPROPERTY DETAILS\n{line}\nArea/Address: {lead['property_address'] or '-'}\n"
        f"Budget/Price: {lead['budget'] or '-'}\nTimeline: {lead['timeline'] or '-'}\n"
        f"Pre-approval/Motivation: {lead['pre_approval'] or '-'}\nNotes: {lead['notes'] or '-'}\n\n"
        f"{line}\nAI ASSESSMENT\n{line}\nLead Score: {lead['score']}/10\n"
        f"Reasoning: {lead['score_reason'] or '-'}\nQualified: {qualified}\n\n"
        f"{line}\nFULL CHAT TRANSCRIPT\n{line}\n{transcript}\n"
    )
    if settings.alert_emails:
        subject = (f"Hot Lead Alert — {lead['name']} | Score: {lead['score']}/10 - Call Them Now!" if hot
                   else f"🔔 New Lead Alert — {lead['name']} | Score: {lead['score']}/10")
        intro = ("A HOT {kind} lead has just qualified. Call them immediately if you haven't already!" if hot
                 else "A {kind} lead has just qualified.").format(kind=kind.lower())
        await common.send_email(
            settings.alert_emails, subject,
            f"Hi {common.agent_name()},\n\n{intro} Here are the details:\n\n{details}\n"
            f"Please follow up with {lead['name']} at your earliest convenience.\n\n"
            "This is an automated notification from your Lead Management System.",
        )
    if settings.dossier_emails:
        await common.send_email(
            settings.dossier_emails,
            f"Inquiry Dossier - {lead['property_address'] or 'Enquiry'} - {lead['name']}",
            f"AI QUALIFICATION DOSSIER\nDate: {common.fmt_local(db.now_iso())}\n\n{details}\n"
            "Logged via Speed-to-Lead Automation Engine",
        )


# --- Agent actions (used by admin commands) --------------------------------------

async def agent_reply(lead_id: int, text: str) -> str:
    lead = db.get_lead(lead_id)
    if lead is None:
        return f"No lead #{lead_id}."
    if lead["telegram_chat_id"]:
        await tg.send_message(lead["telegram_chat_id"], text)
        db.add_message(lead_id, "agent", "telegram", text)
        channel = "Telegram"
    elif lead["email"]:
        if not await common.send_email(lead["email"], "Your property enquiry", text):
            return "Email failed to send — check the mail settings."
        db.add_message(lead_id, "agent", "email", text)
        channel = "email"
    else:
        return f"Lead #{lead_id} has no Telegram or email to reach."
    db.update("leads", lead_id, {"last_contacted_at": db.now_iso()})
    return f"Sent to {lead['name'] or 'lead'} via {channel}."


def set_status(lead_id: int, status: str) -> str:
    lead = db.get_lead(lead_id)
    if lead is None:
        return f"No lead #{lead_id}."
    values: dict[str, Any] = {"status": status}
    if status in ("IN_PROGRESS", "INITIATED"):
        values.update(common.conversation_turn_values())
    db.update("leads", lead_id, values)
    return f"Lead #{lead_id} {lead['name'] or ''} is now {STATUS_LABEL[status]}."
