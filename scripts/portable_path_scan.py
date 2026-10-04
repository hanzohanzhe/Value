"""Reject developer-machine path assumptions from distributable source."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.path_hygiene import scan_path


ROOTS = ("backend", "gridform_core", "app", "scripts")
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".ps1", ".cmd"}
EXCLUDED = {
    (ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh" / "compat").resolve(),
    Path(__file__).resolve(),
    # This second policy scanner must contain the forbidden-path regexes it
    # applies to built wheel contents; those patterns are rules, not paths.
    (ROOT / "scripts" / "package_policy_scan.py").resolve(),
}


def main() -> None:
    issues: list[str] = []
    for root_name in ROOTS:
        for path in (ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                continue
            if path.name.startswith("redraw_"):
                # Historical, one-off figure scripts are not shipped as VALUE
                # application code. Their source-image locators remain local.
                continue
            if any(excluded == path.resolve() or excluded in path.resolve().parents for excluded in EXCLUDED):
                continue
            for finding in scan_path(path):
                issues.append(
                    f"{path.relative_to(ROOT)}:{finding.line}: "
                    f"{finding.kind}: {finding.value}"
                )
    if issues:
        raise SystemExit("PORTABLE PATH SCAN FAILED\n" + "\n".join(issues))
    print("PORTABLE PATH SCAN PASSED")


if __name__ == "__main__":
    main()
