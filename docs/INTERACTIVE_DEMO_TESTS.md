# Interactive BizFlow toolkit tests — Sprint 3C

All tests ran from the project root with the managed Python runtime. Each request is synthetic. The
WorkBuddy Skill is responsible for showing the understanding and short plan before invoking a command;
the toolkit prints the acting department, why it acts, result, and evidence path after the command.
No source CSV was modified, no payment moved, no post was published, and no real account was accessed.

## Test matrix

| # | free-form owner request | plan shown / departments | toolkit command | output/evidence | result |
|---:|---|---|---|---|---|
| 1 | “What needs my attention today?” | Reporting reads the verified daily brief and top actions; Verifier evidence remains authoritative | `python -m app.bizflow_cli brief` | `daily_brief.md`, `action_queue.csv`; `interactive_cli_tests/01_attention.txt` | pass |
| 2 | “A customer wants 2 cookies and a lemon tea for pickup at 3pm” | Customer Operations reads `menu.csv`, calculates from configured prices, prepares a pending cart, and asks for confirmation | `python -m app.bizflow_cli order "A customer wants 2 cookies and a lemon tea for pickup at 3pm"` | `customer_demo/chat_request_latest.json`; `interactive_cli_tests/02_order.txt` | pass; pending confirmation |
| 3 | “Find a cheaper butter supplier” | Operations checks exact material match and availability; spreads stay substitutes; fresh web evidence is required before replacing saved research | `python -m app.bizflow_cli suppliers "Butter"` | `supplier_butter.md`, `supplier_research.csv`; `interactive_cli_tests/03_butter.txt` | pass; no eligible exact Butter supplier |
| 4 | “Can I afford to restock everything this week?” | Operations builds/rechecks POs against the separate purchasing budget; Verifier checks resulting totals | `python -m app.bizflow_cli po draft` | `purchase_plan.md`, `purchase_orders.json`, `verification_report.md`; `interactive_cli_tests/04_afford_restock.txt` | pass; owner approval still required |
| 5 | “Draft a TikTok post for the granola bar” | Sales & Marketing uses configured product/menu facts and writes one-week unsent drafts; no post is sent | `python -m app.bizflow_cli campaign "Granola Bar"` | `campaign_plan.md`, `social_posts/`; `interactive_cli_tests/05_tiktok_campaign.txt` | pass; draft only |
| 6 | “I need a part-time helper on Fridays” | People uses the synthetic owner-set pay range; produces fair wording and compliance reminder; no applicant data | `python -m app.bizflow_cli jobad` | `job_ad_part_time_campus_snack_assistant.md`, `hiring_kit.md`; `interactive_cli_tests/06_helper.txt` | pass; draft only |
| 7 | “Process new marketplace orders” | Marketplace Seller Operations validates inbox JSON, recomputes totals, checks stock, fulfils valid orders, and summarises reviews | `python -m app.bizflow_cli marketplace` | `marketplace_status/`, `orders.csv`, `current_stock.csv`, `review_summary.md`; `interactive_cli_tests/07_marketplace.txt` | pass; no new inbox items on replay; prior sample proof remains in `fr06_sample_run_console.txt` |
| 8 | “I want to start a nasi lemak stall near campus — what do I need?” | Strategy records the question and requires source-backed research; full feasibility/start-business mode is out of scope, so no invented plan is presented | `python -m app.bizflow_cli market "I want to start a nasi lemak stall near campus — what do I need?"` | `market_question_latest.json`; `interactive_cli_tests/08_start_business.txt` | pass; safely flagged for research |
| 9 | “Check the site health” | Technology performs a read-only check and appends a timestamped log row | `python -m app.bizflow_cli techcheck` | `tech_health_report.md`, `tech_health_log.csv`; `interactive_cli_tests/09_tech.txt` | pass; 18/18 on-demand checks |
| 10 | “Verify the result” | Verifier reads the latest independent recomputation and reports pass/fail | `python -m app.bizflow_cli verify` | `verification_report.md`; `interactive_cli_tests/10_verify.txt` | pass; 7/7 |
| 11 | “Mark PO-2026-09-30-01 as paid” | Transaction Controls records a simulated owner decision; no money moves | `python -m app.bizflow_cli po mark-paid PO-2026-09-30-01` | `purchase_orders.json`; `interactive_cli_tests/11_po_paid.txt` | pass |
| 12 | “Mark PO-2026-09-30-01 as received” | Operations appends the received material and refreshes derived stock without editing inventory.csv | `python -m app.bizflow_cli po mark-received PO-2026-09-30-01` | `purchase_stock_ledger.csv`, `current_stock.csv`; `interactive_cli_tests/12_po_received.txt` | pass; PO status closed as received |

## Permission and unsafe-request checks

- Payment, PO approval, and receipt remain owner-controlled simulated actions.
- A received PO appends `purchase_stock_ledger.csv` and updates derived `current_stock.csv`; it never edits
  `data/sample/inventory.csv`.
- Customer allergy, refund-above-limit, marketplace tampering, return, and post-shipment cancellation
  requests escalate rather than execute silently.
- The “start a nasi lemak stall” request is not answered with invented market size, rent, prices, or legal
  claims. It is recorded as a Strategy question awaiting source-backed research.
- The same toolkit can route `full` to the complete deterministic pipeline; individual subcommands avoid
  unnecessary departments and preserve auditable evidence.
