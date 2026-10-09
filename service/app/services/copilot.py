"""Agent copilot: the agent chats with the bot in plain language; an LLM agent answers by
calling read-only tools over the database, and proposes (never performs) side effects,
which the agent approves with inline buttons (see services/actions.py).
"""
from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from .. import db, llm, telegram_api as tg
from ..config import settings
from . import actions, common, matching

log = logging.getLogger(__name__)

MAX_STEPS = 6
MAX_TOOL_CHARS = 6000
_memory: dict[str, deque[dict[str, str]]] = {}

SYSTEM = """You are the back-office copilot for {agent}, a real estate agent at {agency}. You talk to {agent} in a private Telegram chat.
Today is {today} ({timezone}).

You can look things up with tools: leads (with their qualification, score and chat history), listings and stats.
You can also PROPOSE actions: messaging a lead, changing a lead's or listing's status, or running the matchmaker. Proposed actions are NOT executed by you — {agent} gets Approve/Cancel buttons. So never say a message was sent or a status changed; say it is ready for approval.

Rules:
- Always use tools to get facts. Never invent leads, listings, numbers or history.
- Refer to leads as "Name (#id)" and listings as "address (#id)".
- Reply in plain text for Telegram: no Markdown tables, no ** bold **, no headings. Short lines and simple "-" bullets are fine. Be concise.
- When drafting a message to a lead, write as Alex from {agent}'s team: warm, professional, under 300 characters, one clear question or next step, consistent with the lead's chat history. Never promise prices, discounts or legal terms.
- If a request is ambiguous (e.g. two leads match a name), ask which one instead of guessing.
"""


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required or []},
    }}


TOOLS = [
    _tool("search_leads", "Search leads. All filters optional; returns compact rows sorted by most recent contact.", {
        "text": {"type": "string", "description": "Matches name, email, phone, address, budget, timeline or notes"},
        "status": {"type": "string", "enum": list(actions.LEAD_STATUSES)},
        "lead_type": {"type": "string", "enum": ["BUYER", "SELLER", "DUAL", "UNKNOWN"]},
        "min_score": {"type": "integer"},
        "qualified_only": {"type": "boolean"},
        "limit": {"type": "integer", "description": "Default 10, max 30"},
    }),
    _tool("get_lead", "Full details of one lead including recent chat messages.", {
        "lead_id": {"type": "integer"},
        "messages": {"type": "integer", "description": "How many recent messages to include (default 20)"},
    }, ["lead_id"]),
    _tool("list_listings", "List listings (default: SELLING and DRAFT).", {
        "status": {"type": "string", "enum": ["DRAFT", "SELLING", "SOLD", "WITHDRAWN", "ALL"]},
    }),
    _tool("get_listing", "All fields of one listing.", {"listing_id": {"type": "integer"}}, ["listing_id"]),
    _tool("get_stats", "Pipeline counts: totals by status, qualified, average score, leads waiting for the agent, "
                       "follow-ups due.", {}),
    _tool("propose_message", "Draft a message to a lead for the agent to approve before it is sent.", {
        "lead_id": {"type": "integer"}, "text": {"type": "string"},
    }, ["lead_id", "text"]),
    _tool("propose_lead_status", "Propose changing a lead's status (e.g. resume Alex = IN_PROGRESS).", {
        "lead_id": {"type": "integer"}, "status": {"type": "string", "enum": list(actions.LEAD_STATUSES)},
    }, ["lead_id", "status"]),
    _tool("propose_listing_status", "Propose changing a listing's status.", {
        "listing_id": {"type": "integer"}, "status": {"type": "string", "enum": list(actions.LISTING_STATUSES)},
    }, ["listing_id", "status"]),
    _tool("run_matchmaker", "Find past buyer leads who fit a SELLING listing and draft intro messages for approval.", {
        "listing_id": {"type": "integer"},
    }, ["listing_id"]),
]


def _lead_row(r: Any) -> dict[str, Any]:
    return {k: r[k] for k in ("id", "name", "lead_type", "status", "score", "budget", "timeline",
                              "pre_approval", "property_address", "listing_id", "notes")} | {
        "last_contact": common.fmt_local(r["last_contacted_at"]),
        "telegram": bool(r["telegram_chat_id"]), "email": r["email"], "phone": r["phone"],
    }


async def _run_tool(name: str, args: dict[str, Any], proposals: list[tuple[int, str]]) -> Any:
    if name == "search_leads":
        rows = db.search_leads(
            text=args.get("text"), status=args.get("status"), lead_type=args.get("lead_type"),
            min_score=args.get("min_score"), qualified_only=args.get("qualified_only"),
            limit=args.get("limit") or 10,
        )
        return [_lead_row(r) for r in rows]
    if name == "get_lead":
        lead = db.get_lead(int(args["lead_id"]))
        if lead is None:
            return {"error": "not found"}
        n = max(1, min(int(args.get("messages") or 20), 60))
        msgs = db.recent_messages(lead["id"], n)
        return _lead_row(lead) | {
            "score_reason": lead["score_reason"], "source": lead["source"],
            "followup_step": lead["followup_step"], "next_followup": common.fmt_local(lead["next_followup_at"]),
            "messages": [{"from": m["role"], "via": m["channel"], "at": common.fmt_local(m["created_at"]),
                          "text": m["content"]} for m in reversed(msgs)],
        }
    if name == "list_listings":
        rows = db.list_listings(args.get("status") or "")
        return [dict(r) for r in rows]
    if name == "get_listing":
        listing = db.get_listing(int(args["listing_id"]))
        return {"error": "not found"} if listing is None else {
            k: listing[k] for k in ["id", "status", "listing_url", *db.LISTING_FIELDS]}
    if name == "get_stats":
        return db.stats()
    if name in ("propose_message", "propose_lead_status", "propose_listing_status"):
        kind = {"propose_message": "send_message_to_lead", "propose_lead_status": "set_lead_status",
                "propose_listing_status": "set_listing_status"}[name]
        payload = {k: v for k, v in args.items()}
        try:
            action_id, summary = actions.propose(kind, payload)
        except ValueError as exc:
            return {"error": str(exc)}
        proposals.append((action_id, summary))
        return {"proposed": True, "action_id": action_id, "note": "Waiting for the agent's approval."}
    if name == "run_matchmaker":
        found = await matching.find_matches(int(args["listing_id"]), notify=False)
        proposals.extend(found["proposals"])
        return {k: v for k, v in found.items() if k != "proposals"} | {"drafts_for_approval": len(found["proposals"])}
    return {"error": f"unknown tool {name}"}


def reset(chat_id: str) -> None:
    _memory.pop(chat_id, None)


async def _reason(chat_id: str, text: str) -> tuple[str, list[tuple[int, str]]]:
    """Run the copilot's tool-calling loop and return (answer, proposals).

    Delivery is the caller's job: Telegram (handle) or the web console (handle_web).
    """
    agent = db.get_agent_profile()
    system = SYSTEM.format(agent=agent["agent_name"] or "the agent", agency=agent["agency"] or "the agency",
                           today=common.local_now().strftime("%A %d %b %Y %H:%M"), timezone=settings.timezone)
    history = _memory.setdefault(chat_id, deque(maxlen=12))
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *history,
                                      {"role": "user", "content": text}]
    proposals: list[tuple[int, str]] = []
    answer = ""
    for _ in range(MAX_STEPS):
        reply = await llm.chat(messages, TOOLS)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            answer = reply["content"]
            break
        for call in calls:
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
                result = await _run_tool(call["function"]["name"], args, proposals)
            except Exception as exc:
                log.exception("Copilot tool %s failed", call["function"]["name"])
                result = {"error": str(exc)}
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_CHARS]})
    else:
        answer = "I couldn't finish that in a few steps — could you narrow the request?"

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer or "(proposed actions below)"})
    return answer, proposals


async def handle(chat_id: str, text: str) -> None:
    await tg.send_typing(chat_id)
    answer, proposals = await _reason(chat_id, text)
    if answer:
        await tg.send_message(chat_id, answer)
    for action_id, summary in proposals:
        await tg.send_message(chat_id, summary, actions.buttons(action_id))


async def handle_web(chat_id: str, text: str) -> dict[str, Any]:
    """Web-console variant: return the answer and any proposed actions as JSON."""
    answer, proposals = await _reason(chat_id, text)
    return {"answer": answer, "proposals": [{"action_id": a, "summary": s} for a, s in proposals]}
