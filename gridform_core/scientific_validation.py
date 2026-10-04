"""Scientific acceptance reporting independent of process completion."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .builtin.scheme_c_1000twh.runtime_compat.storage_cost import DynamicAnnualStorageCost
from .dispatch_benchmark import solve_fixture


SCHEMA_VERSION = "value.scientific-validation/v1"
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


def build_scientific_validation_report(
    *,
    mode: str,
    periods_per_year: int,
    parity_report: Mapping[str, object],
    mechanism_checks: list[MechanismCheck] | None = None,
    retained_comparison_role: str = RETAINED_COMPARISON_REQUIRED,
) -> dict[str, object]:
    if retained_comparison_role not in {
        RETAINED_COMPARISON_REQUIRED,
        RETAINED_COMPARISON_INFORMATIONAL,
    }:
        raise ValueError(f"Unknown retained comparison role: {retained_comparison_role}")
    checks = mechanism_checks if mechanism_checks is not None else analytical_mechanism_checks()
    mechanism_passed = bool(checks) and all(check.passed for check in checks)
    mechanism_status = (PASSED if mechanism_passed else FAILED) if checks else NOT_EVALUATED
    contract_passed = parity_report.get("contract_parity_passed") is True
    retained = parity_report.get("retained_numerical_parity_passed")
    retained_status = PASSED if retained is True else NOT_EVALUATED
    if retained is False:
        retained_status = (
            FAILED
            if retained_comparison_role == RETAINED_COMPARISON_REQUIRED
            else EXPECTED_DIFFERENCE
        )
    annual_economics_eligible = (
        periods_per_year == 17_520 and contract_passed and mechanism_passed
    )
    if not contract_passed or mechanism_status == FAILED:
        scientific_status = FAILED
    elif mechanism_status == NOT_EVALUATED or periods_per_year != 17_520:
        scientific_status = NOT_EVALUATED
    elif retained_comparison_role == RETAINED_COMPARISON_REQUIRED:
        scientific_status = retained_status
    else:
        # A deliberately different scientific policy is validated by its own
        # contracts and analytical mechanisms.  Its numerical delta from the
        # retained VALUE scenario is evidence to report, not a failed
        # reproduction claim that the project never made.
        scientific_status = PASSED
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "periods_per_year": periods_per_year,
        "execution_status": PASSED,
        "contract_validation_status": PASSED if contract_passed else FAILED,
        "analytical_mechanism_status": mechanism_status,
        "modular_numerical_baseline_status": NOT_EVALUATED,
        "retained_numerical_comparison_role": retained_comparison_role,
        "retained_numerical_comparison_status": retained_status,
        "scientific_validation_status": scientific_status,
        "annual_economics_eligible": annual_economics_eligible,
        "short_run_diagnostics_only": periods_per_year != 17_520,
        "mechanism_checks": [check.to_dict() for check in checks],
    }


def write_scientific_validation_report(
    output_dir: Path,
    *,
    mode: str,
    periods_per_year: int,
    parity_path: Path,
    retained_comparison_role: str = RETAINED_COMPARISON_REQUIRED,
) -> Path:
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    report = build_scientific_validation_report(
        mode=mode,
        periods_per_year=periods_per_year,
        parity_report=parity,
        retained_comparison_role=retained_comparison_role,
    )
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
