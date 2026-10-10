#!/usr/bin/env python3
"""Enterprise Buddy automated tests (Python stdlib unittest - the runner available in this environment).

Golden values come from tests/fixtures/expected_*.json, produced BEFORE the engine existed by
tests/compute_expected_standalone.py and hand-checked in tests/EXPECTED_RESULTS.md.
Run:  python tests/test_engine.py      (add -v for detail)
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from enterprise_buddy_core import Config, calculate, validate  # noqa: E402
from enterprise_buddy_supplier import delivery_score, moq_score, reliability_score, score_material  # noqa: E402
from enterprise_buddy_outputs import build_actions, build_po  # noqa: E402
from enterprise_buddy_profile import FORBIDDEN_FIELDS, sanitise_profile  # noqa: E402
from enterprise_buddy_purchase import build_purchase_plan  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / f"expected_{name}.json").read_text(encoding="utf-8"))


def run_dataset(name: str, data_dir: Path):
    cfg = Config(data_dir=data_dir, output_dir=ROOT / "data" / "output")
    v = validate(data_dir, cfg)
    calc = calculate(v, cfg)
    return cfg, v, calc


def issue_key(i) -> tuple:
    return (i.file, i.row_or_id, i.issue, i.severity)


class GoldenCalculations(unittest.TestCase):
    """Section 9.2 gate: every golden calculation matches its pre-recorded expected result."""

    def _check(self, name: str, data_dir: Path):
        exp = load(name)
        _, v, calc = run_dataset(name, data_dir)

        self.assertEqual(calc["metrics"], exp["metrics"], f"{name}: headline metrics mismatch")
        self.assertEqual(calc["per_product"], exp["per_product"], f"{name}: per-product mismatch")

        for pid, expected_row in exp["stock_and_replenishment"].items():
            actual = calc["stock_and_replenishment"][pid]
            for key in ("window_units", "average_daily_units", "stock_on_hand", "days_of_stock",
                        "target_stock_units", "replenishment_units", "coverage_note"):
                self.assertEqual(actual.get(key), expected_row.get(key),
                                 f"{name}/{pid}: {key} mismatch (actual {actual.get(key)!r} vs expected {expected_row.get(key)!r})")

        self.assertEqual(calc["eligible_lines"], exp["sales_processing"]["eligible_lines"],
                         f"{name}: eligible line count mismatch")

        expected_issues = {(i["file"], i["row_or_id"], i["issue"], i["severity"])
                           for i in exp["data_quality_issues"]}
        actual_issues = {issue_key(i) for i in v.issues}
        self.assertEqual(actual_issues, expected_issues,
                         f"{name}: issue set mismatch\nmissing={expected_issues - actual_issues}\n"
                         f"unexpected={actual_issues - expected_issues}")

    def test_sample_dataset(self):
        self._check("sample", ROOT / "data" / "sample")

    def test_golden_mini_fixture(self):
        self._check("golden_mini", FIX / "golden_mini")

    def test_invalid_data_fixture(self):
        self._check("invalid_data", FIX / "invalid_data")


class SeededDefectDetection(unittest.TestCase):
    """G.5 detection metric: 24 seeded defects (4 demo + 20 invalid fixture) must all be caught."""

    def test_demo_dataset_detects_all_four(self):
        _, v, _ = run_dataset("sample", ROOT / "data" / "sample")
        found = {issue_key(i) for i in v.issues}
        expected = {
            ("sales.csv", "S-0011", "duplicate line_id", "error"),
            ("sales.csv", "S-0059", "unknown product_id 'P999'", "error"),
            ("inventory.csv", "P003", "stock count is 25 days old (threshold 7)", "warning"),
        }
        self.assertTrue(expected.issubset(found), f"missing: {expected - found}")
        promo = [i for i in v.issues if i.issue_id == "WARN" and i.file == "sales.csv"]
        self.assertEqual(len(promo), 1, "the S13 promo-price warning was not detected exactly once")

    def test_invalid_fixture_detects_all_twenty(self):
        _, v, _ = run_dataset("invalid_data", FIX / "invalid_data")
        found = {issue_key(i) for i in v.issues}
        targets = {
            ("sales.csv", "L12", "duplicate line_id", "error"),
            ("sales.csv", "L02", "quantity blank or non-integer", "error"),
            ("sales.csv", "L03", "quantity blank or non-integer", "error"),
            ("sales.csv", "L04", "quantity not > 0 (-3)", "error"),
            ("sales.csv", "L05", "discount greater than gross line value", "error"),
            ("sales.csv", "L06", "unit_price/discount missing or negative", "error"),
            ("sales.csv", "L07", "invalid date '2026-09-31'", "error"),
            ("sales.csv", "L08", "unrecognised status 'shipped'", "error"),
            ("sales.csv", "L09", "unknown product_id 'P999'", "error"),
            ("sales.csv", "L10", "unit_price/discount missing or negative", "error"),
            ("inventory.csv", "P202", "duplicate current inventory record", "error"),
            ("inventory.csv", "P205", "unknown product_id", "error"),
            ("inventory.csv", "P206", "stock_on_hand invalid", "error"),
            ("inventory.csv", "P204", "invalid last_count_date", "error"),
            ("inventory.csv", "P203", "stock count is 22 days old (threshold 7)", "warning"),
            ("expenses.csv", "X-02", "invalid date '2026-09-31'", "error"),
            ("expenses.csv", "X-03", "unrecognised paid_status 'pending'", "error"),
            ("expenses.csv", "X-04", "blank category", "error"),
            ("expenses.csv", "X-05", "blank description", "warning"),
            ("products.csv", "P204", "pack_size invalid", "error"),
        }
        self.assertTrue(targets.issubset(found), f"missing detections: {targets - found}")

    def test_valid_rows_are_not_reported_as_errors(self):
        """L13 (outside period), L14/L15 (cancelled/refunded) and L11 (discount = line value) are not errors."""
        _, v, calc = run_dataset("invalid_data", FIX / "invalid_data")
        errors = {(i.file, i.row_or_id) for i in v.issues if i.severity == "error"}
        for clean in ("L11", "L13", "L14", "L15"):
            self.assertNotIn(("sales.csv", clean), errors, f"{clean} must not be reported as an error")
        self.assertEqual(calc["eligible_lines"], 2)


class MarketingHandoff(unittest.TestCase):
    def test_p002_and_p005_trigger_marketing(self):
        _, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        stock = calc["stock_and_replenishment"]
        # P002 triggers via the over-stock branch of the G.9 rule
        self.assertTrue(stock["P002"]["marketing_trigger"], "P002 should trigger the marketing handoff")
        self.assertIn("13.86", stock["P002"]["marketing_reason"])
        # P005 triggers via the zero-eligible-sales branch of the G.9 rule
        self.assertTrue(stock["P005"]["marketing_trigger"],
                        "P005 has stock but zero eligible sales in the window - it must qualify (G.9)")
        self.assertIn("zero eligible sales", stock["P005"]["marketing_reason"])
        # only P002 and P005 qualify; the others do not
        for pid in ("P001", "P003", "P004"):
            self.assertFalse(stock[pid]["marketing_trigger"], f"{pid} should not trigger marketing")

    def test_g9_rule_zero_sales_branch(self):
        _, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        p5 = calc["stock_and_replenishment"]["P005"]
        self.assertEqual(p5["window_units"], 0)
        self.assertEqual(p5["stock_on_hand"], 34)
        self.assertTrue(p5["marketing_trigger"])

    def test_p005_stock_is_usable_and_zero_demand_is_visible(self):
        _, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        p5 = calc["stock_and_replenishment"]["P005"]
        self.assertEqual(p5["stock_on_hand"], 34, "P005 stock must be usable (no duplicate record)")
        self.assertEqual(p5["window_units"], 0)
        self.assertIn("zero eligible sales", p5["coverage_note"])


class SupplierScoring(unittest.TestCase):
    """G.11 - the hand-worked examples in tests/EXPECTED_RESULTS.md section D."""

    def test_full_tier_chocolate_chips(self):
        rows = [
            {"supplier_name": "BakeMart Malaysia", "comparable_price": "28.00", "minimum_order": "5 kg",
             "delivery_or_lead_time": "2 days", "seller_type": "official_shop",
             "listing_updated_within_90d": "yes", "location": "Malaysia"},
            {"supplier_name": "Cocoa Supply Co", "comparable_price": "33.00", "minimum_order": "20 kg",
             "delivery_or_lead_time": "4 days", "seller_type": "rated_seller",
             "listing_updated_within_90d": "yes", "location": "Malaysia"},
            {"supplier_name": "GlobalBake", "comparable_price": "30.50", "minimum_order": "25 kg",
             "delivery_or_lead_time": "12 days", "seller_type": "official_shop",
             "listing_updated_within_90d": "no", "location": "Overseas"},
        ]
        scored = score_material(rows, "full", Decimal("9360"), Decimal("30100"), "g")
        self.assertEqual(scored[0]["supplier_name"], "BakeMart Malaysia")
        self.assertEqual(scored[0]["score"], "100.00")
        self.assertEqual(scored[1]["score"], "78.94")
        self.assertEqual(scored[2]["score"], "54.72")
        self.assertEqual([r["rank"] for r in scored], [1, 2, 3])
        self.assertTrue(all(r["recommended"] == "yes" for r in scored))

    def test_light_tier_sugar(self):
        rows = [
            {"supplier_name": "Pasar Bulk", "comparable_price": "3.20", "seller_type": "official_shop",
             "listing_updated_within_90d": "yes", "location": "Malaysia"},
            {"supplier_name": "Kedai Borong", "comparable_price": "3.60", "seller_type": "rated_seller",
             "listing_updated_within_90d": "yes", "location": "Malaysia"},
            {"supplier_name": "Unbranded", "comparable_price": "4.00", "seller_type": "not_stated",
             "listing_updated_within_90d": "not_stated", "location": "Malaysia"},
        ]
        scored = score_material(rows, "light")
        self.assertEqual(scored[0]["score"], "65.00")
        self.assertEqual(scored[1]["score"], "60.56")
        self.assertEqual(scored[2]["score"], "42.00")

    def test_components(self):
        self.assertEqual(delivery_score("2 days"), 20)
        self.assertEqual(delivery_score("4 days"), 12)
        self.assertEqual(delivery_score("9 days"), 6)
        self.assertEqual(delivery_score("12 days"), 0)
        self.assertEqual(delivery_score(""), 0)
        self.assertEqual(moq_score("5 kg", Decimal("9360"), Decimal("30100"), "g"), 15)
        self.assertEqual(moq_score("20 kg", Decimal("9360"), Decimal("30100"), "g"), 8)
        self.assertEqual(moq_score("200 kg", Decimal("9360"), Decimal("30100"), "g"), 0)
        self.assertEqual(moq_score("", Decimal("9360"), Decimal("30100"), "g"), 0)
        self.assertEqual(reliability_score("official_shop", "yes"), 15)
        self.assertEqual(reliability_score("official_shop", "no"), 10)
        self.assertEqual(reliability_score("not_stated", "not_stated"), 0)

    def test_missing_price_is_not_scored(self):
        rows = [{"supplier_name": "No Price Listed", "comparable_price": "", "location": "Malaysia"}]
        scored = score_material(rows, "light")
        self.assertIsNone(scored[0]["score"], "an unpriced listing must not be scored")
        self.assertIn("not comparable", scored[0]["score_breakdown"])

    def test_unpriced_rows_are_never_recommended(self):
        """Regression: an unpriced row must rank last and must not be marked recommended.

        Marking an unpriced supplier 'recommended' would imply a price comparison that was
        never made, and would let a material with no usable source look researched.
        """
        rows = [
            {"supplier_name": "Quote Only Co", "comparable_price": "", "location": "Malaysia",
             "seller_type": "official_shop", "notes": "no price published"},
            {"supplier_name": "Priced Co", "comparable_price": "10.00", "location": "Malaysia",
             "seller_type": "official_shop", "notes": ""},
        ]
        scored = score_material(rows, "light")
        self.assertEqual(scored[0]["supplier_name"], "Priced Co")
        self.assertEqual(scored[0]["recommended"], "yes")
        self.assertEqual(scored[1]["supplier_name"], "Quote Only Co")
        self.assertIsNone(scored[1]["score"])
        self.assertEqual(scored[1]["recommended"], "no")

    def test_material_with_no_priced_supplier_has_no_recommendation(self):
        rows = [{"supplier_name": "Quote Only Co", "comparable_price": "", "location": "Malaysia"}]
        scored = score_material(rows, "full")
        self.assertTrue(all(r["recommended"] == "no" for r in scored),
                        "a material with no comparable price must not look researched")

    def test_unavailable_listing_is_never_recommended(self):
        rows = [
            {"material_name": "Chicken filling", "supplier_name": "Inactive Supplier",
             "comparable_price": "16.80", "available": "no", "material_match": "yes",
             "notes": "supplier not active"},
            {"material_name": "Chicken filling", "supplier_name": "Active Supplier",
             "comparable_price": "18.00", "available": "yes", "material_match": "yes", "notes": ""},
        ]
        scored = score_material(rows, "full")
        inactive = next(r for r in scored if r["supplier_name"] == "Inactive Supplier")
        active = next(r for r in scored if r["supplier_name"] == "Active Supplier")
        self.assertEqual(inactive["recommended"], "no")
        self.assertIn("unavailable", inactive["notes"].lower())
        self.assertEqual(active["recommended"], "yes")

    def test_substitute_is_not_recommended(self):
        rows = [
            {"material_name": "Butter", "supplier_name": "Spread Co", "comparable_price": "20.00",
             "available": "yes", "material_match": "no", "notes": "blended spread, not dairy butter"},
            {"material_name": "Butter", "supplier_name": "Dairy Co", "comparable_price": "55.00",
             "available": "yes", "material_match": "yes", "notes": "block butter"},
        ]
        scored = score_material(rows, "full")
        substitute = next(r for r in scored if r["supplier_name"] == "Spread Co")
        exact = next(r for r in scored if r["supplier_name"] == "Dairy Co")
        self.assertEqual(substitute["recommended"], "no")
        self.assertIn("substitute", substitute["notes"].lower())
        self.assertEqual(exact["recommended"], "yes")

    def test_over_budget_po_does_not_reduce_budget_for_later_po(self):
        cfg = Config(data_dir=ROOT / "data" / "sample", output_dir=ROOT / "data" / "output")
        profile = {"purchasing_budget": "100.00", "purchasing_budget_used": "0.00"}
        scored = [
            {"material_name": "A", "supplier_name": "A Supplier", "score": "60.00", "recommended": "yes",
             "available": "yes", "material_match": "yes", "price_unit": "1 kg", "listed_price": "60.00"},
            {"material_name": "B", "supplier_name": "B Supplier", "score": "60.00", "recommended": "yes",
             "available": "yes", "material_match": "yes", "price_unit": "1 kg", "listed_price": "60.00"},
            {"material_name": "C", "supplier_name": "C Supplier", "score": "40.00", "recommended": "yes",
             "available": "yes", "material_match": "yes", "price_unit": "1 kg", "listed_price": "40.00"},
        ]
        pos, skipped = build_purchase_plan(scored,
            {"A": Decimal("1"), "B": Decimal("1"), "C": Decimal("1")}, cfg, profile)
        by_supplier = {p["supplier_name"]: p for p in pos}
        self.assertFalse(by_supplier["A Supplier"]["over_budget"])
        self.assertTrue(by_supplier["B Supplier"]["over_budget"])
        self.assertFalse(by_supplier["C Supplier"]["over_budget"],
                         "the flagged/unapproved B PO must not consume purchasing budget")
        self.assertEqual(by_supplier["C Supplier"]["budget_remaining_after_this"], "40.00")
        self.assertFalse(skipped)


class ActionsAndSafety(unittest.TestCase):
    def test_every_action_has_evidence_and_status(self):
        cfg, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        actions = build_actions(v, calc, cfg)
        self.assertTrue(actions)
        for a in actions:
            self.assertTrue(a["evidence_refs"], f"{a['action_id']} has no evidence")
            self.assertTrue(a["metric_values"], f"{a['action_id']} has no metric values")
            self.assertIn(a["priority"], ("P1", "P2", "P3", "INFO"))
            self.assertEqual(a["status"], "proposed")

    def test_replenishment_and_recount_actions_exist(self):
        cfg, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        titles = " ".join(a["title"] for a in build_actions(v, calc, cfg))
        self.assertIn("Reorder Chocolate Chip Cookies", titles)
        self.assertIn("Reorder Spicy Chicken Bun", titles)
        self.assertIn("Recount stock for Banana Muffin", titles)

    def test_no_replenishment_is_computed_from_a_stale_count(self):
        cfg, v, calc = run_dataset("sample", ROOT / "data" / "sample")
        p3 = calc["stock_and_replenishment"]["P003"]
        self.assertIsNone(p3["replenishment_units"])
        self.assertIn("stale", p3["replenishment_note"])

    def test_po_budget_check(self):
        cfg = Config(data_dir=ROOT / "data" / "sample", output_dir=ROOT / "data" / "output")
        profile = {"monthly_budget": "1500.00", "purchasing_budget": "1000.00",
                   "preferred_payment_type": "bank transfer"}
        lines = [{"material": "Flour", "quantity": 24, "pack_size": 12,
                  "unit_price": "38.40", "line_total": "76.80"}]
        po = build_po("PO-TEST-001", cfg, {"supplier_name": "S", "source_url": "u", "retrieved_at": "d"},
                      lines, profile, Decimal("950.00"))
        self.assertEqual(po["total"], "76.80")
        self.assertTrue(po["over_budget"], "76.80 against 50.00 remaining must be flagged")
        self.assertEqual(po["purchasing_budget"], "1000.00")
        self.assertEqual(po["status"], "draft")


class ProfileSafety(unittest.TestCase):
    def test_forbidden_fields_are_rejected(self):
        raw = {"business_name": "Campus Crumb", "area": "Campus", "delivery_area": "Campus",
               "monthly_budget": "1000", "preferred_payment_type": "bank transfer",
               "preferred_suppliers": "BakeMart", "card_number": "4111 1111 1111 1111",
               "password": "hunter2"}
        clean, rejected = sanitise_profile(raw)
        self.assertNotIn("card_number", clean)
        self.assertNotIn("password", clean)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(clean["business_name"], "Campus Crumb")

    def test_forbidden_field_list_is_not_empty(self):
        self.assertTrue(FORBIDDEN_FIELDS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
