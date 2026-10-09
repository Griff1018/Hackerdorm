from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, llm, telegram_api as tg  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import common  # noqa: E402


class Fake:
    """Records outbound traffic and serves scripted LLM replies."""

    def __init__(self) -> None:
        self.telegram: list[tuple[str, str]] = []
        self.admin: list[str] = []
        self.emails: list[tuple[Any, str, str]] = []
        self.documents: list[str] = []
        self.replies: list[str] = []        # queued llm.complete results
        self.json_replies: list[dict] = []  # queued llm.complete_json results
        self.prompts: list[str] = []
        self.chat_replies: list[dict] = []  # queued llm.chat results (assistant messages)
        self.chat_calls: list[list[dict]] = []
        self.buttons: list[tuple[str, str, list]] = []
        self.edits: list[str] = []


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Fake:
    f = Fake()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "admin_chat_ids", ["999"])
    monkeypatch.setattr(settings, "telegram_bot_username", "TestBot")
    monkeypatch.setattr(settings, "reply_debounce_seconds", 0)
    monkeypatch.setattr(settings, "alert_emails", ["agent@example.com"])
    monkeypatch.setattr(settings, "dossier_emails", [])
    monkeypatch.setattr(settings, "gmail_address", "leads@example.com")
    monkeypatch.setattr(settings, "gmail_app_password", "x")
    monkeypatch.setattr(settings, "listing_senders", ["agent@example.com"])
    db.connect(":memory:")
    db.save_agent_profile({"agent_name": "Marcus", "agency": "Paradise", "working_hours": "9am-6pm"})

    async def send_message(chat_id: Any, text: str, buttons: Any = None) -> None:
        f.telegram.append((str(chat_id), text))
        if buttons:
            f.buttons.append((str(chat_id), text, buttons))

    async def notify_admins(text: str, buttons: Any = None) -> None:
        f.admin.append(text)
        if buttons:
            f.buttons.append(("admin", text, buttons))

    async def edit_message(chat_id: Any, message_id: int, text: str) -> None:
        f.edits.append(text)

    async def chat(messages: list, tools: Any = None, **_: Any) -> dict:
        f.chat_calls.append(list(messages))
        return f.chat_replies.pop(0)

    async def send_document(chat_id: Any, filename: str, content: bytes, caption: str = "") -> None:
        f.documents.append(filename)

    async def noop(*_: Any, **__: Any) -> None:
        return None

    async def send_email(to: Any, subject: str, body: str) -> bool:
        f.emails.append((to, subject, body))
        return True

    async def complete(system: str, user: str | None = None, **_: Any) -> str:
        f.prompts.append(system)
        return f.replies.pop(0)

    async def complete_json(system: str, user: str | None = None, **_: Any) -> dict:
        f.prompts.append(system)
        return f.json_replies.pop(0)

    monkeypatch.setattr(tg, "send_message", send_message)
    monkeypatch.setattr(tg, "notify_admins", notify_admins)
    monkeypatch.setattr(tg, "send_document", send_document)
    monkeypatch.setattr(tg, "send_typing", noop)
    monkeypatch.setattr(tg, "answer_callback", noop)
    monkeypatch.setattr(tg, "edit_message", edit_message)
    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(common, "send_email", send_email)
    monkeypatch.setattr(llm, "complete", complete)
    monkeypatch.setattr(llm, "complete_json", complete_json)
    return f
