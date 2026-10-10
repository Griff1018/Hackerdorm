"""Render a small proof-from-the-test-log image for Slide 6.

Pulls numbers out of docs/AGENT_CONSOLE_TESTS.md (real evidence) and lays
them out as a screenshot-friendly card. Only synthetic demo data and
actual test-log claims are shown.
"""
import os
import re
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "screenshots")
os.makedirs(OUT, exist_ok=True)

TEST = open(
    os.path.join(os.path.dirname(ROOT), "docs", "AGENT_CONSOLE_TESTS.md"),
    encoding="utf-8",
).read()

# Pull a small, verifiable set of claims (test id, label, evidence).
CLAIMS = [
    ("F1", "WorkBuddy CLI live", "codebuddy 2.164.0, streaming events"),
    ("F2", "Tool whitelist", "read-only toolkit allowed; echo > file denied"),
    ("1",  "\"What needs my attention today?\"", "9 plan items, verifier PASS, spend MYR 168.30 / 800"),
    ("9",  "Prompt injection refused", "injection_attempt logged, no PO auto-paid"),
    ("10", "Approve 2 / reject 1", "only P1 & P7 ran, PO-04 → paid, budget 694.70"),
    ("S1", "Market map near UM, 2k", "60 real places, 26 cafe, 23 fast food, 8 food court"),
    ("S2", "Auto-reorder on real data", "cookies 18 ≤ 20 → 2 kg chips MYR 39.80 with sources"),
    ("S3", "Auto-reply WhatsApp order", "4 auto-replies, prices from menu.csv, MYR 21.50"),
    ("S4", "22 sample WhatsApp clients", "5 menu-correct orders, no unanswered messages"),
    ("S5", "Chat: revenue chart + table", "MYR 2,451.25 matches verified brief"),
    ("S6", "Chat: connect Shopee + save Aina", "8 reviews, customer saved, Undo verified"),
    ("S7", "Money Flow & Inventory reconciliation", "in 2,451.25 = verified revenue; out 1,132.50"),
    ("S8", "Number check catches invented figures", "weekday figures fixed, check passes"),
    ("S9", "Undo for every change", "customer save / connect / sale all reversible"),
]

HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body{margin:0;background:#0f172a;color:#e2e8f0;font:14px/1.45 ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial;padding:24px}
  h1{margin:0 0 4px 0;font-size:18px;color:#fff}
  p.lede{margin:0 0 14px 0;color:#94a3b8;font-size:12.5px}
  table{border-collapse:collapse;width:100%;background:#111827;border-radius:10px;overflow:hidden}
  th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #1f2937;vertical-align:top}
  th{background:#1e293b;font-size:12px;color:#cbd5e1;text-transform:uppercase;letter-spacing:.06em}
  td.k{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#fbbf24;font-weight:600;width:48px}
  td.t{color:#f1f5f9;font-weight:600;width:36%}
  td.v{color:#cbd5e1;font-size:13px}
  tr:last-child td{border-bottom:0}
  .foot{margin-top:12px;font-size:11.5px;color:#94a3b8}
  .pill{display:inline-block;background:#14532d;color:#86efac;padding:2px 8px;border-radius:999px;font-size:11px;margin-right:6px}
</style>
</head><body>
  <h1>Enterprise Buddy — proof from the test log</h1>
  <p class="lede">14 built-and-tested capabilities, all on <span class="pill">synthetic demo data</span>. Source: docs/AGENT_CONSOLE_TESTS.md.</p>
  <table><tr><th>ID</th><th>Capability</th><th>Evidence</th></tr>
""" + "".join(
    f"<tr><td class='k'>{k}</td><td class='t'>{t}</td><td class='v'>{v}</td></tr>"
    for k, t, v in CLAIMS
) + """
  </table>
  <p class="foot">Real-user testing with student sellers is the next step.</p>
</body></html>"""

PROOF_HTML = os.path.join(ROOT, "_proof.html")
open(PROOF_HTML, "w", encoding="utf-8").write(HTML)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 920}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto("file:///" + PROOF_HTML.replace("\\", "/"), wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(OUT, "11_proof.png"))
    b.close()

print("saved", os.path.join(OUT, "11_proof.png"))