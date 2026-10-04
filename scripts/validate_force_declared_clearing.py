"""Validate a live VALUE declared-input ledger with the independent CBC oracle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_validation.value_clearing_oracle import validate_declared_database
from gridform_validation.independent_oracle import solver_identity


REQUIRED_RESOURCE_KINDS = {"thermal", "vre", "storage_discharge", "import"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = validate_declared_database(args.database)
    present = set(report["resource_kinds"])
    missing = sorted(REQUIRED_RESOURCE_KINDS - present)
    report["oracle"] = solver_identity()
    report["required_resource_kinds"] = sorted(REQUIRED_RESOURCE_KINDS)
    report["missing_required_resource_kinds"] = missing
    report["clearing_validation_passed"] = bool(report["passed"] and not missing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "declared_rows": report["declared_rows"],
        "lp_passed_rows": report["lp_passed_rows"],
        "lp_failed_rows": report["lp_failed_rows"],
        "non_lp_rows": report["non_lp_information_structure_rows"],
        "storage_transition_failed_rows": report["storage_transition_failed_rows"],
        "missing_required_resource_kinds": missing,
        "clearing_validation_passed": report["clearing_validation_passed"],
    }, indent=2))
    raise SystemExit(0 if report["clearing_validation_passed"] else 1)


if __name__ == "__main__":
    main()
