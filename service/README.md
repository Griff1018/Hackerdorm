# Property Agent service

A Python service that replaces the five Make.com scenarios. It runs as a single HTTP process, which makes it deployable with WorkBuddy's **发布为应用** (publish as app). SQLite holds all the data.

| Old Make.com scenario | Now |
|---|---|
| TLG Hybrid Bot Model | Telegram bot. Admin commands go to `app/services/admin.py`; Alex's lead chat lives in `app/services/leads.py` |
| Gmail Hook | Gmail is polled over IMAP. Enquiry emails are turned into leads, and Alex sends an opener email with a Telegram link |
| Lead Reengagement | A daily job at 9am (`app/services/reengagement.py`), toggled with `/reengagement_on` and `/reengagement_off` |
| Link Prefiller | An email from the agent with a Contract of Sale PDF and a listing URL produces an AI-extracted draft, which the agent reviews at `/listings/review/<token>` |
| Listing Script | Approving the review form makes the listing live (status `SELLING`) |

## How a lead flows

1. An enquiry email arrives in the Gmail inbox. The LLM extracts the name, email, phone, buyer or seller, and address. Newsletters and other non-enquiries are skipped.
2. The lead is found by email or phone, or created. A returning lead is updated in place and the new enquiry is logged in `enquiries`, so leads are never duplicated.
3. Alex emails a one-line opener plus a `t.me/<bot>?start=<code>` link. Tapping the link connects the lead's Telegram chat to the lead record. If the lead replies by email instead, Alex answers by email.
4. On Telegram, Alex qualifies the lead. Rapid-fire messages are batched for `REPLY_DEBOUNCE_SECONDS`, and Alex appends a tag to its reply that drives what happens next:
   - `[QUALIFIED]`: the lead is scored out of 10. The agent gets a Telegram alert plus emails, with **HOT** at a score of 6 or more.
   - `[HANDOVER]`: Alex pauses for this lead. The agent replies with `/reply <id> <text>` and hands back with `/resume <id>`.
   - `[IGNORE]`: the lead is banned. Undo with `/unban <id>`.
   - `[UPDATE]` / `[STANDBY]`: logged. The agent is notified on `[UPDATE]`.
5. Leads who go quiet get follow-ups on days 3, 5, 7 and 30 by Telegram, then an email on day 90. The clock restarts whenever the lead replies.

Anyone who messages the bot directly, without a link, also becomes a lead.

## Agentic features

Each of these is an LLM agent working on the same database. Anything that messages a lead or changes data is saved as a **pending action** and sent to you with ✅ Approve / ✖️ Cancel buttons. Nothing happens until you tap Approve.

- **Copilot** (`services/copilot.py`): type any plain-English message to the bot, for example "who's waiting on me?", "which buyers can afford Help Street?" or "tell David the inspection moved to 11am". The agent searches leads and listings with tools, answers, and drafts messages or status changes for you to approve. It remembers the last few exchanges; `/reset` clears that memory.
- **Matchmaker** (`services/matching.py`): runs when you approve a listing, or on demand with `/match <id>`. It ranks past buyer leads against the listing and drafts a personal intro for each strong fit. When you approve an intro, it's sent, and the lead is linked to the new listing so Alex can answer their questions about it.
- **Morning briefing** (`services/briefing.py`): every day at `BRIEFING_HOUR` (default 8am) you get a prioritised to-do list: hot leads to call, handovers waiting, follow-ups due and listings to review. Get one now with `/briefing`, and turn it on or off with `/briefing_on` / `/briefing_off`.

`/approvals` re-sends anything still waiting for your decision. Pending actions expire after 48 hours.

## Setup

1. **Telegram bot:** create one with @BotFather, which gives you `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME`. Get the agent's chat ID from @userinfobot and put it in `ADMIN_CHAT_IDS`.
2. **Gmail:** use a dedicated inbox for enquiries. Turn on 2-Step Verification, then create an App Password, which goes in `GMAIL_APP_PASSWORD`. Forward portal enquiries (REA/Domain) to this inbox. The agent's own address goes in `LISTING_SENDERS`, so their PDF emails are treated as listings.
3. **Hunyuan:** create an API key in the Tencent **TokenHub** console. The default model is `hy3`.
4. Copy `.env.example` to `.env` and fill it in.
5. Install the dependencies and load the legacy data. The import cleans the agent profile, listings and the re-engagement setting; add `--with-leads` to also import the template's test leads.

```bash
pip install -r requirements.txt
python -m app.import_excel "../(FINAL) ULTIMATE Template - Ultimate Lead Database.xlsx"
python -m app.check          # verifies LLM, Telegram, IMAP, SMTP
```

## Run locally

```bash
python start.py              # http://localhost:8000, Telegram via long polling
python -m pytest -q          # tests (LLM/Telegram/SMTP mocked)
python -m pytest -q -k handover   # a single test
```

With `PUBLIC_BASE_URL` empty, the bot uses long polling, so it works from your own machine.

## Deploy on WorkBuddy

1. In WorkBuddy, ask it to publish this `service/` folder (发布 `service` 目录). It's a Python app, started with `python start.py`, which listens on `$PORT` and binds `0.0.0.0`. `.env` is uploaded with the code, because that's how the sandbox gets its configuration.
2. Copy the share link it returns into `.env` as `PUBLIC_BASE_URL`, then publish again. On startup the bot registers its Telegram webhook at `<PUBLIC_BASE_URL>/telegram/webhook`, which is protected by `TELEGRAM_WEBHOOK_SECRET`.
3. Manage the app under **设置 — 数据管理 — 发布的应用** (Settings - Data Management - Published Apps).

Caveats with the WorkBuddy sandbox:

- **Data on redeploy:** SQLite lives in `DATA_DIR` (`data/`). Before every redeploy, run `/export` in Telegram to download a full Excel backup. After your first redeploy, confirm the data survived with `/summary`. Never publish a local `data/` folder, because it would be uploaded along with the code.
- **The 9am job only runs while the service is awake.** If the sandbox sleeps when idle, the day's run happens the first time it wakes after 9am. For an exact schedule, set `CRON_SECRET` and have any external scheduler call `POST <PUBLIC_BASE_URL>/cron/reengagement?key=<CRON_SECRET>` each morning.
- **Inbound email is checked by polling** every `IMAP_POLL_SECONDS`, so it also depends on the service being awake.

## Agent commands (Telegram)

| Command | What it does |
|---|---|
| `/leads` | Today's leads |
| `/top` | Top 3 qualified leads this week |
| `/summary` | All-time stats |
| `/recent` | Last 5 qualified leads |
| `/pending` | The re-engagement queue |
| `/lead <id>` | Lead details and transcript |
| `/reply <id> <text>` | Message a lead |
| `/resume <id>` | Hand a lead back to Alex |
| `/unban <id>` | Un-ban a lead |
| `/listing` | How to add a listing, and current listings |
| `/sold <id>` | Mark a listing sold |
| `/profile`, `/setprofile <field> <value>` | View or edit the agent profile |
| `/reengagement_on`, `/reengagement_off` | Start or stop daily follow-ups |
| `/run_followups` | Send due follow-ups now |
| `/briefing`, `/briefing_on`, `/briefing_off` | Morning briefing now, or on/off |
| `/match <listing id>` | Find past buyers who fit a listing |
| `/approvals` | Actions waiting for your approval |
| `/reset` | Clear the copilot's memory |
| any plain text | Ask the copilot |
| `/export` | Download the database as `.xlsx` (replaces the old `/gs` sheet link) |
| `/help` | Show the command menu |
