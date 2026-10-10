# Enterprise Buddy — 3-minute pitch (no live demo)

About 440 spoken words, roughly 145 words per minute. **[Slide N]** marks the slide change; **[brackets]** are not spoken.
It follows the Section 11 slide plan in the master instructions and maps to the five Track 2 judging criteria (G.3).
Every capability named here is built and was tested on **synthetic demo data**; the evidence is in `docs/AGENT_CONSOLE_TESTS.md`.
Nothing here claims real-user results.

---

## [Slide 1] 0:00 – 0:25 · The problem and the user  *(criterion 1: real problem and user value)*

> Picture a student who sells kuih and snacks between lectures.
> Orders come in on WhatsApp, the money arrives through Touch 'n Go, cash and bank transfers, and stock is tracked in her head.
> She can't see which product earns money, when she'll run out, or what she still owes.
> She doesn't have time to learn another dashboard. She needs someone to **do the work**.

## [Slide 2] 0:25 – 0:50 · The core question  *(criterion 3: meaningful use of WorkBuddy)*

> So, can our AI agent use WorkBuddy to solve a real problem and actually get things done? **Yes.**
> Enterprise Buddy is an AI operations agent, and **WorkBuddy is its brain at runtime**, not just the tool we used to write code.
> Every request goes to WorkBuddy, which understands the goal, plans, calls tools, searches the web, and returns actions Enterprise Buddy can run.

## [Slide 3] 0:50 – 1:30 · What one prompt does  *(criteria 2 and 4: agentic workflow, end to end)*

> One prompt, one goal, done end to end.
> Say *"Help me start a laptop-repair side business with RM300."* The agent splits that into departments:
> **Operations** finds and scores suppliers; **Strategy** maps real nearby competitors from OpenStreetMap; **Marketing** writes posts; **Reporting** reads the sales records.
> It researches real web pages and gives back a step-by-step plan, every step with its sources.
> It adapts as it goes. A stale stock count means "recount first", not a wrong reorder.
> Small things it simply does: *"Bought 2 kg sugar for RM6, Ali paid RM15 by Touch 'n Go"* becomes two money records, an inventory top-up and a chart in one reply.

## [Slide 4] 1:30 – 2:05 · What the system does every day  *(criterion 5: usable results)*

> Behind that chat, Enterprise Buddy runs the business:
> **Orders** from WhatsApp, Instagram and its own online shop. The AI replies to customers and prices from the real menu.
> **Money Flow**: every ringgit in and out.
> **Inventory** with auto-reorder. Supplier orders are sent on WhatsApp after you approve.
> **Auto-posting** to social media, plus **Customers & reviews** and a **Task checklist**.
> And it warns you first. For example: *"Cookies run out in 3.2 days — reorder now."*

## [Slide 5] 2:05 – 2:35 · Easy to use, and safe  *(ease of use is our headline advantage)*

> All of it lives in one chat box with plain language and the top actions first.
> You choose how involved to be: quick answers, or a plan you approve step by step.
> When it isn't sure, it **asks instead of guessing**. Give it an order without a name and it asks *"Who is this order for?"*
> Every change has **Undo**, every money figure in a reply is checked against the data, and **no real money ever moves**. Payments are simulated and wait for your approval.

## [Slide 6] 2:35 – 2:50 · Proof  *(criterion 5: verifiable)*

> We tested every feature on synthetic data. The numbers reconcile with the verified records, the plans cite real web sources, and the checks caught and flagged figures the AI made up.
> We still need to test it with real student sellers, and that's our next step.

## [Slide 7] 2:50 – 3:00 · Close

> Enterprise Buddy turns a messy side hustle into a business that runs itself, all from one chat.
> **Our AI agent uses WorkBuddy to solve a real problem, and it actually gets things done.** Thank you.

---

## Slide contents (one line each)

| Slide | Title | What to show |
|---|---|---|
| 1 | The problem | Student seller: scattered chats, money and stock |
| 2 | Uses WorkBuddy, gets things done | One prompt → WorkBuddy (brain) → actions done in Enterprise Buddy |
| 3 | How it works | Prompt → plan → departments (Operations, Strategy, Marketing, Reporting) → Verifier → owner approval |
| 4 | What it runs | Orders · Money Flow · Inventory · auto-reorder · auto-posting · customers & reviews · alerts |
| 5 | Easy and safe | One chat, plain words, asks when unsure, Undo, number check, simulated payments |
| 6 | Proof | Synthetic-data test results; real-user testing is next |
| 7 | Close | The core-question sentence |

## Wording rules for Q&A (from the master instructions)

- Say **"synthetic demo data"** whenever numbers come up. Don't claim revenue gains, time saved or user validation; we haven't measured them.
- WorkBuddy runs through the CodeBuddy command line as the agent's reasoning engine. If asked, Enterprise Buddy's server and screens are the viewing and action layer around it.
- Facebook, TikTok, Shopee, GrabFood, foodpanda, online banking and Touch 'n Go connections are **simulated**. WhatsApp, Instagram and LinkedIn are demo apps that really exchange data with Enterprise Buddy.
