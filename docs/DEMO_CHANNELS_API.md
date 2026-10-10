# Connecting demo WhatsApp / Instagram / LinkedIn to Enterprise Buddy

Enterprise Buddy's **📥 Online Requests** tab is one inbox for all channels. Any demo app can plug in with three HTTP calls
to the Enterprise Buddy console (`python console/server.py` → `http://127.0.0.1:8090`). No API keys. Synthetic people only.

Tip: serve your demo page **from Enterprise Buddy's origin** (put it in the project and add a route like `/instagram/`), or
call the API from your own dev server — Enterprise Buddy does not send CORS headers, so a page on another port must proxy.

## 1. A customer / candidate sends a message → Enterprise Buddy

```
POST /api/channels/<channel>/incoming
Content-Type: application/json

{"contact": {"handle": "60123456789", "name": "Hafiz"}, "text": "Can I order 2 cookies?", "business_id": "campus-crumb"}
```
`<channel>` is `whatsapp`, `instagram` or `linkedin`. `handle` identifies the person (phone number, IG handle,
LinkedIn handle). Response: `{"thread_id": "T…", "messages": [...]}`.

## 2. Show the shop owner's replies in your demo app (poll every 2–3 s)

```
GET /api/channels/<channel>/thread?handle=60123456789&business_id=campus-crumb
```
Returns `{"messages": [{"from": "them" | "me", "text": "...", "at": "ISO time"}, ...]}`.
`"them"` = the customer/candidate (your demo user), `"me"` = the shop owner replying from Enterprise Buddy.

## 3. Demo LinkedIn: give Enterprise Buddy candidate profiles

Either push them:
```
POST /api/channels/linkedin/candidates
[{"handle": "nurul-izzah", "name": "Nurul Izzah", "headline": "Food Science student, UM",
  "skills": ["customer service", "food handling", "cashier"], "availability": ["Wed", "Fri"],
  "location": "Universiti Malaya, Kuala Lumpur", "expected_pay": 13, "certs": ["food handler", "typhoid"],
  "profile_url": "http://127.0.0.1:XXXX/in/nurul-izzah", "about": "..."}]
```
or set `LINKEDIN_DEMO_URL` (an endpoint returning that list) before starting Enterprise Buddy — it is fetched on every scan.
Enterprise Buddy re-scores everyone against the owner's role every 60 s (skills 40, days 25, pay 15, location 10,
food-handler/typhoid 10) and lists matches ≥ 60/100 under **Automations → 👥 Recruiting**. When the owner presses
**✉ Message on LinkedIn**, the message appears in the LinkedIn thread for that handle (read it with call 2).

The five built-in candidates are SYNTHETIC placeholders until your demo LinkedIn pushes its own.

## Already connected
- **Instagram mock** (`instagram_mock/index.html`, served at `/instagram/`): DMs use calls 1 and 2 as customer
  `aisyah.um` (change with `?as=<handle>&name=<name>`).

## Demo LinkedIn (connected)
`linkedin_mock/index.html` is served by Enterprise Buddy at **`/linkedin/?business_id=campus-crumb`** (its `.env` with an OpenAI key was
not copied; Copilot Studio uses its built-in offline writer).
- The company page is the Enterprise Buddy business (`GET /api/linkedin/bootstrap`).
- Roles saved in Enterprise Buddy → Automations → 👥 Recruiting appear as job posts (`GET /api/linkedin/posts`, polled every 4 s).
- **Easy Apply** (with skills, days, expected pay, location, food-handler/typhoid ticks) → `POST /api/linkedin/apply` → scored and listed.
- **InMail** (name + email added) → arrives in 📥 Online Requests as a LinkedIn chat.
- **Talent** tab: suitable candidates with Enterprise Buddy scores; chat with "Send as <business>" and "Reply as <candidate> (demo)".

## Auto-reply and pending orders
Right-click a WhatsApp/Instagram chat in 📥 Online Requests → 🤖 auto-reply. The agent takes the order (items from the menu,
pickup/delivery, address, time, name, phone), suggests one add-on, uses only the shop's policy file, prices are computed by Enterprise Buddy
from `menu.csv`, and after the customer says YES the order appears under 📦 Pending orders.
