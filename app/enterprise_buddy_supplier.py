"""Enterprise Buddy supplier scoring (Section G.11).

The score is computed by CODE from fields recorded from the source - never estimated by the model.
Full tier  = price 40 + delivery 20 + minimum order 15 + reliability 15 + location 10  = 100
Light tier = price 40 + reliability 15 + location 10                                   =  65
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from enterprise_buddy_core import dec, q2

UNIT_TO_BASE = {"kg": ("g", Decimal(1000)), "g": ("g", Decimal(1)),
                "l": ("ml", Decimal(1000)), "litre": ("ml", Decimal(1000)), "litres": ("ml", Decimal(1000)),
                "ml": ("ml", Decimal(1)), "pcs": ("pcs", Decimal(1)), "piece": ("pcs", Decimal(1)),
                "pieces": ("pcs", Decimal(1)), "unit": ("pcs", Decimal(1)), "units": ("pcs", Decimal(1))}

RESEARCH_COLUMNS = [
    "material_name", "tier", "supplier_name", "listed_price", "currency", "price_unit",
    "comparable_price", "minimum_order", "delivery_or_lead_time", "seller_type",
    "listing_updated_within_90d", "location", "source_url", "retrieved_at",
    "available", "material_match", "score", "score_breakdown", "rank", "recommended", "notes",
]


def parse_amount_unit(text: str):
    """'5 kg' -> (Decimal(5), 'g', Decimal(5000)). Returns None if unparseable."""
    if not text:
        return None
    s = str(text).strip().lower().replace(",", "")
    parts = s.split()
    if len(parts) < 1:
        return None
    try:
        value = Decimal(parts[0])
    except (InvalidOperation, ValueError):
        return None
    unit = parts[1] if len(parts) > 1 else ""
    factor = UNIT_TO_BASE.get(unit)
    if factor is None:
        return (value, unit, None)
    base_unit, mult = factor
    return (value, base_unit, value * mult)


def parse_days(text: str):
    """'2 days' / '3-5 days' / '2' -> highest stated day number, or None."""
    if not text:
        return None
    s = str(text).strip().lower()
    nums = []
    for tok in s.replace("days", " ").replace("day", " ").replace("-", " ").split():
        tok = tok.strip("~<>+")
        try:
            nums.append(int(float(tok)))
        except ValueError:
            pass
    if not nums:
        return None
    return max(nums)


def delivery_score(text: str) -> int:
    d = parse_days(text)
    if d is None:
        return 0
    if d <= 2:
        return 20
    if d <= 5:
        return 12
    if d <= 10:
        return 6
    return 0


def moq_score(minimum_order: str, use_4w: Decimal | None, use_3m: Decimal | None,
              material_unit: str) -> int:
    """15 = covers up to 4 weeks of use; 8 = up to 3 months; 0 = more than that or not stated."""
    p = parse_amount_unit(minimum_order)
    if p is None or p[2] is None:
        return 0
    _, unit, base = p
    if unit != material_unit:
        return 0  # not comparable - do not guess a conversion the source did not give
    if use_4w is not None and base <= use_4w:
        return 15
    if use_3m is not None and base <= use_3m:
        return 8
    return 0


def reliability_score(seller_type: str, updated_90d: str) -> int:
    s = (seller_type or "").strip().lower()
    u = (updated_90d or "").strip().lower()
    score = 0
    if s in ("official_shop", "official shop", "official", "rated_seller", "rated seller", "rated", "verified"):
        score += 10
    if u in ("yes", "true", "y"):
        score += 5
    return score


def location_score(location: str) -> int:
    return 10 if "malaysia" in (location or "").strip().lower() else 0


def score_row(row: dict, lowest_comparable: Decimal | None, tier: str,
              use_4w: Decimal | None = None, use_3m: Decimal | None = None,
              material_unit: str = "") -> tuple[Decimal | None, str]:
    """Return (score, breakdown string). Score is None when the price is not comparable."""
    price = dec(row.get("comparable_price"))
    bits = []
    total = Decimal(0)

    if price is None or lowest_comparable is None or price <= 0:
        bits.append("price=not comparable (pack size not stated)")
        price_part = None
    else:
        price_part = q2(Decimal(40) * (lowest_comparable / price))
        bits.append(f"price={price_part:.2f}")
        total += price_part

    if tier == "light":
        rel = reliability_score(row.get("seller_type", ""), row.get("listing_updated_within_90d", ""))
        loc = location_score(row.get("location", ""))
        bits.append(f"reliability={rel}")
        bits.append(f"location={loc}")
        bits.append("light tier - score out of 65")
        total = (price_part or Decimal(0)) + Decimal(rel) + Decimal(loc)
        return (None if price_part is None else q2(total)), "; ".join(bits)

    d = delivery_score(row.get("delivery_or_lead_time", ""))
    m = moq_score(row.get("minimum_order", ""), use_4w, use_3m, material_unit)
    rel = reliability_score(row.get("seller_type", ""), row.get("listing_updated_within_90d", ""))
    loc = location_score(row.get("location", ""))
    bits.append(f"delivery={d}")
    bits.append(f"moq={m}")
    bits.append(f"reliability={rel}")
    bits.append(f"location={loc}")
    total = (price_part or Decimal(0)) + Decimal(d + m + rel + loc)
    return (None if price_part is None else q2(total)), "; ".join(bits)


def score_material(rows: list[dict], tier: str, use_4w=None, use_3m=None, material_unit="") -> list[dict]:
    """Score every supplier row for one material, rank them and mark the top 3 recommended.

    A row is eligible to be recommended only if it has a comparable price AND is available
    AND is the specified material. Unpriced, unavailable, or substitute listings are never
    recommended:
      - unpriced     -> ranked last, never recommended (a comparison was never made)
      - unavailable  -> never recommended; may not be ordered (e.g. "supplier not active")
      - substitute   -> not recommended; shown as "substitute - owner decides" so the owner
                        can still see it but is not led to order the wrong item
    """
    # Compare exact, available listings first. If none exist, retain a comparable-price baseline
    # from the recorded rows so unavailable/substitute listings can be shown as evidence without
    # becoming recommendations. This avoids falsely reporting a published price as "unpriced".
    eligible_prices = [dec(r.get("comparable_price")) for r in rows
                       if (r.get("available") or "yes") != "no"
                       and (r.get("material_match") or "yes") == "yes"]
    eligible_prices = [p for p in eligible_prices if p is not None and p > 0]
    all_prices = [dec(r.get("comparable_price")) for r in rows]
    all_prices = [p for p in all_prices if p is not None and p > 0]
    lowest = min(eligible_prices or all_prices) if (eligible_prices or all_prices) else None

    scored = []
    for r in rows:
        score, breakdown = score_row(r, lowest, tier, use_4w, use_3m, material_unit)
        r = {**r, "score": None if score is None else f"{score:.2f}", "score_breakdown": breakdown}
        r.setdefault("available", "yes")
        r.setdefault("material_match", "yes")
        scored.append(r)

    def eligible(r: dict) -> bool:
        return (r["score"] is not None
                and (r.get("available") or "yes") == "yes"
                and (r.get("material_match") or "yes") == "yes")

    # Rank eligible (priced + available + matching) suppliers first, highest score first.
    def key(r):
        if not eligible(r):
            return (1, Decimal(0))
        return (0, -Decimal(r["score"]))

    scored.sort(key=key)
    eligible_seen = 0
    for i, r in enumerate(scored, start=1):
        r["rank"] = i
        if eligible(r):
            eligible_seen += 1
            r["recommended"] = "yes" if eligible_seen <= 3 else "no"
        else:
            r["recommended"] = "no"
            note = (r.get("notes", "") or "").rstrip(" |")
            if r["score"] is None and "not comparable" not in note.lower():
                note = (note + " | NOT RECOMMENDED: no comparable price recorded from this source, "
                        "so it cannot be compared.").strip(" |")
            if (r.get("available") or "yes") == "no" and "unavailable" not in note.lower():
                note = (note + " | NOT RECOMMENDED: listing marked unavailable/inactive at source - "
                        "cannot be ordered.").strip(" |")
            if (r.get("material_match") or "yes") == "no" and "substitute" not in note.lower():
                note = (note + " | SUBSTITUTE - not the specified material; shown for owner review, "
                        "not recommended.").strip(" |")
            r["notes"] = note
    return scored


def expected_use(material: dict, adu_by_product: dict, unit: str) -> tuple[Decimal | None, Decimal | None]:
    """Expected use of a material per 4 weeks (28 d) and per 3 months (90 d), in `unit`."""
    total_per_day = Decimal(0)
    for pid, qty in material.get("per_product_qty", {}).items():
        adu = adu_by_product.get(pid)
        if adu is None:
            continue
        total_per_day += Decimal(str(qty)) * Decimal(str(adu))
    if unit == "g":
        return total_per_day * 28, total_per_day * 90
    if unit == "ml":
        return total_per_day * 28, total_per_day * 90
    return total_per_day * 28, total_per_day * 90


def write_research_csv(path: Path, rows: list[dict]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESEARCH_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in RESEARCH_COLUMNS})
