"""Human-in-the-loop actions: agents propose, the agent (human) approves in Telegram.

Every side effect that an LLM agent wants (messaging a lead, changing a status) is stored
as a pending action and only runs when the agent taps Approve. Callback data is
"act:<id>:yes" / "act:<id>:no".
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable

from .. import db
from . import leads, listings

log = logging.getLogger(__name__)

EXPIRY = timedelta(hours=48)
LEAD_STATUSES = ("INITIATED", "IN_PROGRESS", "QUALIFIED", "NEEDS_AGENT", "BANNED")
LISTING_STATUSES = ("SELLING", "SOLD", "WITHDRAWN")


async def _send_message(p: dict[str, Any]) -> str:
    result = await leads.agent_reply(int(p["lead_id"]), str(p["text"]))
    if p.get("listing_id") and result.startswith("Sent"):
        # Matchmaker intro: point the lead at the new listing so Alex has its details when they
        # reply, and reopen qualification for it.
        lead = db.get_lead(int(p["lead_id"]))
        values: dict[str, Any] = {"listing_id": int(p["listing_id"])}
        listing = db.get_listing(int(p["listing_id"]))
        if listing:
            values["property_address"] = listing["address"]
        if lead and lead["status"] in ("QUALIFIED", "INITIATED"):
            values["status"] = "IN_PROGRESS"
        db.update("leads", int(p["lead_id"]), values)
    return result


async def _set_lead_status(p: dict[str, Any]) -> str:
    return leads.set_status(int(p["lead_id"]), str(p["status"]))


async def _set_listing_status(p: dict[str, Any]) -> str:
    return listings.set_status(int(p["listing_id"]), str(p["status"]))


EXECUTORS: dict[str, Callable[[dict[str, Any]], Awaitable[str]]] = {
    "send_message_to_lead": _send_message,
    "set_lead_status": _set_lead_status,
    "set_listing_status": _set_listing_status,
}


def describe(kind: str, payload: dict[str, Any]) -> str:
    """Validate a proposal and return its human-readable summary (raises ValueError)."""
    if kind == "send_message_to_lead":
        lead = db.get_lead(int(payload.get("lead_id", 0)))
        text = str(payload.get("text", "")).strip()
        if lead is None:
            raise ValueError(f"no lead #{payload.get('lead_id')}")
        if not text:
            raise ValueError("message text is empty")
        if not (lead["telegram_chat_id"] or lead["email"]):
            raise ValueError(f"lead #{lead['id']} has no Telegram or email")
        via = "Telegram" if lead["telegram_chat_id"] else "email"
        return f"✉️ Send to {lead['name'] or 'lead'} (#{lead['id']}) via {via}:\n\n{text}"
    if kind == "set_lead_status":
        lead = db.get_lead(int(payload.get("lead_id", 0)))
        status = str(payload.get("status", "")).upper()
        if lead is None:
            raise ValueError(f"no lead #{payload.get('lead_id')}")
        if status not in LEAD_STATUSES:
            raise ValueError(f"status must be one of {', '.join(LEAD_STATUSES)}")
        payload["status"] = status
        return f"🔁 Set lead #{lead['id']} {lead['name'] or ''} status: {lead['status']} → {status}"
    if kind == "set_listing_status":
        listing = db.get_listing(int(payload.get("listing_id", 0)))
        status = str(payload.get("status", "")).upper()
        if listing is None:
            raise ValueError(f"no listing #{payload.get('listing_id')}")
        if status not in LISTING_STATUSES:
            raise ValueError(f"status must be one of {', '.join(LISTING_STATUSES)}")
        payload["status"] = status
        return f"🏠 Set listing #{listing['id']} {listing['address']}: {listing['status']} → {status}"
    raise ValueError(f"unknown action {kind}")


def propose(kind: str, payload: dict[str, Any], source: str = "copilot") -> tuple[int, str]:
    """Store a pending action. Returns (id, summary). Raises ValueError if invalid."""
    summary = describe(kind, payload)
    action_id = db.insert("pending_actions", {
        "kind": kind, "payload": json.dumps(payload), "summary": summary,
        "source": source, "created_at": db.now_iso(),
    })
    return action_id, summary


def buttons(action_id: int) -> list[list[tuple[str, str]]]:
    return [[("✅ Approve", f"act:{action_id}:yes"), ("✖️ Cancel", f"act:{action_id}:no")]]


async def decide(action_id: int, approve: bool) -> str:
    row = db.get_pending_action(action_id)
    if row is None:
        return "That action no longer exists."
    if row["status"] != "PENDING":
        return f"Already {row['status'].lower()}."
    created = db.from_iso(row["created_at"])
    if created and db.utcnow() - created > EXPIRY:
        _finish(action_id, "EXPIRED", None)
        return "Expired — ask again if you still want it."
    if not approve:
        _finish(action_id, "CANCELLED", None)
        return "Cancelled."
    try:
        result = await EXECUTORS[row["kind"]](json.loads(row["payload"]))
        _finish(action_id, "DONE", result)
        return f"Done. {result}"
    except Exception as exc:
        log.exception("Action %s failed", action_id)
        _finish(action_id, "FAILED", str(exc))
        return f"Failed: {exc}"


def _finish(action_id: int, status: str, result: str | None) -> None:
    db.update("pending_actions", action_id, {"status": status, "result": result, "decided_at": db.now_iso()})


def parse_callback(data: str) -> tuple[int, bool] | None:
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[0] == "act" and parts[1].isdigit() and parts[2] in ("yes", "no"):
        return int(parts[1]), parts[2] == "yes"
    return None
