"""National bid-at-cost ahead market with an injected balancing module."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ...methodology import methodology_scoped
from ... import agent_cashflow
from ...asset_economics import (
    CAPITAL_COST_COMPONENTS_KEY,
    capital_cost_components,
    primary_annual_asset_costs,
    validate_asset_economics,
)
from ...comparison_eligibility import build_psm_comparison_input_evidence
from ...market_ledger import (
    BoundaryPeriodLedgerRow,
    DispatchSummaryRow,
    MarketLedger,
    MarketPeriodBatch,
    NetworkSolverDiagnosticRow,
    NullMarketLedger,
    OrderLedgerRow,
    PeriodLedgerRow,
    PeriodIntegrity,
    PhysicalDispatchRow,
    RedispatchSummaryRow,
    RedispatchSettlementRow,
    SolverDeclarationLinkRow,
    StorageSummaryRow,
    StorageStateRow,
    VRECurtailmentDetailRow,
    VRECurtailmentPeriodRow,
    ZonalAccountingLedgerRow,
    ZonalDemandAlignmentLedgerRow,
    ZonalResourceDispatchRow,
    ZonePeriodLedgerRow,
    build_market_period_batch,
    create_staged_market_ledger_v8,
    market_ledger_boundary,
)
from ...module_context import (
    ImmutableContextResolver,
    RunContextRef,
    RunStaticContext,
    YearContext,
    YearContextRef,
    canonical_context_sha256,
)
from ...staged_market_contracts import (
    AcceptedAdjustment,
    AheadMarketInput,
    AheadMarketResult,
    BalancingInput,
    BalancingResult,
    FlexibilityBid,
    StagedMarketYearResult,
    ZonalRedispatchDomainV2,
    ZonalRedispatchPeriodSlice,
    contract_sha256,
)
from ...subannual_checkpoint import (
    RuntimeCheckpointBoundary,
    calendar_month_boundaries,
)
from ...zonal_demand_alignment import (
    SUPPORTED_ZONAL_DEMAND_MODES,
    ZonalDemandAlignment,
    align_zonal_demand,
)
from ...v2.contracts import (
    ArtifactReference,
    DispatchResource,
    MarketYearResult,
    PSMInput,
    PeriodSummary,
    StorageDispatchResource,
)
from ...zonal_contracts import ZonalNetworkPack
from ...zonal_results import (
    ZONAL_ACCOUNTING_SCHEMA_V2,
    build_reliability_events,
    build_solver_validation_summary,
    build_zonal_period_accounting,
)
from ...vre_curtailment_attribution import (
    ATTRIBUTION_METHOD_ID,
    ATTRIBUTION_SCHEMA,
    FAILURE_SCHEMA,
    CurtailmentAttributionError,
    VRECounterfactualRow,
    VRECounterfactualSnapshot,
    attribute_vre_curtailment,
    build_bid_tranche_id,
    canonical_vre_technology,
    failure_payload,
)
from ...zonal_solver_contract import SOLVER_CONTRACT_VERSION
from ... import network_method_rules
from .copperplate_balancing import CopperplateBalancing
from .psm_runtime_state import StagedPSMRuntimeState, StagedPeriodOutcome
from .runtime_compat.storage_cost import (
    restore_storage_cost_runtime,
    snapshot_storage_cost_runtime,
)


_REQUIRED_VRE_COUNTERFACTUAL_CASES = (
    "perfect_forecast_copperplate",
    "realised_copperplate",
    "zonal_final",
)

_LOCKED_SOLVER_PHASES = {
    "primary_bid_cost",
    "secondary_schedule_deviation",
    "physical_throughput",
}


def _record_period_batch_at_boundary(
    ledger: MarketLedger,
    batch: MarketPeriodBatch,
) -> PeriodIntegrity:
    """Commit one complete period; observation happens after runtime apply."""

    return ledger.record_period_batch(batch)


def _close_unsealed_ledger(ledger: MarketLedger) -> None:
    close_unsealed = getattr(ledger, "close_unsealed", None)
    if callable(close_unsealed):
        close_unsealed()


def _build_redispatch_summary_rows(
    *,
    year: int,
    period: int,
    bids: Sequence[FlexibilityBid],
    accepted_adjustments: Sequence[AcceptedAdjustment],
    ahead_resource_cost_gbp: float,
    blackout_resource_cost_gbp: float,
    zonal_resource_cost_gbp: float,
) -> tuple[RedispatchSummaryRow, ...]:
    """Aggregate accepted physical-cost deltas and reconcile final cost."""

    bid_by_id = {bid.bid_id: bid for bid in bids}
    totals: defaultdict[tuple[str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0]
    )
    for accepted in accepted_adjustments:
        bid_id = str(getattr(accepted, "bid_id"))
        try:
            bid = bid_by_id[bid_id]
        except KeyError as exc:
            raise ValueError(
                f"Accepted redispatch adjustment has no declared bid: {bid_id}"
            ) from exc
        signed_delta = float(getattr(accepted, "accepted_delta_mwh"))
        if (bid.direction == "up" and signed_delta < 0.0) or (
            bid.direction == "down" and signed_delta > 0.0
        ):
            raise ValueError(
                f"Accepted redispatch direction disagrees with bid {bid_id}"
            )
        key = (bid.zone_id, bid.technology, bid.direction)
        totals[key][0] += abs(signed_delta)
        totals[key][1] += signed_delta * bid.physical_cost_gbp_per_mwh
    rows = tuple(
        RedispatchSummaryRow(
            int(year),
            int(period),
            zone,
            technology,
            direction,
            values[0],
            values[1],
        )
        for (zone, technology, direction), values in sorted(totals.items())
    )
    reconstructed = math.fsum((
        float(ahead_resource_cost_gbp),
        float(blackout_resource_cost_gbp),
        *(row.resource_cost_gbp for row in rows),
    ))
    expected = float(zonal_resource_cost_gbp)
    if not math.isclose(reconstructed, expected, rel_tol=1e-10, abs_tol=1e-7):
        raise ValueError(
            "Redispatch physical resource cost does not reconcile to "
            f"zonal_period_accounting ({reconstructed} != {expected})"
        )
    return rows


def _network_solver_diagnostic_rows(
    result: BalancingResult,
    *,
    module_id: str,
    module_version: str,
) -> tuple[NetworkSolverDiagnosticRow, ...]:
    solver = dict(result.extensions.get("solver") or {})
    settings = dict(solver.get("solver_contract") or {})
    stack = dict(solver.get("solver_stack") or {})
    raw_rows = [
        dict(row)
        for row in result.extensions.get("network_solver_diagnostics") or ()
    ]
    phases = {str(row.get("phase_id") or "") for row in raw_rows}
    if len(raw_rows) != 3 or phases != _LOCKED_SOLVER_PHASES:
        raise ValueError(
            "Zonal balancing must emit one solver diagnostic for each locked phase"
        )
    method = str(settings.get("method") or "")
    ipm_tolerance = (
        None
        if method == "highs-ds"
        else float(settings["ipm_optimality_tolerance"])
    )
    return tuple(NetworkSolverDiagnosticRow(
        run_id=result.run_id,
        year=result.year,
        period=result.period,
        period_id=result.period_id,
        phase_id=str(row["phase_id"]),
        module_id=module_id,
        module_version=module_version,
        solver_contract_version=str(settings["contract_version"]),
        scipy_version=str(stack["scipy_version"]),
        highs_identity=str(stack["highs_identity"]),
        highs_binary_sha256=str(stack["highs_binary_sha256"]),
        method=method,
        presolve=settings["presolve"],
        primal_feasibility_tolerance=float(
            settings["primal_feasibility_tolerance"]
        ),
        dual_feasibility_tolerance=float(
            settings["dual_feasibility_tolerance"]
        ),
        ipm_optimality_tolerance=ipm_tolerance,
        objective_unit=str(row["objective_unit"]),
        optimum=float(row["optimum"]),
        achieved_final_value=float(row["achieved_final_value"]),
        degradation=float(row["degradation"]),
        computed_tolerance=float(row["computed_tolerance"]),
        warning_ceiling=(
            float(settings["warning_fraction"])
            * float(row["validated_ceiling"])
        ),
        validated_ceiling=float(row["validated_ceiling"]),
        absolute_ceiling=float(row["absolute_ceiling"]),
        nonzero_term_count=int(row["nonzero_terms"]),
        absolute_term_scale=float(row["absolute_term_scale"]),
        validation_class=str(row["validation_class"]),
        error_code=str(row["error_code"]) if row.get("error_code") else None,
        declared_input_sha256=result.source_input_sha256,
    ) for row in raw_rows)


def _period_value(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    return float(values[period] if period < len(values) else values[period % len(values)])


def _resource_class(resource: DispatchResource) -> str:
    if resource.resource_type == "vre":
        return "vre"
    if resource.resource_type == "import":
        return "import"
    if resource.resource_type == "hydro":
        return "hydro"
    return "thermal"


RUNTIME_FALLBACK_AUDIT_SCHEMA = "value.zonal-runtime-fallback-audit/v1"
# P0-8 OQ-7: above this share of a technology's capacity sitting in an
# unconstrained fallback zone, the zonal result is only spatially indicative.
SPATIALLY_INDICATIVE_FALLBACK_FRACTION = 0.10


def runtime_fallback_audit(
    *,
    year: int,
    fallback_zone_ids: Sequence[str],
    allocations: Sequence[Mapping[str, object]],
    threshold_fraction: float = SPATIALLY_INDICATIVE_FALLBACK_FRACTION,
) -> dict[str, object]:
    """Pure annual audit of capacity placed in unconstrained fallback zones.

    ``allocations`` holds one row per spatialised asset: ``asset_id``,
    ``technology``, ``capacity_mw``, ``shares`` ({zone: share}) and
    ``allocation_source`` (``frozen_zone_shares``, ``pack_mapping``,
    ``interconnector_landing`` or ``runtime_fallback`` - the last is an asset
    with no allocation at all that was placed in the single fallback zone).
    Totals are per technology; a technology whose fallback share exceeds
    ``threshold_fraction`` is flagged ``spatially_indicative`` (P2-13 / P1-14).
    The same inputs always give the same audit, so a resumed year reproduces it.
    """

    fallback = set(str(zone) for zone in fallback_zone_ids)
    by_technology: dict[str, dict[str, float]] = {}
    assets: list[dict[str, object]] = []
    for row in sorted(allocations, key=lambda item: str(item["asset_id"])):
        technology = str(row.get("technology") or "other")
        capacity = float(row.get("capacity_mw") or 0.0)
        shares = {str(zone): float(share) for zone, share in dict(row.get("shares") or {}).items()}
        fallback_share = math.fsum(share for zone, share in shares.items() if zone in fallback)
        totals = by_technology.setdefault(
            technology, {"capacity_mw": 0.0, "fallback_mw": 0.0, "runtime_unallocated_mw": 0.0}
        )
        totals["capacity_mw"] += capacity
        totals["fallback_mw"] += capacity * fallback_share
        if row.get("allocation_source") == "runtime_fallback":
            totals["runtime_unallocated_mw"] += capacity
        if fallback_share > 0:
            assets.append({
                "asset_id": str(row["asset_id"]),
                "technology": technology,
                "capacity_mw": capacity,
                "fallback_mw": capacity * fallback_share,
                "allocation_source": str(row.get("allocation_source") or ""),
            })
    technologies = []
    for technology in sorted(by_technology):
        totals = by_technology[technology]
        fraction = (
            totals["fallback_mw"] / totals["capacity_mw"] if totals["capacity_mw"] > 0 else 0.0
        )
        technologies.append({
            "technology": technology,
            "capacity_mw": totals["capacity_mw"],
            "fallback_mw": totals["fallback_mw"],
            "fallback_fraction": fraction,
            "runtime_unallocated_mw": totals["runtime_unallocated_mw"],
            "spatially_indicative": fraction > threshold_fraction,
        })
    return {
        "schema_version": RUNTIME_FALLBACK_AUDIT_SCHEMA,
        "year": int(year),
        "fallback_zone_ids": sorted(fallback),
        "threshold_fraction": float(threshold_fraction),
        "by_technology": technologies,
        "assets": assets,
        "spatially_indicative": any(row["spatially_indicative"] for row in technologies),
    }


AGENT_VARIABLE_COST_PREFIX = "agent_variable_cost_gbp::"



def _staged_agent_cashflow(
    module_id, generation, resources, base_by_asset, assets, *, variable_cost_gbp_by_asset=None,
) -> dict[str, object]:
    """``value.agent-cashflow/v1`` (P0-7, decision A4) from the staged dispatch.

    Since P0-8 S9 (C22) the running cost is the sum over periods of the
    dispatched MWh times that period's unit cost (the same table that prices
    the zonal and counterfactual cases), so an import with an hourly price is
    charged what it was paid in each period.  The row's unit cost is that sum
    divided by the generated MWh; an asset that generated nothing keeps its
    annual marginal cost when every zone split agrees, otherwise it gets no
    row (a thermal asset then fails closed in ``agent-investment``).
    """
    costs: dict[str, set[float]] = defaultdict(set)
    for resource in resources:
        costs[str(base_by_asset.get(resource.asset_id, resource.asset_id))].add(
            float(resource.marginal_cost_gbp_per_mwh))
    unit_cost = {asset_id: next(iter(values)) for asset_id, values in costs.items() if len(values) == 1}
    for asset_id, total in dict(variable_cost_gbp_by_asset or {}).items():
        generated = float(generation.get(asset_id, 0.0) or 0.0)
        if generated > 0.0:
            unit_cost[asset_id] = max(float(total) / generated, 0.0)
    technology = {asset.asset_id: asset.technology for asset in assets}
    basis = "staged_period_unit_cost_table"
    rows = agent_cashflow.unit_cost_cashflow(generation, unit_cost, technology, cost_basis=basis)
    return agent_cashflow.extension(rows, psm_module_id=module_id, cost_basis=basis)


def _owner_id(resource: object) -> str:
    extensions = dict(getattr(resource, "extensions", {}) or {})
    return str(
        extensions.get("investment_owner_id")
        or extensions.get("agent_id")
        or extensions.get("source_agent_id")
        or extensions.get("base_asset_id")
        or getattr(resource, "asset_id")
    )


def _base_asset_id(resource: object) -> str:
    return str(
        dict(getattr(resource, "extensions", {}) or {}).get("base_asset_id")
        or getattr(resource, "asset_id")
    )


def _canonical_live_vre_technology(raw: object) -> str | None:
    """Bridge the established live ``onshore``/``offshore`` aliases locally."""

    value = str(raw)
    canonical = canonical_vre_technology(value)
    if canonical is not None:
        return canonical
    normalised = " ".join(value.lower().replace("_", " ").replace("-", " ").split())
    if normalised == "onshore":
        return canonical_vre_technology("onshore wind")
    if normalised == "offshore":
        return canonical_vre_technology("offshore wind")
    return None


def _realised_case_input_sha256(
    model_input: BalancingInput,
    resource_cost_gbp_per_mwh_by_asset: Mapping[str, float],
) -> str:
    payload = {
        "period_id": model_input.period_id,
        "real_demand_mwh": float(model_input.real_demand_mwh),
        "realised_availability_mw_by_asset": dict(
            model_input.realised_availability_mw_by_asset
        ),
        "initial_soc_mwh_by_asset": dict(model_input.initial_soc_mwh_by_asset),
        "resource_cost_gbp_per_mwh_by_asset": {
            str(key): float(value)
            for key, value in resource_cost_gbp_per_mwh_by_asset.items()
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _with_declared_vre_zero_dispatch(
    ahead: AheadMarketResult,
    resources: Sequence[DispatchResource],
) -> AheadMarketResult:
    schedule = {
        str(asset_id): float(value)
        for asset_id, value in ahead.schedule_mwh_by_asset.items()
    }
    for resource in resources:
        if _canonical_live_vre_technology(resource.technology) is not None:
            schedule.setdefault(resource.asset_id, 0.0)
    return replace(ahead, schedule_mwh_by_asset=schedule)


def _vre_key_payload(keys: Sequence[tuple[str, str]] | set[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {"asset_id": asset_id, "bid_tranche_id": bid_tranche_id}
        for asset_id, bid_tranche_id in sorted(keys)
    ]


def _validate_vre_counterfactual_cases(
    *,
    expected_keys: set[tuple[str, str]],
    canonical_key_by_asset: Mapping[str, tuple[str, str]],
    dispatch_by_case: Mapping[str, Mapping[str, float]],
    realised_input_sha256_by_case: Mapping[str, str],
    module_identities: Mapping[str, str],
) -> str:
    """Prove raw set and realised-input equality before snapshot construction."""

    required_cases = set(_REQUIRED_VRE_COUNTERFACTUAL_CASES)
    case_inputs = {
        "dispatch_by_case": dispatch_by_case,
        "realised_input_sha256_by_case": realised_input_sha256_by_case,
        "module_identities": module_identities,
    }
    observed_case_names_by_input = {
        input_name: sorted(mapping)
        for input_name, mapping in case_inputs.items()
    }
    missing_case_names_by_input = {
        input_name: sorted(required_cases.difference(mapping))
        for input_name, mapping in case_inputs.items()
    }
    extra_case_names_by_input = {
        input_name: sorted(set(mapping).difference(required_cases))
        for input_name, mapping in case_inputs.items()
    }
    observed_keys_by_case = {
        case: {
            canonical_key_by_asset[asset_id]
            for asset_id in dispatch_by_case.get(case, {})
            if asset_id in canonical_key_by_asset
        }
        for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
    }
    missing_by_case = {
        case: expected_keys.difference(observed_keys_by_case[case])
        for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
    }
    extra_by_case = {
        case: observed_keys_by_case[case].difference(expected_keys)
        for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
    }
    hashes = {
        case: str(realised_input_sha256_by_case.get(case) or "")
        for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
    }
    identities = {
        case: str(module_identities.get(case) or "")
        for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
    }
    case_names_match = not any(missing_case_names_by_input.values()) and not any(
        extra_case_names_by_input.values()
    )
    sets_match = not any(missing_by_case.values()) and not any(extra_by_case.values())
    hashes_match = len(set(hashes.values())) == 1 and all(
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for value in hashes.values()
    )
    identities_complete = all(identities.values())
    if not (case_names_match and sets_match and hashes_match and identities_complete):
        evidence = {
            "required_case_names": list(_REQUIRED_VRE_COUNTERFACTUAL_CASES),
            "observed_case_names_by_input": observed_case_names_by_input,
            "missing_case_names_by_input": missing_case_names_by_input,
            "extra_case_names_by_input": extra_case_names_by_input,
            "canonical_vre_keys": _vre_key_payload(expected_keys),
            "observed_keys_by_case": {
                case: _vre_key_payload(observed_keys_by_case[case])
                for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
            },
            "missing_keys_by_case": {
                case: _vre_key_payload(missing_by_case[case])
                for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
            },
            "extra_keys_by_case": {
                case: _vre_key_payload(extra_by_case[case])
                for case in _REQUIRED_VRE_COUNTERFACTUAL_CASES
            },
            "realised_input_sha256_by_case": hashes,
            "module_identities": identities,
            "raw_reference_groups": [],
            "normalised_reference_groups": [],
            "residual_mwh": None,
            "tolerance_mwh": None,
        }
        raise CurtailmentAttributionError(
            "GF_VRE_COUNTERFACTUAL_SET_MISMATCH",
            "VRE counterfactual cases do not share one explicit object/tranche set, "
            "realised input identity and complete module identity",
            evidence,
        )
    return hashes[_REQUIRED_VRE_COUNTERFACTUAL_CASES[0]]


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _adapter_failure_payload(
    error: CurtailmentAttributionError,
    *,
    run_id: str,
    year: int,
    period: int,
    period_id: str,
    failure_input_sha256: str,
) -> dict[str, object]:
    evidence = dict(error.evidence)
    return {
        "schema": FAILURE_SCHEMA,
        "schema_version": FAILURE_SCHEMA,
        "error_code": error.code,
        "error_message": str(error),
        "run_id": run_id,
        "year": year,
        "period": period,
        "period_id": period_id,
        "realised_input_sha256": failure_input_sha256,
        "module_identities": dict(evidence.get("module_identities") or {}),
        "raw_snapshot": None,
        "raw_reference_groups": evidence.get("raw_reference_groups", []),
        "normalised_reference_groups": evidence.get(
            "normalised_reference_groups", []
        ),
        "residual_mwh": evidence.get("residual_mwh"),
        "tolerance_mwh": evidence.get("tolerance_mwh"),
        "raw_case_diagnostics": evidence,
        "attribution_schema": ATTRIBUTION_SCHEMA,
        "attribution_method_id": ATTRIBUTION_METHOD_ID,
    }


# P0-6 S10 (P5-15): how the staged PSM knows a stored MWh's dwell (it does not).
STAGED_DWELL_SOURCE = "not_tracked_staged_single_pool"


class StagedBidAtCostPSM:
    """Sequential forecast-only scheduling followed by realised balancing."""

    id = "force-staged-bid-at-cost-psm"
    version = "1.3.0"
    execution_kind = "live_module"

    def __init__(
        self,
        network_rules: network_method_rules.NetworkMethodRules | None = None,
    ) -> None:
        # P0-8 S7: the maintained economic rules; LEGACY only for internal tests.
        self._network_rules = network_rules or network_method_rules.ECONOMIC
        self._output_dir: Path | None = None
        self._storage_cost: object | None = None
        self._balancing: object | None = None
        self._network_pack: ZonalNetworkPack | None = None
        self._zonal_demand_mode = ""
        self._weather_spatializer_identity: tuple[str, str] | None = None
        self._ledger_detail = "summary"
        self._invocations: list[int] = []
        self._runtime_fallback_audits: dict[int, dict[str, object]] = {}
        self._run_context: RunStaticContext | None = None
        self._resolver: ImmutableContextResolver | None = None
        self._run_context_ref: RunContextRef | None = None
        self._year_context: YearContext | None = None
        self._year_context_ref: YearContextRef | None = None
        self._period_index_by_id: dict[str, int] = {}
        self._period_boundary_cancellation: Callable[[int, int], None] | None = None
        self._subannual_checkpoint_sink: Callable[
            [RuntimeCheckpointBoundary, Mapping[str, object], object], None
        ] | None = None
        self._restored_runtime_checkpoint: Mapping[str, object] | None = None
        self._active_runtime_state: StagedPSMRuntimeState | None = None
        self._active_chronology_sha256: str | None = None

    def configure_subannual_checkpoint_sink(
        self,
        sink: Callable[
            [RuntimeCheckpointBoundary, Mapping[str, object], object], None
        ] | None,
    ) -> None:
        if sink is not None and not callable(sink):
            raise TypeError("Subannual checkpoint sink must be callable")
        self._subannual_checkpoint_sink = sink

    def export_runtime_checkpoint(
        self, boundary: RuntimeCheckpointBoundary
    ) -> Mapping[str, object]:
        if not isinstance(boundary, RuntimeCheckpointBoundary):
            raise TypeError("boundary must be a RuntimeCheckpointBoundary")
        state = self._active_runtime_state
        if state is None or self._active_chronology_sha256 is None:
            raise RuntimeError("No staged PSM runtime state is active")
        if boundary.run_id != state.run_id or boundary.model_year != state.year:
            raise ValueError("Checkpoint boundary run/year does not match runtime state")
        if boundary.next_period_index != state.next_period_index:
            raise ValueError("Checkpoint boundary does not match the applied runtime state")
        if boundary.chronology_sha256 != self._active_chronology_sha256:
            raise ValueError("Checkpoint boundary chronology does not match runtime state")
        if self._run_context_ref is None or self._year_context_ref is None:
            raise RuntimeError("Subannual checkpoint export requires bound contexts")
        return {
            "schema_version": "value.staged-psm-runtime-checkpoint/v1",
            "run_id": state.run_id,
            "year": state.year,
            "chronology_sha256": self._active_chronology_sha256,
            "run_context_sha256": self._run_context_ref.sha256,
            "year_context_sha256": self._year_context_ref.sha256,
            "runtime_state": state.to_dict(),
        }

    def restore_runtime_checkpoint(
        self, checkpoint: Mapping[str, object]
    ) -> None:
        expected = {
            "schema_version",
            "run_id",
            "year",
            "chronology_sha256",
            "run_context_sha256",
            "year_context_sha256",
            "runtime_state",
        }
        if not isinstance(checkpoint, Mapping) or set(checkpoint) != expected:
            raise ValueError(
                f"Staged PSM runtime-checkpoint fields must be exactly {sorted(expected)}"
            )
        if checkpoint["schema_version"] != "value.staged-psm-runtime-checkpoint/v1":
            raise ValueError("Unsupported staged PSM runtime-checkpoint schema_version")
        runtime_payload = checkpoint["runtime_state"]
        if not isinstance(runtime_payload, Mapping):
            raise ValueError("runtime_state must be an object")
        state = StagedPSMRuntimeState.from_dict(runtime_payload)
        if checkpoint["run_id"] != state.run_id:
            raise ValueError("Checkpoint run identity disagrees with runtime state")
        if checkpoint["year"] != state.year:
            raise ValueError("Checkpoint year identity disagrees with runtime state")
        for field_name in (
            "chronology_sha256",
            "run_context_sha256",
            "year_context_sha256",
        ):
            value = checkpoint[field_name]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"Checkpoint {field_name} must be a lowercase SHA-256")
        self._restored_runtime_checkpoint = {
            **dict(checkpoint),
            "runtime_state": state.to_dict(),
        }

    def configure_period_boundary_cancellation(
        self, callback: Callable[[int, int], None] | None
    ) -> None:
        if callback is not None and not callable(callback):
            raise TypeError("Period-boundary cancellation callback must be callable")
        self._period_boundary_cancellation = callback

    def configure_run(
        self,
        *,
        output_dir: Path | None,
        storage_cost: object,
        balancing: object,
        expected_balancing_identity: tuple[str, str],
        network_pack: ZonalNetworkPack | None = None,
        zonal_demand_mode: str = "",
        weather_spatializer_identity: tuple[str, str] | None = None,
        ledger_detail: str = "summary",
    ) -> None:
        actual = (
            str(getattr(balancing, "id", "")),
            str(getattr(balancing, "version", "")),
        )
        if actual != tuple(expected_balancing_identity):
            raise ValueError(
                "Configured balancing identity does not match the resolved Study: "
                f"expected {expected_balancing_identity}, found {actual}"
            )
        if not callable(getattr(balancing, "clear", None)):
            raise TypeError("Configured balancing module does not expose clear")
        if not callable(getattr(storage_cost, "create", None)):
            raise TypeError("Configured storage-cost module does not expose create")
        self._output_dir = Path(output_dir).resolve() if output_dir is not None else None
        self._storage_cost = storage_cost
        self._balancing = balancing
        self._network_pack = network_pack
        self._weather_spatializer_identity = weather_spatializer_identity
        if ledger_detail not in {"off", "summary", "full"}:
            raise ValueError("Staged market ledger_detail must be off, summary or full")
        self._ledger_detail = ledger_detail
        configure_balancing = getattr(balancing, "configure_run", None)
        if callable(configure_balancing):
            configure_balancing(output_dir=self._output_dir)
        if actual[0] == "value-zonal-redispatch-balancing" and network_pack is None:
            raise ValueError("Zonal balancing requires one immutable zonal network pack")
        if network_pack is not None and zonal_demand_mode not in SUPPORTED_ZONAL_DEMAND_MODES:
            raise ValueError("Zonal balancing requires an explicit supported zonal demand mode")
        if network_pack is None and zonal_demand_mode:
            raise ValueError("A zonal demand mode cannot be used without a network pack")
        self._zonal_demand_mode = str(zonal_demand_mode)
        if network_pack is not None:
            self._period_index_by_id = {
                str(period_id): index
                for index, period_id in enumerate(network_pack.zonal_demand.period_ids)
            }

    def configure(
        self,
        run_context: RunStaticContext,
        resolver: ImmutableContextResolver,
    ) -> None:
        if not isinstance(run_context, RunStaticContext):
            raise ValueError("Staged PSM requires a RunStaticContext")
        if not isinstance(resolver, ImmutableContextResolver):
            raise ValueError("Staged PSM requires an ImmutableContextResolver")
        run_reference = RunContextRef(canonical_context_sha256(run_context))
        if resolver.resolve_run(run_reference) != run_context:
            raise ValueError("Staged PSM run context is not bound")
        if resolver.resolve_module("psm") is not self:
            raise ValueError("Staged PSM is not the exact bound PSM instance")
        if self._balancing is None or resolver.resolve_module("balancing") is not self._balancing:
            raise ValueError("Staged PSM balancing instance is not exactly bound")
        if self._network_pack is not None:
            if run_context.network_pack is None:
                raise ValueError("Zonal staged PSM requires a bound network pack")
            if contract_sha256(self._network_pack) != contract_sha256(
                run_context.to_dict()["network_pack"]
            ):
                raise ValueError("Configured network pack differs from the run context")
        elif run_context.network_pack is not None:
            raise ValueError("Copperplate staged PSM cannot bind a zonal network pack")
        self._run_context = run_context
        self._resolver = resolver
        self._run_context_ref = run_reference
        configure_balancing = getattr(self._balancing, "configure", None)
        if callable(configure_balancing):
            configure_balancing(run_context, resolver)

    def bind_resume_run_context(self, run_context_sha256: str) -> None:
        """Keep a verified historical ledger lineage across runtime-only upgrades."""

        if self._run_context is None or self._resolver is None:
            raise RuntimeError("Staged PSM must be configured before resume lineage")
        reference = RunContextRef(run_context_sha256)
        self._run_context_ref = reference
        bind_balancing = getattr(self._balancing, "bind_resume_run_context", None)
        if callable(bind_balancing):
            bind_balancing(run_context_sha256)

    def start_year(self, year_context: YearContext) -> None:
        if self._run_context is None or self._resolver is None:
            raise RuntimeError("Staged PSM must be configured before start_year")
        if year_context.run_id != self._run_context.run_id:
            raise ValueError("Year context run does not match the configured run")
        if self._run_context_ref is None:
            raise RuntimeError("Staged PSM run context reference is unavailable")
        if year_context.run_context_sha256 != self._run_context_ref.sha256:
            raise ValueError("Year context does not reference the configured run")
        reference = YearContextRef(
            year_context.year, canonical_context_sha256(year_context)
        )
        if self._resolver.resolve_year(reference) != year_context:
            raise ValueError("Staged PSM year context is not bound")
        self._year_context = year_context
        self._year_context_ref = reference
        start_balancing_year = getattr(self._balancing, "start_year", None)
        if callable(start_balancing_year):
            start_balancing_year(year_context)

    def prepare_year_context(
        self, model_input: PSMInput
    ) -> tuple[PSMInput, Mapping[str, object]]:
        """Spatialise once and expose only annual physical metadata to YearContext."""

        prepared, _bases, _owners, zones = self._spatialized_input(model_input)
        chronology = prepared.chronology
        if chronology is None:
            raise ValueError("Staged PSM requires chronological input")
        classes = {
            resource.asset_id: _resource_class(resource)
            for resource in chronology.resources
        }
        costs = {
            resource.asset_id: float(resource.marginal_cost_gbp_per_mwh)
            for resource in chronology.resources
        }
        storage: dict[str, dict[str, object]] = {}
        opening_soc: dict[str, float] = {}
        for resource in chronology.storage:
            classes[resource.asset_id] = "storage"
            costs[resource.asset_id] = float(
                resource.variable_degradation_gbp_per_mwh_discharged
            )
            opening_soc[resource.asset_id] = float(resource.initial_soc_mwh)
            storage[resource.asset_id] = {
                "charge_power_mw": resource.charge_power_mw,
                "discharge_power_mw": resource.discharge_power_mw,
                "energy_capacity_mwh": resource.energy_capacity_mwh,
                "charge_efficiency": resource.charge_efficiency,
                "discharge_efficiency": resource.discharge_efficiency,
                "bid_contract": "convex_net_power_v1",
            }
        for asset_id in dict(
            chronology.extensions.get("boundary_export_envelope_mwh_by_asset") or {}
        ):
            shares = self._zone_shares(str(asset_id), {})
            if len(shares) != 1:
                raise ValueError(f"Boundary export {asset_id} must have one landing zone")
            zones[str(asset_id)] = next(iter(shares))
            classes[str(asset_id)] = "export"
        metadata: Mapping[str, object] = {
            "asset_zone_id_by_asset": dict(sorted(zones.items())),
            "resource_class_by_asset": dict(sorted(classes.items())),
            "resource_cost_gbp_per_mwh_by_asset": dict(sorted(costs.items())),
            "storage": storage,
            "frozen_zone_shares": {
                asset_id: {zone_id: 1.0}
                for asset_id, zone_id in sorted(zones.items())
            },
            "opening_soc_mwh_by_asset": opening_soc,
        }
        return (
            replace(
                prepared,
                extensions={
                    **dict(prepared.extensions),
                    "value_context_prepared": True,
                },
            ),
            metadata,
        )

    def _zone_shares(self, asset_id: str, extensions: Mapping[str, object]) -> dict[str, float]:
        return self._zone_shares_with_source(asset_id, extensions)[0]

    def _zone_shares_with_source(
        self, asset_id: str, extensions: Mapping[str, object]
    ) -> tuple[dict[str, float], str]:
        if self._network_pack is None:
            return {"GB": 1.0}, "copperplate"
        raw = extensions.get("frozen_zone_shares")
        source = "frozen_zone_shares"
        if isinstance(raw, Mapping):
            shares = {str(key): float(value) for key, value in raw.items()}
        else:
            source = "pack_mapping"
            shares = {
                row.zone_id: float(row.share)
                for row in self._network_pack.asset_mappings
                if row.asset_id == asset_id
            }
        if not shares:
            landing = next(
                (
                    row for row in self._network_pack.interconnector_landings
                    if row.asset_id == asset_id
                ),
                None,
            )
            if landing is not None:
                shares = {landing.zone_id: 1.0}
                source = "interconnector_landing"
        if not shares:
            fallback = [
                zone.zone_id for zone in self._network_pack.zones
                if zone.is_unconstrained_fallback
            ]
            if len(fallback) == 1:
                # Still placed in the fallback zone (behaviour unchanged), but
                # no longer silently: runtime_fallback_audit reports it.
                shares = {fallback[0]: 1.0}
                source = "runtime_fallback"
        total = sum(shares.values())
        if total <= 0 or abs(total - 1.0) > 1e-8:
            raise ValueError(f"Asset {asset_id} lacks one reconciled frozen zonal allocation")
        known = {zone.zone_id for zone in self._network_pack.zones}
        if not set(shares).issubset(known):
            raise ValueError(f"Asset {asset_id} has an allocation outside the network pack")
        return dict(sorted(shares.items())), source

    def _spatialized_input(
        self, model_input: PSMInput
    ) -> tuple[PSMInput, dict[str, str], dict[str, str], dict[str, str]]:
        """Create physical tranches while retaining one economic owner per asset."""

        chronology = model_input.chronology
        assert chronology is not None
        if self._network_pack is None:
            bases = {
                row.asset_id: _base_asset_id(row)
                for row in (*chronology.resources, *chronology.storage)
            }
            owners = {
                row.asset_id: _owner_id(row)
                for row in (*chronology.resources, *chronology.storage)
            }
            return model_input, bases, owners, {key: "GB" for key in bases}

        bases: dict[str, str] = {}
        owners: dict[str, str] = {}
        zones: dict[str, str] = {}
        resources: list[DispatchResource] = []
        storage: list[StorageDispatchResource] = []
        allocations: list[dict[str, object]] = []
        for resource in chronology.resources:
            shares, source = self._zone_shares_with_source(resource.asset_id, resource.extensions)
            allocations.append({
                "asset_id": resource.asset_id, "technology": resource.technology,
                "capacity_mw": resource.capacity_mw, "shares": shares,
                "allocation_source": source,
            })
            for zone_id, share in shares.items():
                tranche_id = (
                    resource.asset_id
                    if len(shares) == 1
                    else f"{resource.asset_id}::zone::{zone_id}"
                )
                owner = _owner_id(resource)
                base = _base_asset_id(resource)
                extensions = {
                    **dict(resource.extensions),
                    "base_asset_id": base,
                    "agent_id": owner,
                    "investment_owner_id": owner,
                    "zone_id": zone_id,
                    "zone_share": share,
                    "physical_tranche_only": True,
                }
                resources.append(replace(
                    resource,
                    asset_id=tranche_id,
                    capacity_mw=resource.capacity_mw * share,
                    extensions=extensions,
                ))
                bases[tranche_id], owners[tranche_id], zones[tranche_id] = base, owner, zone_id
        for resource in chronology.storage:
            shares, source = self._zone_shares_with_source(resource.asset_id, resource.extensions)
            allocations.append({
                "asset_id": resource.asset_id, "technology": resource.technology,
                "capacity_mw": resource.discharge_power_mw, "shares": shares,
                "allocation_source": source,
            })
            for zone_id, share in shares.items():
                tranche_id = (
                    resource.asset_id
                    if len(shares) == 1
                    else f"{resource.asset_id}::zone::{zone_id}"
                )
                owner = _owner_id(resource)
                base = _base_asset_id(resource)
                extensions = {
                    **dict(resource.extensions),
                    "base_asset_id": base,
                    "agent_id": owner,
                    "investment_owner_id": owner,
                    "zone_id": zone_id,
                    "zone_share": share,
                    "physical_tranche_only": True,
                }
                storage.append(replace(
                    resource,
                    asset_id=tranche_id,
                    charge_power_mw=resource.charge_power_mw * share,
                    discharge_power_mw=resource.discharge_power_mw * share,
                    energy_capacity_mwh=resource.energy_capacity_mwh * share,
                    initial_soc_mwh=resource.initial_soc_mwh * share,
                    extensions=extensions,
                ))
                bases[tranche_id], owners[tranche_id], zones[tranche_id] = base, owner, zone_id
        self._runtime_fallback_audits[int(model_input.year)] = runtime_fallback_audit(
            year=int(model_input.year),
            fallback_zone_ids=[
                zone.zone_id for zone in self._network_pack.zones
                if zone.is_unconstrained_fallback
            ],
            allocations=allocations,
        )
        zonal_chronology = replace(
            chronology,
            resources=tuple(resources),
            storage=tuple(storage),
            extensions={
                **dict(chronology.extensions),
                "network_pack_id": self._network_pack.network_pack_id,
                "network_pack_scientific_sha256": self._network_pack.scientific_sha256,
            },
        )
        return replace(model_input, chronology=zonal_chronology), bases, owners, zones

    @staticmethod
    def clear_ahead(model_input: AheadMarketInput) -> AheadMarketResult:
        offers = sorted(
            (dict(offer) for offer in model_input.offers),
            key=lambda offer: (
                float(offer["price_gbp_per_mwh"]),
                str(offer["offer_id"]),
            ),
        )
        remaining = float(model_input.forecast_demand_mwh)
        schedule: defaultdict[str, float] = defaultdict(float)
        storage_actions: defaultdict[str, float] = defaultdict(float)
        clearing_price = 0.0
        for offer in offers:
            if remaining <= 1e-12:
                break
            available = max(float(offer["available_mwh"]), 0.0)
            accepted = min(remaining, available)
            if accepted <= 1e-12:
                continue
            asset_id = str(offer["asset_id"])
            schedule[asset_id] += accepted
            if str(offer.get("resource_kind")) == "storage_discharge":
                storage_actions[asset_id] += accepted
            clearing_price = float(offer["price_gbp_per_mwh"])
            remaining -= accepted
        accepted_volume = sum(schedule.values())
        return AheadMarketResult(
            run_id=model_input.run_id,
            year=model_input.year,
            period=model_input.period,
            period_id=model_input.period_id,
            information_scope="forecast_only",
            schedule_mwh_by_asset=dict(schedule),
            clearing_price_gbp_per_mwh=clearing_price,
            accepted_volume_mwh=accepted_volume,
            settlement_mwh_by_asset=dict(schedule),
            storage_scheduled_action_mwh_by_asset=dict(storage_actions),
            source_input_sha256=contract_sha256(model_input),
            extensions={
                "unserved_forecast_mwh": max(remaining, 0.0),
                "pricing_rule": "pay_as_clear",
                "tie_break": "price_then_offer_id",
            },
        )

    @staticmethod
    def _asset_capex(model_input: PSMInput, asset_id: str) -> float:
        resource = next(
            (
                row for row in (model_input.chronology.storage if model_input.chronology else ())
                if row.asset_id == asset_id
            ),
            None,
        )
        if resource is not None:
            base_id = _base_asset_id(resource)
            share = float(resource.extensions.get("zone_share", 1.0) or 1.0)
        else:
            base_id, share = asset_id, 1.0
        for asset in model_input.operating_state.assets:
            if asset.asset_id == base_id:
                return float(asset.extensions.get("total_capex_gbp", 0.0) or 0.0) * share
        return 0.0

    def _storage_models(
        self, model_input: PSMInput
    ) -> tuple[dict[str, object], dict[str, float]]:
        assert model_input.chronology is not None
        assert self._storage_cost is not None
        observations = dict(
            model_input.operating_state.extensions.get("storage_cost_observations") or {}
        )
        models: dict[str, object] = {}
        soc: dict[str, float] = {}
        for resource in model_input.chronology.storage:
            cost = self._storage_cost.create(
                battery_type=resource.technology,
                period_hours=model_input.period_hours,
                legacy_storage_fee=float(
                    resource.extensions.get("legacy_storage_fee", 0.0) or 0.0
                ),
                legacy_holding_fee=float(
                    resource.extensions.get("legacy_holding_fee", 0.0) or 0.0
                ),
            )
            previous = getattr(cost, "previous", None)
            base_id = _base_asset_id(resource)
            share = float(resource.extensions.get("zone_share", 1.0) or 1.0)
            row = dict(observations.get(base_id) or observations.get(resource.asset_id) or {})
            if previous is not None and row:
                previous.year = row.get("prepared_year")
                previous.sold_energy_mwh = float(
                    row.get("current_year_sold_mwh", 0.0) or 0.0
                ) * share
                previous.dwell_weighted_sold_mwh_periods = (
                    previous.sold_energy_mwh
                    * float(row.get("current_year_average_dwell_periods", 0.0) or 0.0)
                )
            cost.prepare_year(
                model_input.year,
                capital_cost_gbp=self._asset_capex(model_input, resource.asset_id),
                power_capacity_mw=resource.discharge_power_mw,
                energy_capacity_mwh=resource.energy_capacity_mwh,
                discharge_efficiency=resource.discharge_efficiency,
            )
            models[resource.asset_id] = cost
            soc[resource.asset_id] = float(resource.initial_soc_mwh)
        return models, soc

    @staticmethod
    def _ahead_offers(
        model_input: PSMInput,
        period: int,
        soc: Mapping[str, float],
        storage_models: Mapping[str, object],
    ) -> tuple[dict[str, object], ...]:
        assert model_input.chronology is not None
        multiplier = float(model_input.parameters.get("market.bid_multiplier", 1.0))
        offers: list[dict[str, object]] = []
        for resource in model_input.chronology.resources:
            availability = max(_period_value(resource.availability, period), 0.0)
            available_mwh = resource.capacity_mw * availability * model_input.period_hours
            if available_mwh <= 1e-12:
                continue
            physical_cost = (
                _period_value(resource.marginal_cost_profile_gbp_per_mwh, period)
                if resource.marginal_cost_profile_gbp_per_mwh
                else resource.marginal_cost_gbp_per_mwh
            )
            marginal_cost = physical_cost * multiplier
            offers.append({
                "offer_id": f"ahead:{model_input.year}:{period}:resource:{resource.asset_id}",
                "agent_id": str(resource.extensions.get("agent_id") or resource.asset_id),
                "asset_id": resource.asset_id,
                "technology": resource.technology,
                "resource_kind": resource.resource_type,
                "available_mw": resource.capacity_mw * availability,
                "available_mwh": available_mwh,
                "price_gbp_per_mwh": marginal_cost,
                "physical_cost_gbp_per_mwh": physical_cost,
                "zone_id": str(resource.extensions.get("zone_id") or "GB"),
            })
        for resource in model_input.chronology.storage:
            available_mwh = min(
                resource.discharge_power_mw * model_input.period_hours,
                soc[resource.asset_id] * resource.discharge_efficiency,
            )
            if available_mwh <= 1e-12:
                continue
            cost = storage_models[resource.asset_id]
            bid_price = float(cost.bid_price_gbp_per_mwh(0.0)) * multiplier
            offers.append({
                "offer_id": f"ahead:{model_input.year}:{period}:storage:{resource.asset_id}",
                "agent_id": _owner_id(resource),
                "asset_id": resource.asset_id,
                "technology": resource.technology,
                "resource_kind": "storage_discharge",
                "available_mw": available_mwh / model_input.period_hours,
                "available_mwh": available_mwh,
                "price_gbp_per_mwh": bid_price,
                "physical_cost_gbp_per_mwh": (
                    resource.variable_degradation_gbp_per_mwh_discharged
                ),
                "zone_id": str(resource.extensions.get("zone_id") or "GB"),
            })
        return tuple(offers)

    def _flexibility_bids(
        self,
        model_input: PSMInput,
        period: int,
        ahead: AheadMarketResult,
        soc: Mapping[str, float],
        storage_models: Mapping[str, object],
    ) -> tuple[FlexibilityBid, ...]:
        """Balancing bids of one period (P0-8 S7 economic dec pricing).

        BM convention: an up bid is paid MWh x price, a down (dec) bid pays
        MWh x price back, and the balancer accepts the highest dec first.  Dec
        prices follow :mod:`gridform_core.network_method_rules`: a fuel unit
        returns its avoided running cost, an import its period price, VRE and
        run-of-river hydro lose their support, nuclear also carries the
        inflexibility premium, and storage bids at most min(own up x round-trip
        efficiency, the period's lowest inc price).  A dec'd thermal unit
        therefore keeps no windfall (review P2-05).
        """

        assert model_input.chronology is not None
        rules = self._network_rules
        period_id = str(model_input.chronology.period_ids[period])
        multiplier = float(model_input.parameters.get("market.bid_multiplier", 1.0))
        pricing = network_method_rules.dec_pricing_inputs(model_input.parameters)
        bids: list[FlexibilityBid] = []
        for resource in model_input.chronology.resources:
            available_mw = resource.capacity_mw * max(
                _period_value(resource.availability, period), 0.0
            )
            available_mwh = available_mw * model_input.period_hours
            scheduled = float(ahead.schedule_mwh_by_asset.get(resource.asset_id, 0.0))
            marginal = (
                _period_value(resource.marginal_cost_profile_gbp_per_mwh, period)
                if resource.marginal_cost_profile_gbp_per_mwh
                else resource.marginal_cost_gbp_per_mwh
            )
            agent_id = str(resource.extensions.get("agent_id") or resource.asset_id)
            zone_id = str(resource.extensions.get("zone_id") or "GB")
            resource_class = _resource_class(resource)
            up_mwh = max(available_mwh - scheduled, 0.0)
            if up_mwh > 1e-12:
                bids.append(FlexibilityBid(
                    f"balance:{model_input.year}:{period}:up:{resource.asset_id}",
                    agent_id,
                    resource.asset_id,
                    resource.technology,
                    zone_id,
                    period_id,
                    "up",
                    up_mwh / model_input.period_hours,
                    marginal * multiplier,
                    scheduled / model_input.period_hours,
                    marginal,
                    f"{zone_id}:injection",
                    {"resource_class": resource_class, "priority": 0},
                    extensions={"available_mwh": up_mwh},
                ))
            if scheduled > 1e-12:
                curtailment_class = "balancing_added_vre" if resource_class == "vre" else ""
                dec_price = network_method_rules.resource_dec_price(
                    rules,
                    resource_class=resource_class,
                    technology=resource.technology,
                    marginal_cost_gbp_per_mwh=marginal,
                    inputs=pricing,
                    legacy_curtailment_cost_gbp_per_mwh=float(
                        resource.extensions.get("curtailment_cost_gbp_per_mwh", 0.0) or 0.0
                    ),
                )
                bids.append(FlexibilityBid(
                    f"balance:{model_input.year}:{period}:down:{resource.asset_id}",
                    agent_id,
                    resource.asset_id,
                    resource.technology,
                    zone_id,
                    period_id,
                    "down",
                    scheduled / model_input.period_hours,
                    dec_price,
                    scheduled / model_input.period_hours,
                    marginal,
                    f"{zone_id}:injection",
                    {
                        "resource_class": resource_class,
                        "curtailment_class": curtailment_class,
                        "dec_class": network_method_rules.dec_class(
                            resource_class, resource.technology
                        ),
                    },
                    extensions={"available_mwh": scheduled},
                ))
        storage_rows: list[tuple[object, str, str, float, float]] = []
        for resource in model_input.chronology.storage:
            owner_id = _owner_id(resource)
            zone_id = str(resource.extensions.get("zone_id") or "GB")
            scheduled = float(ahead.schedule_mwh_by_asset.get(resource.asset_id, 0.0))
            maximum_discharge = min(
                resource.discharge_power_mw * model_input.period_hours,
                soc[resource.asset_id] * resource.discharge_efficiency,
            )
            up_mwh = max(maximum_discharge - scheduled, 0.0)
            price = float(storage_models[resource.asset_id].bid_price_gbp_per_mwh(0.0))
            storage_rows.append((resource, owner_id, zone_id, scheduled, price * multiplier))
            if up_mwh > 1e-12:
                bids.append(FlexibilityBid(
                    f"balance:{model_input.year}:{period}:up-storage:{resource.asset_id}",
                    owner_id,
                    resource.asset_id,
                    resource.technology,
                    zone_id,
                    period_id,
                    "up",
                    up_mwh / model_input.period_hours,
                    price * multiplier,
                    scheduled / model_input.period_hours,
                    resource.variable_degradation_gbp_per_mwh_discharged,
                    f"{zone_id}:injection",
                    {"resource_class": "storage", "priority": 0},
                    extensions={"available_mwh": up_mwh},
                ))
        up_prices = [bid.price_gbp_per_mwh for bid in bids if bid.direction == "up"]
        lowest_inc = min(up_prices) if up_prices else None
        for resource, owner_id, zone_id, scheduled, up_price in storage_rows:
            down_mwh = scheduled + min(
                resource.charge_power_mw * model_input.period_hours,
                max(resource.energy_capacity_mwh - soc[resource.asset_id], 0.0)
                / max(resource.charge_efficiency, 1e-12),
            )
            if down_mwh > 1e-12:
                bids.append(FlexibilityBid(
                    f"balance:{model_input.year}:{period}:down-storage:{resource.asset_id}",
                    owner_id,
                    resource.asset_id,
                    resource.technology,
                    zone_id,
                    period_id,
                    "down",
                    down_mwh / model_input.period_hours,
                    network_method_rules.storage_dec_price(
                        rules,
                        up_price_gbp_per_mwh=up_price,
                        charge_efficiency=resource.charge_efficiency,
                        discharge_efficiency=resource.discharge_efficiency,
                        lowest_inc_price_gbp_per_mwh=lowest_inc,
                    ),
                    scheduled / model_input.period_hours,
                    resource.variable_degradation_gbp_per_mwh_discharged,
                    f"{zone_id}:withdrawal",
                    {"resource_class": "storage", "priority": 0},
                    extensions={"available_mwh": down_mwh},
                ))
        export_envelopes = dict(
            model_input.chronology.extensions.get(
                "boundary_export_envelope_mwh_by_asset"
            )
            or {}
        )
        export_prices = dict(
            model_input.chronology.extensions.get(
                "boundary_export_price_gbp_per_mwh_by_asset"
            )
            or {}
        )
        for asset_id, raw_envelope in sorted(export_envelopes.items()):
            envelope_mwh = max(_period_value(tuple(raw_envelope), period), 0.0)
            if envelope_mwh <= 1e-12:
                continue
            raw_prices = tuple(export_prices.get(asset_id) or ())
            price = max(_period_value(raw_prices, period), 0.0)
            country = str(asset_id).split(":", 1)[-1]
            shares = self._zone_shares(str(asset_id), {})
            if len(shares) != 1:
                raise ValueError(f"Boundary export {asset_id} must have one landing zone")
            zone_id = next(iter(shares))
            bids.append(FlexibilityBid(
                f"balance:{model_input.year}:{period}:down-export:{asset_id}",
                f"interconnector:{country}",
                str(asset_id),
                "interconnector_export",
                zone_id,
                period_id,
                "down",
                envelope_mwh / model_input.period_hours,
                price,
                0.0,
                0.0,
                f"{zone_id}:withdrawal",
                {"resource_class": "export", "priority": 1},
                extensions={"available_mwh": envelope_mwh},
            ))
        return tuple(bids)

    @methodology_scoped
    def run(self, model_input: PSMInput) -> MarketYearResult:
        if self._storage_cost is None or self._balancing is None:
            raise RuntimeError("Staged PSM was not configured from the resolved module graph")
        if bool(model_input.extensions.get("value_context_prepared")):
            chronology = model_input.chronology
            if chronology is None:
                raise ValueError("Staged PSM requires chronological input")
            rows = (*chronology.resources, *chronology.storage)
            base_by_asset = {row.asset_id: _base_asset_id(row) for row in rows}
            owner_by_asset = {row.asset_id: _owner_id(row) for row in rows}
            zone_by_asset = {
                row.asset_id: str(row.extensions.get("zone_id") or "GB")
                for row in rows
            }
        else:
            model_input, base_by_asset, owner_by_asset, zone_by_asset = self._spatialized_input(
                model_input
            )
        chronology = model_input.chronology
        if chronology is None:
            raise ValueError("Staged PSM requires chronological input")
        forecast = tuple(
            float(value)
            for value in chronology.extensions.get("forecast_demand_mwh", ())
        )
        if len(forecast) != len(chronology.period_ids):
            raise ValueError("Staged PSM requires one declared forecast demand per period")
        if len(chronology.demand_mwh) != len(chronology.period_ids):
            raise ValueError("Staged PSM requires one realised demand per period")
        demand_alignment: ZonalDemandAlignment | None = None
        if self._network_pack is not None:
            demand_alignment = align_zonal_demand(
                mode=self._zonal_demand_mode,
                period_ids=chronology.period_ids,
                research_real_mwh=chronology.demand_mwh,
                research_forecast_mwh=forecast,
                network_demand=self._network_pack.zonal_demand,
            )
            chronology = replace(
                chronology,
                demand_mwh=demand_alignment.real_demand_mwh,
                extensions={
                    **dict(chronology.extensions),
                    "forecast_demand_mwh": demand_alignment.forecast_demand_mwh,
                },
            )
            model_input = replace(model_input, chronology=chronology)
            forecast = demand_alignment.forecast_demand_mwh

        availability_by_technology: defaultdict[str, list[float]] = defaultdict(
            lambda: [0.0] * len(chronology.period_ids)
        )
        for resource in chronology.resources:
            for period in range(len(chronology.period_ids)):
                availability_by_technology[resource.technology][period] += (
                    float(resource.capacity_mw)
                    * max(_period_value(resource.availability, period), 0.0)
                    * float(model_input.period_hours)
                )
        comparison_input_evidence = build_psm_comparison_input_evidence(
            year=model_input.year,
            period_ids=chronology.period_ids,
            real_demand_mwh=chronology.demand_mwh,
            forecast_demand_mwh=forecast,
            availability_mwh_by_technology=availability_by_technology,
            boundary_series_sha256=dict(chronology.extensions.get("boundary_raw_series") or {}).get(
                "boundary_series_sha256"),
            data_method_id=dict(dict(chronology.extensions.get("data_method") or {}).get("method_ids") or {}).get(
                "data_method"),
        )

        storage_models, soc = self._storage_models(model_input)
        if self._network_pack is not None:
            if (
                self._run_context_ref is None
                or self._year_context_ref is None
                or self._year_context is None
            ):
                raise RuntimeError("Zonal staged PSM requires bound run and year contexts")
            if self._year_context.year != model_input.year:
                raise ValueError("PSM input year does not match the active year context")
            annual = self._year_context.operating_state
            resource_cost = {
                str(asset): float(value)
                for asset, value in dict(
                    annual.get("resource_cost_gbp_per_mwh_by_asset") or {}
                ).items()
            }
            resource_class = {
                str(asset): str(value)
                for asset, value in dict(
                    annual.get("resource_class_by_asset") or {}
                ).items()
            }
            annual_zones = {
                str(asset): str(value)
                for asset, value in dict(
                    annual.get("asset_zone_id_by_asset") or {}
                ).items()
            }
            if annual_zones:
                zone_by_asset = annual_zones
        else:
            resource_cost = {
                resource.asset_id: float(resource.marginal_cost_gbp_per_mwh)
                for resource in chronology.resources
            }
            resource_class = {
                resource.asset_id: _resource_class(resource)
                for resource in chronology.resources
            }
        storage_by_id = {resource.asset_id: resource for resource in chronology.storage}
        if self._network_pack is None:
            for resource in chronology.storage:
                resource_cost[resource.asset_id] = (
                    resource.variable_degradation_gbp_per_mwh_discharged
                )
                resource_class[resource.asset_id] = "storage"

        chronology_sha256 = contract_sha256({
            "period_ids": tuple(chronology.period_ids),
            "period_hours": float(model_input.period_hours),
            "model_year": model_input.year,
        })
        solver_contract_defaults: Mapping[str, object] = {}
        if self._run_context is not None:
            configured_defaults = self._run_context.solver_contract.get("defaults")
            if isinstance(configured_defaults, Mapping):
                solver_contract_defaults = configured_defaults
        # C22: the maintained balancing identity comes from the module class,
        # so a version bump cannot silently disable subannual restore.
        from ...zonal_redispatch import COUNTERFACTUAL_ENGINE, ZonalRedispatchBalancing

        maintained_zonal_runtime = (
            self._network_pack is not None
            and (
                str(getattr(self._balancing, "id", "")),
                str(getattr(self._balancing, "version", "")),
            )
            == (ZonalRedispatchBalancing.id, ZonalRedispatchBalancing.version)
            and self._run_context is not None
            and str(
                self._run_context.solver_contract.get("contract_version")
                or solver_contract_defaults.get("contract_version")
                or ""
            )
            == SOLVER_CONTRACT_VERSION
        )
        if self._restored_runtime_checkpoint is not None and not maintained_zonal_runtime:
            raise ValueError(
                "Subannual restore requires the maintained zonal v2 solver chain"
            )

        runtime_state: StagedPSMRuntimeState | None = None
        if maintained_zonal_runtime:
            export_balancing_state = getattr(
                self._balancing, "export_runtime_state", None
            )
            restore_balancing_state = getattr(
                self._balancing, "restore_runtime_state", None
            )
            if not callable(export_balancing_state) or not callable(
                restore_balancing_state
            ):
                raise TypeError(
                    "Maintained zonal balancing must expose runtime-state hooks"
                )
            if self._restored_runtime_checkpoint is None:
                runtime_state = StagedPSMRuntimeState.initial(
                    run_id=model_input.run_id,
                    year=model_input.year,
                    soc_mwh_by_asset=soc,
                    storage_cost_state_by_asset={
                        asset_id: snapshot_storage_cost_runtime(model)
                        for asset_id, model in storage_models.items()
                    },
                    balancing_state=export_balancing_state(),
                )
            else:
                checkpoint = self._restored_runtime_checkpoint
                if checkpoint["run_id"] != model_input.run_id:
                    raise ValueError("Checkpoint run does not match the PSM input run")
                if checkpoint["year"] != model_input.year:
                    raise ValueError("Checkpoint year does not match the PSM input year")
                if checkpoint["chronology_sha256"] != chronology_sha256:
                    raise ValueError("Checkpoint chronology does not match the PSM input")
                if self._run_context_ref is None or self._year_context_ref is None:
                    raise RuntimeError("Subannual restore requires bound contexts")
                if checkpoint["run_context_sha256"] != self._run_context_ref.sha256:
                    raise ValueError("Checkpoint run context does not match")
                if checkpoint["year_context_sha256"] != self._year_context_ref.sha256:
                    raise ValueError("Checkpoint year context does not match")
                raw_runtime_state = checkpoint["runtime_state"]
                if not isinstance(raw_runtime_state, Mapping):
                    raise ValueError("Checkpoint runtime_state must be an object")
                runtime_state = StagedPSMRuntimeState.from_dict(raw_runtime_state)
                if runtime_state.next_period_index > len(chronology.period_ids):
                    raise ValueError(
                        "Checkpoint next_period_index is outside the chronology"
                    )
                completed_period_ids = tuple(
                    str(row["period_id"]) for row in runtime_state.summaries
                )
                expected_period_ids = tuple(
                    str(value)
                    for value in chronology.period_ids[: runtime_state.next_period_index]
                )
                if completed_period_ids != expected_period_ids:
                    raise ValueError(
                        "Checkpoint completed periods do not match the chronology"
                    )
                if set(runtime_state.soc_mwh_by_asset) != set(storage_models):
                    raise ValueError("Checkpoint storage SOC assets do not match")
                if set(runtime_state.storage_cost_state_by_asset) != set(
                    storage_models
                ):
                    raise ValueError("Checkpoint storage-cost assets do not match")
                for asset_id, model in storage_models.items():
                    restore_storage_cost_runtime(
                        model, runtime_state.storage_cost_state_by_asset[asset_id]
                    )
                restore_balancing_state(runtime_state.balancing_state)
                soc = dict(runtime_state.soc_mwh_by_asset)
                self._restored_runtime_checkpoint = None

        month_boundary_by_period: dict[int, RuntimeCheckpointBoundary] = {}
        if (
            maintained_zonal_runtime
            and self._subannual_checkpoint_sink is not None
            and self._output_dir is not None
            and self._ledger_detail != "off"
        ):
            month_boundary_by_period = {
                boundary.last_period_index: boundary
                for boundary in calendar_month_boundaries(
                    chronology.period_ids,
                    model_year=model_input.year,
                    period_hours=model_input.period_hours,
                    run_id=model_input.run_id,
                )
            }
        self._active_runtime_state = runtime_state
        self._active_chronology_sha256 = (
            chronology_sha256 if runtime_state is not None else None
        )

        ledger = NullMarketLedger()
        ledger_metadata: dict[str, object] | None = None
        demand_alignment_rows_by_period: dict[
            int, ZonalDemandAlignmentLedgerRow
        ] = {}
        if demand_alignment is not None:
            demand_alignment_rows_by_period = {
                period: ZonalDemandAlignmentLedgerRow(
                    model_input.year,
                    period,
                    row.period_id,
                    demand_alignment.mode,
                    row.research_real_demand_mwh,
                    row.research_forecast_demand_mwh,
                    row.network_national_demand_mwh,
                    row.scale_factor,
                    row.aligned_zonal_total_mwh,
                    row.conservation_residual_mwh,
                )
                for period, row in enumerate(demand_alignment.rows)
            }
        if self._output_dir is not None:
            parent_run_id = ""
            lineage_path = self._output_dir / "run-lineage.json"
            if lineage_path.is_file():
                lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
                parent_run_id = str(lineage.get("comparison_parent_run_id") or "")
            ledger = create_staged_market_ledger_v8(
                self._output_dir / "market" / "market.sqlite",
                self._ledger_detail,
                storage_cost_module_id=str(getattr(self._storage_cost, "id", "unknown")),
                semantic_metadata={
                    "run_id": model_input.run_id,
                    "run_parent_id": parent_run_id,
                    "data_pack_id": model_input.data_pack_id,
                    "network_pack_id": (
                        self._network_pack.network_pack_id
                        if self._network_pack is not None else "copperplate"
                    ),
                    "zonal_demand_mode": self._zonal_demand_mode,
                    "module_ids": [self.id, str(getattr(self._balancing, "id"))],
                    "module_versions": [self.version, str(getattr(self._balancing, "version"))],
                    "period_hours": float(model_input.period_hours),
                    "weather_spatializer": self._weather_spatializer_identity,
                    "dispatch_commitment": "final_realised_dispatch_once",
                    "settlement_accounts": "national_plus_signed_pay_as_bid_redispatch",
                    "run_context_sha256": (
                        self._run_context_ref.sha256
                        if self._run_context_ref is not None else "0" * 64
                    ),
                    "year_context_sha256": (
                        self._year_context_ref.sha256
                        if self._year_context_ref is not None else "0" * 64
                    ),
                    "network_method_rules": self._network_rules.record(),
                    "zonal_accounting_schema": (
                        ZONAL_ACCOUNTING_SCHEMA_V2
                        if self._network_pack is not None else "not_applicable"
                    ),
                    "counterfactual_engine": (
                        COUNTERFACTUAL_ENGINE
                        if self._network_pack is not None else "not_applicable"
                    ),
                    "run_context_artifact_path": "market/context/run-context.json",
                    "year_context_artifact_path": (
                        f"market/context/year-{model_input.year}.json"
                    ),
                },
            )

        summaries: list[PeriodSummary] = [
            PeriodSummary.from_dict(row)
            for row in (runtime_state.summaries if runtime_state is not None else ())
        ]
        ahead_hashes: dict[str, str] = dict(
            runtime_state.ahead_hashes if runtime_state is not None else {}
        )
        balancing_hashes: dict[str, str] = dict(
            runtime_state.balancing_hashes if runtime_state is not None else {}
        )
        generation: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.generation_mwh_by_asset if runtime_state is not None else {},
        )
        income: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.income_gbp_by_owner if runtime_state is not None else {},
        )
        operating_cost = (
            runtime_state.operating_cost_gbp if runtime_state is not None else 0.0
        )
        operating_cost_by_class: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.operating_cost_gbp_by_class
            if runtime_state is not None else {},
        )
        total_blackout = (
            runtime_state.total_blackout_mwh if runtime_state is not None else 0.0
        )
        total_excess = (
            runtime_state.total_excess_mwh if runtime_state is not None else 0.0
        )
        total_export = (
            runtime_state.total_export_mwh if runtime_state is not None else 0.0
        )
        national_settlement: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.national_settlement_gbp_by_owner
            if runtime_state is not None else {},
        )
        redispatch_settlement: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.redispatch_settlement_gbp_by_owner
            if runtime_state is not None else {},
        )
        actual_storage_discharge: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.actual_storage_discharge_mwh_by_asset
            if runtime_state is not None else {},
        )
        final_dispatch_annual: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.final_dispatch_mwh_by_physical_asset
            if runtime_state is not None else {},
        )
        last_soc_by_base: dict[str, float] = dict(
            runtime_state.last_soc_mwh_by_base_asset
            if runtime_state is not None else {}
        )
        zonal_account_totals: defaultdict[str, float] = defaultdict(
            float,
            runtime_state.zonal_account_totals_gbp
            if runtime_state is not None else {},
        )
        reliability_period_rows: list[dict[str, object]] = [
            dict(row)
            for row in (
                runtime_state.reliability_period_rows
                if runtime_state is not None else ()
            )
        ]
        solver_diagnostic_rows: list[NetworkSolverDiagnosticRow] = [
            NetworkSolverDiagnosticRow(**dict(row))
            for row in (
                runtime_state.solver_diagnostic_rows
                if runtime_state is not None else ()
            )
        ]

        export_asset_ids = tuple(sorted(
            str(asset_id)
            for asset_id in dict(
                chronology.extensions.get("boundary_export_envelope_mwh_by_asset") or {}
            )
        ))

        def period_unit_cost(period_index: int) -> dict[str, float]:
            """P0-8 S9 / C22: one unit-cost table per period for every case.

            Resources use their period cost profile when they have one (an
            import's hourly price) and their annual marginal cost otherwise;
            storage its cycle degradation per discharged MWh; exports 0.
            """

            table: dict[str, float] = {}
            for resource in chronology.resources:
                table[resource.asset_id] = float(
                    _period_value(resource.marginal_cost_profile_gbp_per_mwh, period_index)
                    if resource.marginal_cost_profile_gbp_per_mwh
                    else resource.marginal_cost_gbp_per_mwh
                )
            for resource in chronology.storage:
                table[resource.asset_id] = float(
                    resource.variable_degradation_gbp_per_mwh_discharged
                )
            for asset_id in export_asset_ids:
                table.setdefault(asset_id, 0.0)
            return table

        def copperplate_payload(
            ahead_result: AheadMarketResult, unit_cost: Mapping[str, float]
        ) -> dict[str, object]:
            return {
                "schema_version": "force.copperplate-balancing-domain/v1",
                "ahead_result": ahead_result.to_dict(),
                "resource_cost_gbp_per_mwh_by_asset": dict(unit_cost),
                "resource_class_by_asset": resource_class,
                "storage": {
                    resource.asset_id: {
                        "energy_capacity_mwh": resource.energy_capacity_mwh,
                        "charge_efficiency": resource.charge_efficiency,
                        "discharge_efficiency": resource.discharge_efficiency,
                    }
                    for resource in chronology.storage
                },
            }

        def mapping_increment(
            current: Mapping[str, float], previous: Mapping[str, float]
        ) -> dict[str, float]:
            return {
                key: float(current[key]) - float(previous.get(key, 0.0))
                for key in current
            }

        start_period = (
            runtime_state.next_period_index if runtime_state is not None else 0
        )
        for period in range(start_period, len(chronology.period_ids)):
            period_id_raw = chronology.period_ids[period]
            period_id = str(period_id_raw)
            generation_before = dict(generation)
            income_before = dict(income)
            operating_cost_before = operating_cost
            operating_cost_by_class_before = dict(operating_cost_by_class)
            total_blackout_before = total_blackout
            total_excess_before = total_excess
            total_export_before = total_export
            national_settlement_before = dict(national_settlement)
            redispatch_settlement_before = dict(redispatch_settlement)
            actual_storage_discharge_before = dict(actual_storage_discharge)
            final_dispatch_before = dict(final_dispatch_annual)
            zonal_account_totals_before = dict(zonal_account_totals)
            reliability_rows_before = len(reliability_period_rows)
            zonal_accounting_rows: tuple[ZonalAccountingLedgerRow, ...] = ()
            vre_period_rows: tuple[VRECurtailmentPeriodRow, ...] = ()
            vre_detail_rows: tuple[VRECurtailmentDetailRow, ...] = ()
            zone_rows: list[ZonePeriodLedgerRow] = []
            boundary_rows: list[BoundaryPeriodLedgerRow] = []
            resource_rows: list[ZonalResourceDispatchRow] = []
            redispatch_rows: tuple[RedispatchSettlementRow, ...] = ()
            redispatch_summary_rows: tuple[RedispatchSummaryRow, ...] = ()
            solver_link_rows: tuple[SolverDeclarationLinkRow, ...] = ()
            unit_cost = period_unit_cost(period)
            offers = self._ahead_offers(model_input, period, soc, storage_models)
            ahead_input = AheadMarketInput(
                model_input.run_id,
                model_input.year,
                period,
                period_id,
                model_input.period_hours,
                "forecast_only",
                forecast[period],
                offers,
                dict(soc),
                extensions={
                    "availability_scope": "declared_period_availability",
                    "single_zone": True,
                },
            )
            ahead = _with_declared_vre_zero_dispatch(
                self.clear_ahead(ahead_input), chronology.resources
            )
            realised_availability = {
                resource.asset_id: resource.capacity_mw
                * max(_period_value(resource.availability, period), 0.0)
                for resource in chronology.resources
            }
            realised_availability.update({
                resource.asset_id: resource.discharge_power_mw
                for resource in chronology.storage
            })
            bids = self._flexibility_bids(model_input, period, ahead, soc, storage_models)
            interconnector_envelopes: dict[str, dict[str, float]] = {}
            for resource in chronology.resources:
                if resource.resource_type != "import":
                    continue
                maximum = resource.capacity_mw * max(
                    _period_value(resource.availability, period), 0.0
                ) * model_input.period_hours
                interconnector_envelopes[resource.asset_id] = {
                    "import_capacity_mwh": maximum,
                    "export_capacity_mwh": 0.0,
                }
            for asset_id, raw_envelope in dict(
                chronology.extensions.get("boundary_export_envelope_mwh_by_asset") or {}
            ).items():
                interconnector_envelopes[str(asset_id)] = {
                    "import_capacity_mwh": 0.0,
                    "export_capacity_mwh": max(
                        _period_value(tuple(raw_envelope), period), 0.0
                    ),
                }
                shares = self._zone_shares(str(asset_id), {})
                if len(shares) != 1:
                    raise ValueError(f"Boundary export {asset_id} must have one landing zone")
                zone_by_asset[str(asset_id)] = next(iter(shares))
                base_by_asset[str(asset_id)] = str(asset_id)
                owner_by_asset[str(asset_id)] = f"interconnector:{str(asset_id).split(':', 1)[-1]}"
            if self._network_pack is None:
                domain_payload = copperplate_payload(ahead, unit_cost)
            else:
                try:
                    network_period = self._period_index_by_id[period_id]
                except KeyError as exc:
                    raise ValueError(
                        f"Period {period_id} is absent from the selected zonal network pack"
                    ) from exc
                if demand_alignment is None:
                    raise RuntimeError("Zonal demand alignment was not prepared before clearing")
                zonal_demand = {
                    zone.zone_id: float(
                        demand_alignment.demand_mwh_by_zone[zone.zone_id][period]
                    )
                    for zone in self._network_pack.zones
                }
                forecast_total = float(forecast[period])
                real_total = float(chronology.demand_mwh[period])
                if real_total > 0.0:
                    zonal_forecast = {
                        zone: value * forecast_total / real_total
                        for zone, value in zonal_demand.items()
                    }
                elif forecast_total == 0.0:
                    zonal_forecast = {zone: 0.0 for zone in zonal_demand}
                else:
                    pack_total = float(
                        self._network_pack.zonal_demand.national_demand_mwh[
                            network_period
                        ]
                    )
                    if pack_total <= 0.0:
                        raise ValueError(
                            f"Period {period_id} has no zonal forecast allocation basis"
                        )
                    zonal_forecast = {
                        zone.zone_id: float(
                            self._network_pack.zonal_demand.demand_mwh_by_zone[
                                zone.zone_id
                            ][network_period]
                        )
                        * forecast_total
                        / pack_total
                        for zone in self._network_pack.zones
                    }
                profiles = {
                    profile.profile_id: profile
                    for profile in self._network_pack.rating_profiles
                }
                forward_capacity: dict[str, float] = {}
                reverse_capacity: dict[str, float] = {}
                for boundary in self._network_pack.cutsets:
                    multiplier = 1.0
                    if boundary.rating_profile_id:
                        multiplier = profiles[
                            boundary.rating_profile_id
                        ].multipliers[network_period]
                    forward_capacity[boundary.boundary_id] = (
                        boundary.forward_limit_mw
                        * model_input.period_hours
                        * multiplier
                    )
                    reverse_capacity[boundary.boundary_id] = (
                        boundary.reverse_limit_mw
                        * model_input.period_hours
                        * multiplier
                    )
                assert self._run_context_ref is not None
                assert self._year_context_ref is not None

                def zonal_payload(ahead_result: AheadMarketResult) -> dict[str, object]:
                    assert self._run_context_ref is not None
                    assert self._year_context_ref is not None
                    return ZonalRedispatchDomainV2(
                        self._run_context_ref,
                        self._year_context_ref,
                        ZonalRedispatchPeriodSlice(
                            period_id=period_id,
                            ahead_result=ahead_result,
                            zonal_real_demand_mwh=zonal_demand,
                            zonal_forecast_demand_mwh=zonal_forecast,
                            forward_boundary_capacity_mwh=forward_capacity,
                            reverse_boundary_capacity_mwh=reverse_capacity,
                            interconnector_envelopes=interconnector_envelopes,
                            resource_cost_gbp_per_mwh_by_asset=unit_cost,
                        ),
                    ).to_dict()

                domain_payload = zonal_payload(ahead)
            period_initial_soc = dict(soc)
            balancing_input = BalancingInput(
                model_input.run_id,
                model_input.year,
                period,
                period_id,
                contract_sha256(ahead),
                float(chronology.demand_mwh[period]),
                realised_availability,
                period_initial_soc,
                bids,
                model_input.period_hours,
                chronology.voll_gbp_per_mwh,
                domain_payload=domain_payload,
            )
            balancing: BalancingResult = self._balancing.clear(balancing_input)
            period_solver_rows: tuple[NetworkSolverDiagnosticRow, ...] = ()
            if self._network_pack is not None:
                period_solver_rows = _network_solver_diagnostic_rows(
                    balancing,
                    module_id=str(getattr(self._balancing, "id")),
                    module_version=str(getattr(self._balancing, "version")),
                )
            ahead_hashes[period_id] = contract_sha256(ahead)
            balancing_hashes[period_id] = contract_sha256(balancing)

            if ledger is not None and self._network_pack is not None:
                # P0-8 S9 (P2-02/P2-03/P2-04): both reference cases are the
                # zonal LP without the network, with the same bids, envelopes,
                # VOLL, unit-cost table and solver; only the network differs.
                network_free = getattr(self._balancing, "network_free_counterfactual", None)
                if not callable(network_free):
                    raise TypeError(
                        "Zonal balancing must expose network_free_counterfactual"
                    )
                realised_copperplate_input = balancing_input
                realised_copperplate = network_free(realised_copperplate_input)
                perfect_ahead_input = replace(
                    ahead_input,
                    forecast_demand_mwh=float(chronology.demand_mwh[period]),
                )
                perfect_ahead = _with_declared_vre_zero_dispatch(
                    self.clear_ahead(perfect_ahead_input), chronology.resources
                )
                perfect_bids = self._flexibility_bids(
                    model_input, period, perfect_ahead, period_initial_soc, storage_models
                )
                perfect_copperplate_input = BalancingInput(
                    model_input.run_id,
                    model_input.year,
                    period,
                    period_id,
                    contract_sha256(perfect_ahead),
                    float(chronology.demand_mwh[period]),
                    realised_availability,
                    period_initial_soc,
                    perfect_bids,
                    model_input.period_hours,
                    chronology.voll_gbp_per_mwh,
                    domain_payload=zonal_payload(perfect_ahead),
                )
                perfect_copperplate = network_free(perfect_copperplate_input)
                primary_zonal = float(balancing.extensions["primary_objective_gbp"])
                primary_network_free = float(
                    realised_copperplate.extensions["primary_objective_gbp"]
                )
                order_tolerance = 1e-6 + 1e-8 * max(
                    1.0, abs(primary_zonal), abs(primary_network_free)
                )
                if primary_zonal < primary_network_free - order_tolerance:
                    raise ValueError(
                        "GF_NETWORK_COUNTERFACTUAL_ORDER: the zonal primary objective "
                        f"{primary_zonal} is below the network-free one "
                        f"{primary_network_free} in period {period_id}"
                    )
                zonal_account_totals["network_constraint_bid_objective_gbp"] += (
                    primary_zonal - primary_network_free
                )

                counterfactual_identity = (
                    f"{COUNTERFACTUAL_ENGINE}@{getattr(self._balancing, 'version')}"
                )
                module_identities = {
                    "perfect_forecast_copperplate": counterfactual_identity,
                    "realised_copperplate": counterfactual_identity,
                    "zonal_final": (
                        f"{getattr(self._balancing, 'id')}@"
                        f"{getattr(self._balancing, 'version')}"
                    ),
                }
                case_inputs = {
                    "perfect_forecast_copperplate": perfect_copperplate_input,
                    "realised_copperplate": realised_copperplate_input,
                    "zonal_final": balancing_input,
                }
                realised_input_sha256_by_case = {
                    case: _realised_case_input_sha256(case_input, unit_cost)
                    for case, case_input in sorted(case_inputs.items())
                }
                dispatch_by_case = {
                    "perfect_forecast_copperplate": (
                        perfect_copperplate.final_dispatch_mwh_by_asset
                    ),
                    "realised_copperplate": (
                        realised_copperplate.final_dispatch_mwh_by_asset
                    ),
                    "zonal_final": balancing.final_dispatch_mwh_by_asset,
                }

                canonical_key_by_asset: dict[str, tuple[str, str]] = {}
                resource_by_key: dict[tuple[str, str], tuple[DispatchResource, str]] = {}
                for resource in chronology.resources:
                    technology = _canonical_live_vre_technology(resource.technology)
                    if technology is None:
                        continue
                    key = (
                        resource.asset_id,
                        build_bid_tranche_id(
                            technology,
                            float(resource_cost.get(resource.asset_id, 0.0)),
                        ),
                    )
                    canonical_key_by_asset[resource.asset_id] = key
                    resource_by_key[key] = (resource, technology)

                expected_keys = set(resource_by_key)
                try:
                    realised_identity = _validate_vre_counterfactual_cases(
                        expected_keys=expected_keys,
                        canonical_key_by_asset=canonical_key_by_asset,
                        dispatch_by_case=dispatch_by_case,
                        realised_input_sha256_by_case=(
                            realised_input_sha256_by_case
                        ),
                        module_identities=module_identities,
                    )
                except CurtailmentAttributionError as exc:
                    hashes = sorted(set(realised_input_sha256_by_case.values()))
                    failure_input_sha256 = (
                        hashes[0]
                        if len(hashes) == 1
                        else hashlib.sha256(
                            json.dumps(
                                realised_input_sha256_by_case,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest()
                    )
                    ledger.close()
                    if self._output_dir is not None:
                        failure_path = (
                            self._output_dir
                            / "market"
                            / "failures"
                            / f"vre-curtailment-attribution-{failure_input_sha256}.json"
                        )
                        _atomic_write_json(
                            failure_path,
                            _adapter_failure_payload(
                                exc,
                                run_id=model_input.run_id,
                                year=model_input.year,
                                period=period,
                                period_id=period_id,
                                failure_input_sha256=failure_input_sha256,
                            ),
                        )
                    raise

                snapshot = VRECounterfactualSnapshot(
                    run_id=model_input.run_id,
                    year=model_input.year,
                    period=period,
                    period_id=period_id,
                    realised_input_sha256=realised_identity,
                    rows=tuple(
                        VRECounterfactualRow(
                            asset_id=resource.asset_id,
                            owner_id=owner_by_asset.get(
                                resource.asset_id, resource.asset_id
                            ),
                            canonical_technology=technology,
                            zone_id=zone_by_asset.get(resource.asset_id, "GB"),
                            bid_tranche_id=key[1],
                            realised_available_vre_mwh=(
                                resource.capacity_mw
                                * _period_value(resource.availability, period)
                                * model_input.period_hours
                            ),
                            perfect_forecast_copperplate_dispatch_mwh=float(
                                perfect_copperplate.final_dispatch_mwh_by_asset[
                                    resource.asset_id
                                ]
                            ),
                            realised_copperplate_dispatch_mwh=float(
                                realised_copperplate.final_dispatch_mwh_by_asset[
                                    resource.asset_id
                                ]
                            ),
                            zonal_final_dispatch_mwh=float(
                                balancing.final_dispatch_mwh_by_asset[
                                    resource.asset_id
                                ]
                            ),
                        )
                        for key, (resource, technology) in sorted(
                            resource_by_key.items()
                        )
                    ),
                    module_identities=module_identities,
                )
                try:
                    attribution = attribute_vre_curtailment(snapshot)
                except CurtailmentAttributionError as exc:
                    ledger.close()
                    if self._output_dir is not None:
                        failure_path = (
                            self._output_dir
                            / "market"
                            / "failures"
                            / f"vre-curtailment-attribution-{realised_identity}.json"
                        )
                        _atomic_write_json(
                            failure_path, failure_payload(exc, snapshot)
                        )
                    raise

                boundary_shadow = {
                    boundary.boundary_id: 0.0
                    for boundary in self._network_pack.cutsets
                }
                accounting = build_zonal_period_accounting(
                    year=model_input.year,
                    period=period,
                    period_id=period_id,
                    realised_input_sha256=realised_identity,
                    perfect_forecast_resource_cost_gbp=sum(
                        perfect_copperplate.resource_cost_gbp_by_class.values()
                    ),
                    realised_copperplate_resource_cost_gbp=sum(
                        realised_copperplate.resource_cost_gbp_by_class.values()
                    ),
                    zonal_resource_cost_gbp=sum(balancing.resource_cost_gbp_by_class.values()),
                    ahead_settlement_mwh_by_asset=ahead.settlement_mwh_by_asset,
                    national_clearing_price_gbp_per_mwh=ahead.clearing_price_gbp_per_mwh,
                    redispatch_cashflow_gbp_by_agent=balancing.settlement_cashflow_gbp_by_agent,
                    policy_transfer_gbp=0.0,
                    boundary_shadow_value_gbp_per_mwh=boundary_shadow,
                    blackout_mwh=balancing.blackout_mwh,
                )
                zonal_accounting_rows = (
                    ZonalAccountingLedgerRow.from_accounting(accounting),
                )
                vre_period_rows = (
                    VRECurtailmentPeriodRow.from_attribution(attribution),
                )
                vre_detail_rows = VRECurtailmentDetailRow.from_attribution(
                    attribution
                )
                for field in (
                    "system_resource_cost_gbp",
                    "transmission_constraint_resource_cost_gbp",
                    "national_settlement_gbp",
                    "redispatch_settlement_gbp",
                    "policy_transfer_gbp",
                ):
                    zonal_account_totals[field] += float(getattr(accounting, field))

                load_shedding = dict(
                    balancing.extensions.get("load_shedding_mwh_by_zone") or {}
                )
                zone_rows = []
                for zone in self._network_pack.zones:
                    assets = {
                        asset for asset, asset_zone in zone_by_asset.items()
                        if asset_zone == zone.zone_id
                    }
                    ahead_injection = sum(
                        float(ahead.schedule_mwh_by_asset.get(asset, 0.0))
                        for asset in assets
                    )
                    final_injection = sum(
                        float(balancing.final_dispatch_mwh_by_asset.get(asset, 0.0))
                        for asset in assets
                    )
                    shed = float(load_shedding.get(zone.zone_id, 0.0) or 0.0)
                    demand = float(zonal_demand[zone.zone_id])
                    zone_rows.append(ZonePeriodLedgerRow(
                        model_input.year,
                        period,
                        zone.zone_id,
                        demand,
                        ahead_injection,
                        final_injection,
                        final_injection - ahead_injection,
                        shed,
                        final_injection + shed - demand,
                    ))

                profile_by_id = {
                    profile.profile_id: profile
                    for profile in self._network_pack.rating_profiles
                }
                boundary_rows = []
                transfers = dict(
                    balancing.extensions.get("boundary_transfer_mwh_by_id") or {}
                )
                for boundary in self._network_pack.cutsets:
                    multiplier = 1.0
                    if boundary.rating_profile_id:
                        multiplier = float(
                            profile_by_id[boundary.rating_profile_id].multipliers[network_period]
                        )
                    forward = boundary.forward_limit_mw * model_input.period_hours * multiplier
                    reverse = boundary.reverse_limit_mw * model_input.period_hours * multiplier
                    transfer = float(transfers.get(boundary.boundary_id, 0.0) or 0.0)
                    directional_limit = forward if transfer >= 0 else reverse
                    utilisation = abs(transfer) / directional_limit if directional_limit > 0 else 0.0
                    boundary_rows.append(BoundaryPeriodLedgerRow(
                        model_input.year,
                        period,
                        boundary.boundary_id,
                        transfer,
                        forward,
                        reverse,
                        utilisation,
                        boundary_shadow[boundary.boundary_id],
                        "diagnostic_marginal_value_in_accepted_bid_objective_not_zonal_price_or_cash_cost",
                    ))

                technology_by_asset = {
                    resource.asset_id: resource.technology
                    for resource in (*chronology.resources, *chronology.storage)
                }
                storage_dispatch = dict(
                    balancing.extensions.get("storage_dispatch_mwh_by_asset") or {}
                )
                resource_rows = []
                for asset_id, final_dispatch in sorted(
                    balancing.final_dispatch_mwh_by_asset.items()
                ):
                    storage_row = dict(storage_dispatch.get(asset_id) or {})
                    resource_rows.append(ZonalResourceDispatchRow(
                        model_input.year,
                        period,
                        asset_id,
                        owner_by_asset.get(asset_id, asset_id),
                        zone_by_asset.get(asset_id, "GB"),
                        technology_by_asset.get(asset_id, resource_class.get(asset_id, "other")),
                        float(ahead.schedule_mwh_by_asset.get(asset_id, 0.0)),
                        float(final_dispatch),
                        float(final_dispatch) - float(ahead.schedule_mwh_by_asset.get(asset_id, 0.0)),
                        float(balancing.final_soc_mwh_by_asset.get(asset_id, 0.0)),
                        float(storage_row.get("charge_mwh", 0.0) or 0.0),
                        float(storage_row.get("discharge_mwh", 0.0) or 0.0),
                        max(float(final_dispatch), 0.0)
                        * float(unit_cost.get(asset_id, 0.0)),
                    ))

                accepted_by_bid = {
                    row.bid_id: row for row in balancing.accepted_adjustments
                }
                redispatch_rows = tuple(
                    RedispatchSettlementRow(
                        bid.bid_id,
                        model_input.year,
                        period,
                        bid.agent_id,
                        bid.asset_id,
                        bid.zone_id,
                        bid.technology,
                        bid.direction,
                        float(bid.extensions.get("available_mwh", 0.0) or 0.0),
                        float(accepted_by_bid[bid.bid_id].accepted_delta_mwh)
                        if bid.bid_id in accepted_by_bid else 0.0,
                        bid.price_gbp_per_mwh,
                        float(accepted_by_bid[bid.bid_id].cashflow_to_agent_gbp)
                        if bid.bid_id in accepted_by_bid else 0.0,
                        "accepted" if bid.bid_id in accepted_by_bid else "rejected",
                        accepted_by_bid[bid.bid_id].reason_code
                        if bid.bid_id in accepted_by_bid else "not_required_at_optimum",
                    )
                    for bid in balancing_input.bids
                )
                solver_artifact = next(
                    (row.uri for row in balancing.artifacts if row.kind == "solver-diagnostics"),
                    None,
                )
                solver_status = str(
                    dict(balancing.extensions.get("solver") or {}).get("status")
                    or "optimal"
                )
                solver_link_rows = (SolverDeclarationLinkRow(
                    model_input.year,
                    period,
                    balancing.source_input_sha256,
                    "market/market.sqlite#declared-input",
                    solver_artifact,
                    None,
                    solver_status,
                ),)
                reliability_period_rows.append({
                    "year": model_input.year,
                    "period": period,
                    "load_shedding_mwh_by_zone": load_shedding,
                })

            soc = {
                str(key): float(value)
                for key, value in balancing.final_soc_mwh_by_asset.items()
            }
            last_soc_by_base = {}
            for asset_id, value in soc.items():
                base = base_by_asset.get(asset_id, asset_id)
                last_soc_by_base[base] = last_soc_by_base.get(base, 0.0) + float(value)
            for asset_id, dispatch_mwh in balancing.final_dispatch_mwh_by_asset.items():
                final_dispatch_annual[asset_id] += float(dispatch_mwh)
                if asset_id in storage_by_id:
                    if dispatch_mwh > 0:
                        storage_models[asset_id].record_sale(dispatch_mwh, 0.0)
                        actual_storage_discharge[base_by_asset.get(asset_id, asset_id)] += float(dispatch_mwh)
                    continue
                if dispatch_mwh > 0:
                    base = base_by_asset.get(asset_id, asset_id)
                    generation[base] += float(dispatch_mwh)
                    # C22: the running cost of the dispatched MWh at this
                    # period's unit cost.  Kept as prefixed keys of the free
                    # zonal_account_totals mapping so StagedPSMRuntimeState
                    # (and its schema) carries it unchanged across restores.
                    zonal_account_totals[AGENT_VARIABLE_COST_PREFIX + base] += float(
                        dispatch_mwh
                    ) * float(unit_cost.get(asset_id, 0.0))
            for asset_id, settled_mwh in ahead.settlement_mwh_by_asset.items():
                owner = owner_by_asset.get(asset_id, asset_id)
                cashflow = settled_mwh * ahead.clearing_price_gbp_per_mwh
                income[owner] += cashflow
                national_settlement[owner] += cashflow
            for agent_id, cashflow in balancing.settlement_cashflow_gbp_by_agent.items():
                income[agent_id] += float(cashflow)
                redispatch_settlement[agent_id] += float(cashflow)

            period_operating = sum(balancing.resource_cost_gbp_by_class.values())
            operating_cost += period_operating
            for cost_class, amount in balancing.resource_cost_gbp_by_class.items():
                operating_cost_by_class[str(cost_class)] += float(amount)
            total_blackout += balancing.blackout_mwh
            total_export += sum(
                max(-float(value), 0.0)
                for asset_id, value in balancing.final_dispatch_mwh_by_asset.items()
                if asset_id.startswith("export:")
            )
            storage_charge = sum(
                max(-float(balancing.final_dispatch_mwh_by_asset.get(asset_id, 0.0)), 0.0)
                for asset_id in storage_by_id
            )
            storage_discharge = sum(
                max(float(balancing.final_dispatch_mwh_by_asset.get(asset_id, 0.0)), 0.0)
                for asset_id in storage_by_id
            )
            vre_available = sum(
                resource.capacity_mw
                * max(_period_value(resource.availability, period), 0.0)
                * model_input.period_hours
                for resource in chronology.resources
                if resource.resource_type == "vre"
            )
            vre_accepted = sum(
                max(float(balancing.final_dispatch_mwh_by_asset.get(resource.asset_id, 0.0)), 0.0)
                for resource in chronology.resources
                if resource.resource_type == "vre"
            )
            period_excess = max(vre_available - vre_accepted, 0.0)
            total_excess += period_excess
            imported = sum(
                max(float(balancing.final_dispatch_mwh_by_asset.get(resource.asset_id, 0.0)), 0.0)
                for resource in chronology.resources
                if resource.resource_type == "import"
            )
            accepted_supply = sum(
                max(float(value), 0.0)
                for value in balancing.final_dispatch_mwh_by_asset.values()
            )
            market_payment = (
                ahead.accepted_volume_mwh * ahead.clearing_price_gbp_per_mwh
                + sum(balancing.settlement_cashflow_gbp_by_agent.values())
            )
            period_summary = PeriodSummary(
                period_id,
                model_input.year,
                period,
                "final_dispatch",
                forecast[period],
                float(chronology.demand_mwh[period]),
                accepted_supply,
                storage_charge,
                storage_discharge,
                vre_available,
                vre_accepted,
                period_excess,
                imported,
                ahead.clearing_price_gbp_per_mwh,
                period_operating,
                market_payment,
                balancing.blackout_mwh,
                balancing.energy_balance_residual_mwh,
            )
            period_outcome: StagedPeriodOutcome | None = None
            if runtime_state is not None:
                export_balancing_state = getattr(
                    self._balancing, "export_runtime_state", None
                )
                if not callable(export_balancing_state):
                    raise TypeError(
                        "Maintained zonal balancing must export runtime state"
                    )
                period_outcome = StagedPeriodOutcome(
                    run_id=model_input.run_id,
                    year=model_input.year,
                    period_index=period,
                    summary=period_summary.to_dict(),
                    ahead_result_sha256=ahead_hashes[period_id],
                    balancing_result_sha256=balancing_hashes[period_id],
                    post_period_soc_mwh_by_asset=soc,
                    storage_cost_state_by_asset={
                        asset_id: snapshot_storage_cost_runtime(model)
                        for asset_id, model in storage_models.items()
                    },
                    balancing_state=export_balancing_state(),
                    generation_mwh_by_asset=mapping_increment(
                        generation, generation_before
                    ),
                    income_gbp_by_owner=mapping_increment(income, income_before),
                    operating_cost_gbp=operating_cost - operating_cost_before,
                    operating_cost_gbp_by_class=mapping_increment(
                        operating_cost_by_class, operating_cost_by_class_before
                    ),
                    total_blackout_mwh=total_blackout - total_blackout_before,
                    total_excess_mwh=total_excess - total_excess_before,
                    total_export_mwh=total_export - total_export_before,
                    national_settlement_gbp_by_owner=mapping_increment(
                        national_settlement, national_settlement_before
                    ),
                    redispatch_settlement_gbp_by_owner=mapping_increment(
                        redispatch_settlement, redispatch_settlement_before
                    ),
                    actual_storage_discharge_mwh_by_asset=mapping_increment(
                        actual_storage_discharge,
                        actual_storage_discharge_before,
                    ),
                    final_dispatch_mwh_by_physical_asset=mapping_increment(
                        final_dispatch_annual, final_dispatch_before
                    ),
                    last_soc_mwh_by_base_asset=last_soc_by_base,
                    zonal_account_totals_gbp=mapping_increment(
                        zonal_account_totals, zonal_account_totals_before
                    ),
                    reliability_period_rows=tuple(
                        reliability_period_rows[reliability_rows_before:]
                    ),
                    solver_diagnostic_rows=tuple(
                        row.__dict__ for row in period_solver_rows
                    ),
                )
            if ledger is not None:
                period_row = PeriodLedgerRow(
                    model_input.year,
                    period,
                    "final_dispatch",
                    forecast[period],
                    float(chronology.demand_mwh[period]),
                    accepted_supply,
                    storage_charge,
                    storage_discharge,
                    0.0,
                    sum(
                        max(-float(value), 0.0)
                        for asset_id, value in balancing.final_dispatch_mwh_by_asset.items()
                        if asset_id.startswith("export:")
                    ),
                    vre_available,
                    vre_accepted,
                    period_excess,
                    imported,
                    ahead.clearing_price_gbp_per_mwh,
                    period_operating,
                    market_payment,
                    0.0,
                    balancing.blackout_mwh,
                    period_excess,
                    balancing.energy_balance_residual_mwh,
                    0.0,
                    balancing.energy_balance_residual_mwh,
                )
                physical_rows = []
                for resource in chronology.resources:
                    dispatched = float(
                        balancing.final_dispatch_mwh_by_asset.get(resource.asset_id, 0.0)
                    )
                    if dispatched > 1e-12:
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year,
                            period,
                            resource.asset_id,
                            resource.technology,
                            "import" if resource.resource_type == "import" else "generation",
                            dispatched,
                            dispatched,
                            "balancing_final_realised_dispatch",
                        ))
                    if resource.resource_type == "vre":
                        available = (
                            resource.capacity_mw
                            * max(_period_value(resource.availability, period), 0.0)
                            * model_input.period_hours
                        )
                        unused = max(available - max(dispatched, 0.0), 0.0)
                        if unused > 1e-12:
                            physical_rows.append(PhysicalDispatchRow(
                                model_input.year,
                                period,
                                resource.asset_id,
                                resource.technology,
                                "unused_vre",
                                unused,
                                0.0,
                                "realised_availability_minus_final_dispatch",
                            ))
                storage_rows = []
                storage_trace = dict(
                    balancing.extensions.get("storage_dispatch_mwh_by_asset") or {}
                )
                for resource in chronology.storage:
                    row = dict(storage_trace.get(resource.asset_id) or {})
                    net_dispatch = float(
                        balancing.final_dispatch_mwh_by_asset.get(resource.asset_id, 0.0)
                    )
                    charge = float(
                        row.get("charge_mwh", max(-net_dispatch, 0.0)) or 0.0
                    )
                    discharge = float(
                        row.get("discharge_mwh", max(net_dispatch, 0.0)) or 0.0
                    )
                    storage_rows.append(StorageStateRow(
                        model_input.year,
                        period,
                        resource.asset_id,
                        float(balancing.final_soc_mwh_by_asset.get(resource.asset_id, 0.0)),
                        charge,
                        discharge,
                        resource.discharge_power_mw,
                        resource.energy_capacity_mwh,
                    ))
                    if charge > 1e-12:
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year,
                            period,
                            resource.asset_id,
                            resource.technology,
                            "storage_charge",
                            charge,
                            -charge,
                            "balancing_final_realised_dispatch",
                        ))
                    if discharge > 1e-12:
                        physical_rows.append(PhysicalDispatchRow(
                            model_input.year,
                            period,
                            resource.asset_id,
                            resource.technology,
                            "storage_discharge",
                            discharge,
                            discharge,
                            "balancing_final_realised_dispatch",
                        ))
                dispatch_by_zone_technology: defaultdict[
                    tuple[str, str], float
                ] = defaultdict(float)
                for row in physical_rows:
                    if row.flow_type not in {
                        "generation", "import", "storage_discharge"
                    }:
                        continue
                    dispatch_by_zone_technology[
                        (zone_by_asset.get(row.asset_id, "GB"), row.technology)
                    ] += row.energy_mwh
                storage_by_zone_technology: defaultdict[
                    tuple[str, str], list[float]
                ] = defaultdict(lambda: [0.0, 0.0, 0.0])
                storage_technology_by_asset = {
                    row.asset_id: row.technology for row in chronology.storage
                }
                for row in storage_rows:
                    totals = storage_by_zone_technology[
                        (
                            zone_by_asset.get(row.asset_id, "GB"),
                            storage_technology_by_asset.get(row.asset_id, "storage"),
                        )
                    ]
                    totals[0] += row.charge_mwh
                    totals[1] += row.discharge_mwh
                    totals[2] += row.state_of_charge_mwh
                accepted_by_bid = {
                    row.bid_id: row for row in balancing.accepted_adjustments
                }
                order_rows: list[OrderLedgerRow] = []
                for offer in offers:
                    asset_id = str(offer["asset_id"])
                    accepted = max(
                        float(ahead.schedule_mwh_by_asset.get(asset_id, 0.0)),
                        0.0,
                    )
                    offered = float(offer.get("available_mwh", 0.0) or 0.0)
                    price = float(offer.get("price_gbp_per_mwh", 0.0) or 0.0)
                    physical_price = float(
                        offer.get("physical_cost_gbp_per_mwh", price) or 0.0
                    )
                    order_rows.append(OrderLedgerRow(
                        str(offer["offer_id"]),
                        model_input.year,
                        period,
                        "ahead",
                        asset_id,
                        str(offer.get("technology") or offer.get("resource_kind")),
                        "supply",
                        price,
                        offered,
                        min(accepted, offered),
                        "accepted" if accepted > 1e-12 else "rejected",
                        "cleared" if accepted > 1e-12 else "not_selected",
                        min(accepted, offered) * physical_price,
                        min(accepted, offered) * ahead.clearing_price_gbp_per_mwh,
                    ))
                for bid in balancing_input.bids:
                    accepted = accepted_by_bid.get(bid.bid_id)
                    accepted_mwh = (
                        abs(float(accepted.accepted_delta_mwh))
                        if accepted is not None else 0.0
                    )
                    offered_mwh = float(
                        bid.extensions.get("available_mwh", 0.0) or 0.0
                    )
                    order_rows.append(OrderLedgerRow(
                        bid.bid_id,
                        model_input.year,
                        period,
                        "balancing",
                        bid.asset_id,
                        bid.technology,
                        bid.direction,
                        bid.price_gbp_per_mwh,
                        offered_mwh,
                        accepted_mwh,
                        "accepted" if accepted is not None else "rejected",
                        (
                            accepted.reason_code
                            if accepted is not None
                            else "not_required_at_optimum"
                        ),
                        accepted_mwh * bid.physical_cost_gbp_per_mwh,
                        (
                            float(accepted.cashflow_to_agent_gbp)
                            if accepted is not None else 0.0
                        ),
                    ))
                if self._network_pack is not None:
                    redispatch_summary_rows = _build_redispatch_summary_rows(
                        year=model_input.year,
                        period=period,
                        bids=balancing_input.bids,
                        accepted_adjustments=balancing.accepted_adjustments,
                        ahead_resource_cost_gbp=math.fsum(
                            row.physical_resource_cost_gbp
                            for row in order_rows
                            if row.stage == "ahead"
                        ),
                        blackout_resource_cost_gbp=(
                            float(balancing.blackout_mwh)
                            * float(chronology.voll_gbp_per_mwh)
                        ),
                        zonal_resource_cost_gbp=accounting.zonal_resource_cost_gbp,
                    )
                common_rows = {
                    "zonal_period_accounting": zonal_accounting_rows,
                    "vre_curtailment_period": vre_period_rows,
                    "zonal_demand_alignment": (
                        (demand_alignment_rows_by_period[period],)
                        if period in demand_alignment_rows_by_period else ()
                    ),
                    "zone_period_summary": tuple(zone_rows),
                    "boundary_period_summary": tuple(boundary_rows),
                    "solver_declaration_link": solver_link_rows,
                }
                full_rows = {
                    "orders": tuple(order_rows),
                    "storage_state": tuple(storage_rows),
                    "physical_dispatch": tuple(physical_rows),
                    "vre_curtailment_detail": vre_detail_rows,
                    "zonal_resource_dispatch": tuple(resource_rows),
                    "redispatch_settlement": redispatch_rows,
                    "network_solver_diagnostics": tuple(period_solver_rows),
                }
                period_batch = build_market_period_batch(
                    period=period_row,
                    dispatch_summary=(
                        DispatchSummaryRow(
                            model_input.year,
                            period,
                            "final_dispatch",
                            zone,
                            technology,
                            energy,
                        )
                        for (zone, technology), energy in sorted(
                            dispatch_by_zone_technology.items()
                        )
                    ),
                    storage_summary=(
                        StorageSummaryRow(
                            model_input.year,
                            period,
                            zone,
                            technology,
                            totals[0],
                            totals[1],
                            totals[2],
                        )
                        for (zone, technology), totals in sorted(
                            storage_by_zone_technology.items()
                        )
                    ),
                    redispatch_summary=redispatch_summary_rows,
                    common_rows=common_rows,
                    full_rows=full_rows,
                    run_context_sha256=(
                        self._run_context_ref.sha256
                        if self._run_context_ref is not None else "0" * 64
                    ),
                    year_context_sha256=(
                        self._year_context_ref.sha256
                        if self._year_context_ref is not None else "0" * 64
                    ),
                )
                _record_period_batch_at_boundary(ledger, period_batch)
                if period_solver_rows:
                    solver_diagnostic_rows.extend(period_solver_rows)
            summaries.append(period_summary)
            if runtime_state is not None:
                if period_outcome is None:
                    raise RuntimeError("Maintained zonal period outcome is missing")
                runtime_state = runtime_state.apply_period(period_outcome)
                self._active_runtime_state = runtime_state
                boundary = month_boundary_by_period.get(period)
                if (
                    boundary is not None
                    and self._subannual_checkpoint_sink is not None
                    and not isinstance(ledger, NullMarketLedger)
                ):
                    try:
                        ledger_boundary = market_ledger_boundary(
                            ledger.path,
                            year=model_input.year,
                            committed_period=period,
                        )
                        self._subannual_checkpoint_sink(
                            boundary,
                            self.export_runtime_checkpoint(boundary),
                            ledger_boundary,
                        )
                    except Exception:
                        _close_unsealed_ledger(ledger)
                        raise
            if self._period_boundary_cancellation is not None:
                try:
                    self._period_boundary_cancellation(model_input.year, period)
                except Exception:
                    _close_unsealed_ledger(ledger)
                    raise

        if runtime_state is not None:
            if runtime_state.next_period_index != len(chronology.period_ids):
                raise RuntimeError(
                    "Staged PSM runtime state did not reach the chronology end"
                )
            summaries = [
                PeriodSummary.from_dict(row) for row in runtime_state.summaries
            ]
            ahead_hashes = dict(runtime_state.ahead_hashes)
            balancing_hashes = dict(runtime_state.balancing_hashes)
            generation = defaultdict(
                float, runtime_state.generation_mwh_by_asset
            )
            income = defaultdict(float, runtime_state.income_gbp_by_owner)
            operating_cost = runtime_state.operating_cost_gbp
            operating_cost_by_class = defaultdict(
                float, runtime_state.operating_cost_gbp_by_class
            )
            total_blackout = runtime_state.total_blackout_mwh
            total_excess = runtime_state.total_excess_mwh
            total_export = runtime_state.total_export_mwh
            national_settlement = defaultdict(
                float, runtime_state.national_settlement_gbp_by_owner
            )
            redispatch_settlement = defaultdict(
                float, runtime_state.redispatch_settlement_gbp_by_owner
            )
            actual_storage_discharge = defaultdict(
                float, runtime_state.actual_storage_discharge_mwh_by_asset
            )
            final_dispatch_annual = defaultdict(
                float, runtime_state.final_dispatch_mwh_by_physical_asset
            )
            last_soc_by_base = dict(runtime_state.last_soc_mwh_by_base_asset)
            zonal_account_totals = defaultdict(
                float, runtime_state.zonal_account_totals_gbp
            )
            reliability_period_rows = [
                dict(row) for row in runtime_state.reliability_period_rows
            ]
            solver_diagnostic_rows = [
                NetworkSolverDiagnosticRow(**dict(row))
                for row in runtime_state.solver_diagnostic_rows
            ]

        for asset in model_input.operating_state.assets:
            validate_asset_economics(asset)
        primary_costs = tuple(
            primary_annual_asset_costs(asset)
            for asset in model_input.operating_state.assets
        )
        capital = sum(row[0] for row in primary_costs)
        fixed_om = sum(row[1] for row in primary_costs)
        reports_by_base: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for asset_id, model in storage_models.items():
            reports_by_base[base_by_asset.get(asset_id, asset_id)].append(dict(model.report()))
        storage_reports: dict[str, dict[str, object]] = {}
        for base_id, reports in reports_by_base.items():
            report = dict(reports[0])
            report["current_year_sold_mwh"] = sum(
                float(row.get("current_year_sold_mwh", 0.0) or 0.0) for row in reports
            )
            if len(reports) > 1:
                report["physical_tranche_count"] = len(reports)
            # P0-6 S10 (P5-15): the staged PSM keeps one SoC pool, bids d = 0
            # and records sales with dwell 0; it does not track dwell, so the
            # holding coefficient of a dwell-based cost module is not applied.
            report["dwell_source"] = STAGED_DWELL_SOURCE
            storage_reports[base_id] = report
        if ledger is not None:
            if reliability_period_rows:
                ledger.record_reliability_events(build_reliability_events(
                    reliability_period_rows,
                    period_hours=model_input.period_hours,
                ))
            ledger_metadata = ledger.close()
        solver_validation_summary = (
            build_solver_validation_summary(
                solver_diagnostic_rows,
                inherited=(
                    dict(
                        model_input.operating_state.extensions.get(
                            "solver_validation_state"
                        )
                        or {}
                    )
                ),
            )
            if self._network_pack is not None else None
        )
        year_contract = StagedMarketYearResult(
            f"{model_input.run_id}:staged:{model_input.year}",
            model_input.run_id,
            model_input.year,
            self.id,
            self.version,
            str(getattr(self._balancing, "id")),
            str(getattr(self._balancing, "version")),
            ahead_hashes,
            balancing_hashes,
        )
        artifact_rows: list[ArtifactReference] = []
        if self._output_dir is not None:
            market_dir = self._output_dir / "market"
            year_path = market_dir / f"staged-market-year-{model_input.year}.json"
            year_path.write_text(
                json.dumps(year_contract.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            artifact_rows.append(ArtifactReference(
                f"market/staged-market-year-{model_input.year}.json",
                "staged-market-year-result",
                str(year_path),
                "application/json",
                checksum_sha256=_sha256_file(year_path),
                size_bytes=year_path.stat().st_size,
            ))
            fallback_audit = self._runtime_fallback_audits.get(int(model_input.year))
            if self._network_pack is not None and fallback_audit is not None:
                audit_path = market_dir / f"runtime-fallback-audit-{model_input.year}.json"
                audit_path.write_text(
                    json.dumps(fallback_audit, indent=2, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                artifact_rows.append(ArtifactReference(
                    f"market/runtime-fallback-audit-{model_input.year}.json",
                    "zonal-runtime-fallback-audit",
                    str(audit_path),
                    "application/json",
                    checksum_sha256=_sha256_file(audit_path),
                    size_bytes=audit_path.stat().st_size,
                ))
            ledger_path = market_dir / "market.sqlite"
            if ledger_path.is_file():
                artifact_rows.append(ArtifactReference(
                    "market/market.sqlite",
                    "authoritative-market-ledger",
                    str(ledger_path),
                    "application/vnd.sqlite3",
                    checksum_sha256=_sha256_file(ledger_path),
                    size_bytes=ledger_path.stat().st_size,
                ))
        artifacts = tuple(artifact_rows)
        self._invocations.append(model_input.year)
        return MarketYearResult(
            result_id=f"{model_input.run_id}:market:{model_input.year}",
            year=model_input.year,
            module_id=self.id,
            module_version=self.version,
            generation_mwh_by_asset=dict(generation),
            market_income_gbp_by_agent=dict(income),
            total_system_cost_gbp=capital + fixed_om + operating_cost,
            total_operational_cost_gbp=operating_cost,
            total_levelized_capital_cost_gbp=capital + fixed_om,
            total_demand_mwh=sum(float(value) for value in chronology.demand_mwh),
            total_generation_mwh=sum(generation.values()),
            total_blackout_mwh=total_blackout,
            total_excess_mwh=total_excess,
            period_summaries=tuple(summaries),
            artifacts=artifacts,
            extensions={
                "execution_kind": self.execution_kind,
                "live_staged_clearing_invocation": True,
                "live_invocation_sequence": list(self._invocations),
                "balancing_module": {
                    "module_id": str(getattr(self._balancing, "id")),
                    "module_version": str(getattr(self._balancing, "version")),
                },
                "staged_market_year_result": year_contract.to_dict(),
                "storage_cost_module_id": str(getattr(self._storage_cost, "id", "")),
                "storage_cost_observations": storage_reports,
                "final_storage_soc_mwh_by_asset": last_soc_by_base,
                "actual_storage_discharge_mwh_by_asset": dict(actual_storage_discharge),
                CAPITAL_COST_COMPONENTS_KEY: capital_cost_components(model_input.operating_state.assets),
                agent_cashflow.EXTENSION_KEY: _staged_agent_cashflow(
                    self.id, generation, chronology.resources, base_by_asset,
                    model_input.operating_state.assets,
                    variable_cost_gbp_by_asset={
                        key[len(AGENT_VARIABLE_COST_PREFIX):]: float(value)
                        for key, value in zonal_account_totals.items()
                        if key.startswith(AGENT_VARIABLE_COST_PREFIX)
                    },
                ),
                "national_settlement_gbp_by_owner": dict(national_settlement),
                "redispatch_settlement_gbp_by_owner": dict(redispatch_settlement),
                "market_income_identity": "economic_owner",
                "policy_payment_gbp_by_owner": {},
                "final_dispatch_mwh_by_physical_asset": dict(final_dispatch_annual),
                "network_pack": (
                    {
                        "network_pack_id": self._network_pack.network_pack_id,
                        "scientific_sha256": self._network_pack.scientific_sha256,
                    }
                    if self._network_pack is not None else None
                ),
                "zonal_demand_alignment": (
                    dict(demand_alignment.summary)
                    if demand_alignment is not None else None
                ),
                "comparison_input_evidence": comparison_input_evidence,
                "weather_spatializer": (
                    {
                        "module_id": self._weather_spatializer_identity[0],
                        "module_version": self._weather_spatializer_identity[1],
                    }
                    if self._weather_spatializer_identity is not None else None
                ),
                "total_boundary_export_mwh": total_export,
                "physical_operating_cost_components_gbp": {
                    "generation_import_and_reliability": (
                        operating_cost - operating_cost_by_class.get("storage", 0.0)
                    ),
                    "storage_cycle_depreciation": operating_cost_by_class.get(
                        "storage", 0.0
                    ),
                },
                "zonal_accounting_gbp": (
                    {
                        "system_resource_cost_gbp": capital + fixed_om + operating_cost,
                        "transmission_constraint_resource_cost_gbp": zonal_account_totals[
                            "transmission_constraint_resource_cost_gbp"
                        ],
                        "national_settlement_gbp": zonal_account_totals[
                            "national_settlement_gbp"
                        ],
                        "redispatch_settlement_gbp": zonal_account_totals[
                            "redispatch_settlement_gbp"
                        ],
                        "policy_transfer_gbp": zonal_account_totals[
                            "policy_transfer_gbp"
                        ],
                        # P0-8 S9: the same difference on the accepted-bid
                        # objective basis (zonal minus network-free primary).
                        "network_constraint_bid_objective_gbp": zonal_account_totals[
                            "network_constraint_bid_objective_gbp"
                        ],
                        "boundary_shadow_value_gbp": 0.0,
                    }
                    if self._network_pack is not None else None
                ),
                "market_ledger": ledger_metadata,
                "network_method_rules": self._network_rules.record(),
                "solver_validation_summary": solver_validation_summary,
                "vre_expansion_headroom_mw_by_technology": dict(
                    chronology.extensions.get("vre_expansion_headroom_mw_by_technology") or {}
                ),
            },
        )
