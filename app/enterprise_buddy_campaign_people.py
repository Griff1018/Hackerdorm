"""FR-03 campaign planner and FR-04 People/job-ad outputs.

All outputs are drafts. Nothing is posted, no applicants are collected, and no real platform
connection is implied.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_campaign(root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    posts = [
        ("Monday", "Instagram post", "Campus Crumb Granola Bar - check today's menu and message us to order.", "#CampusCrumb #CampusSnacks"),
        ("Tuesday", "Instagram story", "Campus snack break: ask about today's available items.", "#CampusCrumb #StudentSeller"),
        ("Wednesday", "TikTok script", "Show the synthetic campus snack prep table, then invite viewers to check the menu.", "#CampusCrumb #CampusFood"),
        ("Thursday", "Facebook campus group", "Campus Crumb has synthetic demo stock available for campus pickup. Message to order.", "#CampusCrumb #CampusPickup"),
        ("Friday", "WhatsApp Status", "Weekend study snack reminder: see the current menu before ordering.", "#CampusCrumb #StudySnacks"),
    ]
    social_dir = output / "social_posts"
    social_dir.mkdir(parents=True, exist_ok=True)
    for i, (day, platform, caption, tags) in enumerate(posts, 1):
        (social_dir / f"{i:02d}_{day.lower()}.md").write_text(
            f"# {platform} draft - {day}\n\n**DRAFT ONLY - not posted. Synthetic business.**\n\n{caption}\n\n{tags}\n\nImage brief: photograph the product on a plain campus table; no real customer faces.\n",
            encoding="utf-8")
    plan = "# CAMPAIGN PLAN - FR-03\n\n**DRAFT ONLY - nothing is posted automatically.**\n\n"
    plan += "Posting times are general guidelines, not based on engagement data. Prices/offers are omitted unless sourced from configured files.\n\n"
    plan += "| day | platform | draft |\n|---|---|---|\n" + "\n".join(f"| {d} | {p} | [draft](social_posts/{i:02d}_{d.lower()}.md) |" for i, (d, p, _, _) in enumerate(posts, 1)) + "\n\nNo fake reviews, fake engagement, unsupported health claims, or automatic posting."
    (output / "campaign_plan.md").write_text(plan + "\n", encoding="utf-8")
    (output / "social_feed_preview.json").write_text(json.dumps({
        "title": "Campus Crumb social post preview (simulated)", "synthetic": True,
        "platforms_are_generic_previews": True,
        "posts": [{"day": d, "platform": p, "caption": caption, "hashtags": tags,
                   "draft_only": True} for d, p, caption, tags in posts],
    }, indent=2), encoding="utf-8")
    return {"status": "passed", "posts": len(posts), "draft_only": True}


def build_job_ad(root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    profile = json.loads((root / "data" / "business_profile.json").read_text(encoding="utf-8"))
    pay = profile.get("part_time_pay_range_myr", "owner-set range not supplied")
    ad = f"""# Part-time Campus Snack Assistant - draft

**DRAFT ONLY - not posted. Synthetic role for Campus Crumb.**

Campus Crumb is a student-run campus snack and drink seller seeking a part-time assistant for campus pickup and preparation support.

- Tasks: prepare order pick lists, pack synthetic demonstration orders, keep the workspace organised, and help with campus pickup handoff.
- Suggested shifts: owner to confirm days and hours based on actual demand; the current data has dates but not times of day.
- Pay: **{pay}** (confirm compliance with Malaysia's current minimum-wage and employment rules before posting).
- Requirements: reliable communication, safe food-handling awareness, and ability to follow written order instructions.
- Apply: owner to add a manual contact method before posting; no applicant data is collected by this demo.

Fair-wording check: no age, gender, race, religion, marital-status, or appearance requirement is used.
"""
    (output / "job_ad_part_time_campus_snack_assistant.md").write_text(ad, encoding="utf-8")
    kit = """# HIRING KIT - FR-04

**Synthetic draft only. Do not post automatically and do not collect real applicants.**

## Manual posting checklist

1. Owner confirms pay range and legal/employment compliance.
2. Owner adds an approved contact method.
3. Owner copies the draft manually to the chosen channel.
4. Owner records only synthetic test entries during the demo.

## Fair interview questions

- Tell us about a time you had to follow a detailed instruction.
- How would you check an order before handing it to a customer?
- How would you handle a request you are not authorised to answer?
- How would you prioritise two pickup orders arriving together?
- What availability can you reliably commit to?

## Empty applicant tracker template

`applicant_id,display_name,contact_placeholder,availability,notes,status`

No candidate screening, ranking, or real personal data is supported in this build.
"""
    (output / "hiring_kit.md").write_text(kit, encoding="utf-8")
    return {"status": "passed", "job_ad": True, "hiring_kit": True, "draft_only": True}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    output = root / "data" / "output"
    print(json.dumps({"campaign": build_campaign(root, output), "people": build_job_ad(root, output)}, indent=2))
