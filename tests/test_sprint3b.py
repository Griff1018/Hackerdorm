#!/usr/bin/env python3
"""Sprint 3B checks: FR-06 seller side, FR-03 campaign, FR-04 People, FR-05 feed preview."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from enterprise_buddy_campaign_people import build_campaign, build_job_ad  # noqa: E402
from enterprise_buddy_marketplace import process_inbox  # noqa: E402


class Sprint3B(unittest.TestCase):
    def _fixture_root(self, tmp: str) -> Path:
        root = Path(tmp) / "project"
        (root / "data").mkdir(parents=True)
        shutil.copytree(ROOT / "data" / "sample", root / "data" / "sample")
        (root / "data" / "output").mkdir(parents=True)
        return root

    def test_marketplace_full_seller_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture_root(tmp)
            order_dir = root / "data" / "inbox" / "marketplace_orders"
            reviews = root / "data" / "inbox" / "marketplace_reviews"
            order_dir.mkdir(parents=True)
            reviews.mkdir(parents=True)
            valid = {
                "schema": "enterprise_buddy.marketplace_order.v1", "external_order_id": "MP-TEST-0001",
                "channel": "simulated_marketplace", "created_at": "2026-10-10T15:00:00+08:00",
                "buyer": {"buyer_id": "B-1", "display_name": "Synthetic Buyer", "delivery_area": "Campus"},
                "items": [{"product_id": "P001", "product_name": "Cookies", "quantity": 1, "unit_price": "6.00"}],
                "voucher_or_bundle": {"promo_id": "", "discount": "0.00"},
                "shipping": {"method": "standard", "fee": "3.00"},
                "payment": {"method_type": "e-wallet", "status": "simulated_paid"},
                "buyer_note": "synthetic order", "displayed_total": "9.00", "synthetic": True,
            }
            tampered = dict(valid, external_order_id="MP-TEST-0002", displayed_total="0.00")
            out_stock = dict(valid, external_order_id="MP-TEST-0003", displayed_total="5997.00",
                             items=[dict(valid["items"][0], quantity=999)])
            for order in (valid, tampered, out_stock):
                (order_dir / f"{order['external_order_id']}.json").write_text(json.dumps(order), encoding="utf-8")
            (order_dir / "EV-MP-TEST-0001-delivered.json").write_text(json.dumps({
                "schema": "enterprise_buddy.marketplace_event.v1", "external_order_id": "MP-TEST-0001",
                "event": "delivered", "synthetic": True}), encoding="utf-8")
            (order_dir / "EV-MP-TEST-0001-receipt.json").write_text(json.dumps({
                "schema": "enterprise_buddy.marketplace_event.v1", "external_order_id": "MP-TEST-0001",
                "event": "buyer_confirmed_receipt", "synthetic": True}), encoding="utf-8")
            (reviews / "RV-TEST-0001.json").write_text(json.dumps({
                "schema": "enterprise_buddy.marketplace_review.v1", "review_id": "RV-TEST-0001",
                "external_order_id": "MP-TEST-0001", "product_id": "P001", "rating": 4,
                "text": "Packaging was neat.", "synthetic": True}), encoding="utf-8")
            (reviews / "RV-TEST-0002.json").write_text(json.dumps({
                "schema": "enterprise_buddy.marketplace_review.v1", "review_id": "RV-TEST-0002",
                "external_order_id": "MP-TEST-0001", "product_id": "P001", "rating": 2,
                "text": "I have a peanut allergy; please escalate.", "synthetic": True}), encoding="utf-8")
            result = process_inbox(root)
            statuses = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                        for p in (root / "data" / "output" / "marketplace_status").glob("*.json")}
            self.assertEqual(result["status"], "passed")
            self.assertEqual(statuses["MP-TEST-0001"]["status"], "completed")
            self.assertEqual([x["status"] for x in statuses["MP-TEST-0001"]["history"]],
                             ["received", "confirmed", "packing", "shipped", "delivered", "completed"])
            self.assertEqual(statuses["MP-TEST-0002"]["status"], "rejected_invalid")
            self.assertIn("recomputed total", statuses["MP-TEST-0002"]["reason"])
            self.assertEqual(statuses["MP-TEST-0003"]["status"], "rejected_out_of_stock")
            self.assertTrue((root / "data" / "output" / "shipping_labels" / "MP-TEST-0001.html").exists())
            self.assertIn("P1 owner escalation", (root / "data" / "output" / "review_summary.md").read_text(encoding="utf-8"))
            self.assertIn("Packaging was neat.", (root / "data" / "output" / "review_summary.md").read_text(encoding="utf-8"))
            self.assertTrue((root / "data" / "inbox" / "processed" / "MP-TEST-0001.json").exists())

    def test_campaign_people_and_social_preview_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            campaign = build_campaign(ROOT, output)
            people = build_job_ad(ROOT, output)
            self.assertEqual(campaign["posts"], 5)
            self.assertTrue(campaign["draft_only"])
            feed = json.loads((output / "social_feed_preview.json").read_text(encoding="utf-8"))
            self.assertTrue(feed["synthetic"])
            self.assertEqual(len(feed["posts"]), 5)
            ad = (output / "job_ad_part_time_campus_snack_assistant.md").read_text(encoding="utf-8")
            self.assertIn("12.00-15.00 per hour", ad)
            self.assertIn("confirm compliance", ad)
            self.assertIn("DRAFT ONLY", ad)
            kit = (output / "hiring_kit.md").read_text(encoding="utf-8")
            self.assertIn("No candidate screening", kit)

    def test_social_feed_is_generic_and_labelled(self):
        page = (ROOT / "demo" / "social_feed.html").read_text(encoding="utf-8")
        self.assertIn("SIMULATED — not a real platform", page)
        self.assertIn("SYNTHETIC DATA", page)
        for prohibited in ("Shopee", "Lazada", "TikTok Shop", "Instagram logo"):
            self.assertNotIn(prohibited, page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
