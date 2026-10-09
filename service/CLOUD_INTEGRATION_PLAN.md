# Cloud-Service Integration Plan — 房产中介助手 (Property Agent)

> Status: **Plan only.** Cloud activation for `wbapp_T7sp5FS2HmvDIjEwqCM8RN` is still blocked
> (`backend-unavailable` on all 5 attempts). This document prepares the exact code changes so they
> can be executed the moment activation succeeds. Nothing here is implemented yet.

---

## 1. The one constraint that drives every decision

The cloud SDK (`@tencent-ai/workbuddy-cloud-sdk`) is **JavaScript/TypeScript only**. This app is a
**Python FastAPI backend** that also serves a static admin dashboard (plain HTML/JS). Every cloud
operation here — writing leads from the bot, calling the LLM, uploading contracts, admin login — is
**server-side**. There is no JS runtime in the request path that can import the SDK.

**Decision (recommended):** Make the **Python backend the single cloud client**, wrapped in one
isolated module `app/cloud_client.py` that talks to the cloud REST surfaces with `httpx`
(`endpoint` + `publishableKey` from `publicConfig`). The dashboard stays a *thin* client of the
backend (it already is — it calls `/api/admin/*`), so the publish model is unchanged: **one Python
process, one `$PORT`**.

Why not a Node bridge? A Node sidecar using the real SDK would avoid hand-rolling REST, but the
publish runs a single HTTP port and would have to run a second process — extra deploy complexity.
The raw-REST Python wrapper is single-process and deployable. (If exact REST contracts prove fragile
during implementation, fall back to a thin Node bridge behind `localhost`.)

> The code-gen docs say "don't hand-write `fetch` against `/.cloud/*`" — that guidance assumes a JS
> SDK is available. For a Python backend there is no SDK, so an isolated `httpx` client is the only
> option and is the documented exception in spirit. It will be kept in **one file** and mirror the
> SDK's contract exactly.

---

## 2. Feature → Cloud module mapping

| Existing feature | Today | Cloud module | Cloud resource |
|---|---|---|---|
| Leads, Listings, Messages, Enquiries, Pending actions, Listing matches, Agent profile, Settings, Processed emails | SQLite (`app/db.py` + `schema.sql`) | **Database** (managed PostgreSQL / PostgREST) | 9 tables, owner-scoped RLS |
| All LLM calls: Alex replies, scoring, email extraction, copilot, matchmaker, briefing, re-engagement | `app/llm.py` → Hunyuan OpenAI-compat | **LLM** (keyless, streaming SSE) | cloud LLM API |
| Contract PDFs (`listings.contract_file` on disk) | local `data/contracts/*.pdf` | **Storage** (COS `runtime` bucket) | `runtime/shared/<uid>/contracts/` |
| Admin dashboard login (`ADMIN_DASHBOARD_KEY`) | static shared secret | **Auth** (email + password) | agent's cloud Auth account |
| Telegram bot, Gmail IMAP/SMTP intake, cron/follow-ups/briefings | local | — (no cloud needed) | stays on the backend |

**LLM is the single chokepoint** — every call site uses `app/llm.py` (`complete`, `chat`,
`complete_json`). Only that file changes for the LLM module.

---

## 3. Consuming `publicConfig`

On successful activation, `workbuddy_cloud_service` returns `publicConfig` with
`endpoint`, `publishableKey`, `oauthRelayBaseUrl`, `resourceId`. We will:

- Store these in `.env` (never hard-code, never commit secrets):
  `CLOUD_ENDPOINT`, `CLOUD_PUBLISHABLE_KEY`, `CLOUD_OAUTH_RELAY`, plus `CLOUD_ADMIN_EMAIL` /
  `CLOUD_ADMIN_PASSWORD` for the backend to obtain an agent session (see §5).
- Add to `app/config.py`: `cloud_endpoint`, `cloud_publishable_key`, `cloud_oauth_relay`,
  `cloud_admin_email`, `cloud_admin_password`, and a `use_cloud: bool` flag (defaults to
  `True` when `cloud_endpoint` is set). `use_cloud=False` keeps SQLite for **local dev** — do not
  break offline development.

---

## 4. Module-by-module plan

### A. LLM — do this first (lowest risk, decouples from Hunyuan)

Rewrite `app/llm.py` so `complete()`, `chat()`, `complete_json()` call the cloud LLM endpoint
instead of `AsyncOpenAI`. Key rules from the LLM code-gen doc:

- **Always `stream: true`** — non-streaming is rejected (`request_stream_required`). Collect the full
  text from SSE `ChatCompletionChunk` deltas (`choices[0].delta.content`).
- Every call **must** start with a `system` message. `complete()` already does; add a guard in
  `chat()` that prepends a default system message if `messages[0].role != "system"`.
- `chat()` must accumulate `tool_calls` by `index` (id/function.name/function.arguments), exactly as
  the doc shows — copilot (`copilot.py:208`) depends on this.
- One-shot `complete_json()` uses `stream:true` + `response_format:{type:"json_object"}` and parses
  the accumulated text (existing `parse_json_object` is reused).
- Pick the model from `cloud.llm.models.list()` at startup; store the chosen `id` in
  `settings.llm_model_chat` / `llm_model_task`. Drop the Hunyuan-specific
  `reasoning_effort` `extra_body` (not valid for cloud LLM).
- No `LLM_API_KEY` needed anymore (keyless channel authenticated by `publishableKey`).

Call sites that keep working unchanged: `leads.py`, `listings.py`, `matching.py`, `briefing.py`,
`reengagement.py`, `copilot.py`, `check.py`.

### B. Database — schema via MCP, access via `cloud_client`

1. **Schema + RLS via the DB MCP tools** (not app code) once cloud is active:
   - `workbuddy_cloudservice_db_exec_sql` (`mode: migrate`) to create the 9 tables, translating the
     SQLite schema to PostgreSQL: `INTEGER PK AUTOINCREMENT` → `BIGINT GENERATED ALWAYS AS IDENTITY`;
     `TEXT`/`TIMESTAMPTZ`; keep all `CHECK` constraints and `REFERENCES`.
   - Add `owner_id TEXT NOT NULL DEFAULT auth.uid()` to every business table.
   - `ENABLE ROW LEVEL SECURITY`; `GRANT SELECT,INSERT,UPDATE,DELETE ON ... TO authenticated`; policies
     `USING (owner_id = auth.uid())` / `WITH CHECK (owner_id = auth.uid())` (owner-only).
   - Indexes: re-create `idx_leads_email/phone/followup`, `idx_messages_lead`, `idx_listings_review_token`.
   - One statement per `exec_sql` call; `DROP POLICY IF EXISTS` for idempotency.
2. **`app/cloud_client.py`**: a PostgREST wrapper exposing `select/insert/update/delete` per table,
   injecting `apikey: {publishableKey}` and `Authorization: Bearer {agent_token}` headers, returning a
   `sqlite3.Row`-compatible adapter (dict subclass) so existing `row["col"]` / `dict(row)` call sites
   keep working.
3. **`app/db.py`**: keep the **same function signatures** (`query`, `query_one`, `execute`, `update`,
   `insert`, `get_lead`, `create_lead`, `match_listing`, …). Internally branch on `settings.use_cloud`:
   - `use_cloud=False` → current SQLite path (local dev).
   - `use_cloud=True` → `cloud_client` calls. **Never send `owner_id`** (DB fills `DEFAULT auth.uid()`);
     update `insert()` to drop `owner_id` from the payload.
4. **Ownership model**: the backend holds the agent's session token (see §5); all bot/intake writes
   therefore land under `owner_id = agent_uid`, satisfying RLS. The dashboard reads/writes as the same
   owner. No `SECURITY DEFINER` RPC needed.

### C. Auth — replace the static dashboard key

- `app/dashboard.py`'s `_require_admin` currently checks `ADMIN_DASHBOARD_KEY`. Replace with cloud Auth:
  - `POST /api/admin/login` takes `{email, password}`; backend calls cloud Auth sign-in
    (`/.cloud/auth/v1/signin`, email+password), stores the returned session (access + refresh token)
    server-side keyed by a secure HttpOnly cookie / returned bearer token.
  - Subsequent `/api/admin/*` requests send that token; the backend attaches it to cloud DB/Storage
    calls. If the gateway returns 401/RLS-denied, the backend returns 401 → dashboard shows login.
  - Keep `ADMIN_DASHBOARD_KEY` as an **escape-hatch** backdoor (only if `use_cloud=False` or auth
    fails) so we are never locked out.
- The agent's cloud Auth account (email+password) must exist — create it during/after activation.

### D. Storage — contracts to cloud

- `app/services/listings.py` (~line 66): on contract PDF receipt, **upload bytes** to
  `runtime/shared/<agent_uid>/contracts/<token>.pdf` via the Storage REST instead of writing to
  `settings.contracts_dir`. Store the object key in a **new column** `listings.contract_object`
  (keep `contract_url` for external Google-Doc links).
- `app/main.py` (`/contract/{token}`, ~line 249): generate a **signed download URL** via Storage and
  redirect (instead of `FileResponse` from disk).
- `import_excel.py` already sets `contract_url` for external links — unchanged.

---

## 5. How the backend authenticates to cloud (owner model)

At startup (when `use_cloud=True`):
1. Backend signs in to cloud Auth with `CLOUD_ADMIN_EMAIL` / `CLOUD_ADMIN_PASSWORD` → receives
   `access_token` + `refresh_token`.
2. Stores them in memory; refreshes via the auth endpoint before expiry.
3. Every cloud call (DB write, Storage upload, LLM) attaches `Authorization: Bearer {access_token}`.
   DB rows auto-fill `owner_id = auth.uid() = agent_uid`, satisfying RLS.

This makes the bot, the dashboard, and the agent all the **same owner** — clean, and it aligns admin
login with cloud Auth. (Simpler alternative if a stored admin password is undesirable: open RLS +
`publishableKey`-only writes, acceptable for a single-tenant internal tool. Recommended path above is
the secure one.)

---

## 6. Files to create / modify

| File | Change |
|---|---|
| `app/cloud_client.py` | **NEW** — `httpx` wrapper for Database/Auth/Storage/LLM REST; `Row` adapter |
| `app/config.py` | Add cloud settings + `use_cloud` flag |
| `.env` | Add `CLOUD_ENDPOINT`, `CLOUD_PUBLISHABLE_KEY`, `CLOUD_OAUTH_RELAY`, `CLOUD_ADMIN_EMAIL/PASSWORD` |
| `app/llm.py` | Rewrite to cloud LLM (streaming, system-message guard, model list) |
| `app/db.py` | Branch SQLite ↔ cloud; never send `owner_id` in cloud mode |
| `app/schema.sql` | Keep for local dev; cloud schema created via MCP instead |
| `app/dashboard.py` | `_require_admin` → cloud Auth session; login endpoint |
| `app/services/listings.py` | Contract upload → Storage |
| `app/main.py` | `/contract/{token}` → signed Storage URL |
| `app/services/copilot.py` | No change (uses `llm.chat`, which is rewritten) |

---

## 7. Execution order (after activation succeeds)

1. **Activate** cloud for `wbapp_T7sp5FS2HmvDIjEwqCM8RN` (reuse applicationId), capture `publicConfig`.
2. **Phase 1 — LLM**: rewrite `llm.py`; verify `check.py` ping + a copilot turn against cloud.
3. **Phase 2 — Database**: create tables+RLS via MCP; implement `cloud_client.py` + `db.py` branch;
   smoke-test lead create/list/status and listing review.
4. **Phase 3 — Auth**: dashboard login via cloud Auth; keep static-key backdoor.
5. **Phase 4 — Storage**: contract upload/serve via cloud.
6. **Phase 5 — Verify & republish** (with dashboard included, as before). Confirm `data/` is still
   excluded from publish.

---

## 8. Risks & open decisions

- **Activation still blocked** — the whole plan is gated on `backend-unavailable` clearing. No code
  changes until `publicConfig` is in hand.
- **REST contract fidelity** — exact paths (`/.cloud/database/rest`, `/.cloud/auth/v1/signin`,
  `/.cloud/llm/...`, `/.cloud/storage/...`) will be confirmed against the SDK/activation docs at
  implementation time; isolated in `cloud_client.py` so a fix is one file.
- **Stored admin password** — `CLOUD_ADMIN_PASSWORD` in `.env`. Acceptable for a single-admin
  internal tool; the secure-owner model depends on it. Alternative (open RLS) noted in §5.
- **Local dev parity** — `use_cloud=False` keeps SQLite so development isn't blocked by cloud state.
- **Publish caveat unchanged** — never publish `data/`; cloud DB removes the SQLite-reset concern but
  the rule stays.
