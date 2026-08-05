#!/usr/bin/env python3
"""ADR index integrity check.

Verifies that:
  1. Every ADR file under docs/adr/ (except INDEX.md and template) is listed
     in docs/adr/INDEX.md.
  2. Every phase-level `decisions.md` references ADRs (does not introduce
     new decisions without an ADR). Warns on rows that still hold
     decision content inline rather than pointing to an ADR.
  3. ADR files referenced in INDEX.md actually exist.

Exits non-zero on hard failures (missing ADR file, unlisted ADR file).
Inline decision content in phase `decisions.md` is a warning only during
the migration period.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
INDEX = ADR_DIR / "INDEX.md"
DOCS = ROOT / "docs"

ADR_FILE_RE = re.compile(r"^(\d{4})-.+\.md$")


def collect_adr_files() -> set[str]:
    files = set()
    for p in ADR_DIR.iterdir():
        if p.is_file() and p.suffix == ".md" and p.name not in {"INDEX.md", "0000-template.md"}:
            if ADR_FILE_RE.match(p.name):
                files.add(p.name)
    return files


def collect_index_entries() -> set[str]:
    text = INDEX.read_text(encoding="utf-8")
    # rows like `| ADR-0001 | ... |` -> map to file names 0001-...md
    entries: set[str] = set()
    for m in re.finditer(r"\|\s*(ADR-\d{4})\s*\|", text):
        adr_id = m.group(1).replace("ADR-", "")
        # find a file starting with that id
        for f in ADR_DIR.iterdir():
            if f.name.startswith(f"{adr_id}-") and f.suffix == ".md":
                entries.add(f.name)
                break
    return entries


def check_phase_decisions() -> list[str]:
    """Warn on phase decisions.md that introduce decisions without ADR refs."""
    warnings: list[str] = []
    for d in sorted(DOCS.iterdir()):
        if not d.is_dir() or not d.name[:2].isdigit():
            continue
        dec = d / "decisions.md"
        if not dec.exists():
            continue
        text = dec.read_text(encoding="utf-8")
        # crude: any "## D{phase}-{n}" heading without an "ADR-" reference nearby
        for m in re.finditer(r"^##\s+(D\d+-\d+)", text, re.MULTILINE):
            # check there's an ADR reference in the following ~500 chars
            window = text[m.start(): m.start() + 500]
            if "ADR-" not in window:
                warnings.append(
                    f"{dec.relative_to(ROOT)}:{text[:m.start()].count(chr(10)) + 1} "
                    f"decision {m.group(1)} has no ADR reference (migration pending)"
                )
    return warnings


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    adr_files = collect_adr_files()
    index_entries = collect_index_entries()

    unlisted = adr_files - index_entries
    missing = index_entries - adr_files

    for f in sorted(unlisted):
        failures.append(f"ADR file {f} exists but is not listed in INDEX.md")
    for f in sorted(missing):
        failures.append(f"INDEX.md references {f} but file does not exist")

    # Guard against the acoustic-shadow bug: an INDEX that lists ADRs but an
    # empty ADR directory passes the bijection check vacuously (both sets
    # empty). A populated registry MUST have backing files.
    index_rows = len(re.findall(r"\|\s*ADR-\d{4}\s*\|", INDEX.read_text(encoding="utf-8")))
    if index_rows > 0 and not adr_files:
        failures.append(
            f"INDEX.md lists {index_rows} ADRs but no ADR-NNNN-*.md files exist "
            f"in docs/adr/ — registry has no backing records"
        )
    elif index_rows > 0 and len(adr_files) < index_rows:
        missing_count = index_rows - len(adr_files)
        failures.append(
            f"INDEX.md lists {index_rows} ADRs but only {len(adr_files)} ADR files exist "
            f"({missing_count} ADR rows have no backing file)"
        )

    warnings.extend(check_phase_decisions())

    if failures:
        print("FAIL: ADR index integrity check")
        for f in failures:
            print(f"  - {f}")
    else:
        print("OK: ADR index integrity check passed")

    if warnings:
        print("\nWARNINGS (migration pending):")
        for w in warnings:
            print(f"  - {w}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
