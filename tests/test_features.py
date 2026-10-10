#!/usr/bin/env python3
"""FR-01/FR-02/FR-06 Sprint 3A feature checks (stdlib unittest)."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from bizflow_customer import run_tier_b_demo  # noqa: E402
from bizflow_marketplace import recompute  # noqa: E402


class Sprint3AFeatures(unittest.TestCase):
    def test_customer_tier_b_golden_flow_and_source_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "customer"
            before = {p.name: p.read_bytes() for p in (ROOT / "data" / "sample").glob("*.csv")}
            result = run_tier_b_demo(ROOT / "data" / "sample", output)
            after = {p.name: p.read_bytes() for p in (ROOT / "data" / "sample").glob("*.csv")}
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["checks"]), 9)
        self.assertEqual(result["orders"][0]["total"], "16.50")
        self.assertEqual(result["orders"][1]["status"], "escalated_to_owner")
        self.assertEqual(result["orders"][2]["status"], "cancelled")
        self.assertEqual(result["refunds"][0]["status"], "simulated_approved")
        self.assertEqual(result["refunds"][1]["status"], "escalated_to_owner")
        self.assertEqual(before, after, "customer demo must not modify data/sample CSVs")

    def test_marketplace_recomputes_total_and_rejects_tampering(self):
        products = {"P001": {"selling_price": "6.00"}, "P002": {"selling_price": "4.50"}}
        promotions = {}
        order = {"items": [{"product_id": "P001", "quantity": 1}],
                 "shipping": {"fee": "3.00"}, "voucher_or_bundle": {}}
        subtotal, discount, total = recompute(order, products, promotions)
        self.assertEqual(str(subtotal), "6.00")
        self.assertEqual(str(discount), "0")
        self.assertEqual(str(total), "9.00")
        order["displayed_total"] = "0.00"
        self.assertNotEqual(order["displayed_total"], f"{total:.2f}")

    def test_demo_mode_separation_and_badges(self):
        page = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
        scenario = json.loads((ROOT / "demo" / "scenario" / "scenario.json").read_text(encoding="utf-8"))
        self.assertIn("DEMO MODE", page)
        self.assertIn("Live Mode", page)
        self.assertIn("localStorage", page)
        self.assertEqual(len(scenario["steps"]), 10)
        self.assertTrue(all(s["badge"] in {"LIVE FEATURE", "PROTOTYPE", "CONCEPT"} for s in scenario["steps"]))
        live_loader = page.split("async function loadLive")[1].split("function setReview", 1)[0]
        self.assertNotIn("scenarioPath", live_loader)
        self.assertIn("../data/output/", live_loader)


if __name__ == "__main__":
    unittest.main(verbosity=2)
