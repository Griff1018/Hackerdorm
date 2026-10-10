# Enterprise Buddy demo script — Sprint 3C

## Start

From the project root run:

```bash
python -m http.server 8080
```

Open `http://localhost:8080/demo/`. Say: “This is synthetic Campus Crumb data. Live Mode reads the
latest real generated files; Demo Mode is the labelled, reproducible walkthrough.”

## Live Mode — show evidence

1. Toggle **Live Mode**. Point to the auto-refresh Latest activity panel.
2. Show **Overview**: revenue, action count, Verifier and Technology status.
3. Open **Attention**: top three action rows and daily brief.
4. Open **Suppliers**: score breakdown, source links, unavailable/substitute/no-eligible cases.
5. Open **POs**: show a draft, local mark-paid/mark-received controls, and explain the persistent toolkit commands.
6. Run `python -m app.enterprise_buddy_cli po mark-paid <PO>` then `python -m app.enterprise_buddy_cli po mark-received <PO>`
   when the owner approves; show `purchase_stock_ledger.csv` and `current_stock.csv` changing without editing inventory.csv.
7. Open **Customer ops**: order board and chat bubbles; highlight the allergy/refund permission boundary.
8. Open **Campaign** and **People**: LIVE FEATURE draft outputs, not automatic posting or hiring.
9. Open **Marketplace**: completed seller-side status, simulated label and review summary; highlight P1 allergy escalation.

## Demo Mode — ten visual steps

Toggle Live Mode off. Use Next through the ten-step scenario. Every step contains a table, chat bubble,
PO card, label, post preview, or owner-control card. Keep the banner and badge language visible. Reset once
to prove reproducibility.

## WorkBuddy interactive prompt moment

Use one free-form request such as:

> A customer wants 2 cookies and a lemon tea for pickup at 3pm.

WorkBuddy states understanding and plan, says Customer Operations is acting, runs:

```bash
python -m app.enterprise_buddy_cli order "A customer wants 2 cookies and a lemon tea for pickup at 3pm"
```

Then it summarises the pending cart and evidence file. It does not confirm until the customer confirms.

## Safety close

Say: “Everything marked LIVE ran from files and deterministic code. POs, refunds, posts, hiring and
external marketplace connection remain owner-controlled. No real money moved, no real post was published,
and no credentials were requested or stored.”
