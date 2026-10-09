"""Morning briefing: gather pipeline facts with SQL, let the LLM turn them into a short,
prioritised to-do list for the agent. Falls back to the raw facts if the LLM fails."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from .. import db, llm
from ..config import settings
from . import common

log = logging.getLogger(__name__)

PROMPT = """You are the chief of staff for {agent}, a real estate agent. Write their morning briefing for {today}.

Facts from the CRM (JSON):
{facts}

Write plain text for Telegram (no Markdown tables, no ** bold **), max ~15 lines:
1. One line: the headline (e.g. "2 hot leads to call, 1 lead waiting on you").
2. "Do first:" up to 5 concrete actions, most valuable first. Hot qualified leads not yet called and leads waiting on the agent (handover) come first. Name each lead as "Name (#id)" with the reason in a few words and their phone if known.
3. "Pipeline:" one line of counts.
4. If anything needs a decision (draft listings to review, pending approvals), one line about it.
Every lead listed in the facts is active (banned leads are excluded). Only use the facts given. If there is nothing to do, say so in one friendly line."""


def _brief(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "name": r["name"], "type": r["lead_type"], "score": r["score"],
            "phone": r["phone"], "property": r["property_address"], "budget": r["budget"],
            "timeline": r["timeline"], "notes": r["notes"], "last_contact": common.fmt_local(r["last_contacted_at"])}


def gather_facts() -> dict[str, Any]:
    return db.briefing_facts()


def _fallback(facts: dict[str, Any]) -> str:
    lines = ["☀️ Morning briefing"]
    for r in facts["hot_qualified_recently"]:
        lines.append(f"- Call {r['name']} (#{r['id']}) — hot lead {r['score']}/10, {r['phone'] or 'no phone'}")
    for r in facts["waiting_on_agent_handover"]:
        lines.append(f"- {r['name']} (#{r['id']}) is waiting on you (handover)")
    p = facts["pipeline"]
    lines.append(f"Pipeline: {p.get('total') or 0} leads, {p.get('qualified') or 0} qualified, "
                 f"{p.get('needs_agent') or 0} need you. Follow-ups due today: {facts['followups_due_today']}.")
    return "\n".join(lines)


async def build() -> str:
    facts = gather_facts()
    try:
        text = await llm.complete(PROMPT.format(
            agent=common.agent_name(), today=common.local_now().strftime("%A %d %b"),
            facts=json.dumps(facts, ensure_ascii=False, default=str)), temperature=0.4)
        return "☀️ " + common.split_tags(text)[0]
    except Exception:
        log.exception("Briefing LLM call failed; sending raw facts")
        return _fallback(facts)


def enabled() -> bool:
    return db.get_setting("briefing_enabled", "1") == "1"
