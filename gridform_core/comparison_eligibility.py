"""Machine-readable evidence for controlled copperplate/zonal comparisons."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .zonal_demand_alignment import (
    NETWORK_PACK_ABSOLUTE_DEMAND,
    SCENARIO_SCALED_ZONAL_SHARES,
)


COPPERPLATE_SCENARIO_DEMAND = "copperplate_scenario_demand"
SCHEMA_VERSION = "value.comparison-eligibility/v1"
PAIR_SCHEMA_VERSION = "value.network-comparison-eligibility/v1"
CURTAILMENT_PAIR_SCHEMA_VERSION = "value.vre-curtailment-comparison-eligibility/v1"
ABSOLUTE_MODE_LABEL = (
    "Independent zonal-demand study. National demand is supplied by the network "
    "pack. Network-cost attribution against a scenario-demand copperplate run is "
    "disabled."
)


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_series(values: Sequence[float], label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) or value < 0.0 for value in result):
        raise ValueError(f"{label} must contain finite non-negative values")
    return result


def build_psm_comparison_input_evidence(
    *,
    year: int,
    period_ids: Sequence[str],
    real_demand_mwh: Sequence[float],
    forecast_demand_mwh: Sequence[float],
    availability_mwh_by_technology: Mapping[str, Sequence[float]],
    boundary_series_sha256: str | None = None,
    data_method_id: str | None = None,
) -> dict[str, object]:
    """Fingerprint the physical exogenous chronology, independent of zones.

    P0-5a S4: the boundary series (signed flows and raw prices) and the
    data-reading method enter the identity when the chronology records them,
    so two Runs read with different methods are not silently comparable.
    """

    periods = tuple(str(value) for value in period_ids)
    if not periods or len(periods) != len(set(periods)):
        raise ValueError("Comparison evidence requires unique non-empty period IDs")
    real = _finite_series(real_demand_mwh, "real demand")
    forecast = _finite_series(forecast_demand_mwh, "forecast demand")
    if len(real) != len(periods) or len(forecast) != len(periods):
        raise ValueError("Comparison demand evidence must align with period IDs")
    availability = {
        str(technology): _finite_series(values, f"{technology} availability")
        for technology, values in sorted(availability_mwh_by_technology.items())
    }
    if any(len(values) != len(periods) for values in availability.values()):
        raise ValueError("Comparison availability evidence must align with period IDs")
    identity_payload = {
        "year": int(year),
        "period_count": len(periods),
        "real_demand_mwh": real,
        "forecast_demand_mwh": forecast,
        "availability_mwh_by_technology": availability,
        **({"boundary_series_sha256": str(boundary_series_sha256)} if boundary_series_sha256 else {}),
        **({"data_method_id": str(data_method_id)} if data_method_id else {}),
    }
    return {
        "year": int(year),
        "period_count": len(periods),
        "period_ids_sha256": _canonical_sha256(periods),
        "chronology_matching_basis": (
            "ordered_period_position_with_period_ids_audited_separately"
        ),
        "real_demand_sha256": _canonical_sha256(real),
        "forecast_demand_sha256": _canonical_sha256(forecast),
        "availability_sha256": _canonical_sha256(availability),
        "real_demand_mwh": sum(real),
        "forecast_demand_mwh": sum(forecast),
        **({"boundary_series_sha256": str(boundary_series_sha256)} if boundary_series_sha256 else {}),
        **({"data_method_id": str(data_method_id)} if data_method_id else {}),
        "input_identity_sha256": _canonical_sha256(identity_payload),
    }


def build_comparison_eligibility(
    *,
    run_id: str,
    demand_authority_mode: str,
    fixed_inputs: Mapping[str, object],
    annual_input_evidence: Sequence[Mapping[str, object]],
    network_treatment: Mapping[str, object],
) -> dict[str, object]:
    if demand_authority_mode not in {
        COPPERPLATE_SCENARIO_DEMAND,
        SCENARIO_SCALED_ZONAL_SHARES,
        NETWORK_PACK_ABSOLUTE_DEMAND,
    }:
        raise ValueError(f"Unsupported comparison demand authority: {demand_authority_mode}")
    annual = [dict(row) for row in annual_input_evidence]
    matched_annual = [
        {
            "year": row.get("year"),
            "period_count": row.get("period_count"),
            "real_demand_sha256": row.get("real_demand_sha256"),
            "forecast_demand_sha256": row.get("forecast_demand_sha256"),
            "availability_sha256": row.get("availability_sha256"),
            "input_identity_sha256": row.get("input_identity_sha256"),
        }
        for row in annual
    ]
    matched_payload = {
        "fixed_inputs": dict(fixed_inputs),
        # Copperplate uses the model clock's local IDs while the signed network
        # overlay uses source-clock IDs.  Exact IDs remain visible in ``annual``
        # for audit; causal matching follows the explicitly declared ordered
        # period-position basis and therefore hashes physical vectors only.
        "annual_input_evidence": matched_annual,
    }
    absolute = demand_authority_mode == NETWORK_PACK_ABSOLUTE_DEMAND
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(run_id),
        "demand_authority_mode": demand_authority_mode,
        "network_cost_attribution_candidate": not absolute,
        "interpretation_label": (
            ABSOLUTE_MODE_LABEL
            if absolute
            else "Eligible for a controlled network comparison only when paired input identity matches."
        ),
        "matched_input_identity_sha256": _canonical_sha256(matched_payload),
        "fixed_inputs": dict(fixed_inputs),
        "annual_input_evidence": annual,
        "network_treatment": dict(network_treatment),
    }


def evaluate_network_comparison(
    artifacts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    modes = [str(row.get("demand_authority_mode") or "") for row in artifacts]
    identities = [str(row.get("matched_input_identity_sha256") or "") for row in artifacts]
    expected_modes = {COPPERPLATE_SCENARIO_DEMAND, SCENARIO_SCALED_ZONAL_SHARES}
    allowed = False
    if len(artifacts) != 2:
        reason = "requires_exactly_one_copperplate_and_one_zonal_run"
    elif set(modes) != expected_modes:
        reason = "incompatible_demand_authority_modes"
    elif not all(identities) or len(set(identities)) != 1:
        reason = "matched_input_identity_mismatch"
    else:
        treatments = [
            json.dumps(row.get("network_treatment") or {}, sort_keys=True)
            for row in artifacts
        ]
        if len(set(treatments)) != 2:
            reason = "network_treatment_does_not_differ"
        else:
            allowed = True
            reason = "matched_network_treatment_pair"
    return {
        "schema_version": PAIR_SCHEMA_VERSION,
        "network_cost_attribution_allowed": allowed,
        "reason_code": reason,
        "demand_authority_modes": modes,
        "matched_input_identity_sha256": identities[0] if allowed else None,
    }


def _canonical_copy(value: Mapping[str, object]) -> dict[str, object]:
    """Return JSON-safe comparison evidence without giving callers live state."""

    return json.loads(json.dumps(dict(value), sort_keys=True, ensure_ascii=False))


def _nested_string(
    artifact: Mapping[str, object],
    parent: str,
    key: str,
) -> str | None:
    container = artifact.get(parent)
    value = container.get(key) if isinstance(container, Mapping) else None
    return str(value) if isinstance(value, str) and value else None


def _matching_required_identity(
    artifacts: Sequence[Mapping[str, object]],
    *,
    getter,
    reason_code: str,
) -> str | None:
    values = [getter(artifact) for artifact in artifacts]
    if any(value is None for value in values) or len(set(values)) != 1:
        return reason_code
    return None


def evaluate_curtailment_comparison(
    *,
    network_pair: Mapping[str, object],
    attribution_artifacts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Gate VRE-curtailment deltas on identical reconciled run evidence.

    This does not discard the supplied evidence when the gate is closed.  The
    caller can consequently show each run's raw annual values side by side,
    while every difference remains deliberately undefined.
    """

    artifacts = tuple(_canonical_copy(artifact) for artifact in attribution_artifacts)
    reason_code: str | None = None
    if not 2 <= len(artifacts) <= 6:
        reason_code = "requires_two_to_six_attribution_artifacts"
    elif any(not artifact for artifact in artifacts):
        reason_code = "attribution_artifact_missing"
    elif not isinstance(network_pair, Mapping):
        reason_code = "network_pair_evidence_invalid"
    else:
        checks = (
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: (
                        str(row.get("schema_version"))
                        + "|"
                        + str(row.get("contract_version"))
                        if isinstance(row.get("schema_version"), str)
                        and isinstance(row.get("contract_version"), str)
                        else None
                    ),
                    reason_code="attribution_schema_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: row.get("attribution_method_id")
                    if isinstance(row.get("attribution_method_id"), str)
                    else None,
                    reason_code="attribution_method_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: row.get("data_pack_id")
                    if isinstance(row.get("data_pack_id"), str)
                    else None,
                    reason_code="data_pack_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: row.get("network_pack_id")
                    if isinstance(row.get("network_pack_id"), str)
                    else None,
                    reason_code="network_pack_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: _nested_string(
                        row,
                        "matched_counterfactual_proof",
                        "period_identity_set_sha256",
                    ),
                    reason_code="period_identity_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: row.get("counterfactual_realised_input_set_sha256")
                    if isinstance(row.get("counterfactual_realised_input_set_sha256"), str)
                    else None,
                    reason_code="realised_input_identity_mismatch",
                )
            ),
            (
                lambda: _matching_required_identity(
                    artifacts,
                    getter=lambda row: row.get("initial_state_sha256")
                    if isinstance(row.get("initial_state_sha256"), str)
                    else None,
                    reason_code="initial_state_mismatch",
                )
            ),
        )
        for check in checks:
            reason_code = check()
            if reason_code is not None:
                break
        if reason_code is None and any(
            artifact.get("capability_status") != "reconciled"
            for artifact in artifacts
        ):
            reason_code = "attribution_capability_not_reconciled"

    allowed = reason_code is None
    return {
        "schema_version": CURTAILMENT_PAIR_SCHEMA_VERSION,
        "metric_deltas_allowed": allowed,
        "reason_code": "matched_reconciled_vre_curtailment_evidence"
        if allowed
        else reason_code,
        "network_pair": _canonical_copy(network_pair),
        "side_by_side": list(artifacts),
    }


def write_comparison_eligibility(
    destination: Path, artifact: Mapping[str, object]
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(artifact), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_comparison_eligibility(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Comparison eligibility artifact has an unsupported schema")
    return payload
