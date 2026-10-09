"""Listing intake: Contract of Sale PDF + listing URL by email -> AI-extracted draft ->
agent reviews/approves on a web form. Ports "Link Prefiller" + "Listing Script"; the
Google Form + Short.io link is replaced by this service's own review page.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import Any

import httpx
from pypdf import PdfReader

from .. import db, llm, prompts, telegram_api as tg
from ..config import settings
from ..mailer import InboundEmail, html_to_text
from . import common

log = logging.getLogger(__name__)

MAX_CONTRACT_CHARS = 60_000
MAX_LISTING_CHARS = 15_000
_URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
_PORTAL_HINTS = ("realestate.com.au", "domain.com.au", "allhomes", "realcommercial")


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages).strip()


def find_listing_url(text: str) -> str | None:
    urls = [u.rstrip(".,;") for u in _URL_RE.findall(text or "")]
    for url in urls:
        if any(h in url.lower() for h in _PORTAL_HINTS):
            return url
    return urls[0] if urls else None


async def scrape(url: str) -> str:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
        if settings.firecrawl_api_key:
            resp = await http.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True,
                      "blockAds": True, "removeBase64Images": True, "location": {"country": "AU"},
                      "maxAge": 172800000},
            )
            resp.raise_for_status()
            return (resp.json().get("data") or {}).get("markdown", "")
        resp = await http.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PropertyAgentBot/1.0)"})
        resp.raise_for_status()
        return html_to_text(resp.text)


async def intake_listing_email(em: InboundEmail) -> str:
    pdf = em.pdfs[0]
    token = db.new_review_token()
    filename = f"{token}.pdf"

    contract_object: str | None = None
    if settings.use_cloud:
        # Store the contract in cloud Storage instead of the local data dir.
        from .. import cloud_client
        uid = cloud_client.agent_uid() or "agent"
        contract_object = f"shared/{uid}/contracts/{filename}"
        cloud_client.storage_upload(contract_object, pdf.data, "application/pdf")
    else:
        settings.contracts_dir.mkdir(parents=True, exist_ok=True)
        (settings.contracts_dir / filename).write_bytes(pdf.data)

    warnings: list[str] = []
    contract_text = await asyncio.to_thread(extract_pdf_text, pdf.data)
    if len(contract_text) < 200:
        warnings.append("Couldn't read text from the PDF (scanned image?) — contract fields may be missing.")

    url = find_listing_url(em.text)
    listing_text = ""
    if url:
        try:
            listing_text = await scrape(url)
        except Exception as exc:
            warnings.append(f"Couldn't scrape the listing URL ({exc.__class__.__name__}).")
    else:
        warnings.append("No listing URL found in the email body.")

    data = await llm.complete_json(
        prompts.LISTING_EXTRACTION,
        prompts.render(prompts.LISTING_EXTRACTION_USER,
                       email_notes=em.text[:5000] or "(none)",
                       listing_content=listing_text[:MAX_LISTING_CHARS] or "(not available)",
                       contract_text=contract_text[:MAX_CONTRACT_CHARS] or "(not available)"),
        max_tokens=2048,
    )
    now = db.now_iso()
    values: dict[str, Any] = {f: str(data.get(f) or "").strip() for f in db.LISTING_FIELDS}
    values["address"] = values["address"] or "⚠️ [ENTER ADDRESS]"
    listing_values: dict[str, Any] = {
        **values, "contract_file": filename, "listing_url": url, "status": "DRAFT",
        "review_token": token, "created_at": now, "updated_at": now,
    }
    if settings.use_cloud:
        listing_values["contract_object"] = contract_object
    listing_id = db.insert("listings", listing_values)
    note = "\n".join(f"⚠️ {w}" for w in warnings)
    await tg.notify_admins(
        f"🏠 Listing received for {values['address']} (#{listing_id})!\n"
        f"Review your extracted property profile and set final details here:\n"
        f"{common.public_url(f'/listings/review/{token}')}" + (f"\n\n{note}" if note else "")
    )
    return f"listing {listing_id}"


def save_review(token: str, form: dict[str, str]) -> tuple[Any, bool]:
    """Apply review-form values. Returns (listing, newly_approved)."""
    listing = db.listing_by_token(token)
    if listing is None:
        raise KeyError(token)
    values = {f: form.get(f, "").strip() for f in db.LISTING_FIELDS}
    approve = form.get("approve") == "yes"
    newly_approved = approve and listing["status"] == "DRAFT"
    if approve and listing["status"] == "DRAFT":
        values["status"] = "SELLING"  # type: ignore[assignment]
    db.update("listings", listing["id"], values)
    return db.get_listing(listing["id"]), newly_approved


def set_status(listing_id: int, status: str) -> str:
    listing = db.get_listing(listing_id)
    if listing is None:
        return f"No listing #{listing_id}."
    db.update("listings", listing_id, {"status": status})
    return f"Listing #{listing_id} {listing['address']} is now {status}."
