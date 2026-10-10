# DEPENDENCIES — Enterprise Buddy (Section D)

Rule: record every outside library, MCP server and web source with its purpose, licence and **what
data it receives**. Secrets live only in WorkBuddy/MCP configuration or environment variables — never
in project files. Only synthetic data and public search queries go to outside services.

## 1. Runtimes

| item | version | purpose | licence | data it receives |
|---|---|---|---|---|
| Python (managed WorkBuddy runtime) | 3.13.x | deterministic validation/calculation layer, test scripts | PSF licence | local CSV files only |
| Node.js (managed) | v22.22.2 | available for the demo site tooling if needed; not used yet | MIT | none yet |

## 2. Third-party libraries

**None so far.** Everything built in Sprint 1 uses the Python standard library only
(`csv`, `decimal`, `json`, `hashlib`, `argparse`, `pathlib`, `datetime`, `random`).
Any library added later must be listed here with licence and data flow, and approved first
(Section D: "Do not install an external Skill, connector, package, or integration without first
inspecting its source, permissions, data access, license, external side effects…").

## 3. WorkBuddy built-in capabilities used

| capability | purpose | status |
|---|---|---|
| file read / write | all inputs and outputs | confirmed (F1) |
| code execution (Python) | deterministic layer | confirmed (F2/F3) |
| built-in web search | supplier research and market check | confirmed working 2026-10-10 (F5) |
| Automations | hourly Technology check | listing confirmed (F6); hourly firing untested (U1) |
| sub-agents | Analyst / Verifier roles | execution confirmed (F7); parallelism untested (U3) |

## 4. MCP servers

**None configured.** `~/.workbuddy-ai/mcp.json` does not exist and `settings.json` contains no
`mcpServers` key (F10). Whether a **local (stdio)** server is accepted is **not yet verified** (F11).
A team Enterprise Buddy MCP server will only be added if a needed capability is genuinely missing, and only
after a feasibility probe and user approval (Section D).

## 5. Web sources used so far

| query | purpose | retrieved | sources returned | how it is used |
|---|---|---|---|---|
| "wholesale supplier Malaysia chocolate chips bulk 1kg price" | feasibility check F5 — prove that built-in web search returns usable supplier results | 2026-10-10 | supplybunny.com, marubishi-group.com, healthybakermalaysia.com, borong.com, alibaba.com | **capability probe only** — no result is used in any output, and no price from it is recorded as a supplier finding |

Any web finding that later appears in an output must show its source URL and retrieval date; if the
network fails during the demo, the fallback is the last saved file, clearly labelled as cached.

## 6. Data sent outside the workspace

Nothing so far beyond the single public search query above. Supplier and market research in Sprint 2
will send **public product/material queries only** — never the shop's own sales, cost or expense
data (Section D: "send only synthetic data or public search queries to outside services").
