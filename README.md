# Enterprise Buddy — The AI Operations Agent for Microbusinesses

## Quick start

```bash
python console/server.py
```
Open `http://127.0.0.1:8090` (Enterprise Buddy), `/instagram/` (mock Instagram) and `/linkedin/` (mock LinkedIn).
Needs Python 3.11+ (standard library only) and the WorkBuddy / CodeBuddy CLI (`codebuddy`) installed and logged in.

## Repository layout

| folder | what it is |
|---|---|
| `console/` | Enterprise Buddy Agent Console — web app + server (`server.py`), agent rules, automations, inbox, tasks, workspace |
| `app/` | Deterministic Enterprise Buddy toolkit (`python -m app.enterprise_buddy_cli …`): pipeline, suppliers, map, scraper, guides, POs |
| `data/sample/` | Synthetic demo business data (Campus Crumb) · `data/guides/` official how-to guides · `data/output/` toolkit outputs |
| `instagram_mock/`, `linkedin_mock/` | Demo social apps, served by the console and connected to Enterprise Buddy (no API keys) |
| `docs/` | Project docs, test log (`AGENT_CONSOLE_TESTS.md`), channel API (`DEMO_CHANNELS_API.md`) |
| `planning_docs/` | WorkBuddy master instructions, prompts and feature requests used to build the project |
| `tests/`, `scripts/`, `skills/`, `demo/` | Unit tests, data scripts, the WorkBuddy skill, the original demo site |

Chats, uploads and other runtime state live in `data/workspace/` and are not committed; the console recreates demo defaults on first start.

---

**Status:** Agent Console with chat, plan review, automations, online requests and demo channels — see `docs/AGENT_CONSOLE_TESTS.md`. Deadline 09:30 on 2026-10-11.

Core promise: *from business data to verified business actions.*
Track: **Track 2 — WorkBuddy Track: Agentic Solutions.** Built and presented in **Tencent WorkBuddy**.

## What it will do

One prompt from a student seller → Enterprise Buddy validates their CSV records, computes explainable metrics,
researches suppliers for every raw material, checks the market, keeps the demo site healthy,
independently verifies its own numbers, and hands back a prioritised, evidence-backed action queue —
drafts only, nothing sent, ordered or paid.

## Layout

```
README.md  PROJECT_STATUS.md  DECISIONS_LOG.md  ASSUMPTIONS_AND_RISKS.md  CHANGELOG.md
docs/     charter, requirements, architecture, data dictionary, capabilities,
          agent workflow, feasibility checklist, dependencies, feature requests,
          master-instructions extract
data/     sample/  (synthetic inputs)      output/ (run outputs, from Sprint 2)
scripts/  generate_sample_data.py          (regenerates sales.csv, seed 20261010)
tests/    EXPECTED_RESULTS.md (golden)     fixtures/ (mini fixture, supplier-score fixture)
          compute_expected_standalone.py   (independent reference calculator)
demo/ presentation/ app/ skills/           (populated in later sprints)
```

## Start the interactive demo

From the project root, run this one-line command:

```bash
python -m http.server 8080
```

Then open `http://localhost:8080/demo/`. If the page is opened directly as a file, it will show a friendly
message asking for this server because browsers block the local generated-file fetches from `file://`.

## Start the live Agent Console (WorkBuddy as the brain)

```bash
python console/server.py
```

Then open `http://127.0.0.1:8090`. Type any request; the WorkBuddy CLI plans live using the Enterprise Buddy toolkit
(read-only commands only), the plan waits for your approval, and only approved items are executed by the
console from a fixed whitelist. "Reset demo state" restores the purchase orders and other changed files.
Requires the `codebuddy` CLI to be installed and logged in.
Tabs in the console: **Agent** (live plan → approve → execute), **Market map** (real nearby similar stores and
supply shops from OpenStreetMap, no API key), **Suppliers** (scraped image, item name, current listed price,
online/offline ordering; "Buy this…" asks Online → delivery location on a map, or Offline → shop on a map with
directions), **Guides** (official how-to for SSM, food handler + typhoid, council licence, campus permission,
halal, MeSTI, tax, and Enterprise Buddy actions). New toolkit commands: `nearby "<area>" [--kind suppliers]`,
`scrape [url]`, `guide "<topic>"`, `po list`. Tests: `docs/AGENT_CONSOLE_TESTS.md`.

## Quick commands

```bash
python scripts/generate_sample_data.py                     # regenerate data/sample/sales.csv
python tests/compute_expected_standalone.py                # golden values for data/sample
python -m app.enterprise_buddy_cli brief                            # route one owner request to Reporting
python -m app.enterprise_buddy_cli full                             # run the complete deterministic toolkit
python tests/compute_expected_standalone.py \
    --data tests/fixtures/golden_mini --name golden_mini   # golden values for the mini fixture
```

## Ground rules in force

- **Synthetic demonstration data only.** No real business, person or payment data.
- **No secrets** in files, prompts, screenshots or slides.
- Numbers come from deterministic code, never from model arithmetic.
- Nothing is posted, ordered or paid; consequential actions are drafts awaiting the owner.
- Every capability's status is in `docs/CAPABILITIES.md`; only "built and tested" items may be
  presented as working.

This README is a draft; `docs/` is the authoritative detail. It will be rewritten from the actual
implementation in Sprint 5 (Task 9).
