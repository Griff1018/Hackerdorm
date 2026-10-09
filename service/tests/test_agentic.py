"""Copilot, approval flow, matchmaker and morning briefing."""
from __future__ import annotations

import asyncio
import json

from app import db, workers
from app.services import actions, briefing, copilot, matching


def run(coro):  # noqa: ANN001, ANN201
    return asyncio.run(coro)


def tool_call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def say(text: str) -> dict:
    return {"role": "assistant", "content": text}


def make_lead(**over) -> int:  # noqa: ANN003
    values = dict(name="David Miller", email="david@example.com", telegram_chat_id="555", lead_type="BUYER",
                  status="QUALIFIED", source="EMAIL", budget="$1.2M", timeline="1-3 months",
                  notes="Wants 2+ beds, parking", score=8, is_qualified=1,
                  last_contacted_at=db.now_iso())
    values.update(over)
    return db.create_lead(values)["id"]


def make_listing(status: str = "SELLING", address: str = "Unit 701, 4 Saunders Close, Macquarie Park NSW") -> int:
    now = db.now_iso()
    return db.insert("listings", {"address": address, "asking_price": "$1,150,000", "layout_specs": "2 Bed / 2 Bath",
                                  "parking": "1-Car LUG", "status": status, "review_token": f"t{now}{address}",
                                  "created_at": now, "updated_at": now})


def tap(action_id: int, yes: bool, chat_id: str = "999") -> None:
    cb = {"id": "cb", "data": f"act:{action_id}:{'yes' if yes else 'no'}",
          "message": {"message_id": 1, "chat": {"id": int(chat_id)}, "text": "proposal"}}
    run(workers.handle_update({"update_id": 1, "callback_query": cb}))


# --- copilot ----------------------------------------------------------------------

def test_copilot_looks_up_then_proposes_and_waits_for_approval(fake) -> None:  # noqa: ANN001
    lead_id = make_lead()
    fake.chat_replies += [
        tool_call("search_leads", {"text": "David"}),
        tool_call("propose_message", {"lead_id": lead_id, "text": "Hi David, the inspection moved to 11am Sat. Still OK?"}, "c2"),
        say("Drafted a message to David Miller (#1) — approve below."),
    ]
    run(workers.handle_update({"message": {"chat": {"id": 999, "type": "private"}, "from": {"id": 999},
                                           "text": "tell David the inspection moved to 11am"}}))

    # tool results were fed back to the model
    second_call = fake.chat_calls[1]
    assert second_call[-1]["role"] == "tool" and "David Miller" in second_call[-1]["content"]
    assert ("999", "Drafted a message to David Miller (#1) — approve below.") in fake.telegram
    chat_id, summary, buttons = fake.buttons[-1]
    assert chat_id == "999" and "inspection moved to 11am" in summary
    assert not [t for c, t in fake.telegram if c == "555"]  # nothing sent to the lead yet

    action_id = db.query_one("SELECT id FROM pending_actions")["id"]
    assert buttons[0][0][1] == f"act:{action_id}:yes"
    tap(action_id, yes=True)
    assert ("555", "Hi David, the inspection moved to 11am Sat. Still OK?") in fake.telegram
    assert db.query_one("SELECT status FROM pending_actions WHERE id = ?", [action_id])["status"] == "DONE"
    assert "Done." in fake.edits[-1]

    tap(action_id, yes=True)  # double tap is harmless
    assert "Already done" in fake.edits[-1]
    assert len([t for c, t in fake.telegram if c == "555"]) == 1


def test_copilot_invalid_proposal_reports_error_to_model(fake) -> None:  # noqa: ANN001
    fake.chat_replies += [tool_call("propose_lead_status", {"lead_id": 42, "status": "QUALIFIED"}),
                          say("There is no lead #42.")]
    run(copilot.handle("999", "qualify lead 42"))
    assert '"error": "no lead #42"' in fake.chat_calls[1][-1]["content"]
    assert db.query_one("SELECT COUNT(*) n FROM pending_actions")["n"] == 0


def test_copilot_keeps_short_memory(fake) -> None:  # noqa: ANN001
    fake.chat_replies += [say("You have 0 leads."), say("Still 0.")]
    run(copilot.handle("999", "how many leads?"))
    run(copilot.handle("999", "and now?"))
    contents = [m["content"] for m in fake.chat_calls[1]]
    assert "how many leads?" in contents and "You have 0 leads." in contents
    copilot.reset("999")


def test_cancel_and_non_admin_taps(fake) -> None:  # noqa: ANN001
    lead_id = make_lead()
    action_id, _ = actions.propose("set_lead_status", {"lead_id": lead_id, "status": "banned"})
    tap(action_id, yes=True, chat_id="555")  # a lead can't approve
    assert db.query_one("SELECT status FROM pending_actions")["status"] == "PENDING"
    tap(action_id, yes=False)
    assert db.query_one("SELECT status FROM pending_actions")["status"] == "CANCELLED"
    assert db.get_lead(lead_id)["status"] == "QUALIFIED"


# --- matchmaker -------------------------------------------------------------------

def test_matchmaker_drafts_intros_only_for_valid_strong_fits(fake) -> None:  # noqa: ANN001
    good = make_lead()
    weak = make_lead(name="Low Budget", email="low@example.com", telegram_chat_id="556", budget="$500k")
    make_lead(name="Banned", email="b@example.com", telegram_chat_id="557", status="BANNED")
    listing_id = make_listing()
    fake.json_replies.append({"matches": [
        {"lead_id": good, "fit_score": 9, "reason": "Budget and 2 beds fit", "message": "Hi David, a 2-bed in Macquarie Park just listed — want the details?"},
        {"lead_id": weak, "fit_score": 3, "reason": "Budget too low", "message": "x"},
        {"lead_id": 999, "fit_score": 10, "reason": "hallucinated", "message": "x"},
    ]})
    result = run(matching.find_matches(listing_id))
    assert result["candidates"] == 2  # banned lead excluded from the pool
    assert [m["lead_id"] for m in result["matches"]] == [good]
    assert "Banned" not in fake.prompts[-1]
    _, summary, _ = fake.buttons[-1]
    assert "Fit 9/10" in summary and "Macquarie Park just listed" in summary

    action_id = db.query_one("SELECT id FROM pending_actions")["id"]
    tap(action_id, yes=True)
    lead = db.get_lead(good)
    assert lead["listing_id"] == listing_id and lead["status"] == "IN_PROGRESS"
    assert lead["property_address"].startswith("Unit 701")

    fake.json_replies.append({"matches": []})
    again = run(matching.find_matches(listing_id))
    assert again["candidates"] == 1  # the matched lead is not proposed twice


def test_matchmaker_rejects_non_selling_listing(fake) -> None:  # noqa: ANN001
    listing_id = make_listing(status="DRAFT")
    assert "not SELLING" in run(matching.find_matches(listing_id))["error"]


def test_approving_listing_triggers_matchmaker(fake, monkeypatch) -> None:  # noqa: ANN001
    from fastapi.testclient import TestClient
    from app import main
    calls = []

    async def fake_find(listing_id: int, notify: bool = True) -> dict:
        calls.append(listing_id)
        return {}

    monkeypatch.setattr(matching, "find_matches", fake_find)
    listing_id = make_listing(status="DRAFT")
    token = db.get_listing(listing_id)["review_token"]
    form = {f: db.get_listing(listing_id)[f] or "" for f in db.LISTING_FIELDS} | {"approve": "yes"}
    app = main.FastAPI()
    app.add_api_route("/listings/review/{token}", main.submit_listing, methods=["POST"])
    with TestClient(app) as client:
        assert client.post(f"/listings/review/{token}", data=form).status_code == 200
    assert calls == [listing_id]


# --- briefing ---------------------------------------------------------------------

def test_briefing_gathers_facts_and_falls_back_without_llm(fake, monkeypatch) -> None:  # noqa: ANN001
    hot = make_lead(qualified_at=db.now_iso(), score=9, phone="+61400000000")
    make_lead(name="Waiting", email="w@example.com", telegram_chat_id="558", status="NEEDS_AGENT")
    facts = briefing.gather_facts()
    assert [r["id"] for r in facts["hot_qualified_recently"]] == [hot]
    assert facts["waiting_on_agent_handover"][0]["name"] == "Waiting"

    async def broken(*_, **__):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("LLM down")

    monkeypatch.setattr(briefing.llm, "complete", broken)
    text = run(briefing.build())
    assert "Call David Miller (#1)" in text and "+61400000000" in text and "waiting on you" in text


def test_briefing_sent_once_per_day_and_can_be_disabled(fake, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(workers.settings, "briefing_hour", 0)
    fake.replies.append("☀️ Nothing urgent today.")
    run(workers.send_briefing_if_due())
    run(workers.send_briefing_if_due())
    assert len([m for m in fake.admin if "Nothing urgent" in m]) == 1

    db.set_setting("briefing_last_run", "")
    db.set_setting("briefing_enabled", "0")
    run(workers.send_briefing_if_due())
    assert len([m for m in fake.admin if "Nothing urgent" in m]) == 1
