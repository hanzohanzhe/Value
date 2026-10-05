"""Canonical numerical contract for the experimental zonal solver."""

from __future__ import annotations

import math
import hashlib
import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

import numpy as np


# Solver contract v4 (P0-8 S4, Q5): after the primary solve the total load
# shedding is locked first (sum(shed) <= shed*), then only the bid-cost terms
# carry a coefficient-aware numerical lock.  GBP 1 per period remains the
# acceptance ceiling of that lock, never its right-hand side.
SOLVER_SCHEMA_VERSION = "value.network-solver-contract/v4"
SOLVER_CONTRACT_VERSION = "value.zonal-lexicographic-shed-lock/v4"
# Historical contracts stay readable (recorded evidence, frozen Studies) but
# are never executed again.
V3_SOLVER_SCHEMA_VERSION = "value.network-solver-contract/v3"
V3_SOLVER_CONTRACT_VERSION = "value.zonal-lexicographic-gbp1/v3"
V2_SOLVER_SCHEMA_VERSION = "value.network-solver-contract/v2"
V2_SOLVER_CONTRACT_VERSION = "value.zonal-lexicographic/v2"
RECORDED_SOLVER_CONTRACTS = MappingProxyType({
    V2_SOLVER_SCHEMA_VERSION: V2_SOLVER_CONTRACT_VERSION,
    V3_SOLVER_SCHEMA_VERSION: V3_SOLVER_CONTRACT_VERSION,
    SOLVER_SCHEMA_VERSION: SOLVER_CONTRACT_VERSION,
})
SOLVER_VALIDATION_REGISTRY_SCHEMA_VERSION = (
    "value.solver-validation-registry/v1"
)
SOLVER_VALIDATION_REGISTRY_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "contracts"
    / "solver-validation-registry-v1.json"
)
ALLOWED_METHODS = frozenset({"highs-ds", "highs-ipm", "highs"})
_CEILING_KEYS = (
    "primary_bid_cost_gbp",
    "secondary_schedule_deviation_mwh",
    "physical_throughput_mwh",
)

DEFAULT_VALIDATED_CEILINGS = MappingProxyType({
    # Study acceptance ceiling: maximum accepted degradation of the period
    # bid-cost objective.  GBP per solved period, not GBP/MWh or per asset.
    # Since v4 it classifies the numerical lock and is never spent by it.
    "primary_bid_cost_gbp": 1.0,
    "secondary_schedule_deviation_mwh": 0.001,
    "physical_throughput_mwh": 0.001,
})
RECORDED_REFERENCE_THRESHOLDS = MappingProxyType({
    "primary_bid_cost_gbp": 1.0,
    "secondary_schedule_deviation_mwh": 0.01,
    "physical_throughput_mwh": 0.01,
})


@dataclass(frozen=True)
class ZonalSolverSettings:
    schema_version: str
    contract_version: str
    method: str
    presolve: bool
    primal_feasibility_tolerance: float
    dual_feasibility_tolerance: float
    ipm_optimality_tolerance: float
    warning_fraction: float
    validated_ceilings: Mapping[str, float]
    absolute_ceilings: Mapping[str, float]
    is_builtin_default: bool
    requires_acknowledgement: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "method": self.method,
            "presolve": self.presolve,
            "primal_feasibility_tolerance": self.primal_feasibility_tolerance,
            "dual_feasibility_tolerance": self.dual_feasibility_tolerance,
            "ipm_optimality_tolerance": self.ipm_optimality_tolerance,
            "warning_fraction": self.warning_fraction,
            "validated_ceilings": dict(self.validated_ceilings),
            "absolute_ceilings": dict(self.absolute_ceilings),
            "is_builtin_default": self.is_builtin_default,
            "requires_acknowledgement": self.requires_acknowledgement,
        }


def _settings_payload(*, is_builtin_default: bool, requires_acknowledgement: bool) -> dict[str, object]:
    return {
        "schema_version": SOLVER_SCHEMA_VERSION,
        "contract_version": SOLVER_CONTRACT_VERSION,
        "method": "highs-ds",
        "presolve": True,
        "primal_feasibility_tolerance": 1e-9,
        "dual_feasibility_tolerance": 1e-9,
        "ipm_optimality_tolerance": 1e-9,
        "warning_fraction": 0.10,
        "validated_ceilings": dict(DEFAULT_VALIDATED_CEILINGS),
        "absolute_ceilings": dict(RECORDED_REFERENCE_THRESHOLDS),
        "is_builtin_default": is_builtin_default,
        "requires_acknowledgement": requires_acknowledgement,
    }


_default_settings_payload = _settings_payload(is_builtin_default=True, requires_acknowledgement=False)
_default_settings_payload["validated_ceilings"] = DEFAULT_VALIDATED_CEILINGS
_default_settings_payload["absolute_ceilings"] = RECORDED_REFERENCE_THRESHOLDS
DEFAULT_ZONAL_SOLVER_SETTINGS = ZonalSolverSettings(**_default_settings_payload)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _validated_mapping(value: object, label: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(_CEILING_KEYS):
        raise ValueError(f"{label} must contain exactly the declared objective ceilings")
    return MappingProxyType({key: _finite_number(value[key], f"{label}.{key}") for key in _CEILING_KEYS})


def validate_solver_settings(payload: Mapping[str, object]) -> ZonalSolverSettings:
    """Validate settings, preserving immutable execution limits and derived flags."""
    if not isinstance(payload, Mapping):
        raise ValueError("Solver settings must be an object")
    required = set(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
    unknown = set(payload).difference(required)
    missing = required.difference(payload)
    if unknown or missing:
        details = []
        if unknown:
            details.append("unknown fields: " + ", ".join(sorted(map(str, unknown))))
        if missing:
            details.append("missing fields: " + ", ".join(sorted(missing)))
        raise ValueError("Solver settings have " + "; ".join(details))
    if payload["schema_version"] != SOLVER_SCHEMA_VERSION:
        if payload["schema_version"] in RECORDED_SOLVER_CONTRACTS:
            raise ZonalSolverContractError(
                "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED",
                f"{payload['schema_version']} is a historical zonal solver "
                f"contract; executing requires an explicit upgrade to "
                f"{SOLVER_SCHEMA_VERSION}",
            )
        raise ValueError("Unsupported solver settings schema_version")
    if payload["contract_version"] != SOLVER_CONTRACT_VERSION:
        raise ValueError("Unsupported solver settings contract_version")
    method = payload["method"]
    if not isinstance(method, str) or method not in ALLOWED_METHODS:
        raise ValueError("Solver method is invalid")
    if payload["presolve"] is not True:
        raise ValueError("Solver presolve must remain enabled")

    primal = _finite_number(payload["primal_feasibility_tolerance"], "primal_feasibility_tolerance")
    dual = _finite_number(payload["dual_feasibility_tolerance"], "dual_feasibility_tolerance")
    ipm = _finite_number(payload["ipm_optimality_tolerance"], "ipm_optimality_tolerance")
    warning_fraction = _finite_number(payload["warning_fraction"], "warning_fraction")
    if not 1e-10 <= primal <= 1e-7:
        raise ValueError("primal_feasibility_tolerance must be within 1e-10..1e-7")
    if not 1e-10 <= dual <= 1e-7:
        raise ValueError("dual_feasibility_tolerance must be within 1e-10..1e-7")
    if not 1e-12 <= ipm <= 1e-7:
        raise ValueError("ipm_optimality_tolerance must be within 1e-12..1e-7")
    if not 0.0 < warning_fraction <= 1.0:
        raise ValueError("warning_fraction must be within 0..1")

    validated_ceilings = _validated_mapping(payload["validated_ceilings"], "validated_ceilings")
    absolute_ceilings = _validated_mapping(payload["absolute_ceilings"], "absolute_ceilings")
    for key in _CEILING_KEYS:
        if absolute_ceilings[key] != RECORDED_REFERENCE_THRESHOLDS[key]:
            raise ValueError(f"recorded reference threshold differs for {key}")
        if (
            key == "primary_bid_cost_gbp"
            and validated_ceilings[key] != DEFAULT_VALIDATED_CEILINGS[key]
        ):
            raise ValueError(
                "primary_bid_cost_gbp validated ceiling is fixed at GBP 1 "
                "per period by the study acceptance policy"
            )
        within_reference = (
            0.0 < validated_ceilings[key] <= absolute_ceilings[key]
            if key == "primary_bid_cost_gbp"
            else 0.0 < validated_ceilings[key] < absolute_ceilings[key]
        )
        if not within_reference:
            raise ValueError(f"validated ceiling must be positive and at or below the recorded reference threshold: {key}")

    values = {
        "schema_version": SOLVER_SCHEMA_VERSION,
        "contract_version": SOLVER_CONTRACT_VERSION,
        "method": method,
        "presolve": True,
        "primal_feasibility_tolerance": primal,
        "dual_feasibility_tolerance": dual,
        "ipm_optimality_tolerance": ipm,
        "warning_fraction": warning_fraction,
        "validated_ceilings": dict(validated_ceilings),
        "absolute_ceilings": dict(absolute_ceilings),
    }
    builtin_values = _settings_payload(is_builtin_default=True, requires_acknowledgement=False)
    is_builtin_default = all(values[key] == builtin_values[key] for key in values)
    requires_acknowledgement = not is_builtin_default
    if payload["is_builtin_default"] is not is_builtin_default:
        raise ValueError("is_builtin_default must be derived from validated values")
    if payload["requires_acknowledgement"] is not requires_acknowledgement:
        raise ValueError("requires_acknowledgement must be derived from validated values")

    values["validated_ceilings"] = validated_ceilings
    values["absolute_ceilings"] = absolute_ceilings
    values["is_builtin_default"] = is_builtin_default
    values["requires_acknowledgement"] = requires_acknowledgement
    return ZonalSolverSettings(**values)


class ZonalSolverContractError(ValueError):
    """A hard numerical-contract failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def validate_recorded_solver_settings(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate a recorded v2, v3 or v4 contract for reading history only.

    The returned mapping is the recorded payload, unchanged.  It must never be
    passed to a solver: execution accepts only ``validate_solver_settings``
    (v4).  Historical rows keep their own field layout; only the declared
    identity pair, method and numerical ranges are checked.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("Recorded solver settings must be an object")
    schema = payload.get("schema_version")
    if schema == SOLVER_SCHEMA_VERSION:
        return validate_solver_settings(payload).to_dict()
    if schema not in RECORDED_SOLVER_CONTRACTS:
        raise ValueError("Unsupported recorded solver settings schema_version")
    if payload.get("contract_version") != RECORDED_SOLVER_CONTRACTS[schema]:
        raise ValueError("Recorded solver settings contract_version does not match its schema")
    if payload.get("method") not in ALLOWED_METHODS:
        raise ValueError("Recorded solver method is invalid")
    for key in (
        "primal_feasibility_tolerance",
        "dual_feasibility_tolerance",
        "ipm_optimality_tolerance",
        "warning_fraction",
    ):
        value = _finite_number(payload.get(key), key)
        if value <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("validated_ceilings", "absolute_ceilings"):
        _validated_mapping(payload.get(key), key)
    return dict(payload)


def solver_contract_generation(payload: Mapping[str, object] | None) -> str:
    """Return "v4", "v3", "v2" or "unknown" for a recorded contract."""

    if not isinstance(payload, Mapping):
        return "unknown"
    return {
        SOLVER_SCHEMA_VERSION: "v4",
        V3_SOLVER_SCHEMA_VERSION: "v3",
        V2_SOLVER_SCHEMA_VERSION: "v2",
    }.get(str(payload.get("schema_version") or ""), "unknown")


def degradation_identity_matches(
    *,
    optimum: object,
    achieved_final_value: object,
    degradation: object,
    computed_tolerance: object,
) -> bool:
    """Check the unit-preserving final degradation identity.

    The allowance is only floating-point reconstruction noise and is bounded
    by the declared lock tolerance.  It is intentionally much smaller than a
    solver lock allowance for ordinary values, so a stored zero cannot conceal
    a material final objective degradation.
    """

    values: dict[str, float] = {}
    for label, raw in (
        ("optimum", optimum),
        ("achieved_final_value", achieved_final_value),
        ("degradation", degradation),
        ("computed_tolerance", computed_tolerance),
    ):
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ZonalSolverContractError(
                "GF_ZONAL_LOCK_TOLERANCE_INVALID", f"{label} is not numeric"
            ) from exc
        if not math.isfinite(value):
            raise ZonalSolverContractError(
                "GF_ZONAL_LOCK_TOLERANCE_INVALID", f"{label} must be finite"
            )
        values[label] = value
    if values["degradation"] < 0.0 or values["computed_tolerance"] < 0.0:
        return False
    expected = max(
        0.0, values["achieved_final_value"] - values["optimum"]
    )
    scale = max(
        1.0,
        abs(values["optimum"]),
        abs(values["achieved_final_value"]),
        abs(expected),
    )
    reconstruction_tolerance = min(
        values["computed_tolerance"], 8.0e-15 * scale
    )
    return abs(values["degradation"] - expected) <= reconstruction_tolerance


@dataclass(frozen=True)
class LockTolerance:
    nonzero_terms: int
    absolute_term_scale: float
    gamma_n: float
    tolerance: float


@dataclass(frozen=True)
class LockClassification:
    status: str
    ceiling_use: float
    is_solver_validated: bool


@dataclass(frozen=True)
class ObjectiveLockDiagnostic:
    phase_id: str
    objective_unit: str
    optimum: float
    achieved_final_value: float
    degradation: float
    computed_tolerance: float
    validated_ceiling: float
    absolute_ceiling: float
    nonzero_terms: int
    absolute_term_scale: float
    validation_class: str
    warning_fraction: float = 0.10
    error_code: str | None = None


@dataclass(frozen=True)
class SolverStackIdentity:
    scipy_version: str
    highs_extension_path: str
    highs_binary_sha256: str
    highs_identity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "scipy_version": self.scipy_version,
            "highs_extension_path": self.highs_extension_path,
            "highs_binary_sha256": self.highs_binary_sha256,
            "highs_identity": self.highs_identity,
        }


@dataclass(frozen=True)
class SolverValidationRegistryEntry:
    """A reviewed source-controlled disposition for one immutable stack."""

    registry_id: str
    module_id: str
    module_version: str
    solver_contract_version: str
    scipy_version: str
    highs_binary_sha256: str
    highs_identity: str
    status: str
    evidence_references: tuple[str, ...]


_REGISTRY_ENTRY_FIELDS = frozenset(
    {
        "registry_id",
        "module_id",
        "module_version",
        "solver_contract_version",
        "scipy_version",
        "highs_binary_sha256",
        "highs_identity",
        "status",
        "evidence_references",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _registry_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def load_solver_validation_registry(
    path: Path | None = None,
) -> tuple[SolverValidationRegistryEntry, ...]:
    """Load reviewed stack dispositions without consulting runtime discovery."""

    registry_path = path or SOLVER_VALIDATION_REGISTRY_PATH
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "entries",
    }:
        raise ValueError("Solver validation registry must contain exact top-level fields")
    if payload["schema_version"] != SOLVER_VALIDATION_REGISTRY_SCHEMA_VERSION:
        raise ValueError("Unsupported solver validation registry schema_version")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("Solver validation registry entries must be a non-empty array")

    entries: list[SolverValidationRegistryEntry] = []
    registry_ids: set[str] = set()
    stack_identities: set[tuple[str, ...]] = set()
    for index, raw_entry in enumerate(raw_entries):
        label = f"entries[{index}]"
        if not isinstance(raw_entry, dict) or set(raw_entry) != _REGISTRY_ENTRY_FIELDS:
            raise ValueError(f"{label} must contain exact registry entry fields")
        registry_id = _registry_text(raw_entry["registry_id"], f"{label}.registry_id")
        if not _REGISTRY_ID_PATTERN.fullmatch(registry_id):
            raise ValueError(f"{label}.registry_id has invalid syntax")
        status = _registry_text(raw_entry["status"], f"{label}.status")
        if status not in {"candidate", "validated"}:
            raise ValueError(f"{label}.status must be candidate or validated")
        sha256 = _registry_text(
            raw_entry["highs_binary_sha256"],
            f"{label}.highs_binary_sha256",
        )
        if not _SHA256_PATTERN.fullmatch(sha256):
            raise ValueError(f"{label}.highs_binary_sha256 must be lowercase SHA-256")
        highs_identity = _registry_text(
            raw_entry["highs_identity"], f"{label}.highs_identity"
        )
        if highs_identity != f"scipy-embedded-highs:{sha256}":
            raise ValueError(f"{label}.highs_identity does not match its SHA-256")
        raw_evidence = raw_entry["evidence_references"]
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ValueError(f"{label}.evidence_references must be non-empty")
        evidence = tuple(
            _registry_text(item, f"{label}.evidence_references")
            for item in raw_evidence
        )
        if len(set(evidence)) != len(evidence):
            raise ValueError(f"{label}.evidence_references must be unique")
        entry = SolverValidationRegistryEntry(
            registry_id=registry_id,
            module_id=_registry_text(raw_entry["module_id"], f"{label}.module_id"),
            module_version=_registry_text(
                raw_entry["module_version"], f"{label}.module_version"
            ),
            solver_contract_version=_registry_text(
                raw_entry["solver_contract_version"],
                f"{label}.solver_contract_version",
            ),
            scipy_version=_registry_text(
                raw_entry["scipy_version"], f"{label}.scipy_version"
            ),
            highs_binary_sha256=sha256,
            highs_identity=highs_identity,
            status=status,
            evidence_references=evidence,
        )
        stack_identity = (
            entry.module_id,
            entry.module_version,
            entry.solver_contract_version,
            entry.scipy_version,
            entry.highs_binary_sha256,
            entry.highs_identity,
        )
        if entry.registry_id in registry_ids:
            raise ValueError(f"Duplicate solver validation registry_id: {entry.registry_id}")
        if stack_identity in stack_identities:
            raise ValueError("Duplicate immutable solver stack in validation registry")
        registry_ids.add(entry.registry_id)
        stack_identities.add(stack_identity)
        entries.append(entry)
    return tuple(entries)


def solver_stack_is_validated(
    entries: Iterable[SolverValidationRegistryEntry],
    *,
    module_id: str,
    module_version: str,
    solver_contract_version: str,
    scipy_version: str,
    highs_binary_sha256: str,
    highs_identity: str,
) -> bool:
    """Return true only for an exact stack explicitly promoted in the registry."""

    stack_identity = (
        module_id,
        module_version,
        solver_contract_version,
        scipy_version,
        highs_binary_sha256,
        highs_identity,
    )
    return any(
        entry.status == "validated"
        and entry.highs_identity
        == f"scipy-embedded-highs:{entry.highs_binary_sha256}"
        and stack_identity
        == (
            entry.module_id,
            entry.module_version,
            entry.solver_contract_version,
            entry.scipy_version,
            entry.highs_binary_sha256,
            entry.highs_identity,
        )
        for entry in entries
    )


def _contract_number(value: object, label: str, *, positive: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", f"{label} is not numeric") from exc
    if not math.isfinite(result) or (result <= 0.0 if positive else result < 0.0):
        qualifier = "positive and finite" if positive else "non-negative and finite"
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", f"{label} must be {qualifier}")
    return result


def compute_lock_tolerance(
    coefficients: np.ndarray,
    optimum: np.ndarray,
    unit_floor: float,
    solver_tolerance: float,
) -> LockTolerance:
    """Compute the declared one-sided floating-point tolerance for one objective."""
    coefficient_array = np.asarray(coefficients, dtype=float)
    optimum_array = np.asarray(optimum, dtype=float)
    if coefficient_array.shape != optimum_array.shape or coefficient_array.ndim != 1:
        raise ZonalSolverContractError(
            "GF_ZONAL_LOCK_TOLERANCE_INVALID", "coefficient and optimum vectors must be one-dimensional and aligned"
        )
    if not np.all(np.isfinite(coefficient_array)) or not np.all(np.isfinite(optimum_array)):
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "objective vectors must be finite")
    floor = _contract_number(unit_floor, "unit_floor", positive=True)
    solver = _contract_number(solver_tolerance, "solver_tolerance", positive=True)
    mask = coefficient_array != 0.0
    nonzero_terms = int(np.count_nonzero(mask))
    if nonzero_terms <= 0:
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "objective has no non-zero terms")
    absolute_coefficients = np.abs(coefficient_array[mask])
    absolute_term_scale = float(np.sum(absolute_coefficients * np.abs(optimum_array[mask])))
    coefficient_one_norm = float(np.sum(absolute_coefficients))
    epsilon = float(np.finfo(float).eps)
    denominator = 1.0 - nonzero_terms * epsilon
    if not math.isfinite(absolute_term_scale) or not math.isfinite(denominator) or denominator <= 0.0:
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "objective scale is not computable")
    gamma_n = float(nonzero_terms * epsilon / denominator)
    tolerance = max(
        floor,
        solver * max(1.0, absolute_term_scale),
        gamma_n * absolute_term_scale,
        coefficient_one_norm * solver,
    )
    if not math.isfinite(gamma_n) or not math.isfinite(tolerance):
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "lock tolerance is not finite")
    return LockTolerance(
        nonzero_terms=nonzero_terms,
        absolute_term_scale=absolute_term_scale,
        gamma_n=gamma_n,
        tolerance=float(tolerance),
    )


def classify_lock(
    degradation: float,
    computed_tolerance: float,
    validated_ceiling: float,
    warning_fraction: float,
    absolute_ceiling: float,
) -> LockClassification:
    """Classify a lock using the greater of observed degradation and tolerance."""
    degradation_value = _contract_number(degradation, "degradation")
    tolerance_value = _contract_number(computed_tolerance, "computed_tolerance")
    validated_value = _contract_number(validated_ceiling, "validated_ceiling", positive=True)
    warning_value = _contract_number(warning_fraction, "warning_fraction", positive=True)
    absolute_value = _contract_number(absolute_ceiling, "absolute_ceiling", positive=True)
    if warning_value > 1.0:
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "warning_fraction must not exceed one")
    if absolute_value < validated_value:
        raise ZonalSolverContractError("GF_ZONAL_LOCK_TOLERANCE_INVALID", "absolute ceiling cannot be below validated ceiling")
    ceiling_value = max(degradation_value, tolerance_value)
    if degradation_value > tolerance_value:
        raise ZonalSolverContractError(
            "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION", "observed degradation exceeds computed tolerance"
        )
    ceiling_use = ceiling_value / validated_value
    if ceiling_use <= warning_value:
        return LockClassification("GO", ceiling_use, True)
    if ceiling_use <= 1.0:
        return LockClassification("GO_WITH_NUMERICAL_WARNING", ceiling_use, True)
    return LockClassification("COMPLETED_WITH_NUMERICAL_WARNING", ceiling_use, False)


@dataclass(frozen=True)
class StoredLockEvidenceValidation:
    errors: tuple[str, ...]
    authoritative_status: str | None


def gbp1_stored_policy_matches(row: Mapping[str, object]) -> bool:
    """Enforce the recorded primary evidence policy of each contract.

    * v3 (GBP 1 lock): computed_tolerance, validated_ceiling and
      absolute_ceiling all equal GBP 1.  The check names the v3 contract
      explicitly; before P0-8 it compared with the *current* constant and
      would have stopped checking v3 rows once the constant moved to v4.
    * v4 (shed lock + numerical bid lock): GBP 1 is only the validated and
      absolute ceiling; the computed tolerance is the numerical one and must
      not reach the GBP 1 ceiling silently, so it is checked by
      ``classify_lock`` rather than here.
    * v2 and anything else: history is not re-judged.
    """

    contract = str(row.get("solver_contract_version") or "")
    if str(row.get("phase_id") or "") != "primary_bid_cost":
        return True
    try:
        if contract == V3_SOLVER_CONTRACT_VERSION:
            return all(
                float(row[field]) == 1.0
                for field in (
                    "computed_tolerance", "validated_ceiling", "absolute_ceiling"
                )
            )
        if contract == SOLVER_CONTRACT_VERSION:
            return (
                float(row["validated_ceiling"]) == 1.0
                and float(row["absolute_ceiling"]) == 1.0
            )
    except (KeyError, TypeError, ValueError):
        return False
    return True


def validate_stored_lock_evidence(
    row: Mapping[str, object],
) -> StoredLockEvidenceValidation:
    """Recompute one stored diagnostic without trusting its declared class."""

    errors: list[str] = []
    if not gbp1_stored_policy_matches(row):
        errors.append("solver_diagnostics_gbp1_policy_mismatch")
    phase_id = str(row.get("phase_id") or "")
    objective_unit = str(row.get("objective_unit") or "")
    expected_unit = "GBP" if phase_id == "primary_bid_cost" else "MWh"
    if phase_id not in {
        "primary_bid_cost",
        "secondary_schedule_deviation",
        "physical_throughput",
    } or objective_unit != expected_unit:
        errors.append("solver_diagnostics_objective_unit_mismatch")

    method = str(row.get("method") or "")
    primal = row.get("primal_feasibility_tolerance")
    dual = row.get("dual_feasibility_tolerance")
    ipm = row.get("ipm_optimality_tolerance")
    try:
        primal_value = float(primal)
        dual_value = float(dual)
        tolerances_valid = (
            math.isfinite(primal_value)
            and primal_value > 0.0
            and math.isfinite(dual_value)
            and dual_value > 0.0
        )
    except (TypeError, ValueError):
        tolerances_valid = False
    if method not in {"highs-ds", "highs-ipm", "highs"}:
        errors.append("solver_diagnostics_method_contract_invalid")
    elif method == "highs-ds":
        tolerances_valid = tolerances_valid and ipm is None
    else:
        try:
            ipm_value = float(ipm)
            tolerances_valid = (
                tolerances_valid
                and math.isfinite(ipm_value)
                and ipm_value > 0.0
            )
        except (TypeError, ValueError):
            tolerances_valid = False
    if not tolerances_valid:
        errors.append("solver_diagnostics_solver_tolerance_invalid")

    digest = str(row.get("highs_binary_sha256") or "")
    if (
        re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or str(row.get("highs_identity") or "")
        != f"scipy-embedded-highs:{digest}"
    ):
        errors.append("solver_diagnostics_identity_sha_mismatch")

    try:
        identity_matches = degradation_identity_matches(
            optimum=row.get("optimum"),
            achieved_final_value=row.get("achieved_final_value"),
            degradation=row.get("degradation"),
            computed_tolerance=row.get("computed_tolerance"),
        )
    except ZonalSolverContractError:
        identity_matches = False
    if not identity_matches:
        errors.append("solver_diagnostics_degradation_identity_mismatch")

    authoritative_status: str | None = None
    try:
        degradation = float(row["degradation"])
        computed_tolerance = float(row["computed_tolerance"])
        if degradation > computed_tolerance:
            errors.append(
                "solver_diagnostics_degradation_exceeds_computed_tolerance"
            )
        classification = classify_lock(
            degradation,
            computed_tolerance,
            float(row["validated_ceiling"]),
            float(row["warning_ceiling"]) / float(row["validated_ceiling"]),
            float(row["absolute_ceiling"]),
        )
        authoritative_status = classification.status
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        if not (
            isinstance(exc, ZonalSolverContractError)
            and exc.code == "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION"
        ):
            errors.append("solver_diagnostics_lock_classification_invalid")

    stored_status = str(row.get("validation_class") or "")
    if stored_status not in _STATUS_ORDER:
        errors.append("solver_diagnostics_validation_class_unsupported")
    elif (
        authoritative_status is not None
        and stored_status != authoritative_status
    ):
        errors.append("solver_diagnostics_validation_class_mismatch")
    return StoredLockEvidenceValidation(
        tuple(dict.fromkeys(errors)), authoritative_status
    )


_STATUS_ORDER = {
    "GO": 0,
    "GO_WITH_NUMERICAL_WARNING": 1,
    "COMPLETED_WITH_NUMERICAL_WARNING": 2,
}


def summarise_solver_diagnostics(rows: Iterable[ObjectiveLockDiagnostic]) -> dict[str, object]:
    """Aggregate locked-phase evidence while preserving the worst period status."""
    phases: dict[str, dict[str, float | int]] = {}
    worst_status = "GO"
    for row in rows:
        if row.validation_class not in _STATUS_ORDER:
            raise ValueError(f"Unknown solver validation class: {row.validation_class}")
        values = (
            row.degradation,
            row.computed_tolerance,
            row.validated_ceiling,
            row.absolute_ceiling,
            row.absolute_term_scale,
            row.warning_fraction,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Solver diagnostic values must be finite")
        if (
            row.validated_ceiling <= 0.0
            or row.degradation < 0.0
            or row.computed_tolerance < 0.0
            or not 0.0 < row.warning_fraction <= 1.0
        ):
            raise ValueError("Solver diagnostic values are out of range")
        phase = phases.setdefault(row.phase_id, {
            "max_tolerance": 0.0,
            "max_degradation": 0.0,
            "periods_above_warning_fraction": 0,
            "periods_above_validated_ceiling": 0,
            "cumulative_absolute_degradation": 0.0,
        })
        phase["max_tolerance"] = max(float(phase["max_tolerance"]), row.computed_tolerance)
        phase["max_degradation"] = max(float(phase["max_degradation"]), row.degradation)
        ceiling_value = max(row.degradation, row.computed_tolerance)
        if ceiling_value > row.warning_fraction * row.validated_ceiling:
            phase["periods_above_warning_fraction"] = int(phase["periods_above_warning_fraction"]) + 1
        if ceiling_value > row.validated_ceiling:
            phase["periods_above_validated_ceiling"] = int(phase["periods_above_validated_ceiling"]) + 1
        phase["cumulative_absolute_degradation"] = (
            float(phase["cumulative_absolute_degradation"]) + abs(row.degradation)
        )
        if _STATUS_ORDER[row.validation_class] > _STATUS_ORDER[worst_status]:
            worst_status = row.validation_class
    return {"study_status": worst_status, "phases": phases}


def solver_stack_identity() -> SolverStackIdentity:
    """Return an auditable identity for SciPy and its embedded HiGHS binary."""
    try:
        scipy = importlib.import_module("scipy")
        highs_wrapper = importlib.import_module("scipy.optimize._highs._highs_wrapper")
        module_path = Path(str(highs_wrapper.__file__)).resolve(strict=True)
        digest = hashlib.sha256(module_path.read_bytes()).hexdigest()
    except (AttributeError, ImportError, OSError, TypeError, ValueError) as exc:
        raise ZonalSolverContractError(
            "GF_ZONAL_SOLVER_IDENTITY_UNAVAILABLE", "embedded HiGHS extension binary is unavailable"
        ) from exc
    return SolverStackIdentity(
        scipy_version=str(scipy.__version__),
        highs_extension_path=str(module_path),
        highs_binary_sha256=digest,
        highs_identity=f"scipy-embedded-highs:{digest}",
    )
