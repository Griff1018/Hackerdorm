"""BizFlow business profile (Section G.14).

Stored locally, synthetic in the demo. It never asks for, and never stores, an account number,
card number, e-wallet number, password, PIN or OTP. If one is offered it is refused and dropped.
"""
from __future__ import annotations

import json
from pathlib import Path

# Any key containing one of these is refused outright.
FORBIDDEN_FIELDS = (
    "card_number", "card_no", "account_number", "account_no", "bank_account", "iban",
    "ewallet", "e_wallet", "wallet_number", "password", "passwd", "pin", "otp", "cvv", "cvc",
    "api_key", "apikey", "secret", "token", "credential",
)

ALLOWED_FIELDS = (
    "business_name", "business_type", "area", "delivery_area", "monthly_budget", "purchasing_budget",
    "purchasing_budget_used", "preferred_payment_type", "part_time_pay_range_myr", "preferred_suppliers", "currency",
)


def is_forbidden(key: str) -> bool:
    k = (key or "").strip().lower()
    return any(f in k for f in FORBIDDEN_FIELDS)


def sanitise_profile(raw: dict) -> tuple[dict, list[str]]:
    """Return (clean profile, list of rejected field names)."""
    clean: dict = {}
    rejected: list[str] = []
    for k, v in (raw or {}).items():
        if is_forbidden(k):
            rejected.append(k)
            continue
        clean[k] = v
    return clean, rejected


def load_profile(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_profile(path: Path, raw: dict) -> tuple[dict, list[str]]:
    clean, rejected = sanitise_profile(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return clean, rejected
