# Presentation plan — Enterprise Buddy pitch

3-minute spoken pitch, no live demo (per Section 0.4). 7 slides, one visual each.
Source folder for screenshots: `presentation/screenshots/`. Evidence column links each slide to a row in `docs/AGENT_CONSOLE_TESTS.md` or a known run file in `data/output/console_runs/`.
The agent runtime is the **CodeBuddy CLI** (`codebuddy` 2.164.0) inside WorkBuddy — Enterprise Buddy's server and screens are the viewing and action layer around it.
All numbers shown are **synthetic demo data**; real-user testing is the next step.

| # | Slide title | Message on screen (≤ 25 words) | Visual | Evidence — test id / file | Judging criterion (G.3) |
|---|---|---|---|---|---|
| 1 | The problem and the user | "Orders on WhatsApp. Money in 22 sample chats — Touch 'n Go, online banking, cash. Stock tracked in her head. She needs someone to do the work." | Demo WhatsApp inbox with 14 customer chats visible | S4 (22 sample WhatsApp customers) · `presentation/screenshots/01_whatsapp.png` | 1 · Real problem & user value |
| 2 | The core question — WorkBuddy is the brain | "Can our AI agent use WorkBuddy to solve a real problem and actually get things done? Yes. WorkBuddy is the agent's runtime, not just the IDE we used to write code." | Enterprise Buddy Chat tab on Campus Crumb | F1 (codebuddy 2.164.0, stream-json events) · `console/agent_rules.md` · `presentation/screenshots/02_chat.png` | 3 · Meaningful use of WorkBuddy |
| 3 | One prompt → plan → departments → owner approval | One prompt, one goal, done end to end. Operations scores suppliers · Strategy maps competitors from OpenStreetMap · Guides drafts permits · Marketing drafts posts. Every step is cited. | Chat with the real plan and review panel from "I want to sell kuih at my campus near Universiti Malaya" (conversation `1010174017-288a`, run `171822-c203`), showing the OpenStreetMap competitor map (60 real places: 26 cafe, 23 fast food, 8 food court, 2 beverages, 1 bakery) | run `171822-c203` · S1 (Market map — competitors near UM) · test "I want to sell kuih at my campus near UM" · `presentation/screenshots/03_plan.png` | 2 · Agentic workflow + 4 · End-to-end execution |
| 4 | What the system runs every day | "Money Flow: MYR 2,507.25 in / MYR 1,172.30 out / MYR 1,334.95 kept — synthetic. Orders, Inventory with auto-reorder, Auto-posting, Customers & reviews, Task checklist. Heads-up: cookies run out in 3.2 days." | Money Flow page with KPI tiles, daily chart, customer-payment ledger, and supplier-order ledger | S7 (Money Flow reconciliation: in MYR 2,451.25 = verified revenue; out MYR 1,132.50; current page now includes customer-order payments) · Dashboard "cookies 3.2 days" · S2 (auto-reorder) · S3 (auto-reply WhatsApp orders) · `presentation/screenshots/04_money_flow.png` | 5 · Usable & verifiable results |
| 5 | Easy and safe | "Plain language. The owner chooses how involved. Asks instead of guessing. Undo on every change. Number check. No real money ever moves — payments simulated and approved." | Inventory page showing the "Approve & pay" / "Not now" gate, supplier options side-by-side, and "Why this amount? (sources)" expander | S2 (auto-reorder: 18 ≤ 20 → 2 × 1 kg chocolate chips MYR 39.80 with sources) · S9 (Undo verified for every change) · S8 (number check caught invented weekday figures) · "Bug: agent assumed the customer of an unnamed order" fix · `presentation/screenshots/07_inventory.png` | 5 · Usable & verifiable results (ease-of-use is the headline advantage) |
| 6 | Proof from the test log | "Tested every feature on synthetic data. The numbers reconcile. The plans cite real web sources. The number check caught and fixed figures the AI invented." | Rendered 14-row evidence table from the test log | F1, F2 · test 1 ("What needs my attention today?", 9 plan items, verifier PASS) · test 9 (prompt-injection refused) · test 10 (approve 2 / reject 1, budget MYR 694.70) · S1–S9 · `presentation/screenshots/11_proof.png` | 5 · Verifiable |
| 7 | Close | "Enterprise Buddy turns a messy side hustle into a business that runs itself, all from one chat. Our AI agent uses WorkBuddy to solve a real problem, and it actually gets things done." | The hero line; repo URL and one-liner to run it | — (closes the core question) | — (repeat of the core-question sentence) |

## Slide evidence — detail by slide

- **Slide 1 — WhatsApp screenshot** (`01_whatsapp.png`). The demo WhatsApp lives at `/whatsapp/?business_id=campus-crumb` and is built per `docs/DEMO_CHANNELS_API.md`. The 22 sample customers come from `console/wa_seed.py` (test log row S4: "22 sample WhatsApp customers, 5 menu-correct orders, no unanswered messages"). Touch 'n Go and online banking are simulated feeds; Money Flow shows them as `Online banking (DuitNow / FPX)` rows.
- **Slide 2 — Chat tab** (`02_chat.png`). The chat shows the live "How can I help Campus Crumb today?" landing with six suggested prompts that adapt to the business. The agent runtime is the CodeBuddy CLI (F1). The whitelist restricts the agent to read-only commands (F2). Real conversations are saved in `data/workspace/conversations/`; runs live in `data/output/console_runs/`.
- **Slide 3 — Plan + map** (`03_plan.png`). Conversation `1010174017-288a` ("I want to sell kuih at my campus near Universiti Malaya"); run `171822-c203`. The OpenStreetMap overlay shows 60 real competitor places inside 2 km of UM (test row "Market map — competitors near 'Universiti Malaya, Kuala Lumpur', 2 km").
- **Slide 4 — Money Flow** (`04_money_flow.png`). The Money Flow page renders verified figures from `console/money.py` and `app/appdata.py`. S7 records the reconciliation to the verified brief (in MYR 2,451.25 / out MYR 1,132.50); the current page shows higher in/out because more customer-order payments and supplier payments have landed since the test was logged. Test row S2 records the cookies-stocked-out-in-3.2-days alert.
- **Slide 5 — Inventory** (`07_inventory.png`). The Inventory page lists 17 ingredients with stock bars and per-row supplier pickers, plus the supplier-order card with "Approve & pay" and "Not now" buttons. The "Why this amount?" expander links to the sources row in `docs/AGENT_CONSOLE_TESTS.md` S2. The "Who is this order for?" question is from the fix logged under "Bug: agent assumed the customer of an unnamed order".
- **Slide 6 — Proof** (`11_proof.png`). Rendered from `docs/AGENT_CONSOLE_TESTS.md`; every row is a real pass or fix in that file. Numbers shown (e.g. MYR 39.80, MYR 21.50, MYR 694.70, 60 places) are the literal values written in those tests.

## Run the pitch

1. Open `presentation/Enterprise_Buddy_Pitch.pptx` in PowerPoint, Keynote or Google Slides.
2. Each slide has speaker notes with timing and a one-line criterion tag.
3. The runtime to show alongside is `python console/server.py` on `PORT=8091` → `http://127.0.0.1:8091` (Choose **Continue as guest**, default business is Campus Crumb). Demo apps at `/whatsapp/`, `/shop/`, `/instagram/`, `/linkedin/`.
4. If the schedule is shorter than 3 minutes, cut slide 6 first (the proof survives in the speaker notes and in `docs/AGENT_CONSOLE_TESTS.md`).

## Honest scope line for the vision slide (per Section 0.5)

What is built and tested is in this plan. Anything else — recruiting at scale, real WhatsApp Business Platform, real marketplace connections, full customer-support agent, "Start my business" feasibility — is on the vision slide as **"coming next"**, never presented as working today.

## Open questions for the organisers (carry-over from Section G.8)

- Scoring weight of each of the five Track 2 criteria.
- The actual pitch/demo duration (Section 0.4 assumes 3 minutes; we will scale the script if asked).
- Submission format and venue — the script is ready for in-person, but a pre-recorded video and the GitHub repo are also available.