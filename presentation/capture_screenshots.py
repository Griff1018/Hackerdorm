"""Capture Enterprise Buddy screenshots for the pitch deck.

Run the console first:  PORT=8091 python console/server.py
Then:                   python presentation/capture_screenshots.py

Only synthetic demo data is on screen. Never run with real business data.
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("EB_BASE", "http://127.0.0.1:8091")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
BIZ = "campus-crumb"
PLAN_CHAT = os.environ.get("EB_PLAN_CHAT", "1010174017-288a")  # "sell kuih at my campus near UM"

os.makedirs(OUT, exist_ok=True)


def new_page(ctx):
    p = ctx.new_page()
    p.set_viewport_size({"width": 1600, "height": 1000})
    return p


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = new_page(ctx)

        # --- front door: continue as guest ---
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.click("#guest")
        page.wait_for_url(BASE + "/", timeout=20000)
        page.wait_for_timeout(1500)

        # pin the demo business (Campus Crumb)
        page.evaluate(
            """(biz) => {
                localStorage.setItem('enterprise_buddy.scope', JSON.stringify('single'));
                localStorage.setItem('enterprise_buddy.bid', JSON.stringify(biz));
            }""",
            BIZ,
        )
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        def shot(name, wait=1400):
            page.wait_for_timeout(wait)
            page.screenshot(path=os.path.join(OUT, name + ".png"))
            print("saved", name)

        def tab(t, wait=1800):
            page.evaluate("(t) => showTab(t)", t)
            page.wait_for_timeout(wait)

        # 1. Chat - the one box the owner actually uses
        shot("02_chat")

        # 2. Chat with a real plan (kuih at campus near UM)
        page.evaluate(
            """async (cid) => { const r = await fetch('/api/conversations/' + cid); return r.ok; }""",
            PLAN_CHAT,
        )
        page.evaluate("(cid) => openConv(cid)", PLAN_CHAT)
        page.wait_for_timeout(2500)
        shot("03_plan", wait=1000)

        # 3. Money Flow
        tab("money", 2600)
        shot("04_money_flow")

        # 4. Today
        tab("daily", 2600)
        shot("05_today")

        # 5. Orders
        tab("orders", 2400)
        shot("06_orders")

        # 6. Inventory
        tab("inventory", 2400)
        shot("07_inventory")

        # 7. Automations
        tab("automations", 2600)
        shot("08_automations")

        # --- demo channels ---
        for name, url, wait in [
            ("01_whatsapp", "/whatsapp/?business_id=" + BIZ, 3000),
            ("09_online_shop", "/shop/?business_id=" + BIZ, 3000),
            ("10_instagram", "/instagram/", 3000),
        ]:
            try:
                page.goto(BASE + url, wait_until="domcontentloaded")
                page.wait_for_timeout(wait)
                page.screenshot(path=os.path.join(OUT, name + ".png"))
                print("saved", name)
            except Exception as exc:  # keep going: a missing demo page is not fatal
                print("SKIP", name, exc)

        browser.close()
    print("done ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
