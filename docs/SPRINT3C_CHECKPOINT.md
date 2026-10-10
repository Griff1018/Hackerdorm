# Sprint 3C Checkpoint — Interactive Enterprise Buddy inside WorkBuddy

## Completed

### 1. Deterministic toolkit

Added `app/enterprise_buddy_cli.py` with these selectable subcommands:

`brief` · `stock` · `suppliers <material>` · `po draft|mark-paid|mark-received` · `order <message>` ·
`faq <question>` · `refund <order> <amount>` · `marketplace` · `reviews` · `campaign <product>` · `jobad` ·
`market <question>` · `techcheck` · `verify` · `full`.

The toolkit prints the acting department and reason before the local operation, then prints the result and
evidence path. The updated Skill requires WorkBuddy to add the natural-language understanding, short plan,
adaptation narration, verification and owner-approval closeout around those calls.

Numbers remain deterministic. The LLM does not set prices, totals, stock, supplier scores, discounts, or
refund outcomes.

### 2. Live Mode

`demo/index.html` now renders generated files rather than feature descriptions:

- real top-three action rows and daily brief
- supplier top-three cards with score breakdowns, availability/material-match status, retrieval dates and source links
- no-eligible and quotation-gap cases
- draft PO cards with local simulated paid/received controls
- customer order board and chat bubbles
- campaign post cards
- owner-set job ad and hiring-kit link
- marketplace status and simulated shipping-label link
- review summary with allergy escalation highlighted
- auto-refreshing Latest activity panel from `run_log.jsonl`

### 3. Demo Mode

All ten scenario steps now show a visual table, chat transcript, PO card, shipping label, post preview,
People card, or owner-control card. The banner, badges, reset, Live/Demo separation and friendly offline
failure remain active.

### 4. Paid → received loop

`app/enterprise_buddy_po_actions.py` provides owner-controlled simulated state transitions:

```text
draft → paid → received
```

`mark-received` appends `purchase_stock_ledger.csv`, adds raw-material rows to derived `current_stock.csv`,
closes the PO, and never modifies `data/sample/inventory.csv`.

### 5. WorkBuddy start command

`README.md` now gives the one-line command:

```bash
python -m http.server 8080
```

Opening the page without a server shows a friendly instruction instead of pretending that live files loaded.

## Evidence

- `tests/test_engine.py`: **24/24 passed**
- `tests/test_features.py`: **3/3 passed**
- `tests/test_sprint3b.py`: **3/3 passed**
- `tests/test_po_actions.py`: **1/1 passed**
- Toolkit help exposes all requested subcommands.
- Twelve interactive routes are recorded in `docs/INTERACTIVE_DEMO_TESTS.md` with the prompt, department
  plan, command, evidence file and result.
- Skill package revalidated at `data/output/enterprise-buddy-pipeline.zip`.
- Project source CSVs remained protected; received-stock test confirms `inventory.csv` byte identity.

## Known limits

1. The external marketplace store path was not supplied. FR-06 is complete against the project-owned
   Section 14.3 synthetic inbox contract; no external connection is claimed.
2. At the current checkpoint time, the requested 16:35 threshold has not yet been reached. The hourly
   Automation is active and has manual/activation-proof rows, but U1 must remain untested until a genuine
   scheduler-produced row after 16:35 is identified in `tech_health_log.csv`.
3. Live Mode PO buttons show local browser review state; persistent paid/received state uses the toolkit
   commands, so the demo cannot imply that a static HTTP server wrote files.

## Schedule

Sprint 3C did not cut verification or the protected schedule. Sprint 4 testing remains due by **00:00**
and Sprint 5 slides/rehearsal remain due by **03:00**.

**Sprint 3C is complete.**
