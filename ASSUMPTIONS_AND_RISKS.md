# ASSUMPTIONS AND RISKS — BizFlow

Updated: end of Sprint 1 (2026-10-10). "Approval required = yes" means we must not proceed on that
assumption without an explicit owner decision.

## 1. Assumptions

| # | assumption | why we assume it | approval required | if wrong |
|---|---|---|---|---|
| A-01 | The judges' Track 2 criteria in Section G are accurate | transcribed from photos the user supplied 2026-10-10; nothing better available | no (but re-check if the original slides appear) | priorities could be mis-set |
| A-02 | Synthetic MYR data is acceptable for the demo | Section 4.5 | no | – |
| A-03 | Reporting period can be **proposed from the data** when the owner does not state one | Section 5.1 | no | – |
| A-04 | Duplicate ids: exclude all copies | Section 4.6 "do not auto-delete" | **yes** (D-04) | totals could change |
| A-05 | 14-day demand window, 3-day safety stock, 7-day staleness | Section 5.7/5.8 give the defaults; thresholds are ours | **yes** (D-05) | action priorities may shift |
| A-06 | One aggregated sales line per product per day is representative enough | keeps the sample auditable | **yes** (D-03) | realism of the demo |
| A-07 | A static HTML/JS demo site can be previewed in this WorkBuddy install | needed for Sprint 3; the preview mechanism exists | **yes** if it fails (U4) | fall back to a WorkBuddy report + labelled screenshots |
| A-08 | Sub-agents can be used for the Verifier role | F7 confirmed execution | no | emulate sequentially and say so (G.4) |
| A-09 | Hourly Automation will fire while the laptop is awake | G.12; listing confirmed, firing not | **yes** if no rows appear by Sprint 4 | use the team scheduler and state it honestly |
| A-10 | The 17-material catalogue is researchable inside Sprint 2 | ~4 full-tier + ~13 light-tier searches | **yes** (D-02) | trim the catalogue or label some materials "not found" |

## 2. Risks

| # | risk | likelihood | impact | mitigation | owner decision needed |
|---|---|---|---|---|---|
| R-01 | **Time**: Sprint 1 already finished past its nominal window; five sprints remain before 09:30 | high | high | cut in the §10.0 order (marketing polish → live web research → visual polish); never cut verification or honest labelling | yes — see alternatives |
| R-02 | Local MCP support unverified, so a needed capability might be missing | medium | medium | built-ins first; if something is genuinely missing, ask before adding | only if a gap appears |
| R-03 | Live web research fails during the demo | medium | medium | cached `supplier_research.csv` labelled with its retrieval date; rehearse the fallback | no |
| R-04 | Hourly Automation produces no real log before the demo | medium | medium | create it at the end of Sprint 3, keep the laptop awake and plugged in, verify rows each sprint | no |
| R-05 | Golden test and engine share a misreading of a rule | medium | high | hand arithmetic on the mini fixture + a second fixture; investigate every mismatch instead of reconciling silently | no |
| R-06 | A capability is presented as built when it is only planned | low | **high** (credibility + judging criterion 5) | CAPABILITIES.md statuses + the G.13 gate before slides | yes — approve the docs |
| R-07 | Sample data is mistaken for real business data | low | medium | "SYNTHETIC DEMONSTRATION DATA" label on data, site, reports and slides | no |
| R-08 | A secret, key or card number ends up in a file or slide | low | high | never store them; scan in Sprint 4; the profile has no field for them | no |
| R-09 | Effort/user-value metrics (G.5) are never measured | medium | medium | reserve 15 min in Sprint 4; if not measured, the slides must say "remains to be validated" | yes at Sprint 4 |
| R-10 | Presenter has no rest before the demo (UD-12) | certain | medium | rehearse the exact script twice; keep backup screenshots | no |

## 3. Open questions for the organisers (Section G.8 — do NOT invent answers)

1. Scoring weight of each of the five criteria.
2. Pitch / demo duration.
3. How and where to submit.

Already confirmed: deadline 09:30 on 2026-10-11 · live demo required · slides present the demo site
(ease of use is a headline advantage) · outside libraries and web research allowed · slides must
show the agent using WorkBuddy to get things done.

## 4. Unknowns about the platform (see WORKBUDDY_FEASIBILITY_CHECKLIST.md)

U1 hourly Automation firing · U2 local MCP · U3 parallel sub-agents · U4 HTML preview ·
U5 slide generation path · U6 BizFlow Skill invoked in a real run.
