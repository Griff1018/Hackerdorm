-- All timestamps are ISO-8601 UTC text (e.g. 2026-10-08T05:23:00+00:00).
-- Display formatting/timezone happens in the app, never in stored values.

CREATE TABLE IF NOT EXISTS agent_profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    agent_name          TEXT NOT NULL DEFAULT '',
    agency              TEXT NOT NULL DEFAULT '',
    service_areas       TEXT NOT NULL DEFAULT '',
    working_hours       TEXT NOT NULL DEFAULT '',
    phone_number        TEXT NOT NULL DEFAULT '',
    include_phone       INTEGER NOT NULL DEFAULT 0,   -- 1 = Alex may share the agent's number
    commission_policy   TEXT NOT NULL DEFAULT '',
    marketing_services  TEXT NOT NULL DEFAULT '',
    mortgage_partner    TEXT NOT NULL DEFAULT '',
    conveyancer_partner TEXT NOT NULL DEFAULT '',
    showing_style       TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    address            TEXT NOT NULL,
    property_type      TEXT NOT NULL DEFAULT '',
    asking_price       TEXT NOT NULL DEFAULT '',
    method_of_sale     TEXT NOT NULL DEFAULT '',
    auction_date       TEXT NOT NULL DEFAULT '',
    layout_specs       TEXT NOT NULL DEFAULT '',
    aspect             TEXT NOT NULL DEFAULT '',
    parking            TEXT NOT NULL DEFAULT '',
    inclusions         TEXT NOT NULL DEFAULT '',
    outdoor_features   TEXT NOT NULL DEFAULT '',
    tenancy_income     TEXT NOT NULL DEFAULT '',
    zoning             TEXT NOT NULL DEFAULT '',
    easements          TEXT NOT NULL DEFAULT '',
    strata_status      TEXT NOT NULL DEFAULT '',
    strata_levies      TEXT NOT NULL DEFAULT '',
    council_rates      TEXT NOT NULL DEFAULT '',
    water_rates        TEXT NOT NULL DEFAULT '',
    pet_policy         TEXT NOT NULL DEFAULT '',
    rental_policy      TEXT NOT NULL DEFAULT '',
    upgrades           TEXT NOT NULL DEFAULT '',
    vendor_terms       TEXT NOT NULL DEFAULT '',
    occupancy_access   TEXT NOT NULL DEFAULT '',
    inspection_windows TEXT NOT NULL DEFAULT '',
    contract_file      TEXT,                          -- filename under DATA_DIR/contracts
    contract_url       TEXT,                          -- external link (e.g. imported Google Doc)
    listing_url        TEXT,
    status             TEXT NOT NULL DEFAULT 'DRAFT'
                       CHECK (status IN ('DRAFT', 'SELLING', 'SOLD', 'WITHDRAWN')),
    review_token       TEXT UNIQUE,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL DEFAULT '',
    email               TEXT,
    phone               TEXT,
    telegram_chat_id    TEXT UNIQUE,
    telegram_username   TEXT,
    link_code           TEXT NOT NULL UNIQUE,         -- t.me/<bot>?start=<link_code>
    lead_type           TEXT NOT NULL DEFAULT 'UNKNOWN'
                        CHECK (lead_type IN ('BUYER', 'SELLER', 'DUAL', 'UNKNOWN')),
    property_address    TEXT NOT NULL DEFAULT '',
    listing_id          INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    source              TEXT NOT NULL CHECK (source IN ('EMAIL', 'TELEGRAM', 'IMPORT')),
    status              TEXT NOT NULL DEFAULT 'INITIATED'
                        CHECK (status IN ('INITIATED', 'IN_PROGRESS', 'QUALIFIED', 'NEEDS_AGENT', 'BANNED')),
    is_returning        INTEGER NOT NULL DEFAULT 0,
    -- Qualification result (NULL until scored)
    timeline            TEXT,
    budget              TEXT,
    pre_approval        TEXT,
    score               INTEGER CHECK (score BETWEEN 0 AND 10),
    score_reason        TEXT,
    is_qualified        INTEGER,                      -- 1 yes / 0 no / NULL not assessed
    notes               TEXT,
    qualified_at        TEXT,
    -- Re-engagement
    followup_step       INTEGER NOT NULL DEFAULT 0,   -- next step to send, 0..len(schedule)
    followup_anchor_at  TEXT,                         -- last real conversation turn
    next_followup_at    TEXT,
    last_contacted_at   TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_followup ON leads(status, next_followup_at);

-- Replaces the Chat_History text blob: one row per message.
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id    INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('lead', 'ai', 'agent')),
    channel    TEXT NOT NULL CHECK (channel IN ('telegram', 'email')),
    kind       TEXT NOT NULL DEFAULT 'chat',          -- chat | enquiry | opener | followup
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_lead ON messages(lead_id, id);

-- Each inbound enquiry email (a returning lead gets a new row here, not a duplicate lead).
CREATE TABLE IF NOT EXISTS enquiries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id          INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    property_address TEXT NOT NULL DEFAULT '',
    lead_type        TEXT NOT NULL DEFAULT 'UNKNOWN',
    message          TEXT NOT NULL DEFAULT '',
    email_subject    TEXT,
    email_from       TEXT,
    received_at      TEXT NOT NULL
);

-- Idempotency for the IMAP poller.
CREATE TABLE IF NOT EXISTS processed_emails (
    message_id   TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,                       -- lead | listing | skipped | error
    detail       TEXT,
    processed_at TEXT NOT NULL
);

-- Agent-proposed side effects (messages to leads, status changes) awaiting the agent's
-- Approve/Cancel tap in Telegram. Nothing here runs without a human decision.
CREATE TABLE IF NOT EXISTS pending_actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,                         -- send_message_to_lead | set_lead_status | set_listing_status
    payload    TEXT NOT NULL,                         -- JSON arguments
    summary    TEXT NOT NULL,                         -- human-readable description shown with the buttons
    source     TEXT NOT NULL DEFAULT 'copilot',       -- copilot | matchmaker
    status     TEXT NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING', 'DONE', 'CANCELLED', 'FAILED', 'EXPIRED')),
    result     TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

-- Listing <-> lead matches found by the matchmaker (prevents re-proposing the same pair).
CREATE TABLE IF NOT EXISTS listing_matches (
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    lead_id    INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    fit_score  INTEGER NOT NULL,
    reason     TEXT,
    action_id  INTEGER REFERENCES pending_actions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (listing_id, lead_id)
);
