"""22 SYNTHETIC WhatsApp customers for the demo (from the team's demoWhatsapp sample clients), rewritten for
Campus Crumb's real menu, prices and policies so every total matches menu.csv and the policy file.

Each chat is stored as a normal BizFlow WhatsApp thread (customer messages + replies by BizFlow's AI agent).
Confirmed orders become BizFlow orders. seed() is idempotent: chats that already exist are skipped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

MENU = {"cookies": ("Chocolate Chip Cookies (6pcs)", 6.00), "tea": ("Iced Lemon Tea 500ml", 4.50), "muffin": ("Banana Muffin", 5.00),
        "bun": ("Spicy Chicken Bun", 5.50), "granola": ("Granola Bar", 4.00)}


def _lines(items):
    return "\n".join(f"• {q}× {MENU[k][0]} – RM{q * MENU[k][1]:.2f}" for k, q in items)


def _total(items):
    return sum(q * MENU[k][1] for k, q in items)


# (name, phone, minutes ago, unread, [("c"|"a", text)], order: (items, fulfilment, when, status) | None)
O1 = [("tea", 2), ("cookies", 1)]
O4 = [("bun", 10), ("muffin", 6)]
O7 = [("bun", 2)]
O13 = [("tea", 1), ("cookies", 1)]
O16 = [("tea", 3), ("granola", 3)]
O19 = [("cookies", 4)]
O22 = [("tea", 2)]
CLIENTS = [
    ("Aisyah Rahman", "60123384410", 3, 0, [
        ("c", "Hi! Can I get 2 iced lemon tea and 1 box of chocolate chip cookies? Self pickup"),
        ("a", f"Hi Aisyah! 😊 Here's your order:\n{_lines(O1)}\n*Total: RM{_total(O1):.2f}* (campus pickup)\n\nReply *YES* to confirm."),
        ("c", "Yes confirm"),
        ("a", "✅ Order confirmed! Ready for pickup in *15 minutes* at our campus stall. Pay by DuitNow QR or cash. See you soon!")],
     (O1, "pickup", "today, 15 min", "pending")),
    ("Jason Tan", "60167720193", 11, 2, [
        ("c", "My order was ready 1 hour late and the lemon tea was already warm. Not acceptable."),
        ("a", "So sorry, Jason 😔 A 1-hour wait and a warm drink is not okay.\n\nI've noted it for the owner and arranged a *free iced lemon tea* on your next order (within our RM10 refund limit). The owner will follow up with you today."),
        ("c", "Ok thanks for the quick response"),
        ("a", "Thank you for your patience, Jason 🙏 We'll make it right.")], None),
    ("Priya Nair", "60172015582", 26, 0, [
        ("c", "Love your muffins! Could you make an eggless one? I'm allergic to egg 🥲"),
        ("a", "Thank you Priya! 💡 An eggless muffin is a great idea — I've passed it to the owner.\n\nBecause it's about an allergy, the owner will reply to you personally; we can't guarantee any current item is egg-free.")], None),
    ("Muhammad Hafiz", "60134809921", 41, 1, [
        ("c", "Assalamualaikum, nak order 10 spicy chicken bun and 6 banana muffin for our club meeting tomorrow"),
        ("a", f"Waalaikumsalam Hafiz! 🙌\n{_lines(O4)}\n*Total: RM{_total(O4):.2f}*\n\nPickup or campus delivery?"),
        ("c", "Delivery to KK8 lobby, UM"),
        ("a", f"Got it! 📍 KK8 lobby, UM\n*Total: RM{_total(O4):.2f}*\n\nWhat time tomorrow (8am–6pm)? Then reply *YES* to confirm.")], None),
    ("Mei Ling Chong", "60129053347", 58, 0, [
        ("c", "Hello, where is your stall ah? Open what time?"),
        ("a", "Hi Mei Ling! 👋 We do *campus pickup at Universiti Malaya*, Monday–Friday *8am–6pm*. Send us your order and we'll tell you exactly where to collect it ☺️")], None),
    ("Daniel Lim", "60193661208", 85, 0, [
        ("c", "I ordered a granola bar but got a banana muffin instead. Wrong order again 😤"),
        ("a", "Really sorry, Daniel 🙏 That's our mistake.\n\nWe'll give you the correct *Granola Bar* free on your next pickup, and I've asked the owner to double-check orders before packing.")], None),
    ("Siti Nur Azman", "60112045778", 122, 0, [
        ("c", "2 spicy chicken bun delivery to KK12 please"),
        ("a", f"Hi Siti! 😊\n{_lines(O7)}\n*Total: RM{_total(O7):.2f}* (campus delivery to KK12)\n\nReply *YES* to confirm."),
        ("c", "Yes"),
        ("a", "✅ Confirmed! Arriving at KK12 in about *30 minutes* 🛵 Pay by DuitNow QR or cash on delivery.")],
     (O7, "delivery", "today, 30 min", "done")),
    ("Kevin Ong", "60169182264", 170, 0, [
        ("c", "Would be nice if you had a loyalty card. I buy almost every day haha"),
        ("a", "Haha we love seeing you every day, Kevin! 💚\n\nA loyalty stamp card is a great idea — I've passed it to the owner.")], None),
    ("Nurul Izzah", "60146630915", 230, 0, [
        ("c", "The helper at the stall this morning was very rude to my friend. Very upset."),
        ("a", "Nurul, I'm truly sorry 😔 Everyone deserves to be treated with respect.\n\nI've escalated this to the owner, who will talk to the helper and contact you personally today.")], None),
    ("Arjun Pillai", "60124476630", 300, 0, [
        ("c", "Do you do bulk orders? Need snacks + drinks for 30 people at our society event next Friday"),
        ("a", "Yes we can, Arjun! 🎉 For 30 people a mix of *Spicy Chicken Buns, Banana Muffins and Iced Lemon Tea* works well.\n\nShare the venue on campus and the time, and the owner will confirm the quantities and total for you.")], None),
    ("Grace Lee", "60175542981", 380, 0, [
        ("c", "Hope you can add more vegan options! 😅"),
        ("a", "Thanks Grace! 🌱 More vegan choices — noted and passed to the owner. We'll let you know if we try one.")], None),
    ("Faizal Hamid", "60132098874", 460, 0, [
        ("c", "Can pay with touch n go?"),
        ("a", "Hi Faizal! Yes 👍 We accept *DuitNow QR* (works with Touch 'n Go eWallet) and cash.")], None),
    ("Chloe Tan", "60111098335", 600, 0, [
        ("c", "1 iced lemon tea and 1 cookies, pickup in 10 min"),
        ("a", f"Hi Chloe! 🍋\n{_lines(O13)}\n*Total: RM{_total(O13):.2f}*, pickup\n\nReply *YES* to confirm."),
        ("c", "yes pls"),
        ("a", "✅ Confirmed! It'll be ready in 10 minutes 🙌")],
     (O13, "pickup", "10 min", "done")),
    ("Ravi Kumar", "60198724416", 900, 0, [
        ("c", "My cookie box only had 4 cookies inside, it should be 6."),
        ("a", "Sorry about that, Ravi 🙏 We'll give you the *2 missing cookies* on your next pickup, and I've told the owner so we check every box.")], None),
    ("Hannah Wong", "60126601937", 1500, 0, [
        ("c", "Any chance to open later? 6pm is too early for us night owls 🦉"),
        ("a", "Haha fellow night owl! 🦉 Later opening hours — noted and passed to the owner. Thanks Hannah!")], None),
    ("Amirul Hakim", "60173308812", 1600, 0, [
        ("c", "3 iced lemon tea 3 granola bar deliver to KK5 please"),
        ("a", f"Hi Amirul!\n{_lines(O16)}\n*Total: RM{_total(O16):.2f}* (campus delivery to KK5)\n\nReply *YES* to confirm."),
        ("c", "confirm"),
        ("a", "✅ Confirmed! On the way to KK5 in about 30 minutes 🛵")],
     (O16, "delivery", "30 min", "done")),
    ("Sarah Lim", "60162057741", 1700, 0, [
        ("c", "Is your food halal? Bringing my Muslim friends"),
        ("a", "Hi Sarah! 😊 Good question — we don't have a halal certificate on file, so I've asked the owner to answer you directly with the details of our ingredients.")], None),
    ("Wei Jie Tan", "60115532009", 2900, 0, [
        ("c", "I paid twice by DuitNow for yesterday's order!"),
        ("a", "Sorry for the trouble, Wei Jie 🙏 I've flagged the double payment to the owner. Refunds above RM10 are handled by the owner personally, so they'll confirm the refund with you today.")], None),
    ("Farah Diana", "60137781450", 3000, 0, [
        ("c", "4 boxes of chocolate chip cookies for a birthday, delivery pls"),
        ("a", f"Happy birthday to the lucky one! 🎂\n{_lines(O19)}\n\nPlease share your *delivery place on campus* 📍")], None),
    ("Jonathan Chua", "60123196604", 4300, 0, [
        ("c", "Suggestion: give a discount if we bring our own cup? Reduce plastic 🌍"),
        ("a", "Love it, Jonathan! 🌍 A bring-your-own-cup discount — noted and passed to the owner. Thank you!")], None),
    ("Lakshmi Devi", "60178862209", 4500, 0, [
        ("c", "Just wanna say the banana muffin was amazing, my whole group loved it ❤️"),
        ("a", "Aww thank you so much, Lakshmi! ❤️ That made our day. See you again soon!")], None),
    ("Zulkifli Omar", "60194013375", 5800, 0, [
        ("c", "2 iced lemon tea takeaway, I'll collect"),
        ("a", f"Hi Zulkifli! 🍋\n{_lines(O22)}\n*Total: RM{_total(O22):.2f}*, self-collect\n\nReply *YES* to confirm."),
        ("c", "ok"),
        ("a", "✅ Confirmed! Ready in 15 minutes.")],
     (O22, "pickup", "15 min", "done")),
]


def seed(d: dict, bid: str = "campus-crumb", tz=None) -> int:
    """Add the sample chats (and their confirmed orders) to an inbox dict in place. Returns how many chats were added."""
    now = datetime.now(tz)
    have = {(t["channel"], t["contact"]["handle"], t["business_id"]) for t in d["threads"]}
    added = 0
    d.setdefault("orders", [])
    for name, phone, ago, unread, msgs, order in CLIENTS:
        if ("whatsapp", phone, bid) in have:
            continue
        last = now - timedelta(minutes=ago)
        n = len(msgs)
        tid = "T" + uuid.uuid4().hex[:7]
        th = {"id": tid, "business_id": bid, "channel": "whatsapp", "contact": {"handle": phone, "name": name}, "unread": unread,
              "auto_reply": True, "synthetic": True, "messages": [], "updated_at": last.isoformat(timespec="seconds")}
        for i, (who, text) in enumerate(msgs):
            at = (last - timedelta(minutes=2 * (n - 1 - i))).isoformat(timespec="seconds")
            m = {"id": "m" + uuid.uuid4().hex[:6], "from": "them" if who == "c" else "me", "text": text, "at": at}
            if who == "a":
                m["by"] = "auto"
            th["messages"].append(m)
        d["threads"].append(th)
        if order:
            items, ful, when, status = order
            d["orders"].append({"id": "O" + uuid.uuid4().hex[:6], "status": status, "created_at": th["messages"][-1]["at"],
                                "updated_at": th["messages"][-1]["at"], "business_id": bid, "thread_id": tid, "channel": "whatsapp",
                                "customer": name, "phone": phone,
                                "items": [{"item": MENU[k][0], "qty": q, "price": f"{MENU[k][1]:.2f}", "line_total": f"{q * MENU[k][1]:.2f}"} for k, q in items],
                                "total": f"{_total(items):.2f}", "fulfilment": ful, "when": when, "notes": "", "source": "auto-reply (sample chat)", "synthetic": True})
        added += 1
    return added
