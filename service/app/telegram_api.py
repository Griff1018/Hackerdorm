"""Minimal Telegram Bot API client (plain HTTP, no framework)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4096
ALLOWED_UPDATES = ["message", "callback_query"]
_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(70.0, connect=10.0))
    return _http


def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


async def call(method: str, **params: Any) -> Any:
    payload = {k: v for k, v in params.items() if v is not None}
    for attempt in range(3):
        try:
            resp = await _client().post(_url(method), json=payload)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if attempt == 2:
                raise
            await asyncio.sleep(1 + attempt)  # transient network blips are common
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
    return data["result"]


def _chunks(text: str) -> list[str]:
    text = text.strip() or "(empty)"
    parts = []
    while len(text) > MAX_MESSAGE_LEN:
        cut = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        cut = cut if cut > 0 else MAX_MESSAGE_LEN
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


async def send_message(chat_id: int | str, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
    """Send text (split if long). `buttons` = rows of (label, callback_data), attached to the last part."""
    parts = _chunks(text)
    for i, part in enumerate(parts):
        markup = None
        if buttons and i == len(parts) - 1:
            markup = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
        await call("sendMessage", chat_id=chat_id, text=part, disable_web_page_preview=True, reply_markup=markup)


async def answer_callback(callback_id: str, text: str = "") -> None:
    try:
        await call("answerCallbackQuery", callback_query_id=callback_id, text=text[:200] or None)
    except Exception:
        log.exception("answerCallbackQuery failed")


async def edit_message(chat_id: int | str, message_id: int, text: str) -> None:
    """Replace a message's text and drop its buttons."""
    try:
        await call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:MAX_MESSAGE_LEN],
                   disable_web_page_preview=True)
    except Exception:
        log.exception("editMessageText failed")


async def notify_admins(text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
    for chat_id in settings.admin_chat_ids:
        try:
            await send_message(chat_id, text, buttons)
        except Exception:
            log.exception("Failed to notify admin %s", chat_id)


async def send_document(chat_id: int | str, filename: str, content: bytes, caption: str = "") -> None:
    files = {"document": (filename, content)}
    resp = await _client().post(
        _url("sendDocument"), data={"chat_id": str(chat_id), "caption": caption}, files=files
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendDocument failed: {data.get('description')}")


async def send_typing(chat_id: int | str) -> None:
    try:
        await call("sendChatAction", chat_id=chat_id, action="typing")
    except Exception:
        pass


async def set_webhook(url: str, secret: str) -> None:
    await call("setWebhook", url=url, secret_token=secret or None,
               allowed_updates=ALLOWED_UPDATES, drop_pending_updates=False)


async def delete_webhook() -> None:
    await call("deleteWebhook", drop_pending_updates=False)


async def get_updates(offset: int | None, timeout: int = 50) -> list[dict[str, Any]]:
    return await call("getUpdates", offset=offset, timeout=timeout, allowed_updates=ALLOWED_UPDATES)


async def set_commands(commands: list[tuple[str, str]], chat_id: str | None = None) -> None:
    scope = {"type": "chat", "chat_id": chat_id} if chat_id else None
    await call("setMyCommands", commands=[{"command": c, "description": d} for c, d in commands], scope=scope)


async def close() -> None:
    global _http
    if _http is not None:
        await _http.aclose()
        _http = None
