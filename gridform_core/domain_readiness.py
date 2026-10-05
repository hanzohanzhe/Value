"""Bounded, canonical input summaries for optional physical-system domains.

The functions in this module do not solve a Study.  They call the same pack
adapters used by run preparation, then reduce the resulting typed contracts to
small provenance-bearing summaries for preflight and the local website.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from .canonical_psm_data import build_chronology, native_initial_state
from .hydrology import HydrologyInputBundle, load_hydrology_inputs_from_pack
from .network_ac import ACGeneratorSpec, load_ac_data_from_pack
from .network_contracts import NetworkPSMInput, load_network_input_from_pack
from .network_expansion import STATE_KEY, NetworkCandidate, load_network_expansion_state
from .parameters import resolve_scheme_c_parameters
from .runtime_capabilities import VALUE_NATIVE, capability_status
from .v2.module_manifest import ModuleRegistryV2
from .zonal_contracts import (
    ZonalNetworkPack,
    ZonalTopologyError,
    audit_zonal_network_topology,
    pack_fallback_assets,
    load_zonal_network_pack,
)


SCHEMA_VERSION = "value.domain-readiness/v1"
MAX_PREVIEW_PERIODS = 336


def _metric(
    value: object,
    *,
    definition_id: str,
    unit: str,
    source_sha256: object = None,
    status: str = "available",
) -> dict[str, object]:
    return {
        "value": value,
        "unit": unit,
        "definition_id": definition_id,
        "source_sha256": source_sha256,
        "status": status,
    }


def _issue(
    code: str,
    message: str,
    *,
    severity: str,
    scope: str,
    control: str,
    corrective_action: str,
) -> dict[str, str]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "scope": scope,
        "control": control,
        "corrective_action": corrective_action,
    }


def _binding_hashes(
    pack_root: Path, manifest: Mapping[str, object], roles: Sequence[str]
) -> dict[str, str]:
    bindings = dict(manifest.get("bindings") or {})
    result: dict[str, str] = {}
    for role in roles:
        binding = bindings.get(role)
        if not isinstance(binding, Mapping):
            continue
        path = (pack_root / str(binding.get("uri") or "")).resolve()
        try:
            path.relative_to(pack_root.resolve())
        except ValueError:
            continue
        if path.is_file():
            result[role] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def summarise_network_input(
    model: NetworkPSMInput,
    *,
    source_sha256: Mapping[str, str],
) -> dict[str, object]:
    """Reduce one already-validated canonical network input."""

    model.validate()
    topology = model.topology
    islands = topology.islands()
    by_bus = topology.bus_by_id()
    mapping_counts = Counter(item.asset_class for item in topology.asset_mappings)
    branch_counts = Counter(item.branch_type for item in topology.branches)
    maximum_reconciliation = max(
        (
            abs(
                sum(float(values[period]) for values in model.demand_mwh_by_bus.values())
                - float(model.chronology.demand_mwh[period])
            )
            for period in range(len(model.chronology.period_ids))
        ),
        default=0.0,
    )
    source_identity = dict(source_sha256)
    return {
        "status": "ready",
        "claim": "Canonical electrical topology and nodal chronology; no geographic placement is inferred.",
        "source_sha256": source_identity,
        "metrics": {
            "buses": _metric(len(topology.buses), definition_id="value.network.bus-count/v1", unit="buses", source_sha256=source_identity),
            "branches": _metric(len(topology.branches), definition_id="value.network.branch-count/v1", unit="branches", source_sha256=source_identity),
            "transformers": _metric(branch_counts.get("transformer", 0), definition_id="value.network.transformer-count/v1", unit="transformers", source_sha256=source_identity),
            "islands": _metric(len(islands), definition_id="value.network.connected-islands/v1", unit="islands", source_sha256=source_identity),
            "in_service_capacity_mw": _metric(sum(item.thermal_rating_mw * item.circuits for item in topology.branches if item.in_service), definition_id="value.network.sum-in-service-thermal-rating/v1", unit="MW-nameplate-sum", source_sha256=source_identity),
            "maximum_nodal_demand_reconciliation_residual_mwh": _metric(maximum_reconciliation, definition_id="value.network.nodal-demand-reconciliation/v1", unit="MWh/period", source_sha256=source_identity),
        },
        "islands": [
            {
                "bus_ids": list(island),
                "reference_bus": next(bus for bus in island if by_bus[bus].is_reference),
            }
            for island in islands
        ],
        "voltage_levels_kv": sorted({float(item.voltage_kv) for item in topology.buses}),
        "branch_types": dict(sorted(branch_counts.items())),
        "asset_mappings": dict(sorted(mapping_counts.items())),
        "period_coverage": {
            "count": len(model.chronology.period_ids),
            "first": model.chronology.period_ids[0] if model.chronology.period_ids else None,
            "last": model.chronology.period_ids[-1] if model.chronology.period_ids else None,
            "definition_id": "value.network.preview-chronology/v1",
        },
    }


def summarise_zonal_network_pack(model: ZonalNetworkPack) -> dict[str, object]:
    """Summarise validated zonal data without implying a power-flow model."""

    model.validate()
    constrained = {
        member.corridor_id for boundary in model.cutsets for member in boundary.members
    }
    maximum_residual = max(
        (
            abs(
                sum(values[index] for values in model.zonal_demand.demand_mwh_by_zone.values())
                - model.zonal_demand.national_demand_mwh[index]
            )
            for index in range(len(model.zonal_demand.period_ids))
        ),
        default=0.0,
    )
    return {
        "status": "data_ready",
        "claim": (
            "Fixed, lossless zonal transport inputs for redispatch; corridors are "
            "computational routing edges rather than physical transmission lines."
        ),
        "network_pack_id": model.network_pack_id,
        "scientific_sha256": model.scientific_sha256,
        "loss_capability": {
            "status": "absent",
            "reason": model.loss_capability_absent_reason,
        },
        "metrics": {
            "zones": _metric(len(model.zones), definition_id="value.zonal.zone-count/v1", unit="zones", source_sha256=model.scientific_sha256),
            "computational_corridors": _metric(len(model.corridors), definition_id="value.zonal.corridor-count/v1", unit="corridors", source_sha256=model.scientific_sha256),
            "etys_cutsets": _metric(len(model.cutsets), definition_id="value.zonal.cutset-count/v1", unit="boundaries", source_sha256=model.scientific_sha256),
            "constrained_corridors": _metric(len(constrained), definition_id="value.zonal.constrained-corridor-count/v1", unit="corridors", source_sha256=model.scientific_sha256),
            "maximum_demand_reconciliation_residual_mwh": _metric(maximum_residual, definition_id="value.zonal.demand-reconciliation/v1", unit="MWh/period", source_sha256=model.scientific_sha256),
            "fallback_assets": _metric(len(model.spatial_audit.fallback_asset_ids), definition_id="value.zonal.fallback-asset-count/v1", unit="assets", source_sha256=model.scientific_sha256),
        },
        "zone_ids": [zone.zone_id for zone in model.zones],
        "boundary_ids": [boundary.boundary_id for boundary in model.cutsets],
        "period_coverage": {
            "count": len(model.zonal_demand.period_ids),
            "first": model.zonal_demand.period_ids[0] if model.zonal_demand.period_ids else None,
            "last": model.zonal_demand.period_ids[-1] if model.zonal_demand.period_ids else None,
        },
        "source_sha256": dict(model.spatial_audit.source_sha256_by_role),
    }


def summarise_ac_input(
    model: NetworkPSMInput,
    *,
    source_sha256: Mapping[str, str],
    selected_module_ids: Sequence[str],
) -> dict[str, object]:
    """Describe the declared AC-feasibility input without running power flow."""

    model.validate()
    extensions = dict(model.extensions)
    specs = tuple(ACGeneratorSpec.from_dict(item) for item in extensions.get("generator_specs", ()))
    reactive = dict(extensions.get("reactive_demand_mvar_by_bus") or {})
    schedule = dict(extensions.get("active_schedule_mwh_by_asset") or {})
    initial = dict(extensions.get("initial_voltage") or {})
    resources = {item.asset_id for item in model.chronology.resources}
    source_identity = dict(source_sha256)
    runtime = capability_status(VALUE_NATIVE, selected_module_ids=selected_module_ids)
    return {
        "status": "experimental",
        "claim": "Local feasibility of a declared active-power schedule; this is not AC OPF.",
        "source_sha256": source_identity,
        "metrics": {
            "generator_specs": _metric(len(specs), definition_id="value.ac.generator-spec-count/v1", unit="assets", source_sha256=source_identity),
            "active_schedule_coverage": _metric(len(resources.intersection(schedule)), definition_id="value.ac.active-schedule-resource-coverage/v1", unit=f"of {len(resources)} resources", source_sha256=source_identity),
            "reactive_demand_bus_coverage": _metric(len(reactive), definition_id="value.ac.reactive-demand-bus-coverage/v1", unit=f"of {len(model.topology.buses)} buses", source_sha256=source_identity),
            "initial_voltage_bus_coverage": _metric(len(initial), definition_id="value.ac.initial-voltage-bus-coverage/v1", unit=f"of {len(model.topology.buses)} buses", source_sha256=source_identity),
        },
        "slack_assets": sorted(item.asset_id for item in specs if item.slack_balancer),
        "generator_pq_limits": {
            item.asset_id: {
                "active_mw": [item.active_min_mw, item.active_max_mw],
                "reactive_mvar": [item.reactive_min_mvar, item.reactive_max_mvar],
                "voltage_setpoint_pu": item.voltage_setpoint_pu,
            }
            for item in specs
        },
        "bus_voltage_limits_pu": {
            item.bus_id: [item.voltage_min_pu, item.voltage_max_pu]
            for item in model.topology.buses
        },
        "declared_schedule_source": "value.network.ac.active-schedule",
        "solver_runtime": runtime,
        "initial_state": "declared" if initial else "flat and alternate starts generated by the AC feasibility module",
    }


def summarise_hydrology_input(bundle: HydrologyInputBundle) -> dict[str, object]:
    """Describe canonical natural-flow hydro and make the pumped-hydro boundary explicit."""

    by_type = Counter(item.technology_class for item in bundle.sites)
    chronology = {
        site_id: {
            "periods": len(series.period_ids),
            "first": series.period_ids[0] if series.period_ids else None,
            "last": series.period_ids[-1] if series.period_ids else None,
            "unit": series.unit,
            "interval_hours": series.interval_hours,
            "timezone": series.timezone,
        }
        for site_id, series in {
            **bundle.run_of_river_inflows,
            **bundle.reservoir_inflows,
        }.items()
    }
    return {
        "status": "experimental",
        "claim": "Natural run-of-river and conventional-reservoir inputs only; pumped hydro remains electrical storage.",
        "source_sha256": dict(bundle.source_sha256),
        "metrics": {
            "run_of_river_sites": _metric(by_type.get("run_of_river", 0), definition_id="value.hydrology.run-of-river-site-count/v1", unit="sites", source_sha256=bundle.source_sha256),
            "reservoir_sites": _metric(by_type.get("reservoir", 0), definition_id="value.hydrology.reservoir-site-count/v1", unit="sites", source_sha256=bundle.source_sha256),
            "asset_site_mappings": _metric(len(bundle.asset_site_mappings), definition_id="value.hydrology.asset-site-map-count/v1", unit="mappings", source_sha256=bundle.source_sha256),
        },
        "sites": [
            {
                "site_id": item.site_id,
                "technology_class": item.technology_class,
                "bus_id": item.bus_id,
                "capacity_mw": item.capacity_mw,
                "turbine_efficiency": item.turbine_efficiency,
                "conversion_mwh_per_water_unit": item.conversion_mwh_per_water_unit,
                "provenance": dict(item.provenance),
            }
            for item in bundle.sites
        ],
        "chronology": chronology,
        "reservoir_parameters": {
            site_id: {
                "volume_bounds": [item.min_volume, item.max_volume],
                "initial_volume": item.initial_volume,
                "terminal_volume": item.terminal_volume,
                "release_bounds_per_period": [
                    item.minimum_environmental_release_per_period,
                    item.max_total_release_per_period,
                ],
                "turbine_release_limit_per_period": item.max_turbine_release_per_period,
                "conversion_mwh_per_water_unit": item.conversion_mwh_per_water_unit,
                "information_structure": item.information_structure,
                "water_unit": item.water_unit,
            }
            for site_id, item in bundle.reservoir_parameters.items()
        },
        "pumped_hydro_included": False,
        "new_build_capex_evidence": {
            "status": "not_evaluated",
            "reason": "The hydrology input contract does not itself authorise a new hydro investment project.",
        },
    }


def summarise_expansion_input(
    candidates: Sequence[NetworkCandidate],
    *,
    source_sha256: str | None,
    annual_budget_gbp: float,
    group_budget_gbp: float,
    topology_bus_ids: Sequence[str],
) -> tuple[dict[str, object], list[dict[str, str]]]:
    bus_ids = set(topology_bus_ids)
    endpoint_errors = sorted(
        item.candidate_id
        for item in candidates
        if item.from_bus not in bus_ids or item.to_bus not in bus_ids
    )
    issues: list[dict[str, str]] = []
    if endpoint_errors:
        issues.append(_issue(
            "GF_DOMAIN_EXPANSION_ENDPOINT",
            "Expansion candidates reference buses outside the selected topology: " + ", ".join(endpoint_errors),
            severity="error", scope="network_expansion", control="data",
            corrective_action="Correct value.network.expansion.candidates endpoints or the Network bus contract.",
        ))
    if annual_budget_gbp <= 0 or group_budget_gbp <= 0:
        issues.append(_issue(
            "GF_DOMAIN_EXPANSION_ZERO_BUDGET",
            "The declared transmission-expansion budget is zero; proposals are disabled.",
            severity="warning", scope="network_expansion", control="studies",
            corrective_action="Set a positive reviewed network expansion budget in Advanced settings to enable proposals.",
        ))
    summary = {
        "status": "experimental" if not endpoint_errors else "blocked",
        "claim": "Candidate corridors are distinct from existing network stock and become operational only after the planning lifecycle commissions them.",
        "source_sha256": source_sha256,
        "metrics": {
            "candidates": _metric(len(candidates), definition_id="value.network-expansion.candidate-count/v1", unit="candidates", source_sha256=source_sha256),
            "maximum_build_capacity_mw": _metric(sum(item.max_build_circuits * item.thermal_rating_mw_per_circuit for item in candidates), definition_id="value.network-expansion.maximum-catalogue-rating/v1", unit="MW-nameplate-sum", source_sha256=source_sha256),
            "annual_budget_gbp": _metric(annual_budget_gbp, definition_id="value.network-expansion.annual-budget/v1", unit="GBP/year", source_sha256="Study parameter"),
            "group_budget_gbp": _metric(group_budget_gbp, definition_id="value.network-expansion.shared-group-budget/v1", unit="GBP/year", source_sha256="Study parameter"),
        },
        "candidate_rows": [
            {
                "candidate_id": item.candidate_id,
                "corridor_id": item.corridor_id,
                "endpoints": [item.from_bus, item.to_bus],
                "technology": item.technology,
                "maximum_circuits": item.max_build_circuits,
                "rating_mw_per_circuit": item.thermal_rating_mw_per_circuit,
                "reactance_pu": item.reactance_pu,
                "capex_gbp_per_build": item.total_capex_gbp_per_build,
                "fom_gbp_per_build_year": item.annual_fixed_opex_gbp_per_build,
                "lead_time_years": item.lead_time_years,
                "economic_life_years": item.economic_life_years,
                "success_probability": item.success_probability,
                "budget_group": item.budget_group,
                "embodied_carbon_status": "available" if item.embodied_carbon_factor_tco2e_per_mw is not None else "not_evaluated",
            }
            for item in candidates
        ],
    }
    return summary, issues


def build_domain_readiness(
    project: Mapping[str, object],
    *,
    pack_root: Path,
    pack_manifest: Mapping[str, object],
    registry: ModuleRegistryV2,
    requested_periods: int,
    network_pack_root: Path | None = None,
    network_pack_manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Resolve all selected domain previews, returning failures as typed issues."""

    selected = dict(project.get("modules") or {})
    extensions = tuple(str(item) for item in project.get("selected_extensions", ()))
    preview_periods = max(1, min(int(requested_periods), MAX_PREVIEW_PERIODS))
    sections: dict[str, object] = {}
    issues: list[dict[str, str]] = []
    psm_id = str(selected.get("psm") or "")
    psm_manifest = None
    try:
        psm_manifest = registry.manifest(psm_id, expected_slot="psm")
    except ValueError as exc:
        issues.append(_issue(
            "GF_DOMAIN_PSM_UNKNOWN", str(exc), severity="error", scope="system",
            control="modules", corrective_action="Choose a registered PSM module.",
        ))
    capabilities = set(psm_manifest.provides_capabilities if psm_manifest else ())
    network_selected = bool(capabilities.intersection({"domain.network.dc", "domain.network.ac"}))
    hydrology_selected = "value-hydrology-extension" in extensions
    expansion_selected = (
        "value-network-expansion-extension" in extensions
        or "network_expansion" in selected
    )
    zonal_selected = "value-zonal-redispatch-extension" in extensions
    if not network_selected and not zonal_selected:
        sections["system"] = {
            "status": "ready",
            "claim": "Single-node system: internal transmission is not represented; interconnectors are boundary offers.",
            "metrics": {},
        }
    chronology = None
    state = None
    resolved_parameters = None
    network = None
    if network_selected or expansion_selected:
        try:
            resolved_parameters = resolve_scheme_c_parameters(
                pack_root,
                project.get("parameters") or project.get("parameter_overrides") or {},
                project.get("runtime_options") or project.get("runtime_controls") or {},
                periods_per_year=preview_periods,
            )
            state = native_initial_state(
                pack_root,
                int(project.get("start_year") or 2025),
                capital_discount_rate=float(resolved_parameters.scientific.values.get("cost.capital_discount_rate", 0.05)),
                scientific_parameters=resolved_parameters.scientific.values,
            )
            chronology = build_chronology(
                pack_root, pack_manifest, state,
                periods=preview_periods,
                period_hours=float(resolved_parameters.scientific.values["clock.period_hours"]),
                terminal_soc_rule=str(resolved_parameters.scientific.values.get("market.perfect_foresight_terminal_soc_rule", "cyclic")),
                voll_gbp_per_mwh=float(resolved_parameters.scientific.values.get("market.voll_gbp_per_mwh", 10_000.0)),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append(_issue(
                "GF_DOMAIN_BASE_ADAPTER", str(exc), severity="error", scope="system",
                control="data", corrective_action="Correct the base pack before previewing optional physical domains.",
            ))

    if network_selected and chronology is not None and resolved_parameters is not None:
        network_roles = (
            "value.network.buses", "value.network.branches",
            "value.network.asset-map", "value.network.nodal-demand",
        )
        try:
            network = load_network_input_from_pack(
                pack_root, pack_manifest, chronology,
                run_id="domain-readiness", year=int(project.get("start_year") or 2025),
                period_hours=float(resolved_parameters.scientific.values["clock.period_hours"]),
                capability="domain.network.ac" if "domain.network.ac" in capabilities else "domain.network.dc",
                information_structure=(
                    "declared_schedule_ac_feasibility"
                    if "domain.network.ac" in capabilities
                    else "chronological_perfect_foresight"
                ),
            )
            hashes = _binding_hashes(pack_root, pack_manifest, network_roles)
            sections["network"] = summarise_network_input(network, source_sha256=hashes)
            bindings = dict(pack_manifest.get("bindings") or {})
            sections["network"]["optional_coverage"] = {
                "dynamic_ratings": "bound" if "value.network.dynamic-ratings" in bindings else "not_bound",
                "contingencies": "bound" if "value.network.contingencies" in bindings else "not_bound",
            }
            if "domain.network.ac" in capabilities:
                ac_roles = (
                    "value.network.ac.generators", "value.network.ac.reactive-demand",
                    "value.network.ac.active-schedule", "value.network.ac.initial-voltage",
                )
                ac_network = load_ac_data_from_pack(pack_root, pack_manifest, network)
                sections["ac_feasibility"] = summarise_ac_input(
                    ac_network,
                    source_sha256=_binding_hashes(pack_root, pack_manifest, ac_roles),
                    selected_module_ids=tuple(selected.values()),
                )
                network = ac_network
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append(_issue(
                "GF_DOMAIN_NETWORK_INPUT", str(exc), severity="error", scope="network",
                control="data", corrective_action="Correct the Network or AC conditional inputs in Data.",
            ))
            sections.setdefault("network", {"status": "blocked", "error": str(exc), "metrics": {}})

    if zonal_selected:
        try:
            zonal_root = network_pack_root or pack_root
            zonal_manifest = network_pack_manifest or pack_manifest
            zonal, topology = audit_zonal_network_topology(zonal_root, zonal_manifest)
            sections["zonal_network"] = summarise_zonal_network_pack(zonal)
            sections["zonal_network"]["cutset_classification"] = dict(topology["counts"])
            # Preflight side of the P0-8 S12 fallback audit: the assets the
            # pack itself places in an unconstrained fallback zone.
            sections["zonal_network"]["fallback_assets"] = pack_fallback_assets(zonal)
            if topology["error_count"]:
                # Same rule as the enforcing loaders of preflight and runs.
                raise ZonalTopologyError(topology)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append(_issue(
                "GF_DOMAIN_ZONAL_INPUT", str(exc), severity="error", scope="zonal_network",
                control="data", corrective_action=(
                    "Correct the eight required value.zonal roles and immutable pack identity."
                ),
            ))
            sections["zonal_network"] = {"status": "blocked", "error": str(exc), "metrics": {}}

    if hydrology_selected:
        try:
            hydro = load_hydrology_inputs_from_pack(pack_root, pack_manifest)
            sections["hydrology"] = summarise_hydrology_input(hydro)
            # Prompt 66 validated the isolated water models, but the ordinary
            # annual application still has no hook that replaces natural-flow
            # hydro availability with these contracts.  Fail closed here.
            issues.append(_issue(
                "GF_HYDROLOGY_EXECUTION_NOT_WIRED",
                "Hydrology inputs are canonical, but this extension is not yet injected into the ordinary annual PSM resource chronology.",
                severity="error", scope="hydrology", control="extensions",
                corrective_action="Use the isolated Prompt 66 fixtures only; a versioned execution hook is required before launching a hydrology Study.",
            ))
            sections["hydrology"]["execution_wiring"] = "not_evaluated"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append(_issue(
                "GF_DOMAIN_HYDROLOGY_INPUT", str(exc), severity="error", scope="hydrology",
                control="data", corrective_action="Correct the five Hydrology roles; do not substitute pumped-hydro storage.",
            ))
            sections["hydrology"] = {"status": "blocked", "error": str(exc), "metrics": {}}

    if expansion_selected and state is not None and resolved_parameters is not None:
        try:
            expanded_state = load_network_expansion_state(pack_root, pack_manifest, state)
            payload = dict(expanded_state.extensions[STATE_KEY])
            candidates = tuple(NetworkCandidate.from_dict(item) for item in payload.get("candidates", ()))
            source_hash = str(payload.get("source_sha256") or "") or None
            bus_ids = [item.bus_id for item in network.topology.buses] if network is not None else []
            summary, expansion_issues = summarise_expansion_input(
                candidates,
                source_sha256=source_hash,
                annual_budget_gbp=float(resolved_parameters.scientific.values.get("network.expansion.annual_budget_gbp", 0.0)),
                group_budget_gbp=float(resolved_parameters.scientific.values.get("network.expansion.group_budget_gbp", 0.0)),
                topology_bus_ids=bus_ids,
            )
            sections["network_expansion"] = summary
            issues.extend(expansion_issues)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            issues.append(_issue(
                "GF_DOMAIN_EXPANSION_INPUT", str(exc), severity="error", scope="network_expansion",
                control="data", corrective_action="Correct candidate identity, endpoints, economics or the selected network topology.",
            ))
            sections["network_expansion"] = {"status": "blocked", "error": str(exc), "metrics": {}}

    errors = [item for item in issues if item["severity"] == "error"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked" if errors else "ready_with_warnings" if issues else "ready",
        "ready": not errors,
        "preview_periods": preview_periods,
        "requested_periods": requested_periods,
        "bounded": requested_periods > preview_periods,
        "selected_extensions": list(extensions),
        "selected_modules": selected,
        "sections": sections,
        "issues": issues,
    }
