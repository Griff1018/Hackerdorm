"""One-prompt harness for the project BizFlow Skill.

The harness is intentionally small: a fresh-context proof supplies only an owner prompt and
this wrapper maps it to the documented full pipeline. It is not a hidden business rule.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument("owner_prompt_file")
    p.add_argument("--output", default="data/output/fresh_chat_skill_proof")
    args = p.parse_args()
    prompt = (root / args.owner_prompt_file).read_text(encoding="utf-8").strip()
    python = sys.executable
    # Refresh deterministic supplier research as part of the Skill workflow, then provide it
    # to the selected output directory. The owner supplies only the prompt.
    subprocess.check_call([python, str(root / "scripts" / "build_supplier_research.py")], cwd=root)
    target = root / args.output
    target.mkdir(parents=True, exist_ok=True)
    source = root / "data" / "output" / "supplier_research_input.csv"
    (target / "supplier_research_input.csv").write_bytes(source.read_bytes())
    cmd = [python, str(root / "app" / "run_bizflow.py"), "--data", "data/sample", "--output", args.output,
           "--po", "--tech", "--customer-demo", "--marketplace", "--campaign", "--people", "--goal", prompt]
    return subprocess.call(cmd, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
