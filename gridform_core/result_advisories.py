"""Read-time presentation of a run's scientific status and advisories (X0 S10).

One module decides what every reader sees about a run's scientific standing:
``/api/runs``, ``/api/runs/<id>``, run summaries, comparisons and the VALUE 101
results all go through :func:`present_scientific_status` (C7, C8, C9).  It never
writes to the run directory: historical bundles are immutable and are only
annotated when read.

* **Status vocabulary** (C8): ``passed``, ``failed``, ``not_evaluated``,
  ``superseded_pre_fix``, ``reproduction_with_declared_deviations``,
  ``reproduction_conformant``.  Only positive claims are overridden: a run
  produced before methodology profiles existed that recorded ``passed`` is
  presented as ``superseded_pre_fix``; the recorded value is kept under
  ``recorded_*``.  ``failed`` and ``not_evaluated`` stay and gain advisories.
* **Advisories**: one per catalogue correction the run did not apply whose
  ``applies_when`` matches the run, plus the generic advisories of
  ``data/methodology/advisories.json``.  Legacy module ids are normalised first.
* **Result publication** (Q14): a profile whose rule is
  ``raw_invariants_must_pass`` (the frozen doctoral reproduction) publishes
  annual results on result pages only when the run's raw invariants all
  passed; otherwise they are ``withheld`` (Inspect and exports stay
  available).  The raw-invariant evidence is written by P0-4 (status fields
  ``raw_invariants`` or ``run_invariant_status`` + ``energy_balance_status``);
  until a run carries it the verdict is ``not_evaluated`` and the results are
  withheld.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from .legacy_module_ids import normalize_engine, normalize_module_id
from .methodology import CATALOGUE_ROOT, SEVERITIES, MethodologyCatalogError, load_catalogue

ADVISORY_SCHEMA = "value.result-advisory/v1"
ADVISORIES_FILE_SCHEMA = "value.methodology-advisories/v1"
GENERIC_PREDICATES = ("pre_profile_run", "legacy_validation_report")
LEGACY_VALIDATION_SCHEMA = "value.scientific-validation/v1"
STATUS_VOCABULARY = (
    "passed", "failed", "not_evaluated", "superseded_pre_fix",
    "reproduction_with_declared_deviations", "reproduction_conformant",
)
# Positive validation claims a pre-profile run may carry; each is superseded.
SUPERSEDED_FIELDS = (
    "scientific_scenario_status", "scientific_validation_status", "contract_validation_status",
)
RAW_INVARIANT_PASS = {"passed", "reproduction_conformant"}
RAW_INVARIANT_FAIL = {"failed", "reproduction_with_declared_deviations"}
NEEDS_REVIEW_SEVERITIES = {"high", "critical"}
WITHHELD_FAILED = "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED"
WITHHELD_NOT_EVALUATED = "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def load_generic_advisories_from(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != ADVISORIES_FILE_SCHEMA:
        raise MethodologyCatalogError(f"advisories.json: schema_version must be {ADVISORIES_FILE_SCHEMA}")
    rows = payload.get("advisories")
    if not isinstance(rows, list):
        raise MethodologyCatalogError("advisories.json: advisories must be a list")
    seen: set[str] = set()
    result = []
    for index, row in enumerate(rows):
        where = f"advisories.json[{index}]"
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row.get("id"):
            raise MethodologyCatalogError(f"{where}: id is required")
        if row["id"] in seen:
            raise MethodologyCatalogError(f"{where}: duplicate id {row['id']}")
        seen.add(row["id"])
        if row.get("applies_to") not in GENERIC_PREDICATES:
            raise MethodologyCatalogError(f"{where}: applies_to must be one of {GENERIC_PREDICATES}")
        if row.get("severity") not in SEVERITIES:
            raise MethodologyCatalogError(f"{where}: severity must be one of {SEVERITIES}")
        for key in ("title", "summary"):
            if not isinstance(row.get(key), str) or not row.get(key):
                raise MethodologyCatalogError(f"{where}: {key} is required")
        metrics = row.get("affected_metrics", [])
        if not isinstance(metrics, list) or not all(isinstance(item, str) for item in metrics):
            raise MethodologyCatalogError(f"{where}: affected_metrics must be a list of strings")
        result.append(copy.deepcopy(dict(row)))
    return tuple(result)


@lru_cache(maxsize=1)
def generic_advisories() -> tuple[dict[str, Any], ...]:
    return load_generic_advisories_from(CATALOGUE_ROOT / "advisories.json")


# --- run evidence -------------------------------------------------------------

def recorded_methodology(run: Mapping[str, Any], run_root: Path) -> dict[str, Any] | None:
    """The methodology a run recorded (status first, then resolved-run.json), or None."""

    for candidate in (
        run.get("methodology"),
        dict(_read_object(run_root / "model-output" / "resolved-run.json").get("extensions") or {}).get("methodology"),
    ):
        if isinstance(candidate, Mapping) and isinstance(candidate.get("profile_id"), str) and candidate.get("profile_id"):
            return dict(candidate)
    return None


def _run_descriptor(run: Mapping[str, Any], run_root: Path) -> dict[str, Any]:
    resolved = _read_object(run_root / "model-output" / "resolved-run.json")
    modules: set[str] = set()
    for value in dict(run.get("modules") or {}).values():
        if value:
            modules.add(normalize_module_id(value))
    for row in dict(resolved.get("modules") or {}).values():
        if isinstance(row, Mapping) and row.get("module_id"):
            modules.add(normalize_module_id(row["module_id"]))
    data_pack = resolved.get("data_pack_id") or dict(
        _read_object(run_root / "input-snapshot" / "project.json")
    ).get("data_pack_id")
    return {
        "modules": modules,
        "mode": str(run.get("mode") or ""),
        "data_pack": str(data_pack or ""),
        "engine": normalize_engine(run.get("execution_engine") or ""),
    }


def _applies(applies_when: Mapping[str, Sequence[str]], descriptor: Mapping[str, Any]) -> bool:
    for key, values in applies_when.items():
        wanted = set(values)
        if key == "modules_any" and not wanted.intersection(descriptor["modules"]):
            return False
        if key == "modes_any" and descriptor["mode"] not in wanted:
            return False
        if key == "data_packs_any" and descriptor["data_pack"] not in wanted:
            return False
        if key == "engines_any" and descriptor["engine"] not in wanted:
            return False
    return True


def _validation_report(run: Mapping[str, Any], run_root: Path) -> dict[str, Any]:
    return _read_object(run_root / "model-output" / str(
        run.get("scientific_validation_artifact") or "validation/scientific-validation.json"
    ))


def evaluate_advisories(run: Mapping[str, Any], run_root: Path) -> list[dict[str, Any]]:
    """Advisories that apply to one run, most severe first.  Read-only."""

    methodology = recorded_methodology(run, run_root)
    applied = set(methodology.get("applied_correction_ids") or []) if methodology else set()
    descriptor = _run_descriptor(run, run_root)
    rows: list[dict[str, Any]] = []
    for correction in load_catalogue().corrections.values():
        if correction.advisory is None or correction.id in applied:
            continue
        if not _applies(correction.applies_when, descriptor):
            continue
        advisory = dict(correction.advisory)
        rows.append({
            "schema_version": ADVISORY_SCHEMA,
            "id": correction.id,
            "source": "correction",
            "correction_id": correction.id,
            "findings": list(correction.findings),
            "track": correction.track,
            "severity": advisory["severity"],
            "title": advisory["title"],
            "summary": advisory["summary"],
            "affected_metrics": list(advisory.get("affected_metrics") or []),
        })
    report = _validation_report(run, run_root)
    predicates = {
        "pre_profile_run": methodology is None,
        "legacy_validation_report": report.get("schema_version") == LEGACY_VALIDATION_SCHEMA,
    }
    for advisory in generic_advisories():
        if predicates.get(str(advisory["applies_to"])):
            rows.append({
                "schema_version": ADVISORY_SCHEMA,
                "id": advisory["id"],
                "source": "generic",
                "correction_id": None,
                "findings": [],
                "track": None,
                "severity": advisory["severity"],
                "title": advisory["title"],
                "summary": advisory["summary"],
                "affected_metrics": list(advisory.get("affected_metrics") or []),
            })
    rank = {severity: index for index, severity in enumerate(SEVERITIES)}
    return sorted(rows, key=lambda row: (-rank[row["severity"]], row["id"]))


def advisory_summary(advisories: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rank = {severity: index for index, severity in enumerate(SEVERITIES)}
    highest = max((row["severity"] for row in advisories), key=lambda value: rank[value], default=None)
    return {
        "count": len(advisories),
        "max_severity": highest,
        "needs_review": highest in NEEDS_REVIEW_SEVERITIES,
    }


def raw_invariants_status(run: Mapping[str, Any], run_root: Path) -> str:
    """passed | failed | not_evaluated, from the P0-4 raw-invariant evidence."""

    report = _validation_report(run, run_root)
    for source in (run, report):
        record = source.get("raw_invariants")
        if isinstance(record, Mapping) and record.get("status") in {"passed", "failed", "not_evaluated"}:
            return str(record["status"])
    for source in (run, report):
        statuses = [source.get("run_invariant_status"), source.get("energy_balance_status")]
        if any(value in RAW_INVARIANT_FAIL for value in statuses):
            return "failed"
        if all(value in RAW_INVARIANT_PASS for value in statuses):
            return "passed"
    return "not_evaluated"


def result_publication(run: Mapping[str, Any], run_root: Path, methodology: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Whether annual results may appear on result pages (Q14)."""

    if methodology is None:
        methodology = recorded_methodology(run, run_root)
    rule = str(dict((methodology or {}).get("result_publication") or {}).get("rule") or "standard")
    if rule != "raw_invariants_must_pass":
        return {"status": "published", "rule": rule}
    verdict = raw_invariants_status(run, run_root)
    if verdict == "passed":
        return {"status": "published", "rule": rule, "raw_invariants_status": verdict}
    return {
        "status": "withheld",
        "rule": rule,
        "decision": "Q14",
        "raw_invariants_status": verdict,
        "reason_code": WITHHELD_FAILED if verdict == "failed" else WITHHELD_NOT_EVALUATED,
        "message": (
            "Doctoral reproduction runs publish annual results only when every raw invariant passes; "
            "the results remain available in Inspect and exports."
        ),
        "available_in": ["inspect", "export"],
    }


# Annual-result resources a withheld run does not serve (Q14).  Half-hour
# replay, Inspect, provenance and exports stay available.
WITHHELD_ANNUAL_RESOURCES = (
    "runs/<id> results[] (present_run)",
    "runs/<id>/summary annual[]",
    "runs/<id>/results/vre-curtailment?resolution=annual",
    "runs/<id>/market/vre-summary",
    "runs/<id>/planning/summary",
    "runs/<id>/domains/network/summary",
    "runs/<id>/domains/expansion/summary",
    "runs/<id>/network-redispatch/annual",
    "comparison annual deltas",
    "VALUE 101 comparison totals",
)


def run_result_publication(run_root: Path, run: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """result_publication of a run read from its directory (status.json + resolved-run.json)."""

    if run is None:
        run = _read_object(Path(run_root) / "status.json")
    return result_publication(run, Path(run_root))


def withheld_annual_result(run_root: Path, resource: str, run: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The response body for an annual-result resource of a withheld run, or None when published (Q14)."""

    publication = run_result_publication(run_root, run)
    if publication.get("status") != "withheld":
        return None
    return {
        "schema_version": "value.result-withheld/v1",
        "status": "withheld",
        "resource": resource,
        "reason_code": publication.get("reason_code"),
        "error_code": publication.get("reason_code"),
        "error": publication.get("message"),
        "decision": "Q14",
        "raw_invariants_status": publication.get("raw_invariants_status"),
        "available_in": list(publication.get("available_in") or ["inspect", "export"]),
        "result_publication": dict(publication),
    }


def present_scientific_status(run: MutableMapping[str, Any], run_root: Path) -> MutableMapping[str, Any]:
    """Set the presented scientific status, methodology, advisories and publication of ``run``.

    The scenario-status rules were moved unchanged from ``backend/server.py``
    ``present_run`` (X0 S10a).  Historical completed bundles are immutable.
    Some dynamic-policy runs were packaged before retained comparison was
    correctly classified as informational.  Present the scenario gate
    separately from the raw embedded report, based only on its preserved
    execution, contract and analytical evidence; never rewrite that report
    on disk.
    """

    validation = _validation_report(run, run_root)
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

    # X0 S10b: methodology, superseded positive claims, advisories, Q14.
    methodology = recorded_methodology(run, run_root)
    if methodology is None:
        run["methodology"] = {"status": "not_recorded", "profile_id": None}
        recorded = {field: run.get(field) for field in SUPERSEDED_FIELDS if run.get(field) == "passed"}
        if recorded:
            run["recorded_validation_statuses"] = recorded
            if "scientific_validation_status" in recorded:
                run["recorded_scientific_validation_status"] = recorded["scientific_validation_status"]
            for field in recorded:
                run[field] = "superseded_pre_fix"
    else:
        run["methodology"] = {**methodology, "status": "recorded"}
    advisories = evaluate_advisories(run, run_root)
    run["advisories"] = advisories
    run["advisory_summary"] = advisory_summary(advisories)
    run["result_publication"] = result_publication(run, run_root, methodology)
    return run


def withhold_annual_results(run: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Remove annual results from a presented run whose publication is withheld (Q14)."""

    publication = run.get("result_publication")
    if isinstance(publication, Mapping) and publication.get("status") == "withheld":
        results = run.get("results")
        run["withheld_result_year_count"] = len(results) if isinstance(results, list) else 0
        run["results"] = []
    return run
