"""FastAPI entry point: Telegram webhook, listing review pages, background workers.

Run locally:   uvicorn app.main:app --port 8000
WorkBuddy:     python start.py   (listens on $PORT, binds 0.0.0.0)
"""
from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db, telegram_api as tg, workers
from .config import settings
from .prompts import LISTING_CHOICES
from .services import admin, common, listings, matching, reengagement
from .dashboard import dashboard_router, public_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

LISTING_LABELS = {
    "address": "Property Address", "property_type": "Property Type", "asking_price": "Asking Price",
    "method_of_sale": "Method of Sale", "auction_date": "Auction Date & Time (if applicable)",
    "layout_specs": "Basic Layout Specs (Beds / Baths / Area / Year Built)",
    "aspect": "Property Aspect / Solar Orientation", "parking": "Parking Availability",
    "inclusions": "Furnishing & Inclusions",
    "outdoor_features": "Outdoor Features & Key Amenities", "tenancy_income": "Tenancy Status & Current Rental Income",
    "zoning": "School Catchments & Zoning", "easements": "Legal Restrictions / Easements",
    "strata_status": "Strata / Body Corporate Status", "strata_levies": "Strata Levies (Quarterly)",
    "council_rates": "Council Rates (Estimated)", "water_rates": "Water Rates (Estimated)",
    "pet_policy": "Pet Policy", "rental_policy": "Rental / Airbnb Restrictions",
    "upgrades": "Key Upgrades & Selling Points", "vendor_terms": "Vendor Terms & Special Notes",
    "occupancy_access": "Occupancy & Inspection Access", "inspection_windows": "Preferred Inspection Windows",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.connect()
    if settings.use_cloud:
        from . import cloud_client
        try:
            cloud_client.ensure_signed_in()
            log.info("Cloud service: agent signed in")
        except Exception:
            log.exception("Cloud service: agent sign-in failed (DB/Storage writes will fail RLS)")
    background: list[asyncio.Task[Any]] = [asyncio.create_task(workers.scheduler_loop())]
    if settings.mail_enabled:
        background.append(asyncio.create_task(workers.mail_loop()))
    elif not settings.gmail_intake_enabled:
        log.info("Gmail intake disabled (GMAIL_INTAKE_ENABLED=0); outbound email still available")
    else:
        log.warning("Gmail not configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD); email intake disabled")
    if settings.telegram_enabled:
        try:
            if settings.public_base_url:
                await tg.set_webhook(f"{settings.public_base_url}/telegram/webhook", settings.telegram_webhook_secret)
                log.info("Telegram webhook registered")
            else:
                background.append(asyncio.create_task(workers.telegram_polling_loop()))
                log.info("Telegram long polling started (no PUBLIC_BASE_URL)")
            for chat_id in settings.admin_chat_ids:
                await tg.set_commands(admin.COMMANDS, chat_id)
        except Exception:
            log.exception("Telegram setup failed")
    elif not settings.telegram_intake_enabled:
        # Intake switched off: make sure no stale webhook keeps pointing at a dead URL.
        log.info("Telegram intake disabled (TELEGRAM_INTAKE_ENABLED=0); clearing any existing webhook")
        try:
            await tg.delete_webhook()
        except Exception:
            log.warning("Could not clear Telegram webhook", exc_info=True)
    else:
        log.warning("TELEGRAM_BOT_TOKEN not set; Telegram disabled")
    try:
        yield
    finally:
        for task in background:
            task.cancel()
        await tg.close()


app = FastAPI(title="Property Agent", lifespan=lifespan, docs_url=None, redoc_url=None)

# The sandbox reverse proxy can present the page and the API on different origins,
# which makes the browser send a CORS preflight (OPTIONS) before the form POST.
# Without CORS handling that preflight 405s and the submit fails as a network error.
# The API is public and carries no cookies, so a permissive origin is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBROOT = Path(__file__).resolve().parent.parent / "webroot"

app.include_router(public_router)
app.include_router(dashboard_router)


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(WEBROOT / "index.html")


@app.get("/styles.css")
async def site_styles() -> FileResponse:
    return FileResponse(WEBROOT / "styles.css", media_type="text/css")


@app.get("/script.js")
async def site_script() -> FileResponse:
    return FileResponse(WEBROOT / "script.js", media_type="application/javascript")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "telegram": settings.telegram_enabled,
        "mail": settings.mail_enabled,
        "mail_in": settings.mail_enabled,      # inbound Gmail polling
        "mail_out": settings.smtp_enabled,     # outbound SMTP (website enquiries, replies)
        "llm": bool(settings.llm_api_key),
        "reengagement": db.reengagement_enabled(),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.telegram_webhook_secret or not hmac.compare_digest(secret, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403)
    workers.spawn_update(await request.json())
    return {"ok": True}


# --- Website enquiry -> real email + Telegram link ------------------------------------------

_INTENT_MAP = {"buy": "BUYER", "rent": "BUYER", "invest": "BUYER", "sell": "SELLER"}


def _web_lead_email(name: str, agent: str, intent: str, message: str, phone: str,
                    tg_link: str | None) -> str:
    first = name.split()[0] if name else "there"
    lines = [
        f"Hi {first},",
        "",
        f"Thanks for your enquiry with {agent}'s team. I'm Alex, your AI property assistant — "
        "I'll help you find the right home and keep you posted on new matches.",
        "",
        "Here's what we received from you:",
        f"  - Looking to: {intent.title()}",
        f"  - Message: {message or 'not provided'}",
        f"  - Contact: {phone or 'not provided'}",
        "",
    ]
    if tg_link:
        lines += [
            "To start the conversation and get matched with listings, tap your private link below "
            "(it opens Telegram — no app install needed):",
            "",
            f"  {tg_link}",
            "",
            "Once you're in, I'll ask a couple of quick questions and share homes that fit your wish-list. "
            "You can also just reply to this email.",
        ]
    else:
        lines += ["Reply to this email and I'll get the conversation started."]
    lines += ["", "Talk soon,", "Alex", f"{agent}'s team"]
    return "\n".join(lines)


@app.post("/api/web-lead")
async def web_lead(request: Request) -> dict[str, Any]:
    """Website enquiry: create a lead, email the enquirer a real Telegram link, notify the agent."""
    try:
        data = await request.json()
    except Exception:
        data = {k: str(v) for k, v in (await request.form()).items()}

    name = common.clean_value(data.get("name")) or ""
    email = common.clean_value(data.get("email")) or ""
    phone = common.normalize_phone(data.get("phone"))
    raw_intent = str(data.get("intent") or "Buy").lower()
    intent = _INTENT_MAP.get(raw_intent, "BUYER")
    message = common.clean_value(data.get("message")) or ""

    if not name or not email or "@" not in email:
        raise HTTPException(status_code=400, detail="name and a valid email are required")
    if not settings.smtp_enabled:
        raise HTTPException(status_code=503, detail="outbound email is not configured")

    lead = db.create_lead({
        "name": name, "email": email, "phone": phone, "lead_type": intent,
        "source": "EMAIL", "status": "INITIATED",
    })
    lead_id = lead["id"]
    summary = message or f"Website enquiry — looking to {raw_intent}"
    db.add_message(lead_id, "lead", "email", summary, kind="enquiry")

    tg_link = common.telegram_link(lead)
    agent = common.agent_name()
    subject = f"Your property search starts here, {name.split()[0] if name else 'there'} — tap to chat with Alex"
    body = _web_lead_email(name, agent, raw_intent, message, phone or "", tg_link)
    email_sent = await common.send_email(email, subject, body)

    notify = (f"\U0001F310 New website lead #{lead_id}\n"
              f"\U0001F4C5 Date: {common.fmt_local(db.now_iso())}\n"
              f"\U0001F464 Name: {name}\n"
              f"\U0001F4E7 Email: {email}\n"
              f"\U0001F4DE Phone: {phone or '-'}")
    await tg.notify_admins(notify)
    alert_to = settings.alert_emails or ([settings.gmail_address] if settings.gmail_address else [])
    if alert_to:
        await common.send_email(
            alert_to, f"New website lead — {name}",
            f"Hi {agent},\n\nA new lead just enquired via the website:\n\n{notify}\n\n"
            "This is an automated notification from your Lead Management System.",
        )

    return {"ok": True, "lead_id": lead_id, "email_sent": email_sent, "telegram_link": tg_link}


@app.post("/cron/reengagement")
async def cron_reengagement(key: str = "") -> JSONResponse:
    if not settings.cron_secret or not hmac.compare_digest(key, settings.cron_secret):
        raise HTTPException(status_code=403)
    summary = await reengagement.run()
    return JSONResponse({"result": summary})


def _listing_or_404(token: str) -> Any:
    listing = db.listing_by_token(token)
    if listing is None:
        raise HTTPException(status_code=404)
    return listing


@app.get("/listings/review/{token}", response_class=HTMLResponse)
async def review_listing(request: Request, token: str) -> HTMLResponse:
    listing = _listing_or_404(token)
    return templates.TemplateResponse(request, "review.html", {
        "listing": listing, "fields": db.LISTING_FIELDS, "labels": LISTING_LABELS,
        "choices": LISTING_CHOICES, "saved": request.query_params.get("saved"),
    })


@app.post("/listings/review/{token}", response_class=HTMLResponse)
async def submit_listing(request: Request, token: str) -> HTMLResponse:
    _listing_or_404(token)
    form = {k: str(v) for k, v in (await request.form()).items()}
    listing, newly_approved = listings.save_review(token, form)
    if newly_approved:
        await tg.notify_admins(f"✅ Your listing details for {listing['address']} (#{listing['id']}) have been recorded! "
                               "Alex will now use them when chatting with leads. Checking past buyers for matches…")
        workers.spawn(matching.find_matches(listing["id"]))
    return templates.TemplateResponse(request, "review.html", {
        "listing": listing, "fields": db.LISTING_FIELDS, "labels": LISTING_LABELS,
        "choices": LISTING_CHOICES, "saved": "approved" if newly_approved else "saved",
    })


@app.get("/listings/contract/{token}")
async def listing_contract(token: str) -> FileResponse:
    listing = _listing_or_404(token)
    if not listing["contract_file"]:
        raise HTTPException(status_code=404)
    if settings.use_cloud and listing.get("contract_object"):
        from . import cloud_client
        url = cloud_client.storage_signed_url(listing["contract_object"], 600)
        if url:
            return RedirectResponse(url)
    path = settings.contracts_dir / listing["contract_file"]
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="application/pdf", filename="contract-of-sale.pdf")
