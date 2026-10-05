"""Scientific acceptance reporting independent of process completion.

Report v2 (P0-4 S2): every status is recomputed from checks executed on the
run - the stage-parity v3 contract checks, the run invariants
(:mod:`gridform_core.run_invariants`) and the read-only energy-balance oracle
(:mod:`gridform_core.energy_balance_oracle`).  A report that executed no check
is ``not_evaluated``; it is never ``passed`` (finding P7-01).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .builtin.scheme_c_1000twh.runtime_compat.storage_cost import DynamicAnnualStorageCost
from .dispatch_benchmark import solve_fixture


SCHEMA_VERSION = "value.scientific-validation/v2"
LEGACY_SCHEMA_VERSION = "value.scientific-validation/v1"
ENERGY_BALANCE_ARTIFACT = "validation/energy-balance-oracle.json"
ENERGY_BALANCE_ENFORCEMENT = "report_only_until_p0_4_s7"
R_CONTRACT_NOT_EXECUTED = "GF_VALIDATION_CONTRACT_NOT_EXECUTED"
R_CONTRACT_MALFORMED = "GF_VALIDATION_CONTRACT_CHECK_MALFORMED"
R_CONTRACT_SELF_INCONSISTENT = "GF_VALIDATION_CONTRACT_SELF_INCONSISTENT"
R_INVARIANTS_NOT_EXECUTED = "GF_RUN_INVARIANTS_NOT_EXECUTED"
R_ENERGY_BALANCE_NOT_EXECUTED = "GF_ENERGY_BALANCE_NOT_EXECUTED"
PASSED = "passed"
FAILED = "failed"
NOT_EVALUATED = "not_evaluated"
EXPECTED_DIFFERENCE = "expected_difference"
RETAINED_COMPARISON_REQUIRED = "required_reproduction_gate"
RETAINED_COMPARISON_INFORMATIONAL = "informational_scenario_difference"


@dataclass(frozen=True)
class MechanismCheck:
    id: str
    actual: float
    expected: float
    unit: str
    absolute_tolerance: float = 1e-9

    @property
    def passed(self) -> bool:
        numbers = (self.actual, self.expected, self.absolute_tolerance)
        if (not self.id or not isinstance(self.unit, str) or not self.unit.strip()
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in numbers)
                or self.absolute_tolerance < 0):
            return False
        return math.isclose(
            self.actual,
            self.expected,
            abs_tol=self.absolute_tolerance,
            rel_tol=1e-10,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "actual": self.actual,
            "expected": self.expected,
            "unit": self.unit,
            "absolute_difference": abs(self.actual - self.expected),
            "absolute_tolerance": self.absolute_tolerance,
            "status": PASSED if self.passed else FAILED,
        }


def analytical_mechanism_checks(
    *,
    storage_factory: Callable[..., object] = DynamicAnnualStorageCost,
) -> list[MechanismCheck]:
    """Return dependency-free analytical checks with explicit physical units."""

    dispatch = solve_fixture({
        "demand_mwh": 130.0,
        "offers": [
            {"asset_id": "vre", "capacity_mwh": 60.0, "marginal_cost_gbp_per_mwh": 0.0},
            {"asset_id": "storage", "capacity_mwh": 40.0, "marginal_cost_gbp_per_mwh": 25.0},
            {"asset_id": "thermal", "capacity_mwh": 100.0, "marginal_cost_gbp_per_mwh": 70.0},
        ],
    })
    checks = [
        MechanismCheck("dispatch.energy_balance", float(dispatch["energy_balance_residual_mwh"]), 0.0, "MWh"),
        MechanismCheck("dispatch.vre_merit_order", float(dispatch["dispatch_mwh"]["vre"]), 60.0, "MWh"),
        MechanismCheck("dispatch.storage_merit_order", float(dispatch["dispatch_mwh"]["storage"]), 40.0, "MWh"),
        MechanismCheck("dispatch.thermal_residual", float(dispatch["dispatch_mwh"]["thermal"]), 30.0, "MWh"),
        MechanismCheck("dispatch.marginal_price", float(dispatch["clearing_price_gbp_per_mwh"]), 70.0, "GBP/MWh"),
    ]

    battery = storage_factory(battery_type="0.5c", period_hours=0.5)
    battery.prepare_year(
        2025,
        capital_cost_gbp=1_000_000.0,
        power_capacity_mw=1.0,
        energy_capacity_mwh=2.0,
        discharge_efficiency=1.0,
    )
    battery_recovery = (
        battery.cycle_depreciation_gbp_per_mwh * battery.pricing_basis_sold_mwh
        + battery.holding_recovery_gbp_per_mwh_period
        * battery.pricing_basis_sold_mwh
        * battery.pricing_basis_average_dwell_periods
    )
    checks.extend([
        MechanismCheck(
            "storage.first_year_full_utilisation_recovery",
            float(battery_recovery),
            float(battery.annual_levelized_project_cost_gbp),
            "GBP/year",
            1e-6,
        ),
        MechanismCheck(
            "storage.fixed_duration",
            float(battery.spec.duration_hours),
            2.0,
            "hours",
        ),
    ])
    battery.record_sale(80.0, 2.0)
    battery.record_sale(20.0, 6.0)
    battery.prepare_year(
        2026,
        capital_cost_gbp=1_000_000.0,
        power_capacity_mw=1.0,
        energy_capacity_mwh=2.0,
        discharge_efficiency=1.0,
    )
    checks.extend([
        MechanismCheck("storage.previous_year_sales", float(battery.pricing_basis_sold_mwh), 100.0, "MWh"),
        MechanismCheck("storage.sales_weighted_dwell", float(battery.pricing_basis_average_dwell_periods), 2.8, "periods"),
    ])

    pumped = storage_factory(battery_type="pumped_hydro", period_hours=0.5)
    pumped.prepare_year(
        2025,
        capital_cost_gbp=500_000_000.0,
        power_capacity_mw=2_000.0,
        energy_capacity_mwh=8_000.0,
        discharge_efficiency=0.87,
    )
    hydrogen = storage_factory(battery_type="hydrogen", period_hours=0.5)
    hydrogen.prepare_year(
        2025,
        capital_cost_gbp=1_000_000.0,
        power_capacity_mw=1.0,
        energy_capacity_mwh=250.0,
        discharge_efficiency=0.57,
    )
    checks.extend([
        MechanismCheck("storage.battery_cycle_depreciation_present", float(battery.cycle_depreciation_gbp_per_mwh > 0), 1.0, "boolean"),
        MechanismCheck("storage.pumped_hydro_cycle_depreciation_absent", float(pumped.cycle_depreciation_gbp_per_mwh), 0.0, "GBP/MWh"),
        MechanismCheck("storage.hydrogen_cycle_depreciation_absent", float(hydrogen.cycle_depreciation_gbp_per_mwh), 0.0, "GBP/MWh"),
    ])
    return checks


def contract_evidence(parity_report: Mapping[str, object]) -> dict[str, object]:
    """Recompute the contract verdict from the parity checks it lists (P7-01).

    A bare ``contract_parity_passed`` flag is not evidence: with no executed
    check the contract is not evaluated.  Every listed check is recomputed
    from its recorded values; a row whose recorded ``pass`` disagrees with
    the recomputation, or a top-level flag that disagrees with the rows, makes
    the report self-inconsistent and the contract failed.
    """

    from .parity import recompute_check

    checks = parity_report.get("checks") if isinstance(parity_report, Mapping) else None
    if not isinstance(checks, list) or not checks:
        return {
            "status": NOT_EVALUATED, "checks_passed": 0, "checks_total": 0,
            "reason_code": R_CONTRACT_NOT_EXECUTED, "parity_schema_version": (
                parity_report.get("schema_version") if isinstance(parity_report, Mapping) else None
            ),
        }
    recomputed = [recompute_check(row) for row in checks]
    malformed = sum(value is None for value in recomputed)
    passed = sum(value is True for value in recomputed)
    inconsistent = [
        index for index, (row, value) in enumerate(zip(checks, recomputed))
        if value is not None and isinstance(row, Mapping) and "pass" in row and row.get("pass") is not value
    ]
    all_passed = malformed == 0 and passed == len(checks)
    declared = parity_report.get("contract_parity_passed")
    reason = None
    if malformed:
        reason = R_CONTRACT_MALFORMED
    elif inconsistent or declared is not all_passed:
        reason = R_CONTRACT_SELF_INCONSISTENT
    status = PASSED if all_passed and reason is None else FAILED
    first = next((row for row, value in zip(checks, recomputed) if value is not True), None)
    return {
        "status": status,
        "checks_passed": passed,
        "checks_total": len(checks),
        "reason_code": reason,
        "first_divergence": first,
        "parity_schema_version": parity_report.get("schema_version"),
    }


def run_invariant_evidence(report: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(report, Mapping) or not isinstance(report.get("checks"), list):
        return {"status": NOT_EVALUATED, "severity": "report", "reason_code": R_INVARIANTS_NOT_EXECUTED,
                "checks_passed": 0, "checks_total": 0}
    from .run_invariants import summarise

    summary = summarise(report["checks"])  # recomputed, not the stored top-level status
    return {
        "status": summary["status"],
        "severity": report.get("severity", "report"),
        "enforcement": report.get("enforcement"),
        "checks_passed": summary["checks_passed"],
        "checks_total": summary["checks_total"],
        "integrity_checks_passed": summary["integrity_checks_passed"],
        "integrity_checks_total": summary["integrity_checks_total"],
        "failed_checks": summary["failed_checks"],
        "not_evaluated_checks": summary["not_evaluated_checks"],
        "artifact": "validation/run-invariants.json",
    }


def energy_balance_summary(report: Mapping[str, object] | None) -> tuple[dict[str, object], dict[str, object] | None]:
    """(energy_balance, stress) summaries of an oracle report (decision A2)."""

    if not isinstance(report, Mapping):
        return ({"status": NOT_EVALUATED, "severity": "report", "enforcement": ENERGY_BALANCE_ENFORCEMENT,
                 "reasons": [R_ENERGY_BALANCE_NOT_EXECUTED], "artifact": None}, None)
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    status = report.get("status")
    if status not in {PASSED, FAILED, NOT_EVALUATED}:
        status = NOT_EVALUATED
    if any(isinstance(row, Mapping) and row.get("status") == FAILED for row in checks):
        status = FAILED
    elif status == PASSED and not checks:
        status = NOT_EVALUATED
    metrics = dict(report.get("metrics") or {})
    reported = dict(metrics.get("reported") or {})
    full_node = dict(metrics.get("full_node") or {})
    envelope = dict(metrics.get("envelope") or {})
    boundary_residual = dict(metrics.get("boundary_residual") or {})
    boundary = dict(report.get("boundary") or {})
    energy_balance = {
        "status": status,
        "severity": "report",
        "enforcement": ENERGY_BALANCE_ENFORCEMENT,
        "boundary_id": boundary.get("boundary_id"),
        "boundary_source": boundary.get("source"),
        "reasons": list(report.get("reasons") or []),
        "periods": metrics.get("periods"),
        "sum_demand_mwh": metrics.get("sum_demand_mwh"),
        "maximum_absolute_full_node_residual_mwh": full_node.get("max_abs_mwh"),
        "maximum_absolute_boundary_residual_mwh": boundary_residual.get("max_abs_mwh"),
        "maximum_absolute_raw_residual_mwh": reported.get("max_abs_raw_residual_mwh"),
        "compatibility_adjustment_periods": reported.get("adjusted_periods"),
        "sum_abs_compatibility_adjustment_mwh": reported.get("sum_abs_adjustment_mwh"),
        "adjusted_energy_share": reported.get("adjusted_energy_share"),
        "adjusted_energy_share_cap": reported.get("adjusted_energy_share_cap"),
        "envelope_lower_violations": envelope.get("lower_violations"),
        "envelope_upper_violations": envelope.get("upper_violations"),
        "maximum_envelope_violation_mwh": max(
            [value for value in (envelope.get("max_lower_violation_mwh"), envelope.get("max_upper_violation_mwh"))
             if isinstance(value, (int, float))] or [0.0]
        ) if envelope else None,
        "worst_periods": list(envelope.get("worst_periods") or [])[:5],
        "artifact": ENERGY_BALANCE_ARTIFACT,
    }
    stress_report = report.get("stress")
    stress = None
    if isinstance(stress_report, Mapping):
        exact = stress_report.get("basis") == "exact"
        years = [row for row in list(stress_report.get("by_year") or []) if isinstance(row, Mapping)]

        def year_sum(key: str) -> float:
            return float(f"{math.fsum(float(row.get(key) or 0.0) for row in years):.12g}")

        stress = {
            "decision": "A2",
            "shortfall_basis": "exact" if exact else "lower_bound",
            "stress_periods": stress_report.get("stress_periods"),
            "possible_stress_periods": stress_report.get("possible_stress_periods"),
            "event_count": stress_report.get("event_count"),
            # Certain shortfall: exact with recorded surplus routing, otherwise
            # the demand that accepted supply did not meet (a lower bound).
            # Summed over stress periods only (tolerance-level noise is not shortfall).
            "shortfall_mwh": year_sum("shortfall_lower_mwh"),
            "shortfall_upper_mwh": year_sum("shortfall_upper_mwh"),
            "recorded_unserved_mwh": stress_report.get("recorded_unserved_mwh"),
            "by_year": [
                {key: row.get(key) for key in (
                    "year", "stress_periods", "possible_stress_periods", "event_count",
                    "shortfall_lower_mwh", "shortfall_upper_mwh", "recorded_unserved_mwh",
                    "hidden_shortfall_lower_mwh",
                )}
                for row in years[:200]
            ],
            "artifact": ENERGY_BALANCE_ARTIFACT,
        }
    return energy_balance, stress


def _validation_warnings(contract: Mapping[str, object], invariants: Mapping[str, object],
                         energy_balance: Mapping[str, object], stress: Mapping[str, object] | None) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []

    def add(code: str, severity: str, message: str, source: str) -> None:
        warnings.append({"code": code, "severity": severity, "message": message, "source": source})

    if contract["status"] == FAILED:
        add("GF_VALIDATION_CONTRACT_FAILED", "error",
            "A recomputed contract parity check failed.", "parity/stage-parity.json")
    elif contract["status"] == NOT_EVALUATED:
        add("GF_VALIDATION_CONTRACT_NOT_EVALUATED", "warning",
            "No contract parity check was executed for this run.", "parity/stage-parity.json")
    if invariants["status"] == FAILED:
        add("GF_RUN_INVARIANTS_FAILED", "error",
            "Run invariants failed: " + ", ".join(invariants.get("failed_checks") or []) +
            " (reported; not yet a gate).", "validation/run-invariants.json")
    elif invariants["status"] == NOT_EVALUATED:
        add("GF_RUN_INVARIANTS_NOT_EVALUATED", "info",
            "Run invariants could not all be evaluated.", "validation/run-invariants.json")
    if energy_balance["status"] == FAILED:
        add("GF_ENERGY_BALANCE_FAILED", "error",
            "The independent ledger check found periods where supply and use do not reconcile "
            "(reported; not yet a gate).", ENERGY_BALANCE_ARTIFACT)
    elif energy_balance["status"] == NOT_EVALUATED:
        add("GF_ENERGY_BALANCE_NOT_EVALUATED", "info",
            "The energy balance could not be verified from this ledger (reasons: "
            + ", ".join(str(item) for item in energy_balance.get("reasons") or []) + ").",
            ENERGY_BALANCE_ARTIFACT)
    adjusted = energy_balance.get("compatibility_adjustment_periods")
    if isinstance(adjusted, int) and adjusted > 0:
        add("GF_COMPAT_ADJUSTMENT_PRESENT", "warning",
            f"{adjusted} periods carry a compatibility adjustment that forces the self-reported residual to zero.",
            ENERGY_BALANCE_ARTIFACT)
    if stress and isinstance(stress.get("stress_periods"), int) and stress["stress_periods"] > 0:
        add("GF_STRESS_EVENTS_RECORDED", "warning",
            f"Accepted supply fell short of demand in {stress['stress_periods']} periods "
            f"({stress.get('event_count')} stress events); dispatch was not altered.", ENERGY_BALANCE_ARTIFACT)
    return warnings


def build_scientific_validation_report(
    *,
    mode: str,
    periods_per_year: int,
    parity_report: Mapping[str, object],
    mechanism_checks: list[MechanismCheck] | None = None,
    retained_comparison_role: str = RETAINED_COMPARISON_REQUIRED,
    run_invariants: Mapping[str, object] | None = None,
    energy_balance: Mapping[str, object] | None = None,
    execution_scope: str = "annual",
) -> dict[str, object]:
    """Scientific-validation report v2: every status traces to executed checks.

    * ``contract_validation_status`` is recomputed from the parity checks
      (none executed: ``not_evaluated``; P7-01).
    * ``analytical_mechanism_status`` (alias ``module_self_test_status``) is
      the fixed analytical self-test of the VALUE mechanisms; it says nothing
      about this run's numbers.
    * ``run_invariant_status`` and ``energy_balance_status`` are recomputed
      from the run-invariant report and the read-only energy-balance oracle.
      Both are reported with severity ``report`` (P0-4 S7 makes them gates of
      the production profile); a failure appears in ``validation_warnings``.
    * ``raw_invariants`` is the evidence of the Q14 publication rule.
    """

    if retained_comparison_role not in {
        RETAINED_COMPARISON_REQUIRED,
        RETAINED_COMPARISON_INFORMATIONAL,
    }:
        raise ValueError(f"Unknown retained comparison role: {retained_comparison_role}")
    checks = mechanism_checks if mechanism_checks is not None else analytical_mechanism_checks()
    mechanism_passed = bool(checks) and all(check.passed for check in checks)
    mechanism_status = (PASSED if mechanism_passed else FAILED) if checks else NOT_EVALUATED
    contract = contract_evidence(parity_report)
    contract_status = contract["status"]
    retained = parity_report.get("retained_numerical_parity_passed")
    retained_status = PASSED if retained is True else NOT_EVALUATED
    if retained is False:
        retained_status = (
            FAILED
            if retained_comparison_role == RETAINED_COMPARISON_REQUIRED
            else EXPECTED_DIFFERENCE
        )
    annual_economics_eligible = (
        periods_per_year == 17_520 and contract_status == PASSED and mechanism_passed
    )
    if contract_status == FAILED or mechanism_status == FAILED:
        scientific_status = FAILED
    elif (contract_status == NOT_EVALUATED or mechanism_status == NOT_EVALUATED
          or periods_per_year != 17_520):
        scientific_status = NOT_EVALUATED
    elif retained_comparison_role == RETAINED_COMPARISON_REQUIRED:
        scientific_status = retained_status
    else:
        # A deliberately different scientific policy is validated by its own
        # contracts and analytical mechanisms.  Its numerical delta from the
        # retained VALUE scenario is evidence to report, not a failed
        # reproduction claim that the project never made.
        scientific_status = PASSED
    invariants = run_invariant_evidence(run_invariants)
    balance, stress = energy_balance_summary(energy_balance)
    raw_status = (
        PASSED if invariants["status"] == PASSED and balance["status"] == PASSED
        else FAILED if FAILED in (invariants["status"], balance["status"])
        else NOT_EVALUATED
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "execution_scope": execution_scope,
        "periods_per_year": periods_per_year,
        "execution_status": PASSED,
        "contract_validation_status": contract_status,
        "contract_validation": contract,
        "analytical_mechanism_status": mechanism_status,
        "module_self_test_status": mechanism_status,
        "module_self_test_scope": "fixed analytical fixtures; independent of this run's numbers",
        "modular_numerical_baseline_status": NOT_EVALUATED,
        "retained_numerical_comparison_role": retained_comparison_role,
        "retained_numerical_comparison_status": retained_status,
        "scientific_validation_status": scientific_status,
        "run_invariant_status": invariants["status"],
        "run_invariants": invariants,
        "energy_balance_status": balance["status"],
        "energy_balance": balance,
        "stress": stress,
        "raw_invariants": {
            "status": raw_status,
            "run_invariant_status": invariants["status"],
            "energy_balance_status": balance["status"],
            "decision": "Q14",
        },
        "validation_warnings": _validation_warnings(contract, invariants, balance, stress),
        "annual_economics_eligible": annual_economics_eligible,
        "short_run_diagnostics_only": periods_per_year != 17_520,
        "mechanism_checks": [check.to_dict() for check in checks],
    }


def _read_optional_json(path: Path | None) -> dict[str, object] | None:
    if path is None or not Path(path).is_file():
        return None
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def write_scientific_validation_report(
    output_dir: Path,
    *,
    mode: str,
    periods_per_year: int,
    parity_path: Path,
    retained_comparison_role: str = RETAINED_COMPARISON_REQUIRED,
    run_invariants_path: Path | None = None,
    energy_balance_path: Path | None = None,
    execution_scope: str = "annual",
    mechanism_checks: list[MechanismCheck] | None = None,
    extra_fields: Mapping[str, object] | None = None,
) -> Path:
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    report = build_scientific_validation_report(
        mode=mode,
        periods_per_year=periods_per_year,
        parity_report=parity,
        retained_comparison_role=retained_comparison_role,
        run_invariants=_read_optional_json(run_invariants_path),
        energy_balance=_read_optional_json(energy_balance_path),
        execution_scope=execution_scope,
        mechanism_checks=mechanism_checks,
    )
    report.update(dict(extra_fields or {}))
    path = output_dir / "validation" / "scientific-validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


_DOCTORAL_SMALL = ("source_oracle", "units", "physical_dispatch", "settlement", "investment",
    "planning", "commissioning", "weather", "nuclear_policy", "checkpoint_identity")
_DOCTORAL_MONTH = _DOCTORAL_SMALL + ("month_resume",)
_DOCTORAL_YEAR = _DOCTORAL_MONTH + ("annual_dispatch", "annual_cashflow", "annual_cost_carbon", "annual_funding")
_DOCTORAL_TWO = _DOCTORAL_YEAR + ("cross_year_state", "ownership_transitions", "capacity_pipeline", "two_year_dispatch")
_DOCTORAL_TIERS = {"small": _DOCTORAL_SMALL, "month": _DOCTORAL_MONTH, "year": _DOCTORAL_YEAR,
    "two-year": _DOCTORAL_TWO, "ten-year": _DOCTORAL_TWO + ("ten_year_dispatch",)}


def validate_alignment_evidence(evidence: Mapping, *, expected_identity: Mapping,
                                required_tier: str = "small") -> dict:
    """Validate explicit doctoral comparison evidence, never run a model.

    The caller must verify the input/code/oracle identity and the referenced
    artifact bytes independently before calling. Local hashes detect drift;
    they are not proof against fabricated evidence. Numerical checks are
    recomputed, not inferred from a process exit code or a reported pass flag.
    """
    from .doctoral_contract import load_thesis96_contract

    def sha(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

    identity_fields = {"thesis_sha256", "candidate_sha256", "oracle_sha256", "inputs_sha256"}
    contract = load_thesis96_contract()
    if (evidence.get("schema_version") != "value.doctoral-alignment-evidence/v1"
            or not identity_fields <= set(expected_identity)
            or any(not sha(expected_identity[field]) for field in identity_fields)
            or expected_identity["thesis_sha256"] != contract["source_sha256"]
            or evidence.get("identity") != dict(expected_identity)):
        raise ValueError("Doctoral comparison evidence identity mismatch")
    if required_tier not in _DOCTORAL_TIERS:
        raise ValueError("Unknown doctoral comparison tier")
    exceptions = evidence.get("exceptions", [])
    if (not isinstance(exceptions, list) or any(not isinstance(item, str) for item in exceptions)
            or not set(exceptions) <= set(contract["retained_authorized_exceptions"])):
        raise ValueError("undeclared_exception in doctoral comparison evidence")
    checks = evidence.get("checks", {})
    if not isinstance(checks, Mapping):
        raise ValueError("Doctoral comparison checks must be a mapping")
    statuses, differences = {}, {}
    for name in _DOCTORAL_TIERS["ten-year"]:
        record = checks.get(name, {})
        if not isinstance(record, Mapping):
            statuses[name] = FAILED
            continue
        declared = record.get("status")
        comparisons = record.get("comparisons")
        if declared == FAILED:
            statuses[name] = FAILED
        elif declared != PASSED or not sha(record.get("artifact_sha256")) or not isinstance(comparisons, list) or not comparisons:
            statuses[name] = NOT_EVALUATED
        else:
            numerical, raw_differences = [], []
            for row in comparisons:
                if not isinstance(row, Mapping):
                    numerical.append(False)
                    continue
                check = MechanismCheck(row.get("id"), row.get("actual"), row.get("expected"),
                                       row.get("unit"), row.get("absolute_tolerance"))
                numerical.append(check.passed)
                # Do not serialize NaN/Inf into the resulting evidence report.
                numeric = all(not isinstance(row.get(key), bool) and isinstance(row.get(key), (int, float))
                              and math.isfinite(row[key]) for key in ("actual", "expected"))
                raw_differences.append({"id": row.get("id"), "unit": row.get("unit"),
                    "absolute_difference": abs(row["actual"] - row["expected"]) if numeric else None,
                    "status": PASSED if check.passed else FAILED})
            differences[name] = raw_differences
            statuses[name] = PASSED if numerical and all(numerical) else FAILED

    coverage = evidence.get("annual_coverage", [])
    years, coverage_valid = [], isinstance(coverage, list) and bool(coverage)
    if isinstance(coverage, list):
        for row in coverage:
            valid = (isinstance(row, Mapping) and type(row.get("year")) is int
                and type(row.get("period_count")) is int and row["period_count"] == 17520
                and type(row.get("start_period_index")) is int and row["start_period_index"] == 0
                and type(row.get("end_period_index_exclusive")) is int and row["end_period_index_exclusive"] == 17520
                and row.get("period_hours") == 0.5 and row.get("annual_complete") is True)
            coverage_valid = coverage_valid and valid
            if valid:
                years.append(row["year"])
    coverage_valid = coverage_valid and years == sorted(set(years))
    unresolved = evidence.get("unresolved_gates", [])
    if not isinstance(unresolved, list) or any(not isinstance(item, str) or not item for item in unresolved):
        raise ValueError("Invalid unresolved doctoral gate list")
    engineering = evidence.get("engineering_tests_passed") is True

    def passed(names):
        return engineering and not unresolved and all(statuses[name] == PASSED for name in names)

    annual = bool(coverage_valid and passed(_DOCTORAL_YEAR))
    two_year = bool(annual and len(years) >= 2 and all(b == a + 1 for a, b in zip(years, years[1:]))
                    and passed(_DOCTORAL_TWO))
    ten_year = bool(two_year and years == list(range(2025, 2035)) and passed(_DOCTORAL_TIERS["ten-year"]))
    blocking = [name for name in _DOCTORAL_TIERS[required_tier] if statuses[name] != PASSED]
    if not engineering:
        blocking.append("engineering_tests")
    blocking.extend(unresolved)
    coverage_ok = {"small": True, "month": True, "year": bool(coverage_valid),
        "two-year": bool(coverage_valid and len(years) >= 2 and all(b == a + 1 for a, b in zip(years, years[1:]))),
        "ten-year": bool(coverage_valid and years == list(range(2025, 2035)))}[required_tier]
    if not coverage_ok:
        blocking.append("annual_coverage")
    status = PASSED if not blocking else (
        FAILED if any(statuses.get(name) == FAILED for name in blocking) else NOT_EVALUATED)
    release = "not_released"
    if status == PASSED:
        release = {"small": "scoped_parity_passed", "month": "month_verified",
            "year": "annual_verified", "two-year": "two_year_verified",
            "ten-year": "full_multiyear_verified"}[required_tier]
    return {"schema_version": "value.doctoral-alignment-validation/v1",
        "required_tier": required_tier, "identity": dict(expected_identity),
        "validation_status": status, "release_status": release,
        "engineering_tests_passed": engineering, "scoped_parity_passed": passed(_DOCTORAL_SMALL),
        "annual_verified": annual, "two_year_verified": two_year, "multiyear_verified": ten_year,
        "blocking_checks": list(dict.fromkeys(blocking)), "check_statuses": statuses,
        "raw_differences": differences, "exceptions": list(exceptions),
        "artifact_authentication": "required_from_caller_not_inferred_from_self_reported_hashes"}
