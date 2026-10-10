# Enterprise Buddy Feature Update 02 — Social Media Promotion, Recruitment Assistant & Demo Mode

**For:** Tencent WorkBuddy, sent by the user at a sprint checkpoint/gate  
**Date:** 2026-10-10  
**Applies to:** `EnterpriseBuddy_WorkBuddy_Master_Instructions.md` (Section A feature-request rule, Sections G.9, G.13, G.16, G.17); works with Feature Update 01 if it was sent.

---

## 0. How to process this update (read first)

This update has **three feature requests**. Handle each with the feature-request rule in Section A of the master instructions:

- **FR-02 — Demo Mode** for the idea-pitching session (highest priority).
- **FR-03 — Social media promotion** (expands the existing Sales & Marketing department).
- **FR-04 — Recruitment assistant** (new People department).

1. Log FR-02, FR-03 and FR-04 in `docs/FEATURE_REQUESTS.md`.
2. Check the time left before the 09:00 submission target and the current sprint.
3. For each request, estimate the build and test time for the options in Section 5, say what each would delay or cut, and mark one option as **recommended**.
4. **STOP** and wait for the user's choices.
5. After the user picks: build only what was chosen, test it, update `docs/CAPABILITIES.md`, `docs/AGENT_WORKFLOW.md`, `PROJECT_STATUS.md`, `DECISIONS_LOG.md`, `CHANGELOG.md` and the slide plan. Then continue to the next gate; before slides, the G.13 gate is presented again.

---

## 1. FR-02 — Demo Mode (for the pitch)

### 1.1 What it is

The demo site gets **two clearly separated modes**, switched by a toggle at the top:

| | **Live Mode** | **Demo Mode** |
|---|---|---|
| Purpose | Prove the real agent works | Pitch the full idea, including features not built yet |
| Data | Outputs of the latest real run (`data/output/`) | A fixed, scripted scenario (`demo/scenario/`), synthetic |
| What it shows | Only capabilities that really ran | The whole vision as a guided walkthrough |
| Rule | No hard-coded numbers (Section 7.3) | Pre-written content is allowed **because it is labelled** |

### 1.2 How Demo Mode works

- **Guided walkthrough:** a step-by-step story with **Next / Back** buttons and a progress bar, about **3 minutes** end to end so it fits the pitch.
- **Suggested story (synthetic shop “Campus Crumb”):**
  1. The owner types one prompt and picks the involvement mode.
  2. The departments start working, shown as a live-looking activity feed.
  3. Operations finds low stock and shows the top-3 supplier comparison.
  4. Reporting shows the daily brief and the top 3 actions.
  5. A customer orders in the WhatsApp-style chat, with an add-on offer, and stock drops (Feature Update 01).
  6. Marketing produces a one-week social media campaign (FR-03).
  7. The People department sees busy days ahead and drafts a part-time job ad for JobStreet and Facebook (FR-04).
  8. The Technology hourly health check catches a broken shop-page price.
  9. The owner approves → a ready-to-pay PO plus the simulated checkout.
  10. Close on a summary of what was done, the time taken, and what needed the owner's approval.
- **Every screen carries a badge**, so nobody is misled:
  - **LIVE FEATURE**: built and tested (matches `docs/CAPABILITIES.md`).
  - **PROTOTYPE**: partly built, or simulated.
  - **CONCEPT**: not built; roadmap only.
- **A banner is always visible in Demo Mode:** “DEMO MODE — illustrative walkthrough with synthetic data. Features marked CONCEPT are not built yet.”
- **Works offline and is reproducible.** The same clicks always show the same content, so it doubles as the **backup** if the live run or the internet fails. When it is used as a backup, the presenter says so (Section 11: never fake a live run).
- **Reset:** a one-click reset back to step 1.
- **Separate data:** scenario content lives in `demo/scenario/` (JSON/Markdown). Live Mode must never read from it, and Demo Mode must never write to `data/output/`.

### 1.3 Rules for Demo Mode

- Badges must match `docs/CAPABILITIES.md` at the time of the pitch. A feature may not be badged LIVE FEATURE unless it is `built and tested` there.
- Demo numbers should be consistent with the synthetic dataset where possible. Where they are invented for a CONCEPT screen, label them “example figures”.
- No real brands' logos (WhatsApp, JobStreet, Facebook, Instagram, TikTok) are used as if connected. Use text such as “JobStreet-ready job ad (draft)”.
- The pitch script (`docs/DEMO_SCRIPT.md`) states which parts are shown in Live Mode and which in Demo Mode.

---

## 2. FR-03 — Social media promotion (expands Sales & Marketing)

### 2.1 What it does

Today Marketing drafts **one** promo post. FR-03 turns this into a small **campaign planner**:

- **Trigger and goal:** reuses the existing documented triggers (slow-moving or overstocked product, a new bundle in `promotions.csv`), plus an owner-chosen goal (for example “sell 30 more cookies this week”).
- **One-week content calendar:** what to post, on which platform, and on which day. Platforms: Instagram (post and story), TikTok (short video script), Facebook (post or campus group), WhatsApp Status.
- **Platform-ready drafts:** caption, hashtags, call to action, and a simple image or video brief (what to photograph or film). Prices and offers come **only** from `menu.csv`/`promotions.csv`/`products.csv`.
- **Posting times:** labelled “general guideline, not based on your data”, unless the business has its own engagement data.
- **Optional ad-budget suggestion:** shown only as a suggestion within the business profile budget; spending always needs owner approval.
- **Results check (optional):** after the campaign, compare the promoted product's sales before and after over matching periods, with the Section 5.9 rule that correlation is not causation.

### 2.2 Rules

- **Draft only.** Nothing is posted. Posting is a manual copy by the owner; automatic posting through official platform APIs is a roadmap item.
- No fake reviews, fake engagement, invented testimonials or unsupported claims (“best in Malaysia”).
- Food claims must be factual (no health or allergy claims).
- If an image is generated, follow the platform's AI-content labelling rules, and say in the brief that it is AI-generated.
- Output files: `data/output/campaign_plan.md` and `data/output/social_posts/` (one file per post).

---

## 3. FR-04 — Recruitment assistant (new “People” department)

### 3.1 What it does

- **Spots staffing need from data:** for example, the upcoming sales volume or days whose units sold exceed an owner-set threshold. It suggests part-time shifts. (The sample `sales.csv` has dates but no times of day, so it cannot claim busy *hours* unless time data exists.)
- **Drafts a job ad:** role, tasks, days and hours, pay (from an **owner-set range in MYR**), requirements, and how to apply. It produces versions formatted for **JobStreet**, **Facebook** (page or campus job group), **Instagram story**, and a **campus job board / WhatsApp group** message.
- **Hiring kit:** a posting checklist (where and how to post manually), 5–8 fair interview questions, and an empty applicant-tracker template (`hiring_tracker.csv` with columns only).
- Output files: `data/output/job_ad_<role>.md` and `data/output/hiring_kit.md`.

### 3.2 Rules

- **Draft only:** nothing is posted. Automatic posting through platform APIs is roadmap.
- **Pay compliance:** the owner sets the pay. The agent adds a note asking the owner to confirm it meets Malaysia's current minimum-wage and employment rules. It does not state a legal figure it has not verified with a dated source.
- **Fair wording:** no requirements on age, gender, race, religion, marital status or appearance, unless legally justified by the owner. The agent flags such wording if the owner asks for it.
- **No candidate screening or ranking of real people**, and no collection of applicants' personal data in the hackathon build. Candidate screening is a roadmap item that would need privacy (PDPA) and fairness review.
- The demo uses a synthetic business and a synthetic role only.

---

## 4. How these fit the departments

| Department | Change |
|---|---|
| Sales & Marketing | FR-03 campaign planner replaces the single promo draft (the single draft remains the minimum) |
| People (new) | FR-04 recruitment assistant |
| Verifier | checks that prices and offers in posts and job-ad pay come from configured or owner-set values |
| Technology | hourly check also confirms that the Demo Mode and Live Mode pages load |
| Transaction & Permission Controls | adds: “post to social media”, “post a job ad” and “spend ad budget” = owner approval (manual in the hackathon build) |

---

## 5. Options to offer the user

| Request | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| **FR-02 Demo Mode** | **Build it (recommended)**: toggle, ~10-step walkthrough, badges, banner, reset, offline (~1.5–2 h, in Sprint 3) | Lite: 5 steps, live features plus 2 concept screens (~1 h) | Slides only, no Demo Mode (0 h) |
| **FR-03 Social media** | **Campaign planner (recommended)**: one-week calendar plus 3–4 platform drafts (~1–1.5 h) | Keep the single promo draft, and show the campaign as a CONCEPT screen in Demo Mode (~20 min) | Vision slide only |
| **FR-04 Recruitment** | Build the job-ad generator plus hiring kit (~1–1.5 h) | **Concept screen in Demo Mode with one pre-written job ad (recommended for time)** (~20 min) | Vision slide only |

**Time-saving tip to offer:** the simulated checkout (G.14) and the WhatsApp-style chat (Feature Update 01) can be shown as **PROTOTYPE** screens inside Demo Mode instead of being built into Live Mode. This can save 1–2 h if Sprint 3 is tight.

Never cut verification, honest badges/labels, or the two rehearsals to make room.

---

## 6. Acceptance criteria and tests

- **Mode separation:** Live Mode reads only `data/output/`, and Demo Mode only `demo/scenario/`. A test confirms that neither reads or writes the other's folder.
- **Badges match evidence:** every LIVE FEATURE badge matches a `built and tested` row in `docs/CAPABILITIES.md`.
- **Banner:** visible on every Demo Mode screen; the toggle shows the current mode.
- **Reproducible:** running the walkthrough twice gives identical screens; reset returns to step 1; it works with the network off.
- **Social posts (if built):** every price or offer in a post matches the configuration (Verifier check), and nothing is posted.
- **Job ad (if built):** pay comes from the owner-set range; the minimum-wage confirmation note and fair-wording check are present; nothing is posted; no applicant data is stored.
- Record the results in `docs/TEST_RESULTS.md`.

---

## 7. Slide impact

- **Slide 5 (live demo):** first show **Live Mode** (the real run), then switch to **Demo Mode** for the full-vision walkthrough, saying aloud “this part is Demo Mode”.
- **Slide 7 (vision):** add the People department (recruitment) and the social media campaign planner, using the same LIVE / PROTOTYPE / CONCEPT badges.
- **Speaker note:** “Everything marked LIVE ran for real today; PROTOTYPE and CONCEPT show where Enterprise Buddy goes next.”

---

## 8. Message to paste into WorkBuddy with this file

> Here is **Feature Update 02** (`WorkBuddy_Feature_Update_02_Growth_and_Demo_Mode.md`). It contains three feature requests: FR-02 Demo Mode, FR-03 Social media promotion and FR-04 Recruitment assistant. Handle them with the feature-request rule in Section A: log them in `docs/FEATURE_REQUESTS.md`, check the time left before the 09:00 submission target, and offer me the options in its Section 5 with time estimates, what each would cut, and your recommendation. Then STOP and wait for my choices. After I choose, build and test only what I picked, update the capability, workflow, status and slide-plan documents, and continue to the next gate.
