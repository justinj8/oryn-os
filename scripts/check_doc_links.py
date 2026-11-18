#!/usr/bin/env python3
"""Fail if the docs cite a file, directory or file:line that doesn't exist.

Checks backticked paths like `backend/oryn/core/db.py:50` and markdown links to local files.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Reader-facing docs only (docs/superpowers holds the historical design spec and build plan).
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")), *sorted((ROOT / "docs" / "adr").glob("*.md"))]
TICK = re.compile(r"`((?:backend|frontend|deploy|scripts|docs|\.github)/[^`\s]+?)(?::(\d+))?`")
LINK = re.compile(r"\]\((?!https?:|#|mailto:)([^)#\s]+)")

problems = []
for doc in DOCS:
    text = doc.read_text()
    for m in TICK.finditer(text):
        path, line = ROOT / m[1], m[2]
        if not path.exists():
            problems.append(f"{doc.relative_to(ROOT)}: missing {m[1]}")
        elif line and path.is_file() and int(line) > len(path.read_text().splitlines()):
            problems.append(f"{doc.relative_to(ROOT)}: {m[1]} has no line {line}")
    for m in LINK.finditer(text):
        if not (doc.parent / m[1]).exists():
            problems.append(f"{doc.relative_to(ROOT)}: broken link {m[1]}")

print("\n".join(problems) or f"ok: {len(DOCS)} documents, all references resolve")
sys.exit(1 if problems else 0)
