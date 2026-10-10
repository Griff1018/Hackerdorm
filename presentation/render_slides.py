"""Render each Enterprise Buddy pitch slide to a PNG so we can preview the deck.

This is a tiny renderer: it draws the same shapes that python-pptx produced
(text, rounded panels, images) onto a 1600x900 canvas. It is not a full
PowerPoint renderer, but it is enough to verify the deck's layout before
opening the .pptx in PowerPoint or Keynote.

Run:  C:/Users/Chew Chee Kin/AppData/Local/Programs/Python/Python313/python.exe presentation/render_slides.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(ROOT, "screenshots")
OUT = os.path.join(ROOT, "screenshots")

# Match 13.333 x 7.5 in @ 120 dpi -> 1600 x 900
W, H = 1600, 900
DPI = 120

# Colors (mirror build_pptx.py)
def rgb(h): return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
INK = rgb("0F172A")
MUTED = rgb("475569")
ACCENT = rgb("14532D")
PANEL = rgb("F4F4F5")
RULE = rgb("E4E7EA")
RED = rgb("B91C1C")
BG = rgb("FFFFFF")

# Fonts: Calibri may be absent; use Windows arial.
FONT_DIR = r"C:\Windows\Fonts"
def font(size, bold=False, italic=False):
    if bold and italic: name = "arialbi.ttf"
    elif bold: name = "arialbd.ttf"
    elif italic: name = "ariali.ttf"
    else: name = "arial.ttf"
    p = os.path.join(FONT_DIR, name)
    return ImageFont.truetype(p, size)


def in_to_px(v_in):
    return int(round(v_in * DPI))


def draw_text(draw, box, text, *, size=18, bold=False, italic=False, color=INK,
              align="left", anchor="top"):
    x, y, w, h = box
    lines = text if isinstance(text, list) else [text]
    line_h = int(size * 1.3)
    f = font(size, bold, italic)
    # Compute total height
    total_h = line_h * len(lines)
    if anchor == "center":
        ty = y + (h - total_h) // 2
    else:
        ty = y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=f)
        tw = bbox[2] - bbox[0]
        if align == "center":
            tx = x + (w - tw) // 2
        elif align == "right":
            tx = x + w - tw
        else:
            tx = x
        draw.text((tx, ty + i * line_h), line, fill=color, font=f)


def draw_rounded(draw, box, fill=PANEL, outline=RULE, radius=10):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill,
                           outline=outline, width=1)


def draw_image_fit(canvas, path, box, radius=10):
    x, y, w, h = box
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    img = Image.open(path).convert("RGB")
    iw, ih = img.size
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    base = Image.new("RGB", (w, h), (240, 240, 240))
    base.paste(img, ((w - nw) // 2, (h - nh) // 2))
    canvas.paste(base, (x, y), mask)


def title_bar(draw, kicker, title, chip):
    draw_text(draw, (in_to_px(0.55), in_to_px(0.35), in_to_px(8), in_to_px(0.3)),
              kicker.upper(), size=11, bold=True, color=MUTED)
    draw_text(draw, (in_to_px(0.55), in_to_px(0.65), in_to_px(9.6), in_to_px(0.85)),
              title, size=26, bold=True, color=INK)
    # chip
    cx, cy, cw, ch = in_to_px(10.55), in_to_px(0.4), in_to_px(2.55), in_to_px(0.45)
    draw_rounded(draw, (cx, cy, cw, ch), fill=PANEL)
    draw_text(draw, (cx, cy + ch // 2 - 6, cw, 12), chip, size=10, bold=True,
              color=MUTED, align="center")
    # rule
    draw.rectangle((in_to_px(0.55), in_to_px(1.55), in_to_px(12.2), in_to_px(1.55) + 1),
                   fill=RULE)


def brand_strip(draw):
    draw_text(draw, (in_to_px(11.45), in_to_px(7.15), in_to_px(1.6), in_to_px(0.25)),
              "Enterprise Buddy", size=9, bold=True, color=MUTED, align="right")
    draw_text(draw, (in_to_px(0.55), in_to_px(7.15), in_to_px(7), in_to_px(0.25)),
              "Synthetic demo data. No real payments move.", size=9, italic=True, color=MUTED)


def render_slide(name, draw_fn):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    draw_fn(d, canvas)
    path = os.path.join(OUT, name)
    canvas.save(path)
    print("rendered", name)


# ---------------- slide 1 ----------------
def slide1(d, canvas):
    title_bar(d, "Slide 1 / 7  ·  0:00 – 0:25",
              "A student seller, scattered chats and stock in her head",
              "Criterion 1 · Real problem & user")
    draw_text(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.5), in_to_px(5.2)),
              ["Orders on WhatsApp.",
               "Money in 22 sample chats — Touch 'n Go, online banking, cash.",
               "Stock tracked in her head.",
               "No time to learn another dashboard.",
               "She needs someone to do the work."],
              size=18, color=INK)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "01_whatsapp.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "Demo WhatsApp inbox — 14 customer chats visible. SYNTHETIC.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 2 ----------------
def slide2(d, canvas):
    title_bar(d, "Slide 2 / 7  ·  0:25 – 0:50",
              "WorkBuddy is the brain, not just the builder",
              "Criterion 3 · Meaningful use of WorkBuddy")
    draw_text(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.6), in_to_px(5.2)),
              ["Can our AI agent use WorkBuddy to solve a real problem — and actually get things done?",
               "Yes.",
               "WorkBuddy is the agent's runtime, not just the IDE we used to write code.",
               "Every request goes to WorkBuddy. It plans, calls a read-only toolkit, searches the web, and returns actions the app runs."],
              size=16, color=INK)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "02_chat.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "One chat box. Suggested prompts adapt to Campus Crumb's data.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 3 ----------------
def slide3(d, canvas):
    title_bar(d, "Slide 3 / 7  ·  0:50 – 1:30",
              "One prompt → plan → departments → owner approval",
              "Criteria 2 + 4 · Agentic · End-to-end")
    draw_text(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.6), in_to_px(5.2)),
              ['Prompt: "I want to sell kuih at my campus near Universiti Malaya."',
               "WorkBuddy splits it: Operations scores suppliers · Strategy maps competitors from OpenStreetMap · Guides drafts permits · Marketing drafts posts.",
               "Every step cites a real web page or the owner's own records.",
               "A stale stock count triggers 'recount first' — never a wrong reorder.",
               'And small things just work — "bought sugar, paid by TNG" becomes two money entries + an inventory top-up in one reply.'],
              size=13, color=INK)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "03_plan.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "Plan P1–P5 with review panel and 60 real competitor places from OpenStreetMap.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 4 ----------------
def slide4(d, canvas):
    title_bar(d, "Slide 4 / 7  ·  1:30 – 2:05",
              "Money in, money out, and the alerts that matter",
              "Criterion 5 · Usable results")
    draw_rounded(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.6), in_to_px(5.05)))
    draw_text(d, (in_to_px(0.75), in_to_px(2.0), in_to_px(5.2), in_to_px(0.4)),
              "Money Flow · synthetic demo data", size=11, bold=True, color=MUTED)
    draw_text(d, (in_to_px(0.75), in_to_px(2.5), in_to_px(5.2), in_to_px(0.5)),
              "MYR 2,507.25 in", size=22, bold=True, color=ACCENT)
    draw_text(d, (in_to_px(0.75), in_to_px(3.05), in_to_px(5.2), in_to_px(0.5)),
              "MYR 1,172.30 out", size=22, bold=True, color=RED)
    draw_text(d, (in_to_px(0.75), in_to_px(3.6), in_to_px(5.2), in_to_px(0.5)),
              "MYR 1,334.95 kept", size=22, bold=True, color=INK)
    draw_text(d, (in_to_px(0.75), in_to_px(4.25), in_to_px(5.2), in_to_px(2.5)),
              ["Orders from WhatsApp, Instagram and the online shop — AI prices from menu.csv.",
               "Inventory with auto-reorder; supplier orders go to the supplier's WhatsApp after you approve.",
               "Auto-posting · Customers & reviews · Task checklist.",
               "Heads-up: 'Cookies run out in 3.2 days — reorder now.'"],
              size=12, color=INK)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "04_money_flow.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "Live Money Flow page. Verified: in MYR 2,507.25, out MYR 1,172.30. Synthetic.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 5 ----------------
def slide5(d, canvas):
    title_bar(d, "Slide 5 / 7  ·  2:05 – 2:35",
              "One chat. Owner approves. Real money never moves.",
              "Criterion 5 · Ease of use · Safety")
    draw_text(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.6), in_to_px(5.2)),
              ["Plain language and the top actions first.",
               "Owner chooses how involved to be: quick answers, or a plan they approve step by step.",
               "If the agent isn't sure, it asks.",
               "Give it an order with no customer name and it asks 'Who is this order for?'",
               "Every change has Undo. Every MYR figure is checked against the data.",
               "Payments are simulated and wait for the owner's approval."],
              size=14, color=INK)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "07_inventory.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "Inventory: 'Approve & pay' / 'Not now' gate, supplier options, sources for every order.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 6 ----------------
def slide6(d, canvas):
    title_bar(d, "Slide 6 / 7  ·  2:35 – 2:50",
              "Tested on synthetic data. Real-user testing is next.",
              "Criterion 5 · Verifiable")
    draw_rounded(d, (in_to_px(0.55), in_to_px(1.85), in_to_px(5.6), in_to_px(5.05)))
    draw_text(d, (in_to_px(0.75), in_to_px(2.0), in_to_px(5.2), in_to_px(0.4)),
              "Evidence at a glance", size=11, bold=True, color=MUTED)
    draw_text(d, (in_to_px(0.75), in_to_px(2.5), in_to_px(5.2), in_to_px(4.2)),
              ["• WorkBuddy CLI live, streaming events  (F1)",
               "• Tool whitelist enforced  (F2)",
               "• 'What needs my attention today?' → 9 plan items, verifier PASS  (test 1)",
               "• Prompt-injection refused  (test 9)",
               "• Approve 2 / reject 1, budget reconciled  (test 10)",
               "• OpenStreetMap competitor map, 60 places  (S1)",
               "• Auto-reorder on real stock, with sources  (S2)",
               "• Auto-reply WhatsApp orders from menu.csv  (S3)",
               "• Money Flow reconciles to verified brief  (S7)",
               "• Number check caught invented figures  (S8)",
               "• Undo verified for every change  (S9)",
               "• 22 sample WhatsApp clients  (S4)"],
              size=12, color=INK)
    draw_text(d, (in_to_px(0.75), in_to_px(6.55), in_to_px(5.2), in_to_px(0.3)),
              "Full log: docs/AGENT_CONSOLE_TESTS.md", size=10, italic=True, color=MUTED)
    draw_rounded(d, (in_to_px(6.4), in_to_px(1.8), in_to_px(6.45), in_to_px(4.95)))
    draw_image_fit(canvas, os.path.join(SHOTS, "11_proof.png"),
                   (in_to_px(6.45), in_to_px(1.85), in_to_px(6.35), in_to_px(4.85)))
    draw_text(d, (in_to_px(6.45), in_to_px(6.78), in_to_px(6.35), in_to_px(0.25)),
              "14-row evidence table rendered from the test log. Synthetic data only.",
              size=9, italic=True, color=MUTED)
    brand_strip(d)


# ---------------- slide 7 ----------------
def slide7(d, canvas):
    title_bar(d, "Slide 7 / 7  ·  2:50 – 3:00",
              "Thank you.",
              "Repeat the core question")
    draw_text(d, (in_to_px(0.55), in_to_px(2.3), in_to_px(12.2), in_to_px(2.0)),
              "Enterprise Buddy turns a messy side hustle into a business that runs itself — all from one chat.",
              size=22, bold=True, color=INK)
    draw_text(d, (in_to_px(0.55), in_to_px(4.0), in_to_px(12.2), in_to_px(1.5)),
              "Our AI agent uses WorkBuddy to solve a real problem, and it actually gets things done.",
              size=20, bold=True, color=ACCENT)
    draw_text(d, (in_to_px(0.55), in_to_px(5.6), in_to_px(12.2), in_to_px(0.6)),
              "github.com/Griff1018/hackerdorm    ·    run with: PORT=8091 python console/server.py",
              size=12, color=MUTED)
    draw_text(d, (in_to_px(0.55), in_to_px(6.4), in_to_px(12.2), in_to_px(0.4)),
              "Synthetic demo data. Live demo apps: WhatsApp, Instagram, LinkedIn, Enterprise Buddy Shop. Simulated: payments, online banking, Touch 'n Go, marketplaces.",
              size=10, italic=True, color=MUTED)
    brand_strip(d)


if __name__ == "__main__":
    for name, fn in [
        ("slide1.png", slide1), ("slide2.png", slide2), ("slide3.png", slide3),
        ("slide4.png", slide4), ("slide5.png", slide5), ("slide6.png", slide6),
        ("slide7.png", slide7),
    ]:
        render_slide(name, fn)