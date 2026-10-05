"""Read-time presentation of a run's scientific status (X0 S10).

One function decides what every reader sees as a run's scientific status:
``/api/runs``, ``/api/runs/<id>``, run summaries and comparisons all call
:func:`present_scientific_status` (C7).  It never writes to the run directory:
historical bundles are immutable and are only annotated when read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def present_scientific_status(run: MutableMapping[str, Any], run_root: Path) -> MutableMapping[str, Any]:
    """Set the presented scenario status and retained-comparison fields of ``run``.

    Moved unchanged from ``backend/server.py`` ``present_run`` (X0 S10a).
    Historical completed bundles are immutable.  Some dynamic-policy runs
    were packaged before retained comparison was correctly classified as
    informational.  Present the scenario gate separately from the raw
    embedded report, based only on its preserved execution, contract and
    analytical evidence; never rewrite that report on disk.
    """

    validation_path = run_root / "model-output" / str(
        run.get("scientific_validation_artifact")
        or "validation/scientific-validation.json"
    )
    validation = _read_object(validation_path)
    storage_policy = str((run.get("modules") or {}).get("storage_cost") or "")
    alternative_policy = storage_policy in {
        "dynamic-annual-storage-cost", "user-formula-storage-cost"
    }
    role = validation.get("retained_numerical_comparison_role")
    if not role:
        role = (
            "informational_scenario_difference"
            if alternative_policy
            else "required_reproduction_gate"
        )
    retained_status = validation.get("retained_numerical_comparison_status")
    if alternative_policy and retained_status == "failed":
        retained_status = "expected_difference"
    evidence_passed = all(
        validation.get(field) == "passed"
        for field in (
            "execution_status",
            "contract_validation_status",
            "analytical_mechanism_status",
        )
    )
    scenario_status = validation.get("scientific_validation_status")
    if alternative_policy and evidence_passed and run.get("mode") in {"full", "two_year"}:
        scenario_status = "passed"
    run["scientific_scenario_status"] = scenario_status or "not_evaluated"
    run["retained_comparison_role"] = role
    run["retained_numerical_comparison_status"] = retained_status or "not_evaluated"
    return run
