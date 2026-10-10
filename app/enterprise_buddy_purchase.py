"""Enterprise Buddy ready-to-pay purchase orders (Section G.13/G.14).

Builds one DRAFT purchase order per supplier from the scored supplier research and the
replenishment list. Nothing here is ordered or paid: Enterprise Buddy produces a draft the owner
pays themselves. If a PO would exceed the remaining purchasing budget it is marked
over_budget and is NOT approved automatically - the owner decides.

Quantities are rounded UP to the supplier's stated pack size, because that is what can
actually be bought.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

from enterprise_buddy_core import q2
from enterprise_buddy_supplier import parse_amount_unit

# Words in a research note that mean "a human must look at this line before paying".
REVIEW_KEYWORDS = (
    "retail", "ambiguous", "not certified", "not currently available",
    "not pure butter", "spread", "adulteration", "syrup", "confirm", "warning",
)


def materials_needed(v, calc: dict) -> dict[str, Decimal]:
    """Units of each material needed to make the replenishment quantity, in the material's own unit."""
    need: dict[str, Decimal] = {}
    replen = {pid: s.get("replenishment_units")
              for pid, s in calc["stock_and_replenishment"].items()}
    for m in v.materials:
        units = replen.get(m["product_id"])
        if not units:
            continue            # no replenishment computed for this product (e.g. stale count)
        qty = Decimal(str(m["quantity_per_unit"])) * Decimal(str(units))
        need[m["material_name"]] = need.get(m["material_name"], Decimal(0)) + qty
    return need


def _review_flags(note: str) -> list[str]:
    low = (note or "").lower()
    return [k for k in REVIEW_KEYWORDS if k in low]


def _classify_skip(mat: str, qty: Decimal, rows: list[dict]) -> dict:
    """Explain why a needed material produced no draft PO."""
    priced = [r for r in rows if r.get("comparable_price")]
    if not priced:
        reason = "no supplier with a comparable price was found - needs a quotation"
    elif any((r.get("available") or "yes") == "no" for r in priced):
        reason = ("no available supplier - the priced option(s) are marked unavailable/inactive "
                  "at source (not ordered)")
    elif all((r.get("material_match") or "yes") == "no" for r in priced):
        reason = ("no supplier found for the specified material; substitute(s) exist but are shown "
                  "as 'substitute - owner decides' only (see supplier_research.csv)")
    else:
        reason = "no eligible supplier (check availability and material match in supplier_research.csv)"
    return {"material_name": mat, "quantity_needed": f"{qty:.2f}", "reason": reason}


def build_purchase_plan(scored: list[dict], need: dict[str, Decimal], cfg, profile: dict,
                        budget_used: Decimal | None = None) -> list[dict]:
    """One draft PO per supplier, using the top-ranked eligible supplier for each needed material.

    Budget rule (explicit):
      * Each PO is checked only against the PURCHASING budget (profile.purchasing_budget), which is
        a separate envelope from the operating budget that covers rent, fuel, wages, etc. Recorded
        expenses such as rent and fuel are never deducted from the purchasing budget.
      * POs are paid one at a time. A PO that is already flagged over-budget is NOT approved and is
        NOT counted against the remaining budget when checking later POs.
    """
    by_mat: dict[str, list] = {}
    for r in scored:
        by_mat.setdefault(r["material_name"], []).append(r)

    # best eligible + recommended row for each material we actually need
    chosen: dict[str, dict] = {}
    skipped: list[dict] = []
    for mat, qty in need.items():
        rows = by_mat.get(mat, [])
        pick = next((r for r in rows if r.get("recommended") == "yes" and r.get("score")), None)
        if pick is None:
            skipped.append(_classify_skip(mat, qty, rows))
            continue
        chosen[mat] = pick

    grouped: dict[str, list] = {}
    for mat, row in chosen.items():
        grouped.setdefault(row["supplier_name"], []).append((mat, row))

    budget = Decimal(str(profile.get("purchasing_budget", "0") or "0"))
    if budget_used is None:
        budget_used = Decimal(str(profile.get("purchasing_budget_used", "0") or "0"))

    pos = []
    cumulative = budget_used  # running spend of APPROVED (in-budget) POs only
    seq = 0
    for supplier, items in sorted(grouped.items()):
        seq += 1
        lines = []
        for mat, row in sorted(items):
            needed_qty = need[mat]
            pack = parse_amount_unit(row.get("price_unit", ""))
            pack_base = pack[2] if pack else None
            if pack_base is None or pack_base <= 0:
                packs = Decimal(1)
                pack_label = row.get("price_unit", "") or "not stated"
            else:
                packs = Decimal(math.ceil(needed_qty / pack_base))
                pack_label = row.get("price_unit", "") or "not stated"
            unit_price = Decimal(str(row.get("listed_price") or "0"))
            line_total = q2(packs * unit_price)
            flags = _review_flags(row.get("notes", ""))
            lines.append({
                "material": mat,
                "quantity_needed": f"{needed_qty.normalize():.2f}",
                "packs": str(int(packs)),
                "pack_size": pack_label,
                "unit_price": f"{unit_price:.2f}",
                "line_total": f"{line_total:.2f}",
                "supplier_score": row.get("score", ""),
                "needs_review": bool(flags),
                "review_reasons": flags,
            })

        total = sum((Decimal(l["line_total"]) for l in lines), Decimal(0))
        cumulative_before = cumulative
        projected = cumulative + total
        over = projected > budget
        if not over:
            cumulative = projected  # only in-budget POs advance the running total
        pos.append({
            "order_id": f"PO-{cfg.period_end.isoformat()}-{seq:02d}",
            "supplier_name": supplier,
            "source_url": items[0][1].get("source_url", ""),
            "retrieved_at": items[0][1].get("retrieved_at", ""),
            "currency": cfg.currency,
            "payment_type": profile.get("preferred_payment_type", "not set"),
            "lines": lines,
            "total": f"{q2(total):.2f}",
            "purchasing_budget": f"{q2(budget):.2f}",
            "budget_already_used": f"{q2(budget_used):.2f}",
            "budget_remaining_after_this": f"{q2(budget - cumulative_before):.2f}",
            "over_budget": over,
            "status": "draft",
        })
    return pos, skipped


def write_purchase_plan(path: Path, pos: list[dict], skipped: list[dict], cfg) -> None:
    L = ["# PURCHASE PLAN - Enterprise Buddy (draft purchase orders)", ""]
    L.append("**SIMULATED. No order is placed and no money moves.** Each PO below is a draft the "
             "owner reviews and pays the supplier directly.")
    L.append("")
    L.append(f"Period {cfg.period_start} .. {cfg.period_end}")
    L.append("")
    if not pos:
        L.append("No purchase orders could be built - see the gaps below.")
    else:
        total_all = sum((Decimal(p["total"]) for p in pos), Decimal(0))
        L.append("| PO | supplier | lines | total | over budget? | needs review? |")
        L.append("|---|---|---|---|---|---|")
        for p in pos:
            review = "yes" if any(l["needs_review"] for l in p["lines"]) else "no"
            L.append(f"| {p['order_id']} | {p['supplier_name']} | {len(p['lines'])} | "
                     f"{p['total']} {p['currency']} | {'YES' if p['over_budget'] else 'no'} | {review} |")
        L.append("")
        L.append(f"**Plan total: {total_all:.2f} {cfg.currency}** against a purchasing budget of "
                 f"{pos[0]['purchasing_budget']} {cfg.currency} (already committed to purchasing "
                 f"{pos[0]['budget_already_used']} {cfg.currency} before this plan).")
        L.append("")
        over = [p for p in pos if p["over_budget"]]
        if over:
            L.append("## Over budget - not approved automatically")
            L.append("")
            for p in over:
                L.append(f"- **{p['order_id']}** ({p['supplier_name']}, {p['total']} {p['currency']}) exceeds the "
                         "remaining budget. Enterprise Buddy does not approve it. The owner must decide: split the order, "
                         "raise the budget, or drop a line.")
            L.append("")
        review_lines = [(p, l) for p in pos for l in p["lines"] if l["needs_review"]]
        if review_lines:
            L.append("## Lines a human must check before paying")
            L.append("")
            for p, l in review_lines:
                L.append(f"- **{p['order_id']} / {l['material']}** ({p['supplier_name']}): "
                         + "; ".join(l["review_reasons"]))
            L.append("")
            L.append("These lines scored well on price but carry a caveat recorded from the source "
                     "(retail listing, ambiguous pack basis, food-contact restriction, product is a "
                     "spread not butter, supplier currently inactive, and so on). Read the note in "
                     "`supplier_research.csv` before paying.")
            L.append("")
    if skipped:
        L.append("## Not ordered - no usable supplier price")
        L.append("")
        for s in skipped:
            L.append(f"- **{s['material_name']}** (needs {s['quantity_needed']}): {s['reason']}")
        L.append("")
    L.append("## Rule")
    L.append("")
    L.append("Quantities are rounded up to the supplier's stated pack size. A PO over the remaining "
             "budget is never approved automatically, and no PO is ever sent or paid by Enterprise Buddy.")
    L.append("")
    L.append("**Budget rule (explicit).** Each PO is checked only against the **purchasing budget** "
             "(`business_profile.json` → `purchasing_budget`), which is a *separate* envelope from the "
             "operating budget that covers rent, fuel and wages. Recorded expenses such as rent and fuel "
             "are **never** deducted from the purchasing budget. POs are paid one at a time: a PO already "
             "flagged over-budget is **not** approved and is **not** counted against the remaining budget "
             "when checking later POs.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_po(path: Path, po: dict) -> None:
    L = [f"# PURCHASE ORDER {po['order_id']} - DRAFT (ready to pay)", ""]
    L.append("**SIMULATED - no real money moves.** Enterprise Buddy never places or pays an order. "
             "This is a draft for the owner to pay the supplier directly.")
    L.append("")
    L.append(f"Supplier: **{po['supplier_name']}**")
    L.append(f"Source: {po['source_url']} (retrieved {po['retrieved_at']})")
    L.append(f"Payment type on file: {po['payment_type']} · currency {po['currency']}")
    L.append("")
    L.append("| material | needed | packs | pack size | unit price | line total | check |")
    L.append("|---|---|---|---|---|---|---|")
    for l in po["lines"]:
        flag = ("REVIEW: " + ", ".join(l["review_reasons"])) if l["needs_review"] else "-"
        L.append(f"| {l['material']} | {l['quantity_needed']} | {l['packs']} | {l['pack_size']} | "
                 f"{l['unit_price']} | {l['line_total']} | {flag} |")
    L.append("")
    L.append(f"**Total: {po['total']} {po['currency']}**")
    L.append("")
    L.append(f"Purchasing budget {po['purchasing_budget']} · already committed to purchasing "
             f"{po['budget_already_used']} · remaining before this PO {po['budget_remaining_after_this']}")
    L.append("")
    if po["over_budget"]:
        L.append("**This order exceeds the remaining purchasing budget. It is NOT approved automatically - "
                 "the owner must decide.**")
        L.append("")
    L.append("Status: draft → approved → ready to pay → paid (the owner pays).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_po_json(path: Path, pos: list[dict], skipped: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"purchase_orders": pos, "not_ordered": skipped}, indent=2),
                    encoding="utf-8")
