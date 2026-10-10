# WORKBUDDY FEASIBILITY CHECKLIST — Enterprise Buddy

Rule (Section D, paragraph 1): *"For any platform feature not confirmed in the user's installed
version, say 'not yet verified' and run a small feasibility check before relying on it."*
This file records what was **actually run** in Sprint 1, on 2026-10-10, and separates it from what
is still unverified. Nothing here is inferred from documentation alone unless the row says so.

## 1. Checks actually performed

| # | capability | how it was checked | result | evidence |
|---|---|---|---|---|
| F1 | File read / write / create in the project workspace | created the folder tree and ~10 files, read several back | **PASS** | `data/sample/*.csv`, `docs/`, `tests/`, `scripts/` |
| F2 | Code execution (Python) | ran the managed Python 3.13 runtime | **PASS** | `python ok 3.13.14` |
| F3 | Deterministic money arithmetic | `0.1 + 0.2` with `Decimal`, plus a tiny CSV sum | **PASS** — exact `0.3`, tiny CSV total `11.90` (3×2.50 + 4×1.10) | Bash output, Sprint 1 |
| F4 | Reading a binary Office file (.docx → text) | unzipped `word/document.xml` and extracted paragraphs and tables | **PASS** — 88 491 chars, 758 lines | `docs/MASTER_INSTRUCTIONS_EXTRACT.md` |
| F5 | Built-in web search | ran one real query: *"wholesale supplier Malaysia chocolate chips bulk 1kg price"* | **PASS** — 5 results returned with URLs, e.g. supplybunny.com, marubishi-group.com, healthybakermalaysia.com. Retrieved **2026-10-10** | search result block, Sprint 1 |
| F6 | Automations (scheduled tasks) exist | listed automations | **PASS** — the tool responded successfully, list is empty | `automation_update mode=list` → `success: true, automations: []` |
| F7 | Sub-agents can execute and write files | launched two general-purpose sub-agents; each had to write a probe file | **PASS** — both files written and read back | `tests/_probe/probe_A.txt`, `tests/_probe/probe_B.txt` |
| F8 | Node runtime present | `node -v` | **PASS** — v22.22.2 (managed) | Bash output |
| F9 | User-level Skill directory exists | listed `~/.workbuddy-ai/skills` | **PASS** — directory exists (currently empty) | Bash output |
| F10 | MCP configuration file | looked for `~/.workbuddy-ai/mcp.json` and `mcpServers` in `settings.json` | **INCONCLUSIVE** — `mcp.json` does not exist; `settings.json` exists but contains no `mcpServers` key | file listing |
| F11 | Local (stdio) vs remote (URL) MCP servers | tried to fetch the official docs page | **NOT VERIFIED** — the docs page returned empty content | `WebFetch https://www.workbuddy.ai/docs/workbuddy/Overview` → empty page |

## 2. Still unverified (must be probed before we depend on it)

| # | capability | why it matters | planned probe |
|---|---|---|---|
| U1 | Hourly Automation actually firing | G.12: the Technology department must run every hour and leave a real log before the demo | create it at the end of Sprint 3 and check `tech_health_log.csv` gains rows |
| U2 | Local MCP server accepted | D only permits a team MCP server if the platform supports it; the Enterprise Buddy tool server is the backup path if built-ins are not enough | Sprint 2: add a minimal stdio server to `~/.workbuddy-ai/mcp.json`, see whether WorkBuddy lists/trusts it, then remove it if unnecessary |
| U3 | Parallel sub-agent execution in one message | G.4 parallel validation is "should-have"; we must not claim it if it does not run | Sprint 2: launch two analysis sub-agents in a single message and time them |
| U4 | HTML preview of a local page | the demo site is the headline deliverable (Sprint 3) | Sprint 3: build the page and open it via the host preview |
| U5 | Slide generation through WorkBuddy | Sprint 5 deck must be produced inside WorkBuddy | Sprint 5, before the deck is needed |
| U6 | A Enterprise Buddy Skill being invoked in a real run | the runnable "one prompt" workflow depends on it (or on an equivalent) | Sprint 2 |

## 3. Consequences for the technical path

- **Confirmed enough to build on:** Python as the deterministic calculation layer, CSV inputs,
  file outputs, built-in web search for supplier and market research, sub-agents for the Analyst /
  Verifier split, managed Python/Node runtimes, WorkBuddy as the runtime that receives the prompt,
  plans, calls tools and writes outputs (Section G.6).
- **Do not depend on yet:** local MCP (use built-ins first — Section D says exactly this), hourly
  Automation logs (create in Sprint 3), parallel execution (emulate sequentially and say so if it
  is not available — G.4 last paragraph).
- **Fallback if the demo site cannot be previewed:** a WorkBuddy-generated report view plus
  labelled screenshots, with the limitation stated (Section 7.3).

## 4. Open questions for the organisers (Section G.8 — do not invent answers)

Scoring weight per criterion · pitch/demo duration · how and where to submit.
Confirmed: deadline 09:30 on 2026-10-11, live demo required, outside libraries and web research
allowed and needed, slides must show the agent using WorkBuddy to get things done.
