"""Fail when scientific runtime globals are mutated outside declared boundaries."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "docs/scientific-readiness/global-mutation-allowlist.json"
PATTERNS = {
    "working_directory": re.compile(r"\bos\.chdir\s*\("),
    "environment": re.compile(r"\bos\.environ(?:\.update|\s*\[)"),
    "compat_config": re.compile(r"\bconfig\.[A-Za-z_][A-Za-z0-9_]*(?:\s*=|\.update\s*\()"),
}
EXCLUDED_PARTS = {"compat", "runtime_compat", "__pycache__"}


def scan() -> dict[str, object]:
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    allowed = {
        (str(row["path"]), kind)
        for row in payload["entries"]
        for kind in row["kinds"]
    }
    findings = []
    for path in (ROOT / "gridform_core").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if set(path.relative_to(ROOT).parts).intersection(EXCLUDED_PARTS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append({
                    "path": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "kind": kind,
                    "allowlisted": (relative, kind) in allowed,
                })
    undeclared = [row for row in findings if not row["allowlisted"]]
    return {
        "schema_version": "value.global-mutation-scan/v1",
        "go": not undeclared,
        "findings": findings,
        "undeclared": undeclared,
    }


def main() -> None:
    report = scan()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["go"] else 1)


if __name__ == "__main__":
    main()
