"""Run pinned npm/Python audits and enforce VALUE's explicit advisory decisions."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS = ROOT / "publication" / "dependency-advisory-decisions.json"
PYTHON_SCOPES = (
    "value-native-py310",
    "force-reference-py310",
    "force-perfect-foresight-py310",
    "force-validation-py310",
    "force-ci-tools-py310",
)


def _command(command: list[str], *, accepted_codes: set[int]) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode not in accepted_codes:
        raise RuntimeError(
            f"Audit command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout), completed.stderr.strip()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Audit command returned invalid JSON: {' '.join(command)}") from exc


def run_audits() -> dict[str, Any]:
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise RuntimeError("npm was not found")
    npm_report, npm_stderr = _command([npm, "audit", "--json"], accepted_codes={0, 1})
    python_reports: dict[str, Any] = {}
    python_stderr: dict[str, str] = {}
    for scope in PYTHON_SCOPES:
        report, stderr = _command(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(ROOT / "requirements" / f"{scope}.lock"),
                "--format",
                "json",
            ],
            accepted_codes={0, 1},
        )
        python_reports[scope] = report
        python_stderr[scope] = stderr
    return {
        "npm": npm_report,
        "npm_stderr": npm_stderr,
        "python": python_reports,
        "python_stderr": python_stderr,
    }


def _live_findings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for package, row in sorted(raw["npm"].get("vulnerabilities", {}).items()):
        findings.append({
            "finding_id": f"npm:{package}",
            "ecosystem": "npm",
            "package": package,
            "severity": row.get("severity"),
            "direct": bool(row.get("isDirect")),
            "range": row.get("range"),
            "nodes": row.get("nodes", []),
            "advisories": [
                item.get("url") or item.get("source")
                for item in row.get("via", [])
                if isinstance(item, dict)
            ],
        })
    for scope, report in raw["python"].items():
        for dependency in report.get("dependencies", []):
            for vulnerability in dependency.get("vulns", []):
                findings.append({
                    "finding_id": f"python:{scope}:{dependency.get('name')}:{vulnerability.get('id')}",
                    "ecosystem": "python",
                    "scope": scope,
                    "package": dependency.get("name"),
                    "version": dependency.get("version"),
                    "advisory": vulnerability.get("id"),
                    "aliases": vulnerability.get("aliases", []),
                    "fix_versions": vulnerability.get("fix_versions", []),
                })
    return findings


def evaluate(raw: dict[str, Any], decisions_path: Path, *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    policy = json.loads(decisions_path.read_text(encoding="utf-8"))
    decision_rows = policy.get("decisions")
    if not isinstance(decision_rows, list):
        raise ValueError("Dependency decision file has no decisions list")
    decisions = {str(row.get("finding_id")): row for row in decision_rows if isinstance(row, dict)}
    findings = _live_findings(raw)
    errors: list[str] = []
    for finding in findings:
        identifier = finding["finding_id"]
        decision = decisions.get(identifier)
        if not decision:
            errors.append(f"unreviewed advisory: {identifier}")
            continue
        review_by = date.fromisoformat(str(decision.get("review_by") or ""))
        if review_by < today:
            errors.append(f"advisory decision expired: {identifier} ({review_by.isoformat()})")
        if decision.get("disposition") != "accepted_time_bound":
            errors.append(f"live advisory has invalid disposition: {identifier}")
        for field in (
            "severity_classification", "reachability", "exploit_surface",
            "fix_availability", "compensating_control",
        ):
            if not str(decision.get(field) or "").strip():
                errors.append(f"advisory decision lacks {field}: {identifier}")
        severity = str(finding.get("severity") or decision.get("severity_classification") or "").lower()
        if severity in {"high", "critical"}:
            errors.append(f"release-blocking {severity} advisory remains: {identifier}")
        finding["decision"] = decision
    live_ids = {finding["finding_id"] for finding in findings}
    stale = sorted(set(decisions).difference(live_ids))
    return {
        "schema_version": "value.dependency-audit/v1",
        "candidate_date": today.isoformat(),
        "passed": not errors,
        "decision": "GO" if not errors else "NO_GO",
        "summary": {
            "npm_total": raw["npm"].get("metadata", {}).get("vulnerabilities", {}).get("total", 0),
            "npm_high": raw["npm"].get("metadata", {}).get("vulnerabilities", {}).get("high", 0),
            "npm_critical": raw["npm"].get("metadata", {}).get("vulnerabilities", {}).get("critical", 0),
            "python_total": sum(1 for finding in findings if finding["ecosystem"] == "python"),
            "live_findings": len(findings),
            "stale_decisions": len(stale),
        },
        "findings": findings,
        "stale_decisions": stale,
        "errors": errors,
        "raw": raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = evaluate(run_audits(), arguments.decisions)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "decision", "summary", "errors")}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
