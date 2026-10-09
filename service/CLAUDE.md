# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Note: the parent-level `Documents/CLAUDE.md` describes an unrelated Android game ("Elements Battle") and does not apply here.

## What this repository is

An AI lead-qualification assistant for a real estate agent. Leads arrive by Gmail or Telegram. "Alex" (an LLM persona) qualifies them over Telegram, scores them, alerts the agent and follows up. The original system was five Make.com scenarios; it has been rebuilt as a Python service in `service/` that deploys on Tencent WorkBuddy ("发布为应用", one HTTP port, SQLite only).

- `service/`: the live system. It's self-contained, and it's the directory that gets published.
- `*.blueprint.json`: the legacy Make.com exports. They are kept as a behavioural reference. The prompts in `service/app/prompts.py` were ported from them.
- `(FINAL) ULTIMATE Template - Ultimate Lead Database.xlsx`: the legacy Google Sheet. Its data is partly corrupted; `service/app/import_excel.py` cleans and imports it.

## Commands (run from `service/`)

```bash
pip install -r requirements.txt
python start.py                      # serve on $PORT (default 8000); Telegram long polling if PUBLIC_BASE_URL empty
python -m pytest -q                  # all tests; LLM/Telegram/SMTP are mocked in tests/conftest.py
python -m pytest -q -k test_name     # single test
python -m app.check                  # verify real credentials (LLM, Telegram, IMAP, SMTP)
python -m app.import_excel <xlsx> [--with-leads]
```

Config comes from `service/.env` (template: `.env.example`). Never publish a local `service/data/` directory: it holds the SQLite DB and would overwrite the deployed data.

## Architecture

- **Single asyncio process.** `app/main.py` is the FastAPI app. Its lifespan starts the loops in `app/workers.py`: the IMAP poller, the daily re-engagement scheduler, and Telegram long polling, which is used only when there is no `PUBLIC_BASE_URL`; otherwise Telegram updates arrive via `POST /telegram/webhook`. All database access happens on the event-loop thread. Blocking IMAP/SMTP calls go through `asyncio.to_thread`.
- **Routing:** `workers.handle_update` sends private chats from `ADMIN_CHAT_IDS` to `services/admin.py` (commands) and everyone else to `services/leads.py`. `workers.process_email` sends PDF emails from `LISTING_SENDERS` to `services/listings.py` and everything else to `leads.intake_email`. Email replies from known leads continue the conversation by email.
- **Alex's control tags.** `leads.generate_reply` builds `prompts.ALEX_SYSTEM` from the agent profile, the matched listing and `db.transcript()`. The model appends `[QUALIFIED]`, `[HANDOVER]`, `[IGNORE]`, `[UPDATE]` or `[STANDBY]`; `common.split_tags` strips the tag and picks one by priority, and the tag drives status changes and alerts. If you change a tag, update both the prompt and `common.TAGS`.
- **Debounce.** Each lead has a version counter and a lock (`leads._versions` / `_locks`). Only the newest message's task replies after `REPLY_DEBOUNCE_SECONDS`. This replaces the Make "Processing" lock and 10-second sleep.
- **Re-engagement** is anchored to `leads.followup_anchor_at` (the last real exchange). `next_followup_at = anchor + FOLLOWUP_SCHEDULE_DAYS[followup_step]`; the last step is sent by email. Any lead/Alex exchange resets the anchor via `common.conversation_turn_values()`.
- **Data model** (`app/schema.sql`): one row per person in `leads`, with chat in `messages` (not a text blob), inbound emails in `enquiries`, and IMAP idempotency in `processed_emails`. All timestamps are ISO UTC text; convert for display only, with `common.fmt_local` in `TIMEZONE`. Listings need status `SELLING` before Alex uses them; `DRAFT` listings wait for the review form.
- **Agentic layer.** `services/copilot.py` (free-text admin chat → tool-calling loop, max 6 steps, short in-memory history), `services/matching.py` (listing → ranked buyer intros) and `services/briefing.py` (SQL facts → LLM summary, raw-facts fallback). Agents never cause side effects directly: they call `actions.propose()`, which stores a `pending_actions` row. The admin's Approve tap (`callback_query` with data `act:<id>:yes`, handled in `workers.handle_callback`) runs `actions.EXECUTORS`. To add a new agent capability that changes anything, add an executor plus a `describe()` branch; don't call services directly from a tool.
- **LLM:** `app/llm.py` is an OpenAI-compatible client pointed at Tencent TokenHub (`hy3` by default). It always uses `parse_json_object` or `complete_json` for structured output, because `response_format` is not relied on. hy3 is a reasoning model whose hidden thinking counts against `max_tokens`. `llm._create` sends `reasoning_effort` (`LLM_REASONING_EFFORT`, default `low`, which is about 2x faster) with a large token budget, and retries once if the model used the whole budget thinking. Don't lower `MAX_TOKENS`, or replies come back empty.
