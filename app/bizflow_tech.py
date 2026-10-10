"""BizFlow Technology department: hourly (or on-demand) health check.

Reads only. It never edits a page, never restarts anything and never applies a fix without approval.
Every run appends one row to tech_health_log.csv so the hourly schedule is provable in the demo.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bizflow_outputs import now_iso

PAGES = ["demo/index.html", "demo/shop_page.html", "demo/social_feed.html"]
REQUIRED_LABEL = "SYNTHETIC"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _local_links(html: str) -> list[str]:
    return re.findall(r'(?:href|src)="([^"#:]+)"', html)


def run_check(root: Path, max_output_age_hours: int = 24) -> dict:
    findings: list[dict] = []

    def add(check, target, result, severity, evidence, fix):
        findings.append({"check": check, "target": target, "result": result, "severity": severity,
                         "evidence": evidence, "proposed_fix": fix})

    # 1. pages exist and are non-empty
    for rel in PAGES:
        p = root / rel
        if not p.exists():
            add("page_exists", rel, "fail", "error", f"{rel} is missing", "create the page")
        elif len(_read(p).strip()) < 50:
            add("page_not_empty", rel, "fail", "error", f"{rel} is empty or nearly empty", "restore the page content")
        else:
            add("page_exists", rel, "pass", "info", f"{rel} present, {len(_read(p))} chars", "")

    # 2. synthetic-data label present on every page
    for rel in PAGES:
        html = _read(root / rel)
        if html and REQUIRED_LABEL not in html.upper():
            add("synthetic_label", rel, "fail", "warning",
                f"'{REQUIRED_LABEL}' not found in {rel}",
                "add the synthetic-data label to the page")
        elif html:
            add("synthetic_label", rel, "pass", "info", "label present", "")

    # 3. internal links resolve (relative to the page that contains them)
    for rel in PAGES:
        html = _read(root / rel)
        page_dir = (root / rel).parent
        for link in _local_links(html):
            link = link.split("?")[0].split("#")[0]
            if not link or "${" in link:
                continue  # dynamic links are resolved by the page at runtime; static check cannot dereference them
            target = (page_dir / link)
            if not target.exists():
                add("link_resolves", f"{rel} -> {link}", "fail", "error",
                    f"{rel} links to {link}, which does not exist", f"fix or remove the link in {rel}")
            else:
                add("link_resolves", f"{rel} -> {link}", "pass", "info", "target exists", "")

    # 4. latest run outputs are fresh
    snap = root / "data" / "output" / "business_snapshot.json"
    if not snap.exists():
        add("output_freshness", "data/output/business_snapshot.json", "fail", "warning",
            "no snapshot from a BizFlow run yet", "run BizFlow once")
    else:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(snap.stat().st_mtime, tz=timezone.utc)
        if age > timedelta(hours=max_output_age_hours):
            add("output_freshness", "data/output/business_snapshot.json", "fail", "warning",
                f"snapshot is {int(age.total_seconds() // 3600)} h old (limit {max_output_age_hours} h)",
                "re-run BizFlow to refresh the outputs")
        else:
            add("output_freshness", "data/output/business_snapshot.json", "pass", "info",
                f"snapshot is {int(age.total_seconds() // 60)} min old", "")

    # 5. shop page stock agrees with inventory.csv
    inv = root / "data" / "sample" / "inventory.csv"
    shop = _read(root / "demo" / "shop_page.html")
    if shop and inv.exists():
        with inv.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        seen: dict[str, set] = {}
        for r in rows:
            seen.setdefault(r["product_id"], set()).add(r["stock_on_hand"])
        for pid, values in seen.items():
            if len(values) > 1:
                add("shop_page_stock", pid, "fail", "warning",
                    f"inventory.csv has conflicting stock values for {pid}: {sorted(values)}",
                    "recount and keep one current record per product")
            m = re.search(rf"{pid}[^0-9]{{0,40}}?(\d+)\s*(?:in stock|units|pcs)", shop, re.I)
            if m and m.group(1) not in values:
                add("shop_page_stock", pid, "fail", "error",
                    f"shop page shows {m.group(1)} for {pid} but inventory.csv says {sorted(values)}",
                    "drafted fix only - the owner decides whether to update the page")
            else:
                add("shop_page_stock", pid, "pass", "info", "shop page agrees with inventory.csv", "")

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    status = "fail" if errors else ("warning" if warnings else "pass")
    return {"checked_at": now_iso(), "status": status, "findings": findings,
            "counts": {"error": len(errors), "warning": len(warnings),
                       "pass": len([f for f in findings if f["severity"] == "info"])}}


def write_report(path: Path, result: dict) -> None:
    L = ["# TECHNOLOGY HEALTH CHECK - BizFlow", ""]
    L.append(f"Checked at {result['checked_at']} · status **{result['status'].upper()}**")
    L.append("")
    L.append("Read-only check. Nothing was changed; every fix below is a **draft** that needs the owner's approval.")
    L.append("")
    L.append("| check | target | result | severity | evidence | proposed fix |")
    L.append("|---|---|---|---|---|---|")
    for f in result["findings"]:
        L.append(f"| {f['check']} | {f['target']} | {f['result']} | {f['severity']} | {f['evidence']} | {f['proposed_fix']} |")
    L.append("")
    L.append(f"Totals: {result['counts']['pass']} pass · {result['counts']['warning']} warning · "
             f"{result['counts']['error']} error")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def append_log(path: Path, result: dict, trigger: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["checked_at", "trigger", "status", "checks_passed", "warnings", "errors"])
        w.writerow([result["checked_at"], trigger, result["status"], result["counts"]["pass"],
                    result["counts"]["warning"], result["counts"]["error"]])
