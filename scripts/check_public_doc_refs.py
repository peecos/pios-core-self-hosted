#!/usr/bin/env python3
"""Fail if public docs reference missing local documentation files."""

from __future__ import annotations

import re
from pathlib import Path


REF_RE = re.compile(r"(docs/[A-Za-z0-9_./-]+\.(?:md|html|txt|json))")


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or ".git" in path.parts:
            continue
        if path.suffix not in {".md", ".html", ".txt", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in REF_RE.finditer(line):
                prefix = line[: match.start()]
                if "https://github.com/peecos/" in prefix:
                    continue
                ref = match.group(1)
                if not (root / ref).exists():
                    findings.append(f"{path.relative_to(root)}:{line_no}: missing {ref}")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan(root)
    if findings:
        print("\n".join(findings))
        return 1
    print("public doc references passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
