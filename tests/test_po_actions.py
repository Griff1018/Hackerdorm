#!/usr/bin/env python3
"""Sprint 3C purchase receive loop tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from bizflow_po_actions import mark_paid, mark_received  # noqa: E402


class PurchaseReceiveLoop(unittest.TestCase):
    def test_paid_po_received_updates_ledger_and_derived_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "data").mkdir(parents=True)
            shutil.copytree(ROOT / "data" / "sample", root / "data" / "sample")
            output = root / "data" / "output"
            output.mkdir()
            (output / "current_stock.csv").write_text(
                "product_id,product_name,selling_price,stock_available,as_of\nP001,Cookies,6.00,18,now\n",
                encoding="utf-8")
            (output / "purchase_orders.json").write_text(json.dumps({"purchase_orders": [{
                "order_id": "PO-TEST-001", "supplier_name": "Synthetic Supplier", "status": "draft",
                "over_budget": False, "lines": [{"material": "Flour", "packs": "2", "pack_size": "25 kg", "line_total": "100.00"}]
            }], "not_ordered": []}), encoding="utf-8")
            inventory_before = (root / "data" / "sample" / "inventory.csv").read_bytes()
            mark_paid(output, "PO-TEST-001")
            po = mark_received(root, "PO-TEST-001")
            self.assertEqual(po["status"], "received")
            self.assertEqual((root / "data" / "sample" / "inventory.csv").read_bytes(), inventory_before)
            ledger = (output / "purchase_stock_ledger.csv").read_text(encoding="utf-8")
            self.assertIn("Flour", ledger)
            self.assertIn("50000.0000", ledger)
            current = (output / "current_stock.csv").read_text(encoding="utf-8")
            self.assertIn("Flour", current)
            self.assertIn("50000.0000", current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
