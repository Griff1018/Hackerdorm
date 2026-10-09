"""Listing matchmaker: when a listing goes live, find past buyer leads who fit it and draft
personal intros. Drafts go to the agent as pending actions (Approve/Cancel)."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from .. import db, llm, telegram_api as tg
from . import actions, common

log = logging.getLogger(__name__)

MIN_FIT = 6
MAX_DRAFTS = 5
MAX_CANDIDATES = 40

PROMPT = """You are a real estate matchmaker for {agent}'s team. A property has just been listed. Decide which past buyer leads genuinely fit it, and draft a short personal intro for each.

NEW LISTING:
{listing}

CANDIDATE LEADS (JSON):
{candidates}

Rules:
- Each lead's notes, timeline and inspection bookings describe their EARLIER enquiry ("enquired_about"), not this listing. Use them to understand what the lead wants, but never imply they booked or viewed THIS property.
- Judge fit on budget vs asking price, required beds/baths/layout, location/area, parking/pets/other must-haves in notes, and timeline.
- fit_score 0-10. Only include leads with fit_score >= {min_fit}. It is fine to return no matches.
- Never include a lead whose stated budget is clearly below the asking price, or whose must-haves conflict with the listing.
- message: written as Alex from {agent}'s team, under 300 characters, personal (use their name and one detail they told us), mention the address, end with ONE low-pressure question (e.g. whether they'd like the details or an inspection time). No prices beyond the listing's asking price, no promises.

Return ONLY JSON:
{{"matches": [{{"lead_id": 1, "fit_score": 8, "reason": "one short sentence", "message": "..."}}]}}"""


def _listing_text(listing: Any) -> str:
    keys = ["address", "property_type", "asking_price", "method_of_sale", "layout_specs", "parking",
            "outdoor_features", "pet_policy", "zoning", "inspection_windows", "upgrades"]
    return "\n".join(f"{k}: {listing[k] or '-'}" for k in keys)


def candidates(listing_id: int) -> list[Any]:
    since = db.to_iso(db.utcnow() - timedelta(days=365))
    return db.match_candidates(listing_id, since, MAX_CANDIDATES)


async def find_matches(listing_id: int, notify: bool = True) -> dict[str, Any]:
    listing = db.get_listing(listing_id)
    if listing is None:
        return {"error": f"no listing #{listing_id}", "matches": [], "proposals": []}
    if listing["status"] != "SELLING":
        return {"error": f"listing #{listing_id} is {listing['status']}, not SELLING", "matches": [], "proposals": []}
    pool = candidates(listing_id)
    if not pool:
        if notify:
            await tg.notify_admins(f"🔎 Matchmaker: no past buyer leads to check for {listing['address']} (#{listing_id}).")
        return {"listing": listing["address"], "candidates": 0, "matches": [], "proposals": []}

    compact = [{
        "lead_id": r["id"], "name": r["name"], "type": r["lead_type"], "budget": r["budget"],
        "timeline": r["timeline"], "finance": r["pre_approval"], "notes": r["notes"],
        "enquired_about": r["property_address"], "score": r["score"],
    } for r in pool]
    result = await llm.complete_json(PROMPT.format(
        agent=common.agent_name(), listing=_listing_text(listing),
        candidates=json.dumps(compact, ensure_ascii=False), min_fit=MIN_FIT,
    ), max_tokens=2000)

    valid_ids = {r["id"] for r in pool}
    matches = []
    for m in result.get("matches") or []:
        try:
            lead_id, fit = int(m["lead_id"]), int(float(m.get("fit_score", 0)))
        except (KeyError, TypeError, ValueError):
            continue
        if lead_id in valid_ids and fit >= MIN_FIT and str(m.get("message", "")).strip():
            matches.append({"lead_id": lead_id, "fit_score": fit, "reason": str(m.get("reason", "")),
                            "message": str(m["message"]).strip()})
    matches.sort(key=lambda m: m["fit_score"], reverse=True)
    matches = matches[:MAX_DRAFTS]

    proposals: list[tuple[int, str]] = []
    for m in matches:
        try:
            action_id, summary = actions.propose(
                "send_message_to_lead",
                {"lead_id": m["lead_id"], "text": m["message"], "listing_id": listing_id},
                source="matchmaker",
            )
        except ValueError as exc:
            log.warning("Skipping match %s: %s", m["lead_id"], exc)
            continue
        summary = f"🎯 Fit {m['fit_score']}/10 — {m['reason']}\n{summary}"
        db.update("pending_actions", action_id, {"summary": summary})
        db.insert("listing_matches", {"listing_id": listing_id, "lead_id": m["lead_id"], "fit_score": m["fit_score"],
                                      "reason": m["reason"], "action_id": action_id, "created_at": db.now_iso()})
        proposals.append((action_id, summary))

    if notify:
        if proposals:
            await tg.notify_admins(f"🔎 Matchmaker: {len(proposals)} past buyer(s) look like a fit for "
                                   f"{listing['address']} (#{listing_id}). Approve the intros you want sent:")
            for action_id, summary in proposals:
                await tg.notify_admins(summary, actions.buttons(action_id))
        else:
            await tg.notify_admins(f"🔎 Matchmaker: checked {len(pool)} past buyer(s) for {listing['address']} "
                                   f"(#{listing_id}) — no strong fits.")
    return {"listing": listing["address"], "candidates": len(pool),
            "matches": [{k: m[k] for k in ("lead_id", "fit_score", "reason")} for m in matches],
            "proposals": proposals}
