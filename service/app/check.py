"""Verify configuration against the real services:  python -m app.check"""
from __future__ import annotations

import asyncio
import imaplib
import smtplib
import ssl

from . import db, llm, telegram_api as tg
from .config import settings


async def _check() -> int:
    failures = 0

    def report(name: str, ok: bool, detail: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")

    try:
        reply = await llm.complete("Reply with the single word: pong", "ping", model=settings.llm_model_chat)
        report("LLM", True, f"{settings.llm_model_chat} @ {settings.llm_base_url} -> {reply[:40]!r}")
    except Exception as exc:
        report("LLM", False, str(exc) or repr(exc))

    if settings.telegram_enabled:
        try:
            me = await tg.call("getMe")
            same = me.get("username", "").lower() == settings.telegram_bot_username.lower()
            report("Telegram", same, f"@{me.get('username')}"
                   + ("" if same else f" (TELEGRAM_BOT_USERNAME is {settings.telegram_bot_username!r})"))
            info = await tg.call("getWebhookInfo")
            report("Telegram webhook", True, info.get("url") or "none (polling mode)")
        except Exception as exc:
            report("Telegram", False, str(exc) or repr(exc))
        report("Admin chat IDs", bool(settings.admin_chat_ids), ", ".join(settings.admin_chat_ids) or "ADMIN_CHAT_IDS empty")
    else:
        report("Telegram", False, "TELEGRAM_BOT_TOKEN not set")

    if settings.smtp_enabled:
        if settings.mail_enabled:
            try:
                with imaplib.IMAP4_SSL(settings.imap_host) as imap:
                    imap.login(settings.gmail_address, settings.gmail_app_password)
                    status, _ = imap.select(settings.imap_folder, readonly=True)
                report("IMAP", status == "OK", f"{settings.gmail_address} / {settings.imap_folder}")
            except Exception as exc:
                report("IMAP", False, str(exc) or repr(exc))
        else:
            report("IMAP", True, "intake disabled (GMAIL_INTAKE_ENABLED=0); outbound only")
        try:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ssl.create_default_context()) as s:
                s.login(settings.gmail_address, settings.gmail_app_password)
            report("SMTP", True, settings.smtp_host)
        except Exception as exc:
            report("SMTP", False, str(exc) or repr(exc))
    else:
        report("Gmail", False, "GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set")

    db.connect()
    profile = db.get_agent_profile()
    report("Agent profile", bool(profile.get("agent_name")), profile.get("agent_name") or "empty — run app.import_excel or /setprofile")
    listings = db.selling_count()
    report("Listings", True, f"{listings} selling")
    report("Public URL", bool(settings.public_base_url), settings.public_base_url or "PUBLIC_BASE_URL empty (local polling mode)")
    await tg.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_check()))
