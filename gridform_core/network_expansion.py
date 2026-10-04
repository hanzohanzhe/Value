"""Typed transmission-expansion lifecycle for the optional network CEM slot."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Sequence

from .network_contracts import NetworkBranch, NetworkPSMInput, NetworkTopology
from .v2.contracts import JsonContract, MarketYearResult, OperatingState, ResolvedRun, YearState


STATE_KEY = "value.network.expansion"
STATE_SCHEMA = "value.network-expansion-state/v1"


def _crf(rate: float, life: float) -> float:
    if rate == 0:
        return 1.0 / life
    return rate * (1 + rate) ** life / ((1 + rate) ** life - 1)


@dataclass(frozen=True)
class NetworkAsset(JsonContract):
    asset_id: str
    source_candidate_id: str
    source_project_id: str
    corridor_id: str
    from_bus: str
    to_bus: str
    technology: str
    circuits: int
    thermal_rating_mw_per_circuit: float
    apparent_power_rating_mva_per_circuit: float | None
    resistance_pu: float | None
    reactance_pu: float | None
    charging_susceptance_pu: float | None
    tap_ratio: float | None
    phase_shift_degrees: float | None
    owner_id: str
    planner_id: str
    total_capex_gbp: float
    annual_fixed_opex_gbp: float
    construction_life_years: float
    economic_life_years: float
    discount_rate: float
    annualized_capex_gbp: float
    commissioning_year: int
    retirement_year: int
    embodied_carbon_factor_tco2e_per_mw: float | None
    embodied_carbon_allocation: str
    embodied_carbon_source: Mapping[str, object]
    status: str = "commissioned"
    residual_value_gbp: float = 0.0
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-asset/v1"


@dataclass(frozen=True)
class NetworkCandidate(JsonContract):
    candidate_id: str
    corridor_id: str
    from_bus: str
    to_bus: str
    technology: str
    circuits_per_build: int
    max_build_circuits: int
    thermal_rating_mw_per_circuit: float
    apparent_power_rating_mva_per_circuit: float | None
    resistance_pu: float | None
    reactance_pu: float | None
    charging_susceptance_pu: float | None
    tap_ratio: float | None
    phase_shift_degrees: float | None
    owner_id: str
    planner_id: str
    total_capex_gbp_per_build: float
    annual_fixed_opex_gbp_per_build: float
    construction_life_years: float
    economic_life_years: float
    discount_rate: float
    lead_time_years: int
    success_probability: float
    budget_group: str
    trigger_branch_ids: Sequence[str]
    trigger_branch_rating_mw: float
    minimum_trigger_utilisation: float
    declared_annual_benefit_gbp: float
    minimum_benefit_cost_ratio: float
    earliest_decision_year: int
    embodied_carbon_factor_tco2e_per_mw: float | None = None
    embodied_carbon_allocation: str = "commissioning_year_once"
    embodied_carbon_source: Mapping[str, object] = field(default_factory=dict)
    delay_years: int = 0
    source: str = "external_candidate_catalogue"
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-candidate/v1"


@dataclass(frozen=True)
class NetworkInvestmentProposal(JsonContract):
    proposal_id: str
    candidate_id: str
    corridor_id: str
    year: int
    circuits: int
    added_rating_mw: float
    committed_capex_gbp: float
    annual_fixed_opex_gbp: float
    observed_trigger_utilisation: float
    declared_annual_benefit_gbp: float
    benefit_cost_ratio: float
    information_structure: str
    objective: str
    expected_completion_year: int
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-investment-proposal/v1"


@dataclass(frozen=True)
class NetworkPlanningProject(JsonContract):
    project_id: str
    proposal_id: str
    candidate_id: str
    corridor_id: str
    from_bus: str
    to_bus: str
    circuits: int
    added_rating_mw: float
    development_stage: str
    status: str
    decision_year: int
    expected_completion_year: int
    success_probability: float
    random_draw: float
    owner_id: str
    planner_id: str
    source: str
    provenance: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-planning-project/v1"


@dataclass(frozen=True)
class NetworkCommissioningEvent(JsonContract):
    event_id: str
    event_type: str
    year: int
    candidate_id: str
    project_id: str | None
    asset_id: str | None
    corridor_id: str
    from_bus: str
    to_bus: str
    circuits: int
    rating_mw: float
    reason_code: str
    lineage: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = "value.network-commissioning-event/v1"


@dataclass(frozen=True)
class NetworkExpansionAdvanceResult(JsonContract):
    year: int
    state: YearState
    active_projects: Sequence[NetworkPlanningProject]
    commissioned_assets: Sequence[NetworkAsset]
    retired_assets: Sequence[NetworkAsset]
    events: Sequence[NetworkCommissioningEvent]
    schema_version: str = "value.network-expansion-advance/v1"


@dataclass(frozen=True)
class NetworkExpansionDecision(JsonContract):
    year: int
    module_id: str
    proposals: Sequence[NetworkInvestmentProposal]
    annual_budget_gbp: float
    committed_budget_gbp: float
    remaining_budget_gbp: float
    rejected: Sequence[Mapping[str, object]]
    schema_version: str = "value.network-expansion-decision/v1"


@dataclass(frozen=True)
class NetworkExpansionAdmission(JsonContract):
    year: int
    admitted_projects: Sequence[NetworkPlanningProject]
    failed_proposals: Sequence[NetworkInvestmentProposal]
    next_projects: Sequence[NetworkPlanningProject]
    events: Sequence[NetworkCommissioningEvent]
    schema_version: str = "value.network-expansion-admission/v1"


def _payload(state: YearState | OperatingState) -> dict[str, object]:
    value = state.extensions.get(STATE_KEY)
    if not isinstance(value, Mapping):
        return {
            "owner": "value-network-expansion-extension",
            "schema_version": STATE_SCHEMA,
            "candidates": [], "assets": [], "projects": [], "events": [],
        }
    if value.get("schema_version") != STATE_SCHEMA:
        raise ValueError("Network expansion state schema is incompatible")
    if value.get("owner") != "value-network-expansion-extension":
        raise ValueError("Network expansion state has the wrong extension owner")
    return dict(value)


def _with_payload(state: YearState, payload: Mapping[str, object]) -> YearState:
    return replace(state, extensions={**dict(state.extensions), STATE_KEY: dict(payload)})


def load_network_expansion_state(
    pack_root: Path,
    manifest: Mapping[str, object],
    state: YearState,
) -> YearState:
    bindings = dict(manifest.get("bindings") or {})
    binding = (
        bindings.get("value.network.expansion.candidates")
        or bindings.get("value.network.expansion-candidates")
    )
    if not isinstance(binding, Mapping):
        raise ValueError(
            "Selected network expansion requires value.network.expansion.candidates"
        )
    path = (pack_root / str(binding.get("uri") or "")).resolve()
    try:
        path.relative_to(pack_root.resolve())
    except ValueError as exc:
        raise ValueError("Network expansion candidate binding escapes the pack") from exc
    if not path.is_file():
        raise ValueError("Network expansion candidate catalogue is missing")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("candidates") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, list):
        raise ValueError("Network expansion catalogue must contain a candidates array")
    candidates = tuple(NetworkCandidate.from_dict(item) for item in rows)
    ids = [item.candidate_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("Network expansion catalogue has duplicate candidate IDs")
    for candidate in candidates:
        if candidate.from_bus == candidate.to_bus:
            raise ValueError(f"Candidate {candidate.candidate_id} is a self-loop")
        if candidate.technology not in {"ac_line", "transformer", "dc_link"}:
            raise ValueError(f"Candidate {candidate.candidate_id} has invalid technology")
        if candidate.circuits_per_build < 1 or candidate.max_build_circuits < candidate.circuits_per_build:
            raise ValueError(f"Candidate {candidate.candidate_id} has invalid circuit limits")
        if candidate.total_capex_gbp_per_build < 0 or candidate.annual_fixed_opex_gbp_per_build < 0:
            raise ValueError(f"Candidate {candidate.candidate_id} has invalid costs")
        if not 0 <= candidate.success_probability <= 1:
            raise ValueError(f"Candidate {candidate.candidate_id} has invalid success probability")
        if candidate.embodied_carbon_factor_tco2e_per_mw is not None and not candidate.embodied_carbon_source:
            raise ValueError(f"Candidate {candidate.candidate_id} has an unprovenanced carbon factor")
    return _with_payload(state, {
        "owner": "value-network-expansion-extension",
        "schema_version": STATE_SCHEMA,
        "candidates": [item.to_dict() for item in candidates],
        "assets": [], "projects": [], "events": [],
        "source_catalogue": path.relative_to(pack_root).as_posix(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })


class ReferenceTransmissionExpansion:
    id = "reference-transmission-expansion"
    version = "1.0.0"

    def advance_year(self, run: ResolvedRun, state: YearState) -> NetworkExpansionAdvanceResult:
        payload = _payload(state)
        candidates = {
            item.candidate_id: item
            for item in (NetworkCandidate.from_dict(row) for row in payload.get("candidates", ()))
        }
        assets = [NetworkAsset.from_dict(row) for row in payload.get("assets", ())]
        projects = [NetworkPlanningProject.from_dict(row) for row in payload.get("projects", ())]
        events = [NetworkCommissioningEvent.from_dict(row) for row in payload.get("events", ())]
        active: list[NetworkPlanningProject] = []
        commissioned: list[NetworkAsset] = []
        retired: list[NetworkAsset] = []
        current_assets: list[NetworkAsset] = []
        for asset in assets:
            if asset.status == "commissioned" and asset.retirement_year <= state.year:
                retired_asset = replace(asset, status="retired")
                retired.append(retired_asset)
                current_assets.append(retired_asset)
                events.append(NetworkCommissioningEvent(
                    f"{run.run_id}:{state.year}:network-retire:{asset.asset_id}",
                    "retired", state.year, asset.source_candidate_id,
                    asset.source_project_id, asset.asset_id, asset.corridor_id,
                    asset.from_bus, asset.to_bus, asset.circuits,
                    asset.thermal_rating_mw_per_circuit * asset.circuits,
                    "economic_life_complete",
                    {"source_asset_id": asset.asset_id},
                ))
            else:
                current_assets.append(asset)
        for project in projects:
            if project.expected_completion_year > state.year:
                active.append(project)
                continue
            candidate = candidates[project.candidate_id]
            existing_circuits = sum(
                item.circuits for item in current_assets
                if item.source_candidate_id == candidate.candidate_id and item.status == "commissioned"
            )
            if existing_circuits + project.circuits > candidate.max_build_circuits:
                raise ValueError(f"Commissioning {project.project_id} exceeds the shared corridor limit")
            asset_id = f"network:{project.project_id}"
            if any(item.asset_id == asset_id for item in current_assets):
                raise ValueError(f"Duplicate commissioned network asset {asset_id}")
            annualized = _crf(candidate.discount_rate, candidate.economic_life_years) * candidate.total_capex_gbp_per_build
            asset = NetworkAsset(
                asset_id, candidate.candidate_id, project.project_id,
                candidate.corridor_id, candidate.from_bus, candidate.to_bus,
                candidate.technology, project.circuits,
                candidate.thermal_rating_mw_per_circuit,
                candidate.apparent_power_rating_mva_per_circuit,
                candidate.resistance_pu, candidate.reactance_pu,
                candidate.charging_susceptance_pu, candidate.tap_ratio,
                candidate.phase_shift_degrees, candidate.owner_id,
                candidate.planner_id, candidate.total_capex_gbp_per_build,
                candidate.annual_fixed_opex_gbp_per_build,
                candidate.construction_life_years, candidate.economic_life_years,
                candidate.discount_rate, annualized, state.year,
                state.year + int(math.ceil(candidate.economic_life_years)),
                candidate.embodied_carbon_factor_tco2e_per_mw,
                candidate.embodied_carbon_allocation,
                dict(candidate.embodied_carbon_source),
                provenance={
                    **dict(candidate.provenance),
                    "candidate_source": candidate.source,
                    "proposal_id": project.proposal_id,
                    "decision_year": project.decision_year,
                },
            )
            current_assets.append(asset)
            commissioned.append(asset)
            events.append(NetworkCommissioningEvent(
                f"{run.run_id}:{state.year}:network-commission:{project.project_id}",
                "commissioned", state.year, candidate.candidate_id,
                project.project_id, asset.asset_id, candidate.corridor_id,
                candidate.from_bus, candidate.to_bus, project.circuits,
                project.added_rating_mw, "planning_complete",
                {
                    "proposal_id": project.proposal_id,
                    "candidate_id": candidate.candidate_id,
                    "annualized_capex_gbp": annualized,
                    "annual_fixed_opex_gbp": asset.annual_fixed_opex_gbp,
                },
            ))
        next_payload = {
            **payload,
            "assets": [item.to_dict() for item in current_assets],
            "projects": [item.to_dict() for item in active],
            "events": [item.to_dict() for item in events],
        }
        next_state = _with_payload(state, next_payload)
        return NetworkExpansionAdvanceResult(
            state.year, next_state, tuple(active), tuple(commissioned),
            tuple(retired), tuple(events[-(len(commissioned) + len(retired)):])
            if commissioned or retired else (),
        )

    def propose(
        self, run: ResolvedRun, state: OperatingState, market: MarketYearResult
    ) -> NetworkExpansionDecision:
        payload = _payload(state)
        candidates = [NetworkCandidate.from_dict(row) for row in payload.get("candidates", ())]
        assets = [NetworkAsset.from_dict(row) for row in payload.get("assets", ())]
        projects = [NetworkPlanningProject.from_dict(row) for row in payload.get("projects", ())]
        network = market.extensions.get("network")
        if not isinstance(network, Mapping):
            raise ValueError("Transmission expansion requires actual network PSM results")
        periods = network.get("periods")
        if not isinstance(periods, Sequence):
            raise ValueError("Network result has no period flow chronology")
        annual_budget = float(run.scientific_parameters.get("network.expansion.annual_budget_gbp", 0.0))
        if not math.isfinite(annual_budget) or annual_budget < 0:
            raise ValueError("Network expansion annual budget is invalid")
        group_budget = float(
            run.scientific_parameters.get("network.expansion.group_budget_gbp", annual_budget)
        )
        group_used: dict[str, float] = {}
        remaining = annual_budget
        proposed: list[NetworkInvestmentProposal] = []
        rejected: list[Mapping[str, object]] = []
        occupied = {item.source_candidate_id for item in assets if item.status == "commissioned"} | {
            item.candidate_id for item in projects
        }
        ranked = []
        for candidate in candidates:
            if candidate.candidate_id in occupied or state.year < candidate.earliest_decision_year:
                continue
            flows = [
                abs(float(dict(period.get("branch_flow_mw") or {}).get(branch_id, 0.0)))
                for period in periods
                for branch_id in candidate.trigger_branch_ids
            ]
            utilisation = max(flows, default=0.0) / candidate.trigger_branch_rating_mw
            annual_cost = (
                _crf(candidate.discount_rate, candidate.economic_life_years)
                * candidate.total_capex_gbp_per_build
                + candidate.annual_fixed_opex_gbp_per_build
            )
            ratio = candidate.declared_annual_benefit_gbp / annual_cost if annual_cost else math.inf
            ranked.append((ratio, utilisation, candidate))
        for ratio, utilisation, candidate in sorted(
            ranked, key=lambda item: (-item[0], item[2].candidate_id)
        ):
            reason = None
            if utilisation < candidate.minimum_trigger_utilisation:
                reason = "congestion_trigger_not_met"
            elif ratio < candidate.minimum_benefit_cost_ratio:
                reason = "declared_benefit_cost_ratio_below_threshold"
            elif candidate.total_capex_gbp_per_build > remaining:
                reason = "shared_system_budget_exhausted"
            group_limit = group_budget
            if reason is None and group_used.get(candidate.budget_group, 0.0) + candidate.total_capex_gbp_per_build > group_limit:
                reason = "shared_budget_group_exhausted"
            if reason:
                rejected.append({
                    "candidate_id": candidate.candidate_id,
                    "reason_code": reason,
                    "observed_utilisation": utilisation,
                })
                continue
            proposal_id = f"network-proposal:{run.run_id}:{state.year}:{candidate.candidate_id}"
            proposed.append(NetworkInvestmentProposal(
                proposal_id, candidate.candidate_id, candidate.corridor_id,
                state.year, candidate.circuits_per_build,
                candidate.thermal_rating_mw_per_circuit * candidate.circuits_per_build,
                candidate.total_capex_gbp_per_build,
                candidate.annual_fixed_opex_gbp_per_build, utilisation,
                candidate.declared_annual_benefit_gbp, ratio,
                "one_year_observed_dc_congestion_no_future_foresight",
                "central_planner_declared_benefit_cost_screen",
                state.year + candidate.lead_time_years + candidate.delay_years,
                {"candidate_source": candidate.source, **dict(candidate.provenance)},
            ))
            remaining -= candidate.total_capex_gbp_per_build
            group_used[candidate.budget_group] = (
                group_used.get(candidate.budget_group, 0.0)
                + candidate.total_capex_gbp_per_build
            )
        return NetworkExpansionDecision(
            state.year, self.id, tuple(proposed), annual_budget,
            annual_budget - remaining, remaining, tuple(rejected),
        )

    def admit(
        self, run: ResolvedRun, state: OperatingState,
        decision: NetworkExpansionDecision,
    ) -> NetworkExpansionAdmission:
        payload = _payload(state)
        candidates = {
            item.candidate_id: item
            for item in (NetworkCandidate.from_dict(row) for row in payload.get("candidates", ()))
        }
        existing = [NetworkPlanningProject.from_dict(row) for row in payload.get("projects", ())]
        admitted: list[NetworkPlanningProject] = []
        failed: list[NetworkInvestmentProposal] = []
        events: list[NetworkCommissioningEvent] = []
        seed = int(run.scientific_parameters.get("network.expansion.random_seed", 0))
        for proposal in decision.proposals:
            candidate = candidates[proposal.candidate_id]
            digest = hashlib.sha256(f"{seed}:{proposal.proposal_id}".encode()).hexdigest()
            draw = int(digest[:13], 16) / float(16 ** 13 - 1)
            if draw > candidate.success_probability:
                failed.append(proposal)
                events.append(NetworkCommissioningEvent(
                    f"{run.run_id}:{state.year}:network-failed:{candidate.candidate_id}",
                    "failed", state.year, candidate.candidate_id, None, None,
                    candidate.corridor_id, candidate.from_bus, candidate.to_bus,
                    proposal.circuits, proposal.added_rating_mw,
                    "seeded_planning_failure",
                    {"proposal_id": proposal.proposal_id, "random_draw": draw,
                     "success_probability": candidate.success_probability},
                ))
                continue
            project = NetworkPlanningProject(
                proposal.proposal_id.replace("network-proposal", "network-project"),
                proposal.proposal_id, candidate.candidate_id,
                candidate.corridor_id, candidate.from_bus, candidate.to_bus,
                proposal.circuits, proposal.added_rating_mw,
                "application_submitted", "active", state.year,
                proposal.expected_completion_year, candidate.success_probability,
                draw, candidate.owner_id, candidate.planner_id,
                "model_generated_from_external_candidate",
                {"proposal": proposal.to_dict(), "candidate_source": candidate.source},
            )
            admitted.append(project)
            events.append(NetworkCommissioningEvent(
                f"{run.run_id}:{state.year}:network-admit:{candidate.candidate_id}",
                "admitted", state.year, candidate.candidate_id,
                project.project_id, None, candidate.corridor_id,
                candidate.from_bus, candidate.to_bus, proposal.circuits,
                proposal.added_rating_mw, "seeded_planning_success",
                {"proposal_id": proposal.proposal_id, "random_draw": draw,
                 "success_probability": candidate.success_probability},
            ))
        return NetworkExpansionAdmission(
            state.year, tuple(admitted), tuple(failed), tuple(existing + admitted), tuple(events)
        )

    def transition(
        self, run: ResolvedRun, next_state: YearState,
        admission: NetworkExpansionAdmission,
    ) -> YearState:
        payload = _payload(next_state)
        prior_events = list(payload.get("events", ()))
        return _with_payload(next_state, {
            **payload,
            "projects": [item.to_dict() for item in admission.next_projects],
            "events": prior_events + [item.to_dict() for item in admission.events],
        })

    def annual_resource_costs(self, state: YearState | OperatingState) -> dict[str, float]:
        assets = [NetworkAsset.from_dict(row) for row in _payload(state).get("assets", ())]
        active = [item for item in assets if item.status == "commissioned"]
        return {
            "annualized_capex_gbp": sum(item.annualized_capex_gbp for item in active),
            "fixed_opex_gbp": sum(item.annual_fixed_opex_gbp for item in active),
            "retirement_residual_value_gbp": sum(item.residual_value_gbp for item in assets if item.status == "retired"),
            "policy_support_gbp": 0.0,
        }


def apply_commissioned_network_assets(
    network: NetworkPSMInput, state: OperatingState
) -> NetworkPSMInput:
    assets = [NetworkAsset.from_dict(row) for row in _payload(state).get("assets", ())]
    branches = list(network.topology.branches)
    known_ids = {item.branch_id for item in branches}
    buses = set(network.topology.bus_by_id())
    for asset in assets:
        if asset.status != "commissioned" or asset.commissioning_year > state.year:
            continue
        if asset.asset_id in known_ids:
            raise ValueError(f"Duplicate network branch injection: {asset.asset_id}")
        if asset.from_bus not in buses or asset.to_bus not in buses:
            raise ValueError(f"Commissioned network asset {asset.asset_id} has an invalid endpoint")
        branches.append(NetworkBranch(
            asset.asset_id, asset.from_bus, asset.to_bus, asset.technology, True,
            asset.thermal_rating_mw_per_circuit,
            reactance_pu=asset.reactance_pu,
            resistance_pu=asset.resistance_pu,
            charging_susceptance_pu=asset.charging_susceptance_pu,
            tap_ratio=asset.tap_ratio,
            phase_shift_degrees=asset.phase_shift_degrees,
            apparent_power_rating_mva=asset.apparent_power_rating_mva_per_circuit,
            circuits=asset.circuits,
            provenance={
                **dict(asset.provenance),
                "network_expansion_asset": True,
                "source_project_id": asset.source_project_id,
                "commissioning_year": asset.commissioning_year,
            },
        ))
        known_ids.add(asset.asset_id)
    topology = replace(network.topology, branches=tuple(branches))
    topology.validate(capability=network.capability)
    return replace(network, topology=topology)


def adjust_carbon_ledger_for_network(
    ledger: Mapping[str, object], *, year: int, state: OperatingState
) -> dict[str, object]:
    result = json.loads(json.dumps(ledger))
    assets = [NetworkAsset.from_dict(row) for row in _payload(state).get("assets", ())]
    additions = [item for item in assets if item.commissioning_year == year and item.status == "commissioned"]
    unresolved = list(result.get("unresolved_activities") or [])
    network_total = 0.0
    lines = list(result.get("lines") or [])
    for asset in additions:
        factor = asset.embodied_carbon_factor_tco2e_per_mw
        if factor is None:
            unresolved.append(f"{asset.asset_id}:network_embodied_factor")
            lines.append({
                "asset_id": asset.asset_id, "component": "network_construction_embodied",
                "emissions_tco2e": None, "activity_mwh": None,
                "factor_record_id": None, "factor_value": None, "factor_unit": None,
                "method": "not_evaluated", "reason": "no_provenanced_factor",
            })
            continue
        rating = asset.thermal_rating_mw_per_circuit * asset.circuits
        emissions = rating * factor
        network_total += emissions
        lines.append({
            "asset_id": asset.asset_id,
            "component": "network_construction_embodied",
            "emissions_tco2e": emissions,
            "activity_mwh": None,
            "factor_record_id": asset.embodied_carbon_source.get("record_id"),
            "factor_value": factor,
            "factor_unit": "tCO2e/MW",
            "method": asset.embodied_carbon_allocation,
            "reason": None,
            "factor_provenance": dict(asset.embodied_carbon_source),
        })
    result["lines"] = lines
    result["unresolved_activities"] = unresolved
    components = dict(result.get("components_tco2e") or {})
    components["network_construction_embodied"] = network_total
    result["components_tco2e"] = components
    total = result.get("total_carbon_emissions_tco2e")
    if unresolved:
        result["status"] = "not_evaluated"
        result["total_carbon_emissions_tco2e"] = None
        result["embodied_status"] = "not_evaluated"
    elif total is not None:
        total = float(total) + network_total
        result["total_carbon_emissions_tco2e"] = total
        denominator = float(dict(result.get("intensities") or {}).get("denominator_mwh") or 0.0)
        if denominator > 0:
            result["intensities"]["overall_kgco2e_per_mwh"] = total * 1000 / denominator
            result["intensities"]["delivered_demand_kgco2e_per_mwh"] = total * 1000 / denominator
    return result


def write_network_expansion_artifacts(path: Path, results: Sequence[object]) -> tuple[Path, Path]:
    path.mkdir(parents=True, exist_ok=True)
    rows = []
    for result in results:
        value = getattr(result, "extensions", {}).get("network_expansion")
        if value:
            rows.append({"year": getattr(result, "year"), **dict(value)})
    json_path = path / "network-expansion.json"
    json_path.write_text(json.dumps({
        "schema_version": "value.network-expansion-history/v1", "years": rows,
    }, indent=2), encoding="utf-8")
    sqlite_path = path / "network-expansion.sqlite"
    if sqlite_path.exists():
        sqlite_path.unlink()
    with closing(sqlite3.connect(sqlite_path)) as connection:
        connection.executescript("""
        CREATE TABLE annual_summary(year INTEGER PRIMARY KEY, proposals INTEGER, admitted INTEGER, commissioned INTEGER, failed INTEGER, retired INTEGER);
        CREATE TABLE events(year INTEGER, event_id TEXT PRIMARY KEY, event_type TEXT, candidate_id TEXT, project_id TEXT, asset_id TEXT, corridor_id TEXT, from_bus TEXT, to_bus TEXT, circuits INTEGER, rating_mw REAL, reason_code TEXT, payload_json TEXT);
        """)
        for row in rows:
            decision = dict(row.get("decision") or {})
            admission = dict(row.get("admission") or {})
            advance = dict(row.get("advance") or {})
            connection.execute(
                "INSERT INTO annual_summary VALUES (?,?,?,?,?,?)",
                (row["year"], len(decision.get("proposals") or []),
                 len(admission.get("admitted_projects") or []),
                 len(advance.get("commissioned_assets") or []),
                 len(admission.get("failed_proposals") or []),
                 len(advance.get("retired_assets") or [])),
            )
            for event in list(advance.get("events") or []) + list(admission.get("events") or []):
                connection.execute(
                    "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row["year"], event["event_id"], event["event_type"],
                     event["candidate_id"], event.get("project_id"), event.get("asset_id"),
                     event["corridor_id"], event["from_bus"], event["to_bus"],
                     event["circuits"], event["rating_mw"], event["reason_code"],
                     json.dumps(event, sort_keys=True)),
                )
        connection.commit()
    return json_path, sqlite_path
