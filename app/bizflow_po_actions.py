"""Owner-controlled purchase-order state and received-stock ledger.

This module never contacts a supplier or moves money. `mark_paid` records the owner's
simulated decision; `mark_received` appends raw-material stock to a separate ledger and
updates the derived current-stock view without editing data/sample/inventory.csv.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from bizflow_supplier import parse_amount_unit

TZ = timezone(timedelta(hours=8))
LEDGER_COLUMNS = ["entry_id", "po_id", "material_name", "quantity", "unit", "change", "timestamp"]


def now_iso():
    return datetime.now(TZ).isoformat()


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in rows)


def _find(pos: list[dict], po_id: str) -> dict:
    for po in pos:
        if po.get("order_id") == po_id:
            return po
    raise ValueError(f"purchase order not found: {po_id}")


def _save_pos(output: Path, pos: list[dict], event: dict):
    _write_json(output / "purchase_orders.json", {"purchase_orders": pos,
                                                     "not_ordered": _read_json(output / "purchase_orders.json", {}).get("not_ordered", []),
                                                     "last_event": event})


def mark_paid(output_dir: Path, po_id: str) -> dict:
    path = output_dir / "purchase_orders.json"
    doc = _read_json(path, {})
    pos = doc.get("purchase_orders", [])
    po = _find(pos, po_id)
    if po.get("over_budget"):
        raise ValueError("over-budget PO cannot be marked paid automatically")
    if po.get("status") not in ("draft", "approved", "ready_to_pay"):
        raise ValueError(f"PO status {po.get('status')} cannot be marked paid")
    po["status"] = "paid"
    po["paid_at"] = now_iso()
    po.setdefault("status_history", []).append({"status": "paid", "at": po["paid_at"], "simulated": True})
    event = {"action": "mark_paid", "po_id": po_id, "at": po["paid_at"], "simulated": True}
    _save_pos(output_dir, pos, event)
    return po


def _material_ledger(output_dir: Path):
    return _read_csv(output_dir / "purchase_stock_ledger.csv")


def mark_received(root: Path, po_id: str) -> dict:
    output = root / "data" / "output"
    path = output / "purchase_orders.json"
    doc = _read_json(path, {})
    pos = doc.get("purchase_orders", [])
    po = _find(pos, po_id)
    if po.get("status") != "paid":
        raise ValueError("PO must be marked paid before it can be received")
    ledger = _material_ledger(output)
    received_at = now_iso()
    for line in po.get("lines", []):
        parsed = parse_amount_unit(line.get("pack_size", ""))
        if parsed and parsed[2] is not None:
            qty = Decimal(line.get("packs", "1")) * parsed[2]
            unit = parsed[1]
        else:
            qty = Decimal(line.get("packs", "1"))
            unit = "pack"
        ledger.append({"entry_id": f"MAT-{len(ledger)+1:04d}", "po_id": po_id,
                       "material_name": line.get("material", ""), "quantity": f"{qty:.4f}",
                       "unit": unit, "change": f"{qty:.4f}", "timestamp": received_at})
    _write_csv(output / "purchase_stock_ledger.csv", LEDGER_COLUMNS, ledger)
    po["status"] = "received"
    po["received_at"] = received_at
    po.setdefault("status_history", []).append({"status": "received", "at": received_at, "simulated": True})
    event = {"action": "mark_received", "po_id": po_id, "at": received_at, "simulated": True}
    _save_pos(output, pos, event)
    update_current_stock(root)
    return po


def update_current_stock(root: Path) -> Path:
    """Preserve product rows and append derived raw-material rows to current_stock.csv."""
    output = root / "data" / "output"
    current = _read_csv(output / "current_stock.csv")
    ledger = _material_ledger(output)
    totals: dict[tuple[str, str], Decimal] = {}
    for r in ledger:
        key = (r.get("material_name", ""), r.get("unit", ""))
        totals[key] = totals.get(key, Decimal("0")) + Decimal(r.get("change", "0"))
    columns = ["product_id", "product_name", "selling_price", "stock_available", "as_of",
               "material_name", "material_unit", "material_stock_available"]
    rows = []
    for r in current:
        rows.append({**r, "material_name": "", "material_unit": "", "material_stock_available": ""})
    for (material, unit), qty in sorted(totals.items()):
        rows.append({"product_id": "", "product_name": "", "selling_price": "", "stock_available": "",
                     "as_of": now_iso(), "material_name": material, "material_unit": unit,
                     "material_stock_available": f"{qty:.4f}"})
    _write_csv(output / "current_stock.csv", columns, rows)
    return output / "current_stock.csv"


def list_pos(output_dir: Path) -> list[dict]:
    return _read_json(output_dir / "purchase_orders.json", {}).get("purchase_orders", [])
