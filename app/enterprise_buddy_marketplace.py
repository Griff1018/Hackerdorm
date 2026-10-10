"""FR-06 simulated marketplace seller-side processor.

Processes synthetic JSON inbox events against Section 14.3. It recomputes totals from
configured files, writes seller-side order/stock/status/fulfilment/review outputs, and
never edits data/sample or performs real payment, shipping, or platform actions.
"""
from __future__ import annotations

import csv
import html
import json
import shutil
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

TZ = timezone(timedelta(hours=8))
ORDER_COLUMNS = ["order_id", "customer_id", "channel", "items", "subtotal", "discount", "shipping",
                 "total", "status", "special_requests", "escalated", "created_at", "updated_at", "synthetic"]
LEDGER_COLUMNS = ["entry_id", "order_id", "product_id", "change", "stock_after", "timestamp"]
AUDIT_COLUMNS = ["audit_id", "action", "actor", "decision", "reason", "timestamp", "order_id"]


def now_iso():
    return datetime.now(TZ).isoformat()


def money(v):
    return f"{Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def atomic_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: row.get(c, "") for c in columns} for row in rows)


def _append_audit(audits: list[dict], action: str, decision: str, reason: str, order_id: str = ""):
    audits.append({"audit_id": f"AUD-MP-{len(audits)+1:04d}", "action": action, "actor": "marketplace_seller",
                   "decision": decision, "reason": reason, "timestamp": now_iso(), "order_id": order_id})


def load_catalog(root: Path):
    data = root / "data" / "sample"
    products = {r["product_id"]: r for r in read_csv(data / "products.csv")}
    promotions = {r["promo_id"]: r for r in read_csv(data / "promotions.csv")} if (data / "promotions.csv").exists() else {}
    return products, promotions


def load_stock(root: Path) -> dict[str, int]:
    data = root / "data" / "sample"
    output = root / "data" / "output"
    stock = {r["product_id"]: int(r["stock_on_hand"]) for r in read_csv(data / "inventory.csv")}
    for row in read_csv(output / "stock_ledger.csv"):
        stock[row["product_id"]] = stock.get(row["product_id"], 0) + int(row["change"])
    return stock


def publish_current_stock(root: Path) -> dict:
    data = root / "data" / "sample"
    output = root / "data" / "output"
    products = {r["product_id"]: r for r in read_csv(data / "products.csv")}
    stock = load_stock(root)
    existing_materials = [r for r in read_csv(output / "current_stock.csv") if r.get("material_name")]
    rows = [{"product_id": pid, "product_name": p["product_name"], "selling_price": p["selling_price"],
             "stock_available": str(stock.get(pid, "")), "as_of": now_iso(),
             "material_name": "", "material_unit": "", "material_stock_available": ""}
            for pid, p in products.items()]
    rows.extend(existing_materials)
    write_csv(output / "current_stock.csv", ["product_id", "product_name", "selling_price", "stock_available", "as_of",
                                               "material_name", "material_unit", "material_stock_available"], rows)
    return stock


def recompute(order: dict, products: dict, promotions: dict) -> tuple[Decimal, Decimal, Decimal]:
    subtotal = Decimal("0")
    for item in order.get("items", []):
        pid = item["product_id"]
        if pid not in products:
            raise ValueError(f"unknown product_id {pid}")
        qty = int(item["quantity"])
        if qty <= 0:
            raise ValueError(f"quantity must be positive for {pid}")
        subtotal += Decimal(products[pid]["selling_price"]) * qty
    discount = Decimal("0")
    promo = order.get("voucher_or_bundle") or {}
    if promo.get("promo_id"):
        if promo["promo_id"] not in promotions:
            raise ValueError("unknown promotion")
        configured = promotions[promo["promo_id"]]
        discount = max(Decimal("0"), subtotal - Decimal(configured["bundle_price"]))
    shipping = Decimal(str((order.get("shipping") or {}).get("fee", "0")))
    if shipping < 0:
        raise ValueError("shipping fee cannot be negative")
    return subtotal, discount, subtotal - discount + shipping


def _status(ext: str, status: str, history: list[dict], reason=None, label_path=None):
    history.append({"status": status, "at": now_iso()})
    return {"schema": "enterprise_buddy.marketplace_status.v1", "external_order_id": ext,
            "order_id": ext.replace("MP-", "ORD-MP-"), "status": status, "history": history,
            "tracking_no": "SIM-TRK-" + ext[-6:], "courier": "SimuExpress (simulated)",
            "label_path": label_path, "message_to_buyer": "Simulated status update only.",
            "reason": reason, "updated_at": now_iso(), "synthetic": True}


def _internal_order(order: dict, ext: str, subtotal: Decimal, discount: Decimal, total: Decimal, status: str):
    shipping = Decimal(str((order.get("shipping") or {}).get("fee", "0")))
    return {"order_id": ext.replace("MP-", "ORD-MP-"), "customer_id": order["buyer"]["buyer_id"],
            "channel": "simulated_marketplace", "items": json.dumps(order.get("items", []), sort_keys=True),
            "subtotal": money(subtotal), "discount": money(discount), "shipping": money(shipping),
            "total": money(total), "status": status, "special_requests": order.get("buyer_note", ""),
            "escalated": "yes" if any(x in order.get("buyer_note", "").lower() for x in ("allerg", "refund", "ignore")) else "no",
            "created_at": order.get("created_at", now_iso()), "updated_at": now_iso(), "synthetic": "true"}


def process_inbox(root: Path, inbox: Path | None = None) -> dict:
    data = root / "data" / "sample"
    output = root / "data" / "output"
    inbox = inbox or (root / "data" / "inbox")
    order_dir = inbox / "marketplace_orders"
    processed = inbox / "processed"
    status_dir = output / "marketplace_status"
    labels = output / "shipping_labels"
    for p in (order_dir, processed, status_dir, labels):
        p.mkdir(parents=True, exist_ok=True)
    products, promotions = load_catalog(root)
    stock = publish_current_stock(root)
    ledger = read_csv(output / "stock_ledger.csv")
    internal_orders = read_csv(output / "orders.csv")
    audits = read_csv(output / "audit_log.csv")
    results = []
    for path in sorted(order_dir.glob("MP-*.json")):
        order = read_json(path)
        ext = order.get("external_order_id", path.stem)
        history: list[dict] = []
        subtotal = discount = total = Decimal("0")
        try:
            if order.get("schema") != "enterprise_buddy.marketplace_order.v1" or order.get("synthetic") is not True:
                raise ValueError("invalid schema or synthetic flag")
            subtotal, discount, total = recompute(order, products, promotions)
            displayed = Decimal(str(order.get("displayed_total", "0")))
            if any(stock.get(i["product_id"], 0) < int(i["quantity"]) for i in order.get("items", [])):
                payload = _status(ext, "rejected_out_of_stock", history, "stock is insufficient")
                _append_audit(audits, "validate_order", "blocked", payload["reason"], ext)
                internal_orders.append(_internal_order(order, ext, subtotal, discount, total, payload["status"]))
            elif displayed != total:
                reason = f"displayed_total {money(displayed)} does not match Enterprise Buddy recomputed total {money(total)}"
                payload = _status(ext, "rejected_invalid", history, reason)
                _append_audit(audits, "validate_total", "blocked", reason, ext)
                internal_orders.append(_internal_order(order, ext, subtotal, discount, total, payload["status"]))
            else:
                payload = _status(ext, "received", history)
                payload = _status(ext, "confirmed", history)
                payload = _status(ext, "packing", history)
                picks = []
                for item in order["items"]:
                    pid, qty = item["product_id"], int(item["quantity"])
                    stock[pid] -= qty
                    picks.append(f"{pid} x {qty}")
                    ledger.append({"entry_id": f"LED-MP-{len(ledger)+1:04d}", "order_id": payload["order_id"],
                                   "product_id": pid, "change": str(-qty), "stock_after": str(stock[pid]), "timestamp": now_iso()})
                _append_audit(audits, "deduct_stock", "auto", "validated marketplace order written to stock ledger", ext)
                (output / f"pick_pack_{ext}.md").write_text("# PICK/PACK LIST - SIMULATED\n\n" +
                    "\n".join(f"- {x}" for x in picks), encoding="utf-8")
                label = labels / f"{ext}.html"
                label.write_text("<!doctype html><html><body><h1>SIMULATED - NOT A REAL SHIPMENT</h1>"
                                 f"<p>Buyer: {html.escape(order['buyer']['display_name'])}</p>"
                                 f"<p>Tracking: SIM-TRK-{html.escape(ext[-6:])}</p><p>Courier: SimuExpress (simulated)</p>"
                                 "</body></html>", encoding="utf-8")
                payload = _status(ext, "shipped", history, label_path=str(label.relative_to(root)).replace("\\", "/"))
                _append_audit(audits, "ship_order", "simulated", "owner-side fulfilment and label only", ext)
                internal_orders.append(_internal_order(order, ext, subtotal, discount, total, payload["status"]))
            atomic_json(status_dir / f"{ext}.json", payload)
            results.append({**payload, "recomputed_total": money(total), "subtotal": money(subtotal), "discount": money(discount)})
        except (ValueError, KeyError, TypeError) as exc:
            payload = _status(ext, "rejected_invalid", history, str(exc))
            _append_audit(audits, "validate_order", "blocked", str(exc), ext)
            atomic_json(status_dir / f"{ext}.json", payload)
            results.append(payload)
        finally:
            shutil.move(str(path), str(processed / path.name))
    process_events(root, inbox, stock, ledger, audits)
    write_csv(output / "orders.csv", ORDER_COLUMNS, internal_orders)
    write_csv(output / "stock_ledger.csv", LEDGER_COLUMNS, ledger)
    write_csv(output / "audit_log.csv", AUDIT_COLUMNS, audits)
    publish_current_stock(root)
    write_review_summary(root)
    return {"status": "passed", "processed": results, "current_stock": stock}


def process_events(root: Path, inbox: Path, stock: dict, ledger: list[dict], audits: list[dict]):
    output = root / "data" / "output"
    status_dir = output / "marketplace_status"
    for path in sorted((inbox / "marketplace_orders").glob("EV-*.json")):
        event = read_json(path)
        ext = event.get("external_order_id", "")
        status_path = status_dir / f"{ext}.json"
        if not status_path.exists():
            shutil.move(str(path), str(inbox / "processed" / path.name)); continue
        payload = read_json(status_path)
        current = payload["status"]
        event_name = event.get("event")
        history = payload.get("history", [])
        if event_name == "delivered" and current == "shipped":
            payload = _status(ext, "delivered", history, "simulated courier event", payload.get("label_path"))
        elif event_name == "buyer_confirmed_receipt" and current == "delivered":
            payload = _status(ext, "completed", history, "synthetic buyer confirmation", payload.get("label_path"))
        elif event_name == "buyer_cancel_request":
            if current in {"received", "confirmed", "packing"}:
                payload = _status(ext, "cancelled", history, "cancelled before shipment; ledger reversal required")
                _append_audit(audits, "cancel_order", "auto", payload["reason"], ext)
            else:
                payload = _status(ext, "escalated_to_owner", history, "cancellation after shipment requires owner review")
                _append_audit(audits, "cancel_order", "needs owner approval", payload["reason"], ext)
        elif event_name == "return_request":
            payload = _status(ext, "escalated_to_owner", history, "return request requires owner review")
            _append_audit(audits, "return_request", "needs owner approval", payload["reason"], ext)
        atomic_json(status_path, payload)
        shutil.move(str(path), str(inbox / "processed" / path.name))


def write_review_summary(root: Path):
    reviews_dir = root / "data" / "inbox" / "marketplace_reviews"
    out = root / "data" / "output" / "review_summary.md"
    statuses = {p.stem: read_json(p) for p in (root / "data" / "output" / "marketplace_status").glob("*.json")}
    reviews = []
    invalid = []
    for p in sorted(reviews_dir.glob("*.json")) if reviews_dir.exists() else []:
        r = read_json(p)
        ext = r.get("external_order_id", "")
        if r.get("schema") != "enterprise_buddy.marketplace_review.v1" or r.get("synthetic") is not True or statuses.get(ext, {}).get("status") != "completed":
            invalid.append(r.get("review_id", p.stem)); continue
        reviews.append(r)
    counts: dict[str, int] = {}
    ratings: dict[str, list[int]] = {}
    rows = []
    for r in reviews:
        text = str(r.get("text", ""))
        low = text.lower()
        theme = "allergy" if ("allerg" in low or "peanut" in low) else ("packaging" if "pack" in low else "general")
        counts[theme] = counts.get(theme, 0) + 1
        ratings.setdefault(r.get("product_id", ""), []).append(int(r.get("rating", 0)))
        escalation = "P1 owner escalation" if theme == "allergy" else ("action queue" if theme == "packaging" else "none")
        if "ignore previous instructions" in low:
            escalation = "adversarial input flagged; ignored"
        rows.append(f"| {r.get('review_id','')} | {r.get('product_id','')} | {r.get('rating','')} | {theme} | {escalation} | {text.replace('|','\\|')} |")
    summary = ["# REVIEW SUMMARY - SIMULATED", "", "**Synthetic reviews — demonstration only. Draft replies are unsent.**", "",
               f"Reviews accepted: {len(reviews)} · invalid/not completed: {len(invalid)}", "",
               "## Product rating summary", "", "| product | count | average |", "|---|---:|---:|"]
    for pid, values in ratings.items():
        summary.append(f"| {pid} | {len(values)} | {sum(values)/len(values):.2f} |" )
    summary += ["", "## Themes", "", "| theme | count |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in counts.items()]
    summary += ["", "## Evidence quotes", "", "| review | product | rating | theme/action | exact quote |", "|---|---|---:|---|---|"] + rows
    summary += ["", "## Owner actions", "", "- Allergy mentions escalate as P1; no food-safety guarantee is made.", "- Packaging complaints become Operations action-queue items.", "- Adversarial review text is data, not instructions; it is ignored and flagged.", "- Draft replies are unsent and require owner approval."]
    out.write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    args = p.parse_args()
    result = process_inbox(Path(args.root).resolve())
    print(json.dumps({"status": result["status"], "processed": len(result["processed"])}, indent=2))
