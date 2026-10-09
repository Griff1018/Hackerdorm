"""Background loops: Gmail poller, daily re-engagement scheduler, Telegram updates."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import db, mailer, telegram_api as tg
from .config import settings
from .mailer import InboundEmail
from .services import actions, admin, briefing, common, leads, listings, reengagement

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Any) -> None:
    """Run a coroutine in the background (keeps a reference so the task isn't GC'd)."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def spawn_update(update: dict[str, Any]) -> None:
    spawn(handle_update(update))


# --- Telegram ------------------------------------------------------------------------

async def handle_callback(cb: dict[str, Any]) -> None:
    """Approve/Cancel taps on pending actions. Only admins may decide."""
    chat_id = str(((cb.get("message") or {}).get("chat") or {}).get("id", ""))
    parsed = actions.parse_callback(cb.get("data", ""))
    if not settings.is_admin(chat_id) or parsed is None:
        await tg.answer_callback(cb["id"])
        return
    action_id, approve = parsed
    await tg.answer_callback(cb["id"], "Working…" if approve else "Cancelling…")
    result = await actions.decide(action_id, approve)
    original = (cb.get("message") or {}).get("text", "")
    await tg.edit_message(chat_id, cb["message"]["message_id"], f"{original}\n\n— {result}")


async def handle_update(update: dict[str, Any]) -> None:
    if update.get("callback_query"):
        try:
            await handle_callback(update["callback_query"])
        except Exception:
            log.exception("Failed to handle callback %s", update.get("update_id"))
        return
    message = update.get("message")
    if not message or (message.get("from") or {}).get("is_bot"):
        return
    if message["chat"].get("type") != "private":
        return  # ignore groups/channels
    chat_id = str(message["chat"]["id"])
    try:
        if settings.is_admin(chat_id):
            await admin.handle(chat_id, message.get("text") or "")
        else:
            await leads.handle_telegram_message(message)
    except Exception:
        log.exception("Failed to handle Telegram update %s", update.get("update_id"))


async def telegram_polling_loop() -> None:
    """Used when PUBLIC_BASE_URL is not set (local development)."""
    await tg.delete_webhook()
    offset: int | None = None
    while True:
        try:
            updates = await tg.get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                spawn_update(update)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Telegram polling error")
            await asyncio.sleep(5)


# --- Gmail -------------------------------------------------------------------------

def _already_processed(message_id: str) -> bool:
    return db.processed_email_exists(message_id)


async def process_email(em: InboundEmail) -> str:
    if em.sender == settings.gmail_address.lower():
        return "skipped: own address"
    if em.sender in settings.listing_senders and em.pdfs:
        return await listings.intake_listing_email(em)
    return await leads.intake_email(em)


async def poll_mail_once() -> int:
    emails = await asyncio.to_thread(mailer.fetch_unseen)
    handled: list[str] = []
    for em in emails:
        if _already_processed(em.message_id):
            handled.append(em.uid)
            continue
        try:
            detail = await process_email(em)
            kind = detail.split(" ")[0].rstrip(":")
        except Exception as exc:
            log.exception("Failed to process email %s", em.message_id)
            detail, kind = f"{exc.__class__.__name__}: {exc}", "error"
            await tg.notify_admins(f"⚠️ Could not process email from {em.sender} ({em.subject!r}): {exc}")
        db.insert("processed_emails", {"message_id": em.message_id, "kind": kind,
                                       "detail": detail[:500], "processed_at": db.now_iso()})
        handled.append(em.uid)
    await asyncio.to_thread(mailer.mark_seen, handled)
    return len(handled)


async def mail_loop() -> None:
    while True:
        try:
            await poll_mail_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Mail polling error")
        await asyncio.sleep(settings.imap_poll_seconds)


# --- Daily re-engagement ------------------------------------------------------------------

async def run_reengagement_if_due() -> None:
    now = common.local_now()
    today = now.date().isoformat()
    if now.hour < settings.reengagement_hour or db.get_setting("reengagement_last_run") == today:
        return
    db.set_setting("reengagement_last_run", today)
    if not db.reengagement_enabled():
        return
    summary = await reengagement.run()
    log.info(summary)
    if "0 follow-up(s) sent" not in summary:
        await tg.notify_admins(summary)


async def send_briefing_if_due() -> None:
    now = common.local_now()
    today = now.date().isoformat()
    if now.hour < settings.briefing_hour or db.get_setting("briefing_last_run") == today:
        return
    db.set_setting("briefing_last_run", today)
    if briefing.enabled() and settings.admin_chat_ids:
        await tg.notify_admins(await briefing.build())


async def scheduler_loop() -> None:
    while True:
        try:
            await send_briefing_if_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Briefing error")
        try:
            await run_reengagement_if_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Scheduler error")
        await asyncio.sleep(60)
