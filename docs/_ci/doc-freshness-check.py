#!/usr/bin/env python3
"""Doc freshness check (S25).

Every doc may carry frontmatter:
  ---
  owner: <team/role>
  last-reviewed: YYYY-MM-DD
  review-cadence: <int>  (days)
  status: draft | active | deprecated | superseded
  supersedes: <path>
  superseded-by: <path>
  ---

This check warns on docs that are overdue for review. Docs without
frontmatter are reported (not failed) — frontmatter is added incrementally.

Exit code 0 always (warn-only by default); set STRICT=1 to fail on missing
frontmatter.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DEFAULT_CADENCE_DAYS = 365
STRICT = os.environ.get("STRICT", "0") == "1"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def main() -> int:
    today = date.today()
    missing: list[str] = []
    overdue: list[str] = []
    deprecated_active: list[str] = []

    for md in DOCS.rglob("*.md"):
        rel = md.relative_to(ROOT)
        # skip CI scripts dir and the ADR template
        if rel.parts[1] == "_ci" if len(rel.parts) > 1 else False:
            continue
        if md.name == "0000-template.md":
            continue
        text = md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm:
            missing.append(str(rel))
            continue
        status = fm.get("status", "active")
        if status in ("deprecated", "superseded"):
            # ensure it has a successor pointer
            if status == "superseded" and not fm.get("superseded-by"):
                deprecated_active.append(f"{rel}: status=superseded but no 'superseded-by'")
            continue
        last = fm.get("last-reviewed")
        cadence = int(fm.get("review-cadence", DEFAULT_CADENCE_DAYS))
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d").date()
                age = (today - last_dt).days
                if age > cadence:
                    overdue.append(f"{rel}: last reviewed {last} ({age} days > {cadence})")
            except ValueError:
                missing.append(f"{rel}: invalid last-reviewed date '{last}'")
        else:
            missing.append(f"{rel}: no last-reviewed frontmatter")

    print("=== Doc freshness report ===")
    if missing:
        print(f"\nMissing/invalid frontmatter ({len(missing)}):")
        for m in missing[:50]:
            print(f"  - {m}")
        if len(missing) > 50:
            print(f"  ... and {len(missing) - 50} more")
    if overdue:
        print(f"\nOverdue for review ({len(overdue)}):")
        for o in overdue:
            print(f"  - {o}")
    if deprecated_active:
        print(f"\nSuperseded without successor ({len(deprecated_active)}):")
        for d in deprecated_active:
            print(f"  - {d}")
    if not (missing or overdue or deprecated_active):
        print("OK: all docs have valid, in-cadence frontmatter")
    else:
        print(f"\nSummary: {len(missing)} missing, {len(overdue)} overdue, {len(deprecated_active)} broken supersession")

    if STRICT and missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
