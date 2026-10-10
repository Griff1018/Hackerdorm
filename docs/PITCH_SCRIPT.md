# Enterprise Buddy — 3-minute pitch (no live demo)

About 430 spoken words, roughly 145 words per minute. **[Slide N]** marks the slide change; **[brackets]** are not spoken.
It follows the Section 11 slide plan in the master instructions and maps to the five Track 2 judging criteria (G.3).
Every claim below is backed by a row in `docs/AGENT_CONSOLE_TESTS.md`; the source column lists the test id.
The agent runtime is the **CodeBuddy CLI** (`codebuddy` 2.164.0) inside WorkBuddy — Enterprise Buddy's web console is the viewing and action layer around it.
Nothing here claims real-user results. All numbers are **synthetic demo data**.

---

## [Slide 1] 0:00 – 0:25 · The problem and the user  *(criterion 1: real problem and user value)*

> Picture a student who sells kuih and snacks between lectures.
> Orders come in on WhatsApp — twenty-two sample customers in our inbox — and the money arrives through Touch 'n Go, online banking and cash.
> Stock is tracked in her head. She can't see which product earns money, when she'll run out, or what she still owes.
> She doesn't have time to learn another dashboard. She needs someone to **do the work**.

## [Slide 2] 0:25 – 0:50 · The core question  *(criterion 3: meaningful use of WorkBuddy)*

> So, can our AI agent use WorkBuddy to solve a real problem and actually get things done? **Yes.**
> Enterprise Buddy is an AI operations agent, and **WorkBuddy is its brain at runtime**, not just the tool we used to write code.
> Every request goes to WorkBuddy. It understands the goal, plans, calls our read-only toolkit, searches the web, and returns actions.

## [Slide 3] 0:50 – 1:30 · What one prompt does  *(criteria 2 and 4: agentic workflow, end to end)*

> One prompt, one goal, done end to end.
> Say *"I want to sell kuih at my campus near Universiti Malaya."* WorkBuddy splits the job: **Operations** scores suppliers, **Strategy** maps real nearby competitors from OpenStreetMap, **Guides** drafts the permits checklist, **Marketing** writes posts.
> Every step cites a real web page or the owner's own records.
> A stale stock count triggers "recount first", not a wrong reorder.
> Small things it simply does: *"Bought 2 kg sugar for RM6, Ali paid RM15 by Touch 'n Go"* becomes two money entries, an inventory top-up and a chart in one reply.

## [Slide 4] 1:30 – 2:05 · What the system runs every day  *(criterion 5: usable results)*

> Behind that chat, Enterprise Buddy runs the business.
> **Orders** from WhatsApp, Instagram and its own online shop — the AI replies and prices from the real menu.
> **Money Flow**: every ringgit in and out — MYR 2,507.25 in, MYR 1,172.30 out, MYR 1,334.95 kept, on synthetic demo data.
> **Inventory** with auto-reorder. Supplier orders go to the supplier's WhatsApp after you approve.
> **Auto-posting**, **Customers & reviews**, a **Task checklist** — and it warns you first: *"Cookies run out in 3.2 days — reorder now."*

## [Slide 5] 2:05 – 2:35 · Easy to use, and safe  *(ease of use is our headline advantage; criterion 5)*

> All of it lives in one chat box with plain language and the top actions first.
> You choose how involved to be: quick answers, or a plan you approve step by step.
> When it isn't sure, it **asks instead of guessing**. An order with no customer name gets *"Who is this order for?"*
> Every change has **Undo**, every MYR figure in a reply is checked against the data, and **no real money ever moves**. Payments are simulated and wait for your approval.

## [Slide 6] 2:35 – 2:50 · Proof  *(criterion 5: verifiable)*

> We tested every feature on synthetic data. The numbers reconcile with the verified brief, plans cite real web sources, and the number check caught and fixed figures the model invented.
> We still need to test it with real student sellers — that's our next step.

## [Slide 7] 2:50 – 3:00 · Close

> Enterprise Buddy turns a messy side hustle into a business that runs itself, all from one chat.
> **Our AI agent uses WorkBuddy to solve a real problem, and it actually gets things done.** Thank you.

---

## Slide contents (one line each)

| Slide | Title | What to show | Source (test id) |
|---|---|---|---|
| 1 | The problem | Student seller: 22 sample customers, scattered chats, money and stock | S4, S3 |
| 2 | Uses WorkBuddy, gets things done | One chat box — WorkBuddy is the brain | F1 |
| 3 | How one prompt runs end to end | Plan with step chips + real competitor map from OpenStreetMap | S1, run `171822-c203` |
| 4 | What it runs every day | Money Flow tiles + chart (MYR 2,507.25 / 1,172.30 / 1,334.95) | S7, S5, S6, S2 |
| 5 | Easy and safe | Inventory: "Approve & pay" / "Not now" gate, sources, supplier options | S2, S9, S8 |
| 6 | Proof | 14-row evidence table from the test log | F1, F2, 1, 9, 10, S1–S9 |
| 7 | Close | The hero — Enterprise Buddy logo line | — |

## Claim → test-log evidence (full traceability)

| Claim in the script | Test-log row |
|---|---|
| 22 sample WhatsApp customers, no unanswered messages | S4 (2026-10-11 — 22 sample WhatsApp customers) |
| WorkBuddy CLI live, stream-json, `codebuddy 2.164.0` | F1 (CLI available + streaming) |
| Read-only toolkit; non-whitelisted writes denied | F2 (tool restriction) |
| "Sell kuih at campus near UM" → Operations, Strategy, Guides, Marketing, with map | test "I want to sell kuih at my campus near UM" (Feature update, 17:00–17:30) — run `171822-c203` |
| OpenStreetMap competitor map: 60 places, 26 cafe, 23 fast food, 8 food court | "Market map — competitors near 'Universiti Malaya, Kuala Lumpur', 2 km" |
| "Bought 2 kg sugar for RM6, Ali paid RM15 by Touch 'n Go" — money in + inventory + chart | "Chat: 'Today I bought 2 kg sugar for RM6, Ali paid RM15 by TNG…'" (2026-10-10 chat-first) |
| WhatsApp / Instagram / online shop order flow with AI-priced replies | S3 (Auto-reply WhatsApp), S6 (Online shop), S4 (22 samples) |
| MYR 2,507.25 in / 1,172.30 out / 1,334.95 kept (Money Flow) | S7 (Money Flow reconciliation: in 2,451.25 = verified revenue; out 1,132.50); current 2,507.25 includes customer-order payments after the test was logged |
| Auto-reorder on real data with sources | S2 (Auto-reorder low stock) |
| "Cookies run out in 3.2 days" | Today page header "Chocolate Chip Cookies (6pcs) runs out in 3.2 days" (Dashboard numbers) |
| Ask "Who is this order for?" when name missing | "Bug: agent assumed the customer of an unnamed order" fix |
| Undo on every change | S9 (Undo for every change) |
| Number check catches invented figures | S8 (Number check catches invented figures) |
| Approve 2 / reject 1, budget reconciliation MYR 694.70 | test 10 (Approve 2, reject 1) |
| Prompt-injection refusal logged | test 9 (Prompt injection) |
| "WorkBuddy is the brain at runtime" | F1 (CLI streams) + `console/agent_rules.md` (rules + owner request go in through stdin) |

## Wording rules for Q&A (from the master instructions)

- Say **"synthetic demo data"** whenever numbers come up. Don't claim revenue gains, time saved or user validation; we haven't measured them.
- WorkBuddy runs through the **CodeBuddy CLI** as the agent's reasoning engine. If asked, Enterprise Buddy's server and screens are the viewing and action layer around it.
- **Live demo apps:** WhatsApp, Instagram, LinkedIn, Enterprise Buddy Shop — these exchange data with Enterprise Buddy (`docs/DEMO_CHANNELS_API.md`).
- **Simulated connections:** Facebook, TikTok, Shopee (real Shopee agent exists, but shop data is synthetic), GrabFood, foodpanda, online banking and Touch 'n Go — the badge says SIMULATED.
- All payments are SIMULATED; no real money moves; the demo site has no field for cards or passwords.
- Real-user testing with student sellers is the next step. Do not claim results we have not measured.

## Honest scope line for the vision slide

What is built and tested is in this script. Anything else — recruiting at scale, real WhatsApp Business Platform, real marketplace connections, full customer-support agent, "Start my business" feasibility — is on the vision slide as **"coming next"**, never presented as working today.