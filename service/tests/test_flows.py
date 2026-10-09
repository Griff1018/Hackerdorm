from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from app import db, workers
from app.llm import parse_json_object
from app.mailer import InboundEmail, strip_quoted
from app.services import admin, common, leads, listings, reengagement

LEGACY_XLSX = Path(__file__).resolve().parents[2] / "(FINAL) ULTIMATE Template - Ultimate Lead Database.xlsx"


def run(coro):  # noqa: ANN001, ANN201
    return asyncio.run(coro)


def tg_message(chat_id: str, text: str, first_name: str = "Mike") -> dict:
    return {"chat": {"id": int(chat_id), "type": "private"}, "from": {"id": int(chat_id), "first_name": first_name},
            "text": text}


async def settle() -> None:
    """Let debounced reply tasks finish."""
    for _ in range(5):
        await asyncio.sleep(0.01)
        pending = list(leads._tasks)
        if pending:
            await asyncio.gather(*pending)


def enquiry_email(**over) -> InboundEmail:  # noqa: ANN003
    base = dict(uid="1", message_id="<m1@x>", sender="m.chang@example.com", sender_name="Michael Chang",
                subject="Enquiry about 12 Help Street", text="Hi, is 12 Help Street still available? Call 0412 345 678")
    base.update(over)
    return InboundEmail(**base)


EXTRACTED = {"is_property_enquiry": True, "lead_name": "Michael Chang", "lead_email": "m.chang@example.com",
             "lead_phone": "+61412345678", "buyer_or_seller": "Buyer",
             "property_address": "12 Help Street, Richmond", "message": "Is it still available?"}


def add_listing() -> int:
    now = db.now_iso()
    return db.insert("listings", {"address": "12 Help Street, Richmond VIC 3121", "asking_price": "$880,000",
                                  "inspection_windows": "Sat 10-11am", "status": "SELLING",
                                  "review_token": "tok", "created_at": now, "updated_at": now})


# --- pure helpers ----------------------------------------------------------------------

def test_split_tags_priority_and_cleanup() -> None:
    assert common.split_tags("Great, noted. [QUALIFIED]") == ("Great, noted.", "QUALIFIED")
    assert common.split_tags("AI: Okay [standby]") == ("Okay", "STANDBY")
    assert common.split_tags("Closing. [QUALIFIED] [IGNORE]")[1] == "IGNORE"
    assert common.split_tags("Just text")[1] is None


def test_parse_json_object_tolerates_fences() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}


def test_normalize_phone() -> None:
    assert common.normalize_phone("+61 412 345 678") == "+61412345678"
    assert common.normalize_phone("0061412345678") == "+61412345678"
    assert common.normalize_phone("null") is None


def test_strip_quoted_reply() -> None:
    body = "Yes, 1-3 months.\n\nOn Mon, 5 Oct 2026, Alex wrote:\n> Are you looking to move soon?"
    assert strip_quoted(body) == "Yes, 1-3 months."


# --- email intake -----------------------------------------------------------------------

def test_new_then_returning_email_lead_is_not_duplicated(fake) -> None:  # noqa: ANN001
    listing_id = add_listing()
    fake.json_replies.append(EXTRACTED)
    fake.replies.append("Hi Michael, thanks for asking about 12 Help Street! Moving in 1-3 months or browsing?")
    result = run(leads.intake_email(enquiry_email()))
    assert result.startswith("lead 1 (new)")

    lead = db.get_lead(1)
    assert lead["listing_id"] == listing_id and lead["status"] == "INITIATED"
    assert lead["next_followup_at"] is not None
    to, _, body = fake.emails[0]
    assert to == "m.chang@example.com" and "https://t.me/TestBot?start=" + lead["link_code"] in body

    fake.json_replies.append({**EXTRACTED, "property_address": "1 Stoke Street"})
    fake.replies.append("Welcome back!")
    result = run(leads.intake_email(enquiry_email(message_id="<m2@x>", subject="Stoke Street")))
    assert result == "lead 1 (returning)"
    assert db.query_one("SELECT COUNT(*) n FROM leads")["n"] == 1
    assert db.query_one("SELECT COUNT(*) n FROM enquiries")["n"] == 2
    assert db.get_lead(1)["is_returning"] == 1


def test_non_enquiry_email_is_skipped(fake) -> None:  # noqa: ANN001
    fake.json_replies.append({"is_property_enquiry": False})
    assert run(leads.intake_email(enquiry_email())).startswith("skipped")
    assert db.query_one("SELECT COUNT(*) n FROM leads")["n"] == 0


def test_email_reply_from_known_lead_continues_conversation(fake) -> None:  # noqa: ANN001
    fake.json_replies.append(EXTRACTED)
    fake.replies.append("Moving in 1-3 months or browsing?")
    run(leads.intake_email(enquiry_email()))
    fake.replies.append("Great — what's your budget range?")
    reply = enquiry_email(message_id="<m3@x>", subject="Re: Enquiry", in_reply_to="<x@y>",
                          text="Within 2 months.\n\nOn Mon, Alex wrote:\n> Moving soon?")
    assert "answered by email" in run(leads.intake_email(reply))
    assert fake.emails[-1][1].startswith("Re:")
    assert "User: Within 2 months." in db.transcript(1)


# --- telegram chat ---------------------------------------------------------------------

def _email_lead(fake) -> dict:  # noqa: ANN001
    add_listing()
    fake.json_replies.append(EXTRACTED)
    fake.replies.append("Moving in 1-3 months or browsing?")
    run(leads.intake_email(enquiry_email()))
    return db.get_lead(1)


def test_start_link_then_qualify(fake) -> None:  # noqa: ANN001
    lead = _email_lead(fake)

    async def flow() -> None:
        await workers.handle_update({"message": tg_message("555", f"/start {lead['link_code']}")})
        await workers.handle_update({"message": tg_message("555", "Next month, budget 900k, pre-approved, 3 bed")})
        await settle()

    fake.replies.append("To confirm: next month, $900k, pre-approved, 3 bed. Look right?")
    run(flow())
    linked = db.get_lead(1)
    assert linked["telegram_chat_id"] == "555" and linked["status"] == "IN_PROGRESS"
    assert fake.telegram[0] == ("555", "Moving in 1-3 months or browsing?")  # opener re-sent on link
    assert "12 Help Street, Richmond VIC 3121" in fake.prompts[-1]          # listing data in Alex prompt

    fake.replies.append("Great, I've noted that down. Marcus will contact you shortly. [QUALIFIED]")
    fake.json_replies.append({"final_lead_type": "BUYER", "extracted_address": "12 Help Street", "timeline": "next month",
                              "budget": "$900k", "pre_approval": "Pre-approved", "notes": "3 bed", "lead_score": 9,
                              "score_reason": "Ready buyer.", "is_qualified": "YES"})

    async def confirm() -> None:
        await workers.handle_update({"message": tg_message("555", "Yes that's right")})
        await settle()

    run(confirm())
    q = db.get_lead(1)
    assert q["status"] == "QUALIFIED" and q["score"] == 9 and q["next_followup_at"] is None
    assert fake.telegram[-1] == ("555", "Great, I've noted that down. Marcus will contact you shortly.")
    assert any("HOT LEAD" in m for m in fake.admin)
    assert any("Hot Lead Alert" in e[1] for e in fake.emails)


def test_debounce_batches_rapid_messages(fake, monkeypatch) -> None:  # noqa: ANN001
    from app.config import settings
    monkeypatch.setattr(settings, "reply_debounce_seconds", 0.05)
    fake.replies.append("Thanks! Are you buying or selling?")

    async def flow() -> None:
        await workers.handle_update({"message": tg_message("777", "hi")})
        await workers.handle_update({"message": tg_message("777", "I saw your listing")})
        await asyncio.sleep(0.2)
        await settle()

    run(flow())
    lead_chat = [t for c, t in fake.telegram if c == "777"]
    assert lead_chat == ["Thanks! Are you buying or selling?"]  # one reply for two messages
    assert "User: hi\nUser: I saw your listing" in db.transcript(1)


def test_handover_pauses_alex_and_forwards(fake) -> None:  # noqa: ANN001
    fake.replies.append("I'll have Marcus contact you directly about price. [HANDOVER]")

    async def flow() -> None:
        await workers.handle_update({"message": tg_message("888", "Will the vendor take 800k?")})
        await settle()
        await workers.handle_update({"message": tg_message("888", "Hello?")})
        await settle()

    run(flow())
    assert db.get_lead(1)["status"] == "NEEDS_AGENT"
    assert any("HANDOVER REQUIRED" in m for m in fake.admin)
    assert any("waiting for you" in m and "Hello?" in m for m in fake.admin)
    assert not fake.replies  # no extra LLM call after handover

    run(admin.handle("999", "/reply 1 Hi, Marcus here."))
    assert ("888", "Hi, Marcus here.") in fake.telegram
    run(admin.handle("999", "/resume 1"))
    assert db.get_lead(1)["status"] == "IN_PROGRESS"


def test_ignore_bans_lead(fake) -> None:  # noqa: ANN001
    fake.replies.append("I am closing this inquiry. Have a good day. [IGNORE]")

    async def flow() -> None:
        await workers.handle_update({"message": tg_message("444", "lol whatever")})
        await settle()
        await workers.handle_update({"message": tg_message("444", "spam spam")})
        await settle()

    run(flow())
    assert db.get_lead(1)["status"] == "BANNED"
    # One closing reply from Alex, plus a short notice on the later message — a banned
    # conversation still acknowledges the user rather than going silent.
    banned_replies = [t for c, t in fake.telegram if c == "444"]
    assert len(banned_replies) == 2
    assert "closing this inquiry" in banned_replies[0].lower()
    assert "closed" in banned_replies[1].lower()


# --- re-engagement --------------------------------------------------------------------

def test_reengagement_steps_and_final_email(fake) -> None:  # noqa: ANN001
    lead = _email_lead(fake)
    db.update("leads", 1, {"telegram_chat_id": "555"})
    anchor = db.utcnow() - timedelta(days=100)
    db.update("leads", 1, {"followup_anchor_at": db.to_iso(anchor), "next_followup_at": db.to_iso(anchor + timedelta(days=3))})

    assert run(reengagement.run()) == "Re-engagement is OFF."
    run(admin.handle("999", "/reengagement_on"))
    for step in range(4):
        fake.replies.append(f"follow-up {step}")
        run(reengagement.run())
        assert fake.telegram[-1] == ("555", f"follow-up {step}")
        assert db.get_lead(1)["followup_step"] == step + 1
    fake.replies.append("Subject: Your plans this quarter\nHi Michael, any change in plans?")
    run(reengagement.run())
    assert fake.emails[-1][1] == "Your plans this quarter"
    final = db.get_lead(1)
    assert final["followup_step"] == 5 and final["next_followup_at"] is None
    assert reengagement.due_leads() == []
    assert lead["link_code"]


def test_scheduler_runs_once_per_day(fake, monkeypatch) -> None:  # noqa: ANN001
    calls = []

    async def fake_run(force: bool = False) -> str:
        calls.append(1)
        return "🔁 Re-engagement run: 1 follow-up(s) sent"

    monkeypatch.setattr(reengagement, "run", fake_run)
    db.set_setting("reengagement_enabled", "1")
    monkeypatch.setattr(workers.settings, "reengagement_hour", 0)
    run(workers.run_reengagement_if_due())
    run(workers.run_reengagement_if_due())
    assert calls == [1]


# --- admin + listings -------------------------------------------------------------------

def test_admin_commands(fake) -> None:  # noqa: ANN001
    _email_lead(fake)
    for cmd in ["/help", "/leads", "/top", "/summary", "/recent", "/pending", "/listing", "/lead 1", "/profile"]:
        run(admin.handle("999", cmd))
    texts = [t for c, t in fake.telegram if c == "999"]
    assert "AVAILABLE COMMANDS" in texts[0]
    assert "TODAY'S LEADS" in texts[1] and "Michael Chang" in texts[1]
    assert "Total leads: 1" in texts[3]
    assert "#1 Michael Chang — step 1" in texts[5]
    run(admin.handle("999", "/export"))
    assert fake.documents and fake.documents[0].endswith(".xlsx")


def test_listing_email_creates_draft_then_approval(fake, monkeypatch) -> None:  # noqa: ANN001
    from app.mailer import Attachment
    monkeypatch.setattr(listings, "extract_pdf_text", lambda data: "CONTRACT TEXT " * 50)

    async def fake_scrape(url: str) -> str:
        return "3 bed 2 bath, inspections Sat 10am"

    monkeypatch.setattr(listings, "scrape", fake_scrape)
    fake.json_replies.append({f: f"value {f}" for f in db.LISTING_FIELDS} | {"address": "9 New Road, Ryde NSW"})
    em = InboundEmail(uid="5", message_id="<l1@x>", sender="agent@example.com", sender_name="Marcus",
                      subject="New listing", text="https://www.realestate.com.au/property-123",
                      attachments=[Attachment("contract.pdf", "application/pdf", b"%PDF-1.4")])
    assert run(workers.process_email(em)) == "listing 1"
    draft = db.get_listing(1)
    assert draft["status"] == "DRAFT" and draft["listing_url"].endswith("property-123")
    assert "/listings/review/" + draft["review_token"] in fake.admin[-1]
    assert db.match_listing("9 New Road Ryde") is None  # drafts are not used by Alex

    form = {f: draft[f] for f in db.LISTING_FIELDS} | {"approve": "yes"}
    listing, approved = listings.save_review(draft["review_token"], form)
    assert approved and listing["status"] == "SELLING"
    assert db.match_listing("9 New Road, Ryde NSW")["id"] == 1


@pytest.mark.skipif(not LEGACY_XLSX.exists(), reason="legacy workbook not present")
def test_import_legacy_workbook(fake, monkeypatch) -> None:  # noqa: ANN001
    from app import import_excel
    monkeypatch.setattr(db, "connect", lambda *a, **k: db.conn())  # keep the in-memory DB
    assert import_excel.main([str(LEGACY_XLSX), "--with-leads"]) == 0
    assert db.query_one("SELECT COUNT(*) n FROM listings")["n"] == 3
    assert db.query_one("SELECT COUNT(*) n FROM leads")["n"] == 4  # 11 duplicated rows -> 4 people
    assert db.get_agent_profile()["include_phone"] == 1


# --- /start must always produce a reply (regression: bot went silent) -------------------

def _make_lead(chat_id: str, status: str, name: str = "Mike Lim") -> int:
    lead = db.create_lead({"name": name, "telegram_chat_id": chat_id, "source": "TELEGRAM"})
    db.update("leads", lead["id"], {"status": status})
    return lead["id"]


def test_start_replies_for_every_status(fake) -> None:  # noqa: ANN001
    """A lead typing /start must always get an answer, whatever their status.

    Regression: after a lead qualified, /start produced no reply at all because the
    handler fell through to a generic opener (or nothing) for non-INITIATED states."""
    for i, status in enumerate(("INITIATED", "IN_PROGRESS", "QUALIFIED", "NEEDS_AGENT", "BANNED")):
        chat_id = str(2000 + i)
        _make_lead(chat_id, status)
        run(leads.handle_telegram_message(tg_message(chat_id, "/start")))
        assert fake.telegram, f"no reply for status {status}"
        assert fake.telegram[-1][0] == chat_id, f"reply went to the wrong chat for {status}"
        fake.telegram.clear()


def test_start_on_qualified_lead_does_not_create_duplicate(fake) -> None:  # noqa: ANN001
    """Re-opening an already-qualified chat must reuse the lead, not fork a new one."""
    lead_id = _make_lead("3001", "QUALIFIED", name="Ada Wong")
    run(leads.handle_telegram_message(tg_message("3001", "/start")))
    assert db.query_one("SELECT COUNT(*) n FROM leads")["n"] == 1
    assert db.get_lead(lead_id)["status"] == "QUALIFIED"
    assert fake.telegram and fake.telegram[-1][0] == "3001"


def test_message_while_needs_agent_is_acknowledged(fake) -> None:  # noqa: ANN001
    """While a human handles the lead, the lead must still get an acknowledgement."""
    _make_lead("4001", "NEEDS_AGENT", name="Sara Tan")
    run(leads.handle_telegram_message(tg_message("4001", "Did you get my message?")))
    assert fake.telegram and fake.telegram[-1][0] == "4001"
    assert fake.admin, "the agent should also be notified"


def test_message_while_banned_is_acknowledged(fake) -> None:  # noqa: ANN001
    """Even a closed conversation answers, instead of silently swallowing the message."""
    _make_lead("5001", "BANNED", name="Troll")
    run(leads.handle_telegram_message(tg_message("5001", "hello?")))
    assert fake.telegram and fake.telegram[-1][0] == "5001"


def test_standby_after_qualification_keeps_followup_alive(fake) -> None:  # noqa: ANN001
    """A qualified lead replying 'Thanks' must refresh the follow-up clock, not stall."""
    lead_id = _make_lead("6001", "QUALIFIED", name="Ben Ho")
    db.add_message(lead_id, "lead", "telegram", "Thanks!")
    fake.replies.append("You're welcome, Ben. Marcus will be in touch. [STANDBY]")
    run(leads.generate_reply(lead_id))
    lead = db.get_lead(lead_id)
    assert lead["status"] == "QUALIFIED"
    assert lead["next_followup_at"] is not None, "follow-up clock should keep running"
    assert fake.telegram and "welcome" in fake.telegram[-1][1].lower()


def test_needs_agent_lead_gets_acknowledgement_and_agent_alert(fake) -> None:  # noqa: ANN001
    """Cover the message path (not just /start) for a handover lead."""
    lead_id = _make_lead("7001", "NEEDS_AGENT", name="Ken Ng")
    run(leads.handle_telegram_message(tg_message("7001", "Can we negotiate the price?")))
    assert db.messages_for(lead_id), "the inbound message must be recorded"
    assert any("waiting for you" in m for m in fake.admin)
