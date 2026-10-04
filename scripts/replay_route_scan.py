from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOW = {
    "gridform_core/builtin/scheme_c_1000twh/reference/__init__.py",
    "gridform_core/builtin/scheme_c_1000twh/reference/replay.py",
    "gridform_core/builtin/scheme_c_1000twh/modular_run.py",
    "gridform_core/reference_comparison.py",
}
TOKENS = ("SchemeCReplayData", "run_modular_scheme_c", ".bind(replay")


def main() -> None:
    findings = []
    for path in (ROOT / "gridform_core").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        matched = [token for token in TOKENS if token in text]
        if matched and relative not in ALLOW:
            findings.append({"path": relative, "tokens": matched})
    report = {
        "schema_version": "value.replay-route-scan/v1",
        "allowlist": sorted(ALLOW),
        "findings": findings,
        "passed": not findings,
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
