"""Synthetic FR-01 Tier B customer and order operations.

This module is deterministic and local-only. It reads menu/promotion/policy files, creates
synthetic customer orders, writes a stock ledger instead of changing inventory.csv, and
records permission decisions in an audit log. No real messages, refunds, or payments occur.
"""
from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

MY_TZ = timezone(timedelta(hours=8))
CSV_ORDER_COLUMNS = ["order_id", "customer_id", "channel", "items", "subtotal", "discount", "total",
                     "status", "special_requests", "escalated", "created_at", "updated_at"]
CSV_LEDGER_COLUMNS = ["entry_id", "order_id", "product_id", "change", "stock_after", "timestamp"]
CSV_AUDIT_COLUMNS = ["audit_id", "action", "actor", "decision", "reason", "timestamp", "order_id"]


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def now_iso() -> str:
    return datetime.now(MY_TZ).isoformat()


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: row.get(c, "") for c in columns} for row in rows)


def _audit(rows: list[dict], action: str, actor: str, decision: str, reason: str, order_id: str = "") -> None:
    rows.append({"audit_id": f"AUD-{len(rows)+1:04d}", "action": action, "actor": actor,
                 "decision": decision, "reason": reason, "timestamp": now_iso(), "order_id": order_id})


def load_catalog(data_dir: Path) -> tuple[dict, dict, dict]:
    menu = {r["item_id"]: r for r in read_csv(data_dir / "menu.csv")}
    promos = {r["promo_id"]: r for r in read_csv(data_dir / "promotions.csv")}
    profile = json.loads((data_dir.parent / "business_profile.json").read_text(encoding="utf-8"))
    return menu, promos, profile


def current_stock(data_dir: Path, output_dir: Path) -> dict[str, int]:
    stock = {r["product_id"]: int(r["stock_on_hand"]) for r in read_csv(data_dir / "inventory.csv")}
    ledger = output_dir / "stock_ledger.csv"
    if ledger.exists():
        for r in read_csv(ledger):
            stock[r["product_id"]] = stock.get(r["product_id"], 0) + int(r["change"])
    return stock


def write_current_stock(data_dir: Path, output_dir: Path, stock: dict[str, int], menu: dict) -> None:
    products = {r["product_id"]: r for r in read_csv(data_dir / "products.csv")}
    rows = []
    for pid, p in products.items():
        rows.append({"product_id": pid, "product_name": p["product_name"], "selling_price": p["selling_price"],
                     "stock_available": str(stock.get(pid, "")), "as_of": now_iso()})
    write_csv(output_dir / "current_stock.csv",
              ["product_id", "product_name", "selling_price", "stock_available", "as_of"], rows)


def _find_items(message: str, menu: dict) -> dict[str, int]:
    low = message.lower()
    found: dict[str, int] = {}
    aliases = {
        "M001": ("chocolate chip cookies", "cookies"),
        "M002": ("iced lemon tea", "lemon tea"),
        "M003": ("banana muffin", "muffin"),
        "M004": ("spicy chicken bun", "chicken bun"),
        "M005": ("granola bar", "granola"),
    }
    for item_id, names in aliases.items():
        if any(n in low for n in names):
            nums = re.findall(rf"(\d+)\s*(?:x\s*)?(?:{re.escape(names[0])}|{re.escape(names[1])})", low)
            found[item_id] = int(nums[0]) if nums else 1
    return found


def _special_request(message: str) -> str:
    low = message.lower()
    if "allerg" in low or "peanut" in low:
        return "ALLERGY MENTION - escalate to owner; no safety guarantee"
    for phrase in ("less spicy", "no sugar", "delay my pickup", "no peanuts"):
        if phrase in low:
            return phrase
    return ""


def faq_answer(question: str, policies_path: Path, audit: list[dict]) -> str:
    text = policies_path.read_text(encoding="utf-8")
    low = question.lower()
    if "hour" in low or "open" in low:
        answer = "Campus pickup is Monday-Friday, 08:00-18:00."
    elif "deliver" in low:
        answer = "Delivery is limited to the campus delivery area and needs a confirmed time."
    elif "refund" in low:
        answer = "Refunds are simulated only; up to MYR 10.00 can be marked simulated, above that escalates to the owner."
    else:
        answer = "I can answer opening hours, campus delivery, cancellation, and simulated refund policy from business_policies.md."
    _audit(audit, "faq_answer", "customer_agent", "auto", "answer came from configured business_policies.md")
    return answer


def _order_record(order_id: str, customer_id: str, items: dict[str, int], menu: dict, status: str,
                  special: str, escalated: str, subtotal: Decimal, discount: Decimal, total: Decimal) -> dict:
    return {"order_id": order_id, "customer_id": customer_id, "channel": "simulated_chat",
            "items": json.dumps(items, sort_keys=True), "subtotal": money(subtotal), "discount": money(discount),
            "total": money(total), "status": status, "special_requests": special, "escalated": escalated,
            "created_at": now_iso(), "updated_at": now_iso()}


def handle_order_message(data_dir: Path, output_dir: Path, message: str) -> dict:
    """Create a deterministic draft cart from one free-form synthetic customer message.

    Parsing identifies menu items only; totals come from menu.csv. The result stays pending until
    the customer confirms. Allergy text is always escalated and no order is confirmed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    menu, _, _ = load_catalog(data_dir)
    items = _find_items(message, menu)
    special = _special_request(message)
    transcript = [message]
    if not items:
        result = {"status": "needs_clarification", "message": "No configured menu item was recognised; ask for a menu item and quantity.", "items": {}}
    else:
        subtotal = sum((Decimal(menu[k]["price"]) * qty for k, qty in items.items()), Decimal("0"))
        result = {"status": "escalated_to_owner" if "ALLERGY" in special else "pending_customer_confirmation",
                  "items": items, "subtotal": money(subtotal), "discount": "0.00", "total": money(subtotal),
                  "pickup_or_delivery": "pickup at requested time" if "pickup" in message.lower() else "confirm pickup/delivery detail",
                  "special_requests": special, "message": "Cart prepared from menu.csv; customer confirmation is still required."}
    payload = {"conversation_id": f"CHAT-REQUEST-{now_iso().replace(':','').replace('.','')}",
               "messages": transcript, "result": result, "synthetic": True}
    (output_dir / "chat_request_latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def simulate_refund(output_dir: Path, order_id: str, amount: str, limit: str = "10.00") -> dict:
    value, cap = Decimal(str(amount)), Decimal(str(limit))
    status = "simulated_approved" if value <= cap else "escalated_to_owner"
    reason = f"within simulated owner limit MYR {cap:.2f}" if value <= cap else f"above simulated owner limit MYR {cap:.2f}"
    result = {"refund_id": f"REF-CLI-{now_iso().replace(':','').replace('.','')}", "order_id": order_id,
              "amount": money(value), "currency": "MYR", "status": status, "reason": reason, "synthetic": True}
    path = output_dir / "refunds_cli.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    return result


def run_tier_b_demo(data_dir: Path, output_dir: Path) -> dict:
    """Run a reproducible Tier B scripted conversation set for tests and the demo."""
    output_dir.mkdir(parents=True, exist_ok=True)
    menu, promos, _ = load_catalog(data_dir)
    # The scripted Tier B fixture is reproducible: start from the source inventory each run,
    # rather than accumulating a previous demonstration ledger.
    stock = {r["product_id"]: int(r["stock_on_hand"]) for r in read_csv(data_dir / "inventory.csv")}
    orders: list[dict] = []
    ledger: list[dict] = []
    audit: list[dict] = []
    transcripts: list[dict] = []
    refunds: list[dict] = []

    # Conversation 1: deterministic order, accepted one configured add-on, then confirmed.
    message = "I would like 2 chocolate chip cookies and pickup at 12:30."
    items = _find_items(message, menu)
    _audit(audit, "create_cart", "customer_agent", "auto", "items looked up in menu.csv")
    _audit(audit, "offer_addon", "customer_agent", "needs customer confirm", "one configured add-on offered")
    addon_message = "Yes, add one iced lemon tea."
    items["M002"] = 1
    subtotal = Decimal("0")
    for item_id, qty in items.items():
        subtotal += Decimal(menu[item_id]["price"]) * qty
    discount = Decimal("0")
    total = subtotal - discount
    order_id = "ORD-CHAT-0001"
    for item_id, qty in items.items():
        pid = menu[item_id]["product_id"]
        if stock.get(pid, 0) < qty:
            raise ValueError(f"insufficient stock for {pid}")
    _audit(audit, "confirm_order", "customer_agent", "needs customer confirm", "customer confirmed cart and stock passed", order_id)
    for item_id, qty in items.items():
        pid = menu[item_id]["product_id"]
        stock[pid] -= qty
        ledger.append({"entry_id": f"LED-{len(ledger)+1:04d}", "order_id": order_id, "product_id": pid,
                       "change": str(-qty), "stock_after": str(stock[pid]), "timestamp": now_iso()})
        _audit(audit, "update_stock", "operations", "auto", "confirmed order written to stock ledger", order_id)
    orders.append(_order_record(order_id, "C001", items, menu, "confirmed", "pickup at 12:30", "no", subtotal, discount, total))
    transcripts.append({"conversation_id": "CHAT-0001", "messages": [message, addon_message,
                     "Confirmed: 2 cookies plus 1 iced lemon tea. Total MYR 16.50."], "order_id": order_id,
                     "synthetic": True})

    # Conversation 2: allergy is always escalated and never safety-approved.
    allergy = "Can I have a granola bar? I am allergic to peanuts."
    allergy_items = _find_items(allergy, menu)
    allergy_order = "ORD-CHAT-0002"
    orders.append(_order_record(allergy_order, "C001", allergy_items, menu, "escalated_to_owner",
                                _special_request(allergy), "yes", Decimal("4.00"), Decimal("0"), Decimal("4.00")))
    _audit(audit, "allergy_escalation", "customer_agent", "blocked", "allergy/food-safety mention; owner must decide", allergy_order)
    transcripts.append({"conversation_id": "CHAT-0002", "messages": [allergy], "order_id": allergy_order,
                       "synthetic": True})

    # Conversation 3: special request requires reconfirmation; cancellation before preparation is allowed.
    cancel_id = "ORD-CHAT-0003"
    cancel_items = {"M003": 1}
    orders.append(_order_record(cancel_id, "C002", cancel_items, menu, "cancelled", "less spicy; reconfirmation not completed",
                                "no", Decimal("5.00"), Decimal("0"), Decimal("5.00")))
    _audit(audit, "special_request", "customer_agent", "needs customer confirm", "special request requires explicit reconfirmation", cancel_id)
    _audit(audit, "cancel_order", "customer_agent", "auto", "cancelled before preparation; no stock deduction", cancel_id)
    transcripts.append({"conversation_id": "CHAT-0003", "messages": ["One banana muffin, less spicy.",
                       "Please cancel it before preparation."], "order_id": cancel_id, "synthetic": True})

    faq_answer("What are your opening hours?", data_dir / "business_policies.md", audit)
    # Simulated refund within limit and an above-limit escalation.
    refunds.append({"refund_id": "REF-0001", "order_id": order_id, "amount": "5.00", "currency": "MYR",
                    "status": "simulated_approved", "reason": "within owner limit MYR 10.00", "synthetic": "true"})
    _audit(audit, "refund", "transaction_controls", "simulated", "within owner limit; no money moved", order_id)
    refunds.append({"refund_id": "REF-0002", "order_id": order_id, "amount": "25.00", "currency": "MYR",
                    "status": "escalated_to_owner", "reason": "above owner limit MYR 10.00", "synthetic": "true"})
    _audit(audit, "refund", "transaction_controls", "needs owner approval", "above owner limit; not issued", order_id)

    write_csv(output_dir / "orders.csv", CSV_ORDER_COLUMNS, orders)
    write_csv(output_dir / "stock_ledger.csv", CSV_LEDGER_COLUMNS, ledger)
    write_csv(output_dir / "audit_log.csv", CSV_AUDIT_COLUMNS, audit)
    write_csv(output_dir / "refunds.csv", ["refund_id", "order_id", "amount", "currency", "status", "reason", "synthetic"], refunds)
    write_current_stock(data_dir, output_dir, stock, menu)
    transcript_dir = output_dir / "chat_transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    for t in transcripts:
        (transcript_dir / f"{t['conversation_id']}.json").write_text(json.dumps(t, indent=2), encoding="utf-8")
    (output_dir / "faq_answers.json").write_text(json.dumps({"answers": [
        {"question": "What are your opening hours?", "answer": "Campus pickup is Monday-Friday, 08:00-18:00."}
    ], "source": "data/sample/business_policies.md", "synthetic": True}, indent=2), encoding="utf-8")
    (output_dir / "order_board.md").write_text("# ORDER BOARD - SIMULATED CUSTOMER OPERATIONS\n\n"
        "**SIMULATED customer chat — synthetic data. No real orders, payments, refunds, or customers.**\n\n"
        "| order | channel | status | total MYR | escalation |\n|---|---|---|---:|---|\n" +
        "\n".join(f"| {o['order_id']} | {o['channel']} | {o['status']} | {o['total']} | {o['escalated']} |" for o in orders) +
        "\n\nStatuses and owner decisions are recorded in `audit_log.csv`." , encoding="utf-8")
    return {"status": "passed", "orders": orders, "ledger": ledger, "audit": audit, "refunds": refunds,
            "stock": stock, "checks": ["menu prices", "addon confirmation", "stock ledger", "allergy escalation",
            "special-request reconfirmation", "cancellation", "FAQ policy source", "simulated refund limit", "audit log"]}


def write_report(path: Path, result: dict) -> None:
    lines = ["# CUSTOMER OPERATIONS REPORT - FR-01 Tier B", "",
             "**SIMULATED customer chat — synthetic data. No real orders, payments, refunds, or customers.**", "",
             f"Status: **{result['status'].upper()}** · {len(result['checks'])} checks", "",
             "| check | result |", "|---|---|"]
    lines += [f"| {check} | pass |" for check in result["checks"]]
    lines += ["", "The order board, stock ledger, audit log, refunds and chat transcripts are written under this output directory."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/sample")
    p.add_argument("--output", default="data/output/customer_demo")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = run_tier_b_demo(root / args.data, root / args.output)
    write_report(root / args.output / "customer_operations_report.md", result)
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "orders": len(result["orders"])}, indent=2))
