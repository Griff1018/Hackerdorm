# FEATURE REQUESTS — BizFlow (Section A, feature-request rule)

Process: at every sprint checkpoint the owner may add features. For each request we record the date,
the request, its user value, estimated build + test time, which judging criterion it helps, and what
it would delay. We then offer three choices — (1) add it in the next sprint and say what to cut or
move so the 09:00 submission still holds, (2) add it later, or (3) put it on the vision slide as
"coming next" — marking one as recommended. After the owner picks, we update `PROJECT_STATUS.md`,
`docs/CAPABILITIES.md` and `docs/AGENT_WORKFLOW.md` and continue.

A new feature never skips a gate, the testing rules, or honest labelling of what is built.

## Log

| date | request | user value | est. build + test | criterion it helps | would delay | decision |
|---|---|---|---|---|---|---|
| 2026-10-10 | **FR-01 Sales & Customer Operations layer (G.15)** — customer/order records, stock check + ledger, simulated chat, one add-on, confirmation, low-stock handoff, allergy escalation, permission/audit controls | Makes BizFlow customer-facing and connects chat → order → stock → Procurement → owner approval | Tier A 1–1.5 h; Tier B 3–3.5 h; Tier D prototype 20–30 min; Tier C 15 min | 2 agent collaboration; 4 end-to-end; 5 usable results | Tier B consumes most of the Sprint 2.1 buffer and may reduce dashboard polish/rehearsal time; never cut verification or safety tests | **Recommend Tier B if the owner accepts a 3–3.5 h buffer allocation; otherwise Tier A** |
| 2026-10-10 | **FR-02 Demo Mode (G.16)** — Live/Demo toggle, guided walkthrough, badges, banner, reset, offline reproducibility | Provides an honest pitch backup and shows the wider vision without pretending concepts are live | Full 1.5–2 h; Lite ~1 h; slides only 0 h | 1 clarity; 4 end-to-end story; 5 usable demo | Full build uses Sprint 3 time and may reduce polish; Lite cuts walkthrough depth | **Recommend full build** because it is both pitch value and backup; keep badges and verification |
| 2026-10-10 | **FR-03 Social media promotion** — one-week calendar and platform-ready drafts | Extends the current single unsent promo into a usable campaign planner | Campaign planner 1–1.5 h; concept screen ~20 min; vision 0 h | 5 usable outputs; 1 collaboration | Planner may displace polish or rehearsal if combined with FR-01 Tier B and FR-06 | **Recommend campaign planner if FR-01 Tier A/B is chosen; otherwise concept screen** |
| 2026-10-10 | **FR-04 Recruitment assistant / People department** — staffing signal, owner-set pay range, job ad versions, hiring kit | Adds a new department and a practical staffing output | Generator + kit 1–1.5 h; Demo concept ~20 min; vision 0 h | 2 agent collaboration; 5 usable results | Full generator competes with Demo Mode and marketplace work; no real applicant data is allowed | **Recommend concept screen for the pitch; retain full generator as a stretch option** |
| 2026-10-10 | **FR-05 simulated social feed + online store** — generic simulated screens, file-backed prices/stock, no fake engagement | Makes outputs tangible without implying a real platform connection | Prototype screens 30–45 min; working store 1.5–2 h; vision 0 h | 4 end-to-end; 5 usable results | Working store requires FR-01 Tier A/B and can consume the demo/polish buffer | **Recommend working simulated store if FR-01 Tier A/B is selected; otherwise prototype screens** |
| 2026-10-10 | **FR-06 simulated marketplace channel (BizFlow as seller)** — inbox processing, recomputed totals, stock ledger, fulfilment, simulated label, buyer updates, review summary | Strongest end-to-end seller-side proof, with all events synthetic and owner-safe | Full seller side 1.5–2 h; orders + shipping 1–1.5 h; vision/standalone store 0 h | 4 end-to-end; 2 collaboration; 5 usable results | Full option may consume Sprint 4 polish and rehearsal time; requires the marketplace store to be ready | **Recommend full seller side if the store is ready; otherwise orders + shipping** |

## Feature Update 01 processing gate (2026-10-10)

Saved as `docs/FEATURE_UPDATE_01.md`. The six requests above were **approved in full** at 15:17 GMT+8,
with implementation split into Sprint 3A and Sprint 3B. Current time checked: **2026-10-10 15:17 GMT+8**;
submission target **2026-10-11 09:00**, hard deadline **09:30**. Sprint 3A is now complete and Sprint 3B
is gated at `docs/SPRINT3A_CHECKPOINT.md`.

### Recommended bundles to choose from

- **Bundle L — protected delivery (recommended if schedule certainty matters):** FR-02 full Demo Mode
  + FR-01 Tier A + FR-05 prototype screens; estimated 2.5–4.25 h. Keep FR-03/04/06 as concept or
  vision-only. Preserves most polish and rehearsal time while adding a credible end-to-end story.
- **Bundle M — larger end-to-end demo:** FR-02 full Demo Mode + FR-01 Tier B + FR-03 campaign planner
  + FR-05 prototype screens; estimated 6.0–8.75 h. Uses the ahead-of-schedule buffer plus Sprint 4
  polish time; FR-06 remains orders/shipping or vision-only. Strengthens collaboration and usable
  outputs, but reduces spare rehearsal/polish time.
- **Bundle H — marketplace proof:** FR-02 full Demo Mode + FR-01 Tier A + FR-05 working store
  + FR-06 orders/shipping; estimated 5.0–7.5 h. Best for criterion 4 if the separate marketplace
  store is ready; cuts dashboard polish and leaves FR-03/04 at concept level.
- **Bundle V — vision-first:** FR-02 Lite + FR-01 Tier D prototype + FR-03/04/05/06 concept screens;
  estimated 1.5–2.5 h. Protects both rehearsals and allows a clearly labelled vision story, but gives
  weaker live end-to-end proof.

**Never cut:** source-data safety, Verifier checks, honest LIVE/PROTOTYPE/CONCEPT badges, synthetic
labelling, permission controls, or the two rehearsals required by the master instructions.

**Current checkpoint condition:** Full options were selected. Sprint 3A is complete; stop at
`docs/SPRINT3A_CHECKPOINT.md` and wait for checkpoint approval before promoting Sprint 3B.

## Standing candidates (from the roadmap, not yet requested)

| candidate | est. | note |
|---|---|---|
| Full "start my business" feasibility mode (audience, market size, competitors, costs) | ~2 h, taken from Sprint 4 polish | §10.0 stretch; offered at the Sprint 2 checkpoint. **Recommended default: keep the light market check.** |
| Period-over-period trends | ~45 min | §2.2 should-have |
| Natural-language questions about computed metrics | ~1 h | §2.2 should-have |
| Downloadable report (PDF/CSV export) | ~30 min | §2.2 should-have |
| Receipt-input experiment | >1 h, risky | only after CSV handling is reliable and the rules permit it |
