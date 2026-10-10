"""Build Enterprise Buddy pitch deck (7 slides, 16:9, <=25 words on screen each).

Reads PITCH_SCRIPT.md and uses the screenshots under presentation/screenshots/.

Run:  C:/Users/Chew Chee Kin/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe presentation/build_pptx.py
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(ROOT, "screenshots")
OUT = os.path.join(ROOT, "Enterprise_Buddy_Pitch.pptx")

# 16:9 widescreen 13.333 x 7.5 inches
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height

# palette
INK = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x47, 0x55, 0x69)
ACCENT = RGBColor(0x14, 0x53, 0x2D)   # deep green
PANEL = RGBColor(0xF4, 0xF4, 0xF5)
RULE = RGBColor(0xE4, 0xE4, 0xE7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

BLANK = prs.slide_layouts[6]


def add_text(slide, left, top, width, height, text, *, size=20, bold=False,
             color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color
        r.font.name = "Calibri"
    return box


def add_title_bar(slide, kicker, title, criterion_chip):
    # kicker (top-left, small)
    add_text(slide, Inches(0.55), Inches(0.35), Inches(8), Inches(0.3),
             kicker.upper(), size=11, bold=True, color=MUTED)
    # title
    add_text(slide, Inches(0.55), Inches(0.65), Inches(9.6), Inches(0.85),
             title, size=30, bold=True, color=INK)
    # criterion chip top-right
    chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Inches(10.55), Inches(0.4), Inches(2.55), Inches(0.45))
    chip.fill.solid(); chip.fill.fore_color.rgb = PANEL
    chip.line.color.rgb = RULE
    tf = chip.text_frame; tf.margin_left = Emu(20000); tf.margin_top = Emu(0)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = criterion_chip
    r.font.size = Pt(10); r.font.bold = True; r.font.color.rgb = MUTED
    r.font.name = "Calibri"
    # rule line
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(0.55), Inches(1.55), Inches(12.2), Emu(12000))
    rule.fill.solid(); rule.fill.fore_color.rgb = RULE
    rule.line.fill.background()


def add_brand_strip(slide):
    """Small 'Enterprise Buddy' brand mark bottom-right."""
    add_text(slide, Inches(11.45), Inches(7.15), Inches(1.6), Inches(0.25),
             "Enterprise Buddy", size=9, bold=True, color=MUTED, align=PP_ALIGN.RIGHT)
    add_text(slide, Inches(0.55), Inches(7.15), Inches(7), Inches(0.25),
             "Synthetic demo data. No real payments move.",
             size=9, italic=True, color=MUTED)


def add_image_fit(slide, path, left, top, width, height):
    """Add an image, fit inside (width, height) preserving aspect ratio, centred."""
    from PIL import Image  # type: ignore
    img = Image.open(path)
    iw, ih = img.size
    box_w = width; box_h = height
    scale = min(box_w / iw, box_h / ih)
    new_w = int(iw * scale); new_h = int(ih * scale)
    new_left = left + (box_w - new_w) // 2
    new_top = top + (box_h - new_h) // 2
    slide.shapes.add_picture(path, new_left, new_top, width=new_w, height=new_h)


def add_notes(slide, text):
    nf = slide.notes_slide.notes_text_frame
    for i, line in enumerate(text if isinstance(text, list) else [text]):
        p = nf.paragraphs[0] if i == 0 else nf.add_paragraph()
        r = p.add_run(); r.text = line
        r.font.size = Pt(11); r.font.name = "Calibri"


def add_panel(slide, left, top, width, height, color=PANEL):
    rect = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    rect.adjustments[0] = 0.06
    rect.fill.solid(); rect.fill.fore_color.rgb = color
    rect.line.color.rgb = RULE
    rect.line.width = Pt(0.75)
    return rect


def build():
    # ---------------- slide 1: problem ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 1 / 7  ·  0:00 – 0:25",
                  "A student seller, scattered chats and stock in her head",
                  "Criterion 1 · Real problem & user")
    # text left
    body = [
        "Orders on WhatsApp.",
        "Money in 22 sample chats — Touch 'n Go, online banking, cash.",
        "Stock tracked in her head.",
        "No time to learn another dashboard.",
        "She needs someone to do the work.",
    ]
    add_text(s, Inches(0.55), Inches(1.85), Inches(5.5), Inches(5.2),
             body, size=20, color=INK)
    # image right
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "01_whatsapp.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "Demo WhatsApp inbox — 14 customer chats visible. SYNTHETIC.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Track 2, Hackerdorm — judges, Track 2: WorkBuddy Track.",
        "Slide 1 — Criterion 1: real problem and user value.",
        "Picture a student who sells kuih between lectures.",
        "Twenty-two sample customers in our demo WhatsApp. (test S4)",
        "Touch 'n Go, online banking, cash — verified on Money Flow. (test S7)",
        "She can't see margins, stockouts or supplier orders. Today's slide 5 shows the alert that fixes that.",
    ])

    # ---------------- slide 2: core question ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 2 / 7  ·  0:25 – 0:50",
                  "WorkBuddy is the brain, not just the builder",
                  "Criterion 3 · Meaningful use of WorkBuddy")
    add_text(s, Inches(0.55), Inches(1.85), Inches(5.6), Inches(5.2),
             [
                 "Can our AI agent use WorkBuddy to solve a real problem — and actually get things done?",
                 "Yes.",
                 "WorkBuddy is the agent's runtime, not just the IDE we used to write code.",
                 "Every request goes to WorkBuddy. It plans, calls a read-only toolkit, searches the web, and returns actions the app runs.",
             ], size=18, color=INK)
    # chat screenshot right
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "02_chat.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "One chat box. Suggested prompts adapt to Campus Crumb's data.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 2 — Criterion 3: meaningful use of WorkBuddy.",
        "Answer the core judging question out loud: yes.",
        "Agent runtime = the CodeBuddy CLI inside WorkBuddy (test F1: codebuddy 2.164.0, stream-json).",
        "Enterprise Buddy's server and screens are the viewing and action layer around it.",
        "Tool whitelist restricts the agent to read-only commands; everything that changes anything goes through owner approval. (test F2)",
    ])

    # ---------------- slide 3: end to end ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 3 / 7  ·  0:50 – 1:30",
                  "One prompt → plan → departments → owner approval",
                  "Criteria 2 + 4 · Agentic · End-to-end")
    add_text(s, Inches(0.55), Inches(1.85), Inches(5.6), Inches(5.2),
             [
                 'Prompt: "I want to sell kuih at my campus near Universiti Malaya."',
                 "WorkBuddy splits it: Operations scores suppliers · Strategy maps competitors from OpenStreetMap · Guides drafts permits · Marketing drafts posts.",
                 "Every step cites a real web page or the owner's own records.",
                 "A stale stock count triggers 'recount first' — never a wrong reorder.",
                 'And small things just work — \"bought sugar, paid by TNG\" becomes two money entries + an inventory top-up in one reply.',
             ], size=14, color=INK)
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "03_plan.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "Plan P1–P5 with review panel and 60 real competitor places from OpenStreetMap.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 3 — Criteria 2 and 4: agentic workflow, end-to-end.",
        "Single prompt, full chain. No intermediate guidance.",
        "Departments are real: Operations, Strategy, Guides, Marketing, Reporting, Verifier, Technology.",
        "Map: 60 real food places around UM (26 cafe, 23 fast food, 8 food court). (test 'Market map — competitors near UM')",
        "Plan record: run 171822-c203 / chat 1010174017-288a.",
        "Chat 'bought sugar, paid TNG' test: 7 app actions, all correct, number check passed.",
    ])

    # ---------------- slide 4: every day ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 4 / 7  ·  1:30 – 2:05",
                  "Money in, money out, and the alerts that matter",
                  "Criterion 5 · Usable results")
    # KPI strip on left
    add_panel(s, Inches(0.55), Inches(1.85), Inches(5.6), Inches(5.05))
    add_text(s, Inches(0.75), Inches(2.0), Inches(5.2), Inches(0.4),
             "Money Flow · synthetic demo data", size=11, bold=True, color=MUTED)
    add_text(s, Inches(0.75), Inches(2.5), Inches(5.2), Inches(0.5),
             "MYR 2,507.25 in", size=22, bold=True, color=ACCENT)
    add_text(s, Inches(0.75), Inches(3.05), Inches(5.2), Inches(0.5),
             "MYR 1,172.30 out", size=22, bold=True, color=RGBColor(0xB9, 0x1C, 0x1C))
    add_text(s, Inches(0.75), Inches(3.6), Inches(5.2), Inches(0.5),
             "MYR 1,334.95 kept", size=22, bold=True, color=INK)
    add_text(s, Inches(0.75), Inches(4.25), Inches(5.2), Inches(2.5),
             [
                 "Orders from WhatsApp, Instagram and the online shop — AI prices from menu.csv.",
                 "Inventory with auto-reorder; supplier orders go to the supplier's WhatsApp after you approve.",
                 "Auto-posting · Customers & reviews · Task checklist.",
                 "Heads-up: 'Cookies run out in 3.2 days — reorder now.'",
             ], size=12, color=INK)
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "04_money_flow.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "Live Money Flow page. Verified: in MYR 2,507.25, out MYR 1,172.30. Synthetic.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 4 — Criterion 5: usable and verifiable results.",
        "All four tile numbers are visible on the Money Flow screenshot on the right.",
        "Online banking and Touch 'n Go connections are simulated feeds; the badge says SIMULATED.",
        "Auto-reorder test S2: cookies 18 ≤ reorder 20 → 2 × 1 kg chips, MYR 39.80, sources.",
        "Auto-reply WhatsApp test S3: 4 automatic replies, MYR 21.50 menu-priced.",
        "Do not claim these are real revenue. They are synthetic demo data.",
    ])

    # ---------------- slide 5: easy and safe ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 5 / 7  ·  2:05 – 2:35",
                  "One chat. Owner approves. Real money never moves.",
                  "Criterion 5 · Ease of use · Safety")
    add_text(s, Inches(0.55), Inches(1.85), Inches(5.6), Inches(5.2),
             [
                 "Plain language and the top actions first.",
                 "Owner chooses how involved to be: quick answers, or a plan they approve step by step.",
                 "If the agent isn't sure, it asks.",
                 "Give it an order with no customer name and it asks 'Who is this order for?'",
                 "Every change has Undo. Every MYR figure is checked against the data.",
                 "Payments are simulated and wait for the owner's approval.",
             ], size=15, color=INK)
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "07_inventory.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "Inventory: 'Approve & pay' / 'Not now' gate, supplier options, sources for every order.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 5 — Criterion 5 (ease-of-use) and safety.",
        "Ease of use is our headline advantage. The chat is the product.",
        "Involvement modes: Auto / Ask me / Approve at end (Section G.10). Live demo uses Auto.",
        "Asks instead of guessing: 'Bug: agent assumed the customer of an unnamed order' fix; console holds unnamed orders and asks.",
        "Undo on every app action. (test S9)",
        "Number check: caught invented weekday figures (test S8). Now fixed and re-verified.",
        "Payments: 'Pay (simulated)' badge; never requests cards or passwords (Section G.14).",
    ])

    # ---------------- slide 6: proof ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 6 / 7  ·  2:35 – 2:50",
                  "Tested on synthetic data. Real-user testing is next.",
                  "Criterion 5 · Verifiable")
    add_panel(s, Inches(0.55), Inches(1.85), Inches(5.6), Inches(5.05))
    add_text(s, Inches(0.75), Inches(2.0), Inches(5.2), Inches(0.4),
             "Evidence at a glance", size=11, bold=True, color=MUTED)
    add_text(s, Inches(0.75), Inches(2.5), Inches(5.2), Inches(4.2),
             [
                 "• WorkBuddy CLI live, streaming events  (F1)",
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
                 "• 22 sample WhatsApp clients  (S4)",
             ], size=12, color=INK)
    add_text(s, Inches(0.75), Inches(6.55), Inches(5.2), Inches(0.3),
             "Full log: docs/AGENT_CONSOLE_TESTS.md",
             size=10, italic=True, color=MUTED)
    add_panel(s, Inches(6.4), Inches(1.8), Inches(6.45), Inches(4.95))
    add_image_fit(s, os.path.join(SHOTS, "11_proof.png"),
                  Inches(6.45), Inches(1.85), Inches(6.35), Inches(4.85))
    add_text(s, Inches(6.45), Inches(6.78), Inches(6.35), Inches(0.25),
             "14-row evidence table rendered from the test log. Synthetic data only.",
             size=9, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 6 — Criterion 5: verifiable.",
        "Every claim on the slide is a row in docs/AGENT_CONSOLE_TESTS.md (date 2026-10-10 and 2026-10-11).",
        "If pressed for a number: every figure shown is on the test-log row, all synthetic.",
        "Honest next step: real-user testing with 3–5 student sellers. Do not claim results we have not measured.",
    ])

    # ---------------- slide 7: close ----------------
    s = prs.slides.add_slide(BLANK)
    add_title_bar(s, "Slide 7 / 7  ·  2:50 – 3:00",
                  "Thank you.",
                  "Repeat the core question")
    add_text(s, Inches(0.55), Inches(2.3), Inches(8.5), Inches(2.0),
             "Enterprise Buddy turns a messy side hustle into a business that runs itself — all from one chat.",
             size=24, bold=True, color=INK)
    add_text(s, Inches(0.55), Inches(4.0), Inches(12.2), Inches(1.5),
             "Our AI agent uses WorkBuddy to solve a real problem, and it actually gets things done.",
             size=22, bold=True, color=ACCENT)
    add_text(s, Inches(0.55), Inches(5.6), Inches(12.2), Inches(0.6),
             "github.com/Griff1018/hackerdorm    ·    run with: PORT=8091 python console/server.py",
             size=12, color=MUTED)
    add_text(s, Inches(0.55), Inches(6.4), Inches(12.2), Inches(0.4),
             "Synthetic demo data. Live demo apps: WhatsApp, Instagram, LinkedIn, Enterprise Buddy Shop. Simulated: payments, online banking, Touch 'n Go, marketplaces.",
             size=10, italic=True, color=MUTED)
    add_brand_strip(s)
    add_notes(s, [
        "Slide 7 — repeat the core judging sentence out loud.",
        "If time runs short, drop slide 6 first; the proof survives in the speaker notes.",
        "Open the repo and the running demo only if asked.",
    ])

    prs.save(OUT)
    print("wrote", OUT)
    print("slides:", len(prs.slides))


if __name__ == "__main__":
    build()