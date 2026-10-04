"""Verify that every project-selected module executed for every model year."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SLOT_ACTIONS = {
    "psm": "psm.complete",
    "investment": "investment.complete",
    "pipeline": "pipeline.complete_year",
    "vre_cap": "vre_cap.complete",
    "storage_cap": "storage_cap.complete",
}


def verify(run_dir: Path) -> dict:
    project_path = run_dir / "project-snapshot.json"
    pack_path = run_dir / "data-pack-snapshot.json"
    result_path = run_dir / "model-output" / "modular-run.json"
    evidence_path = run_dir / "model-output" / "module-events.jsonl"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result_years = sorted(int(row["Year"]) for row in result["system_cost_history"])
    checks = []
    for year in result_years:
        for slot, action in SLOT_ACTIONS.items():
            module_id = project["modules"][slot]
            matches = [
                event
                for event in events
                if int(event["year"]) == year
                and event["module_id"] == module_id
                and event["action"] == action
            ]
            checks.append({
                "year": year,
                "slot": slot,
                "module_id": module_id,
                "action": action,
                "event_count": len(matches),
                "pass": len(matches) == 1,
            })
    return {
        "passed": (
            project_path.is_file()
            and pack_path.is_file()
            and result_years
            and all(check["pass"] for check in checks)
        ),
        "run_dir": str(run_dir.resolve()),
        "years": result_years,
        "project_snapshot": project_path.is_file(),
        "data_pack_snapshot": pack_path.is_file(),
        "checks_passed": sum(check["pass"] for check in checks),
        "checks_total": len(checks),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        key: report[key]
        for key in ("passed", "years", "checks_passed", "checks_total")
    }, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
