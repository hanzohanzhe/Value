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
  ``data/methodology/advisories.json`` (whose ``fleet_assets`` rows, A24-2,
  disclose a limitation of every profile for Runs with a given asset class).
  Legacy module ids are normalised first.
* **Result publication** (Q14): a profile whose rule is
  ``raw_invariants_must_pass`` (the frozen doctoral reproduction) publishes
  annual results on result pages only when the run's raw invariants all
  passed; otherwise they are ``withheld`` (Inspect and exports stay
  available).  The raw-invariant evidence is the run's v2
  scientific-validation report (P0-4 S2: ``raw_invariants``, or
  ``run_invariant_status`` + ``energy_balance_status``), never a copied
  status field alone; a run without that report gets at most ``failed`` from
  the read-time oracle, otherwise ``not_evaluated``, and is withheld.
* **Validation evidence** (P0-4 S3): a run whose scientific-validation report
  is v2 shows the report's recomputed run-invariant, energy-balance and A2
  stress fields (the report is authoritative over copies in status.json).  A
  run without a v2 report (every run before P0-4 S2) has its positive
  validation claims superseded (``superseded_pre_fix``, recorded values kept)
  and its market ledger checked at read time by the read-only oracle
  (``mode=ro&immutable=1``, cached per file identity, nothing written), so a
  ledger that violates the energy-balance envelope is flagged wherever the
  run is shown.
"""

from __future__ import annotations

import copy
import json
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from backend.lifecycle.states import ACTIVE_STATES

from .legacy_module_ids import normalize_engine, normalize_module_id
from .methodology import CATALOGUE_ROOT, SEVERITIES, MethodologyCatalogError, load_catalogue

ADVISORY_SCHEMA = "value.result-advisory/v1"
ADVISORIES_FILE_SCHEMA = "value.methodology-advisories/v1"
GENERIC_PREDICATES = ("pre_profile_run", "legacy_validation_report", "fleet_assets")
# A24-2: ``fleet_assets`` advisories are disclosures of a model limitation that
# holds in every profile; they carry ``applies_when`` with ``assets_any`` only
# and use the same fleet evidence as the asset-filtered correction advisories.
GENERIC_APPLIES_WHEN_KEYS = ("assets_any",)
LEGACY_VALIDATION_SCHEMA = "value.scientific-validation/v1"
VALIDATION_SCHEMA = "value.scientific-validation/v2"
# Evidence fields a v2 report carries (and model_runner copies onto status).
VALIDATION_EVIDENCE_FIELDS = (
    "run_invariant_status", "run_invariants", "energy_balance_status",
    "energy_balance", "stress", "raw_invariants", "validation_warnings",
    "storage_invariant_status", "storage_invariants", "validation_gate", "declared_deviations",
)
ACTIVE_STATUSES = frozenset(ACTIVE_STATES)
# Ledgers above this size are not re-read on every listing; the CLI
# (python -B -m gridform_core.energy_balance_oracle <run>) checks them.
READ_TIME_ORACLE_MAX_BYTES = 256 * 1024 * 1024
READ_TIME_ORACLE_CACHE_SIZE = 256
R_READ_TIME_SKIPPED = "GF_ENERGY_BALANCE_READ_TIME_SKIPPED_SIZE"
STATUS_VOCABULARY = (
    "passed", "failed", "not_evaluated", "superseded_pre_fix",
    "reproduction_with_declared_deviations", "reproduction_conformant",
)
# Positive validation claims a pre-profile run may carry; each is superseded.
SUPERSEDED_FIELDS = (
    "scientific_scenario_status", "scientific_validation_status", "contract_validation_status",
)
RAW_INVARIANT_PASS = {"passed", "reproduction_conformant", "not_applicable"}
RAW_INVARIANT_FAIL = {"failed", "reproduction_with_declared_deviations"}
# Gate components of the Q14 raw-invariant verdict, in report order.
RAW_INVARIANT_COMPONENTS = ("run_invariant_status", "energy_balance_status", "storage_invariant_status")
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
        applies_when = row.get("applies_when")
        if row["applies_to"] == "fleet_assets":
            if (not isinstance(applies_when, Mapping) or not applies_when
                    or set(applies_when) - set(GENERIC_APPLIES_WHEN_KEYS)
                    or not all(isinstance(values, list) and values
                               and all(isinstance(item, str) and item for item in values)
                               for values in applies_when.values())):
                raise MethodologyCatalogError(
                    f"{where}: fleet_assets needs applies_when with a non-empty assets_any list")
        elif applies_when is not None:
            raise MethodologyCatalogError(f"{where}: applies_when is only allowed with applies_to fleet_assets")
        if row.get("severity") not in SEVERITIES:
            raise MethodologyCatalogError(f"{where}: severity must be one of {SEVERITIES}")
        for key in ("title", "summary"):
            if not isinstance(row.get(key), str) or not row.get(key):
                raise MethodologyCatalogError(f"{where}: {key} is required")
        metrics = row.get("affected_metrics", [])
        if not isinstance(metrics, list) or not all(isinstance(item, str) for item in metrics):
            raise MethodologyCatalogError(f"{where}: affected_metrics must be a list of strings")
        findings = row.get("findings", [])
        if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
            raise MethodologyCatalogError(f"{where}: findings must be a list of strings")
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


_ASSET_CACHE: "OrderedDict[tuple, frozenset[str] | None]" = OrderedDict()
_ASSET_CACHE_LOCK = threading.Lock()


def run_asset_classes(run_root: Path) -> frozenset[str] | None:
    """Asset classes of a Run's frozen fleet, or None when it cannot be read.

    R3-N7 (DECISIONS A23): the evidence for ``applies_when.assets_any``.  The
    fleet is the ``fleet.generators`` role of the Run's input snapshot
    (generators, batteries, interconnectors), grouped with
    ``market_replay.canonical_technology``; cached per file identity.
    """

    from .market_replay import canonical_technology

    pack = Path(run_root) / "input-snapshot" / "pack"
    binding = dict(_read_object(pack / "manifest.json").get("bindings") or {}).get("fleet.generators")
    if not isinstance(binding, Mapping) or not binding.get("uri"):
        return None
    path = pack / str(binding["uri"])
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ino)
    with _ASSET_CACHE_LOCK:
        if key in _ASSET_CACHE:
            _ASSET_CACHE.move_to_end(key)
            return _ASSET_CACHE[key]
    fleet = _read_object(path)
    classes: frozenset[str] | None
    if not isinstance(fleet.get("generators"), Mapping):
        classes = None
    else:
        found = {canonical_technology(str(name)) for name in fleet["generators"]}
        if fleet.get("batteries"):
            found.add("battery_storage")
        if fleet.get("connections"):
            found.add("boundary_import")
        classes = frozenset(found)
    with _ASSET_CACHE_LOCK:
        _ASSET_CACHE[key] = classes
        while len(_ASSET_CACHE) > READ_TIME_ORACLE_CACHE_SIZE:
            _ASSET_CACHE.popitem(last=False)
    return classes


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
        "assets": run_asset_classes(run_root),
        # R4-1 (A26): the recorded methodology profile (None before X0 S9).
        "profile": (recorded_methodology(run, run_root) or {}).get("profile_id"),
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
        # Unknown fleet evidence keeps the advisory (fail towards disclosure).
        if key == "assets_any" and descriptor.get("assets") is not None and not wanted.intersection(descriptor["assets"]):
            return False
        # R4-1 (A26): a Run without a recorded profile (pre-profile) keeps the advisory.
        if key == "profiles_any" and descriptor.get("profile") and descriptor["profile"] not in wanted:
            return False
    return True


def _validation_report(run: Mapping[str, Any], run_root: Path) -> dict[str, Any]:
    return _read_object(run_root / "model-output" / str(
        run.get("scientific_validation_artifact") or "validation/scientific-validation.json"
    ))


def methodology_unresolved(run: Mapping[str, Any]) -> bool:
    """A run created after X0 S9 whose profile could not be resolved (e.g. an unknown id).

    It is not a pre-fix run: it gets no pre-profile advisory and its claims
    are not rewritten to superseded_pre_fix.
    """

    record = run.get("methodology")
    return isinstance(record, Mapping) and record.get("status") == "unresolved"


def legacy_validation_report(report: Mapping[str, Any]) -> bool:
    """A recorded validation report that is not the recomputed v2 report."""

    return bool(report) and report.get("schema_version") != VALIDATION_SCHEMA


_ORACLE_CACHE: "OrderedDict[tuple, dict[str, Any]]" = OrderedDict()
# The API is a ThreadingHTTPServer: the cache is shared between threads.
_ORACLE_CACHE_LOCK = threading.Lock()


def read_time_energy_balance(run_root: Path) -> dict[str, Any] | None:
    """Oracle report of a run's ledger, evaluated read-only and cached; None without a ledger."""

    from .energy_balance_oracle import REPORT_SCHEMA_VERSION, evaluate_run_ledger

    database = Path(run_root) / "model-output" / "market" / "market.sqlite"
    try:
        stat = database.stat()
    except OSError:
        return None
    if stat.st_size > READ_TIME_ORACLE_MAX_BYTES:
        return {
            "schema_version": REPORT_SCHEMA_VERSION, "status": "not_evaluated",
            "reasons": [R_READ_TIME_SKIPPED], "checks": [], "metrics": {}, "stress": None,
            "ledger_bytes": stat.st_size,
        }
    key = (str(database.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ino)
    with _ORACLE_CACHE_LOCK:
        cached = _ORACLE_CACHE.get(key)
        if cached is not None:
            _ORACLE_CACHE.move_to_end(key)
            return copy.deepcopy(cached)
    # Evaluated outside the lock (it reads the ledger); a concurrent first
    # read of the same file evaluates it twice, which is harmless.
    evaluated = evaluate_run_ledger(Path(run_root) / "model-output")
    with _ORACLE_CACHE_LOCK:
        _ORACLE_CACHE[key] = evaluated
        _ORACLE_CACHE.move_to_end(key)
        while len(_ORACLE_CACHE) > READ_TIME_ORACLE_CACHE_SIZE:
            _ORACLE_CACHE.popitem(last=False)
    return copy.deepcopy(evaluated)


def validation_evidence(run: Mapping[str, Any], run_root: Path, report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The run-invariant, energy-balance and stress evidence of a run (P0-4 S3).

    The only sources are the run's v2 scientific-validation report (recomputed
    when the run finished) or, for a run without one, the read-only oracle on
    its ledger now.  Copies of these fields in status.json are never trusted
    on their own: a legacy run cannot claim passed raw invariants.
    """

    from .scientific_validation import energy_balance_summary

    if report is None:
        report = _validation_report(run, run_root)
    if report.get("schema_version") == VALIDATION_SCHEMA:
        evidence = {field: copy.deepcopy(report[field]) for field in VALIDATION_EVIDENCE_FIELDS if field in report}
        evidence["validation_evidence"] = {
            "source": "scientific_validation_v2",
            "artifact": str(run.get("scientific_validation_artifact") or "validation/scientific-validation.json"),
        }
        return evidence
    if str(run.get("status") or "") in ACTIVE_STATUSES:
        return {
            "run_invariant_status": "not_evaluated",
            "energy_balance_status": "not_evaluated",
            "validation_evidence": {"source": "not_yet_available"},
        }
    oracle = read_time_energy_balance(run_root)
    balance, stress = energy_balance_summary(oracle)
    balance["source"] = "read_time_oracle"
    balance["artifact"] = None
    if stress is not None:
        stress["artifact"] = None
    warnings = [{
        "code": "GF_VALIDATION_LEGACY_REPORT", "severity": "warning",
        "message": "This run has no recomputed (v2) validation report; its ledger was checked when it was read.",
        "source": "read_time",
    }]
    if balance["status"] == "failed":
        warnings.append({
            "code": "GF_ENERGY_BALANCE_FAILED", "severity": "error",
            "message": "The independent ledger check found periods where supply and use do not reconcile.",
            "source": "read_time_oracle",
        })
    if stress and isinstance(stress.get("stress_periods"), int) and stress["stress_periods"] > 0:
        warnings.append({
            "code": "GF_STRESS_EVENTS_RECORDED", "severity": "warning",
            "message": f"Accepted supply fell short of demand in {stress['stress_periods']} periods.",
            "source": "read_time_oracle",
        })
    evidence: dict[str, Any] = {
        "run_invariant_status": "not_evaluated",
        "energy_balance_status": balance["status"],
        "energy_balance": balance,
        "validation_warnings": warnings,
        "raw_invariants": {
            "status": "failed" if balance["status"] == "failed" else "not_evaluated",
            "run_invariant_status": "not_evaluated",
            "energy_balance_status": balance["status"],
            "decision": "Q14",
            "source": "read_time_oracle",
        },
        "validation_evidence": {"source": "read_time_oracle" if oracle is not None else "not_recorded"},
    }
    if stress is not None:
        evidence["stress"] = stress
    return evidence


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
        "pre_profile_run": methodology is None and not methodology_unresolved(run),
        "legacy_validation_report": legacy_validation_report(report),
    }
    for advisory in generic_advisories():
        if advisory["applies_to"] == "fleet_assets":
            if not _applies(advisory["applies_when"], descriptor):
                continue
        elif not predicates.get(str(advisory["applies_to"])):
            continue
        rows.append({
            "schema_version": ADVISORY_SCHEMA,
            "id": advisory["id"],
            "source": "generic",
            "correction_id": None,
            "findings": list(advisory.get("findings") or []),
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


def raw_invariants_status(run: Mapping[str, Any], run_root: Path, evidence: Mapping[str, Any] | None = None) -> str:
    """passed | failed | not_evaluated, from the P0-4 raw-invariant evidence.

    The verdict is derived from the gate statuses of the run's v2 report
    (run invariants, energy balance and - from P0-4 S7 - storage
    invariants), or of the read-time oracle for a run without one
    (:func:`validation_evidence`).  The stored ``raw_invariants.status`` is
    not trusted on its own: when it disagrees with the derived verdict the
    evidence is self-inconsistent and the verdict is ``failed``.
    """

    if evidence is None:
        evidence = validation_evidence(run, run_root)
    statuses = [evidence.get(field) for field in RAW_INVARIANT_COMPONENTS[:2]]
    if "storage_invariant_status" in evidence:
        statuses.append(evidence.get("storage_invariant_status"))
    if any(value in RAW_INVARIANT_FAIL for value in statuses):
        derived = "failed"
    elif all(value in RAW_INVARIANT_PASS for value in statuses):
        derived = "passed"
    else:
        derived = "not_evaluated"
    record = evidence.get("raw_invariants")
    if isinstance(record, Mapping) and record.get("status") is not None and record.get("status") != derived:
        return "failed"
    return derived


# Spec 11.3 (R-D1): the names the status bar and the withheld notice give the
# raw-invariant checks (gridform_core.energy_balance_oracle check ids).
RAW_INVARIANT_CHECK_NAMES = {
    "storage.rated_power": "Storage rated power",
    "storage.single_direction": "Storage single direction",
    "storage.soc_bounds": "Storage state-of-charge bounds",
    "storage.soc_identity": "Storage state-of-charge identity",
    "storage.audit_coverage": "Storage audit coverage",
    "period.balance_account": "Energy balance account",
    "period.finite": "Finite ledger values",
    "ledger.self_report": "Ledger self-report",
    "period.surplus_conservation": "Surplus conservation",
    "run.adjustment_share": "Compatibility adjustment share",
    "period.envelope": "Energy balance envelope",
    "period.boundary_residual": "Boundary residual",
}
RAW_INVARIANT_GATE_NAMES = {
    "run_invariants": "Run invariants", "energy_balance": "Energy balance", "storage_invariants": "Storage limits",
}


def _first_sentence(text: str) -> str:
    text = " ".join(str(text or "").split())
    for index, char in enumerate(text):
        if char == "." and (index + 1 == len(text) or text[index + 1] == " "):
            return text[: index + 1]
    return text


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def raw_invariant_failures(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The raw-invariant checks that failed, with their size and any declared deviation (spec 11.3, R-D1).

    Read-only presentation of the evidence already on the run: the gate
    statuses decide which gates failed; the failing check ids, their row or
    period counts and the matched declared deviations come from the same
    report.  A gate without check detail is listed under its own name.
    """

    from .declared_deviations import catalogue, withdrawn

    # R4-1 (A26): a Run made before a deviation was corrected keeps its
    # matched id; the withdrawn entry still names what it was.
    summaries = {str(row["id"]): _first_sentence(str(row.get("description") or ""))
                 for row in (*withdrawn(), *catalogue())}
    declared = evidence.get("declared_deviations")
    matched: dict[str, Mapping[str, Any]] = {}
    if isinstance(declared, Mapping):
        for row in declared.get("matched") or []:
            if isinstance(row, Mapping) and row.get("check"):
                matched[str(row["check"])] = row
    failures: list[dict[str, Any]] = []

    def add(gate: str, check: str, count: int | None, unit: str | None) -> None:
        row = matched.get(check) or {}
        ids = [str(item) for item in row.get("deviation_ids") or []]
        failures.append({
            "gate": gate, "check": check,
            "name": RAW_INVARIANT_CHECK_NAMES.get(check) or RAW_INVARIANT_GATE_NAMES.get(check) or check,
            "count": count, "unit": unit if count is not None else None,
            "deviation_ids": ids,
            "deviations": [{"id": item, "summary": summaries.get(item)} for item in ids],
        })

    def section(name: str) -> Mapping[str, Any]:
        value = evidence.get(name)
        return value if isinstance(value, Mapping) else {}

    if evidence.get("run_invariant_status") in RAW_INVARIANT_FAIL:
        for check in section("run_invariants").get("failed_checks") or ["run_invariants"]:
            add("run_invariants", str(check), None, None)
    if evidence.get("energy_balance_status") in RAW_INVARIANT_FAIL:
        balance = section("energy_balance")
        for check in balance.get("gate_failed_checks") or ["energy_balance"]:
            count = _count((matched.get(str(check)) or {}).get("periods"))
            if count is None and check == "period.balance_account":
                count = _count(dict(balance.get("balance_account") or {}).get("open_periods"))
            add("energy_balance", str(check), count, "periods")
    if evidence.get("storage_invariant_status") in RAW_INVARIANT_FAIL:
        storage = section("storage_invariants")
        counts = {str(row.get("id")): row.get("count") for row in storage.get("checks") or [] if isinstance(row, Mapping)}
        for check in storage.get("failed_checks") or ["storage_invariants"]:
            count = _count((matched.get(str(check)) or {}).get("rows"))
            if count is None:
                count = _count(counts.get(str(check)))
            add("storage_invariants", str(check), count, "rows")
    return failures


def result_publication(run: Mapping[str, Any], run_root: Path, methodology: Mapping[str, Any] | None = None,
                       evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Whether annual results may appear on result pages (Q14)."""

    if methodology is None:
        methodology = recorded_methodology(run, run_root)
    rule = str(dict((methodology or {}).get("result_publication") or {}).get("rule") or "standard")
    if rule != "raw_invariants_must_pass":
        return {"status": "published", "rule": rule}
    verdict = raw_invariants_status(run, run_root, evidence)
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
    "runs/<id>/summary annual[], planning, vre_curtailment_attribution, terminal",
    "runs/<id>/results/vre-curtailment?resolution=annual",
    "runs/<id>/market/vre-summary",
    "runs/<id>/planning/summary",
    "runs/<id>/domains/network/summary",
    "runs/<id>/domains/expansion/summary",
    "runs/<id>/network-redispatch/annual",
    "comparison annual deltas",
    "VALUE 101 comparison totals",
)

# Row-level ledgers that stay available for a withheld run on purpose: they
# are the Inspect view of individual projects, events and periods, not
# annual results (Q14 keeps Inspect and export available).  A page that
# aggregates them into annual totals must use a gated resource above.
INSPECT_LEVEL_UNGATED_RESOURCES = (
    "runs/<id>/planning/projects",
    "runs/<id>/planning/events",
    "runs/<id>/domains/expansion/events",
    "runs/<id>/domains/network/periods",
    "runs/<id>/domains/network/branches",
    "runs/<id>/market/periods",
    "runs/<id>/market/dispatch",
    "runs/<id>/market/vre-timeline",
    "runs/<id>/market/stress-events",
    "runs/<id>/results/vre-curtailment?resolution=half_hour",
    "runs/<id>/market/orders|storage|physical",
    "runs/<id>/provenance",
    "runs/<id>/artifacts",
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
    legacy_report = legacy_validation_report(validation)
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
    scenario_status = validation.get("scientific_validation_status")
    if legacy_report:
        # The scenario reading of a v1 report, kept only as the recorded value
        # of a claim that is superseded below; a v2 report already classifies
        # the retained comparison itself, so nothing is forced to "passed".
        evidence_passed = all(
            validation.get(field) == "passed"
            for field in (
                "execution_status",
                "contract_validation_status",
                "analytical_mechanism_status",
            )
        )
        if alternative_policy and evidence_passed and run.get("mode") in {"full", "two_year"}:
            scenario_status = "passed"
    run["scientific_scenario_status"] = scenario_status or "not_evaluated"
    run["retained_comparison_role"] = role
    run["retained_numerical_comparison_status"] = retained_status or "not_evaluated"

    # X0 S10b: methodology, superseded positive claims, advisories, Q14.
    methodology = recorded_methodology(run, run_root)
    supersede = False
    if methodology is None and methodology_unresolved(run):
        unresolved = dict(run["methodology"])
        run["methodology"] = {"status": "unresolved", "profile_id": None, "error": unresolved.get("error")}
    elif methodology is None:
        run["methodology"] = {"status": "not_recorded", "profile_id": None}
        supersede = True
    else:
        run["methodology"] = {**methodology, "status": "recorded"}
    # P0-4 S3: a passed claim resting on a legacy (v1) report was never
    # recomputed (P7-01), whatever methodology the run recorded.
    supersede = supersede or legacy_report
    if supersede:
        recorded = {field: run.get(field) for field in SUPERSEDED_FIELDS if run.get(field) == "passed"}
        if recorded:
            run["recorded_validation_statuses"] = recorded
            if "scientific_validation_status" in recorded:
                run["recorded_scientific_validation_status"] = recorded["scientific_validation_status"]
            for field in recorded:
                run[field] = "superseded_pre_fix"
    # P0-4 S3: recomputed evidence replaces any copied claim on the record.
    evidence = validation_evidence(run, run_root, validation)
    for field in VALIDATION_EVIDENCE_FIELDS:
        run.pop(field, None)
    run.update(evidence)
    advisories = evaluate_advisories(run, run_root)
    run["advisories"] = advisories
    run["advisory_summary"] = advisory_summary(advisories)
    run["result_publication"] = result_publication(run, run_root, methodology, evidence)
    run["raw_invariant_failures"] = raw_invariant_failures(evidence)
    return run


def compact_validation_fields(row: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Bound a listed run's validation evidence to its badges (/api/runs/<id> has the rest)."""

    # The listing carries the energy-balance badge and the stress count only.
    for field in ("energy_balance", "run_invariants", "run_invariant_status", "raw_invariants",
                  "validation_evidence", "validation_warnings", "storage_invariants", "validation_gate",
                  "declared_deviations"):
        row.pop(field, None)
    stress = row.get("stress")
    if isinstance(stress, Mapping):
        row["stress"] = {key: stress.get(key) for key in ("stress_periods", "shortfall_mwh", "shortfall_basis")}
    # Spec 11.3: the status bar's Raw invariants field reads the listing row too.
    failures = row.get("raw_invariant_failures")
    if isinstance(failures, list):
        row["raw_invariant_failures"] = failures[:10]
    return row


def withhold_annual_results(run: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Remove annual results from a presented run whose publication is withheld (Q14)."""

    publication = run.get("result_publication")
    if isinstance(publication, Mapping) and publication.get("status") == "withheld":
        results = run.get("results")
        run["withheld_result_year_count"] = len(results) if isinstance(results, list) else 0
        run["results"] = []
    return run
