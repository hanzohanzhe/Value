"""Native Scheme-C-derived CEM modules for the public v2 lifecycle.

Historical replay belongs to the private ``reference`` namespace and cannot be
bound into these production modules.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import replace
from typing import Mapping, Sequence

from ...asset_economics import (
    build_asset_economic_extensions,
    commissioned_asset_record,
    resize_asset_economics,
    validate_asset_economics,
)
from ...agent_cashflow import EXTENSION_KEY as AGENT_CASHFLOW_KEY, cost_rows_for_a4
from ...cem_identity import cem_identity_summary
from ...investment_accounts import (
    A4_NET_NOISE_RTOL,
    GROSS_PROFIT_TECHNOLOGIES,
    MONEY_BASIS,
    a4_net_revenue_for_decidable_groups,
    allocate_capped_requests,
)
from ...cem_investment_policy import (
    investment_mode,
    missing_site_evidence,
    policy_summary,
)
from .storage_headroom import corrected_storage_headroom, headroom_pools
from ...v2.contracts import (
    AssetStateV2,
    ExpansionHeadroom,
    InvestmentDecision,
    InvestmentProposal,
    MarketYearResult,
    OperatingState,
    PlanningAdmissionResult,
    PlanningAdvanceResult,
    PlanningProject,
    PlanningEvent,
    PlanningEventType,
    PlanningReasonCode,
    ResolvedRun,
    YearState,
)


class _NativeDefinition:
    """Marker base for direct typed execution; it has no replay binding API."""

    execution_kind = "live_module"


def run_methodology(run: ResolvedRun):
    """The methodology of ``run``: the active one inside a run, else the run's declared profile.

    Mirrors ``methodology.methodology_scoped`` for module calls made outside
    ``run_project_application`` (unit tests, tools): an absent profile is the
    default (corrected) profile.
    """
    from ...methodology import (
        PROFILE_PARAMETER,
        MethodologyMismatchError,
        active_methodology,
        resolve_methodology,
    )

    declared = run.scientific_parameters.get(PROFILE_PARAMETER)
    declared = str(declared) if declared else None
    current = active_methodology()
    if current is not None:
        if declared is not None and declared != current.profile_id:
            raise MethodologyMismatchError(
                f"run {run.run_id} declares methodology {declared} inside an active {current.profile_id} run")
        return current
    return resolve_methodology(declared)


class _ExpansionDefinition(_NativeDefinition):
    def evaluate(self, run: ResolvedRun, state: OperatingState, market: MarketYearResult) -> ExpansionHeadroom:
        if self.id == "vre-expansion-cap":
            raw = market.extensions.get("vre_expansion_headroom_mw_by_technology") or {}
            fraction = float(run.scientific_parameters.get("expansion.vre_cap_fraction", 0.20))
            limits = {
                str(key): max(0.0, float(value)) * fraction
                for key, value in dict(raw).items()
            }
            evidence = {"cap_fraction": fraction, "native_typed_execution": 1.0}
        elif run_methodology(run).enabled("p07.storage-leftover-headroom"):
            # P0-7 S6/S7 (P5-01, P5-02; value-corrected only): post-charge
            # leftover surplus, full-year guard, one power-battery pool, no
            # kernel global rebound.  The doctoral profile keeps the branch below.
            existing: defaultdict[str, float] = defaultdict(float)
            for asset in state.assets:
                if asset.capacity_mw > 0 and asset.status != "retired":
                    existing[asset.technology] += float(asset.capacity_mw)
            limits, evidence, extensions = corrected_storage_headroom(
                tuple(market.period_summaries),
                market.extensions,
                cap_fraction=float(run.scientific_parameters.get("expansion.storage_cap_fraction", 0.20)),
                period_hours=float(run.scientific_parameters.get("clock.period_hours", 0.5)),
                pooled=run_methodology(run).enabled("p07.power-battery-pool"),
                existing_mw_by_technology={
                    tech: value for tech, value in existing.items()
                    if tech in {"0.25c_battery", "0.5c_battery", "1c_battery", "hydrogen_battery", "pumped_hydro"}
                },
            )
            return ExpansionHeadroom(
                f"{run.run_id}:{self.id}:{market.year}", market.year, self.id,
                dict(limits), evidence=evidence, extensions=extensions,
            )
        else:
            # The copied aligned-utilisation calculation operates on the typed
            # period summaries emitted by the selected PSM, never on live files.
            from .storage import storage_expansion_cap as kernel

            periods = tuple(market.period_summaries)
            vre = [row.vre_accepted_mwh for row in periods]
            demand = [row.real_demand_mwh for row in periods]
            discharge = [row.storage_discharge_mwh for row in periods]
            cap_row = {
                kernel.BATTERY_CAP_COLUMNS[asset.technology]: asset.capacity_mw
                for asset in state.assets
                if asset.technology in kernel.BATTERY_CAP_COLUMNS
            }
            previous_fraction = kernel.CAP_FRACTION
            try:
                kernel.CAP_FRACTION = float(
                    run.scientific_parameters.get("expansion.storage_cap_fraction", 0.20)
                )
                limits = kernel.calculate_storage_expansion_limits_from_profiles(
                    vre,
                    demand,
                    prices=[row.clearing_price_gbp_per_mwh for row in periods],
                    cap_row=cap_row,
                    storage_discharge=discharge,
                    credit_mode="scheme_c",
                ) if periods else {}
            finally:
                kernel.CAP_FRACTION = previous_fraction
            evidence = {
                "cap_fraction": float(
                    run.scientific_parameters.get("expansion.storage_cap_fraction", 0.20)
                ),
                "native_typed_execution": 1.0,
            }
        return ExpansionHeadroom(
            f"{run.run_id}:{self.id}:{market.year}", market.year, self.id,
            dict(limits), evidence=evidence,
        )


class SchemeCVREExpansionPolicyDefinition(_ExpansionDefinition):
    id, version = "vre-expansion-cap", "2.0.0"


class SchemeCStorageExpansionPolicyDefinition(_ExpansionDefinition):
    id, version = "storage-expansion-scheme-c", "5.0.0"


class SchemeCAgentInvestmentDefinition(_NativeDefinition):
    id, version = "agent-investment", "3.0.0"

    def decide(self, run: ResolvedRun, state: OperatingState, market: MarketYearResult, headroom: Sequence[ExpansionHeadroom]) -> InvestmentDecision:
        caps: dict[str, float] = {}
        for row in headroom:
            for technology, value in row.allowed_additions_mw.items():
                value = max(0.0, float(value))
                caps[technology] = min(caps.get(technology, value), value)
        remaining_caps = dict(caps)
        # P0-7 S4, decision A4 (universal p07.thermal-net-revenue, both
        # profiles): thermal net revenue = income - generated MWh x gen_cost
        # from the PSM's agent cashflow; VRE and storage keep gross = profit.
        a4_costs = cost_rows_for_a4(market.extensions)
        a4_operating: dict[str, float] = {}
        methodology = run_methodology(run)
        pools = headroom_pools(headroom, pooled=methodology.enabled("p07.power-battery-pool"))
        pooled_technologies = {tech for spec in pools.values() for tech in spec["technologies"]}
        pending: list[dict[str, object]] = []
        pool_record: dict[str, object] = {}
        proposals: list[InvestmentProposal] = []

        def propose(index, owner, technology, region, members, capacity, cost_per_mw, life,
                    preferred, target_payback, recommendation, mode, roi, payback, addition):
            """One proposal; arithmetic identical to the HEAD loop body (35aadb3)."""
            proposal_id = f"{run.run_id}:{market.year}:{owner}:{index}"
            duration = (
                sum(float(asset.energy_capacity_mwh or 0.0) for asset in members) / capacity
                if any(asset.energy_capacity_mwh is not None for asset in members) and capacity > 0 else None
            )
            proposal_energy = addition * duration if duration is not None else None
            fixed_om = sum(
                float(asset.extensions.get("annual_fixed_opex_gbp", 0.0) or 0.0)
                for asset in members
            )
            project_extensions = build_asset_economic_extensions(
                technology,
                addition,
                energy_capacity_mwh=proposal_energy,
                capital_costs_per_mw={technology: cost_per_mw},
                lifetimes={technology: life, "default": life},
                discount_rate=max(
                    float(asset.extensions.get("capital_discount_rate", 0.05) or 0.05)
                    for asset in members
                ),
                source_record_id=proposal_id,
                capital_cost_per_mw_override=cost_per_mw,
                annual_fixed_opex_gbp_override=(
                    fixed_om * addition / capacity if capacity > 0 else 0.0
                ),
            )
            project_extensions.update({
                "energy_capacity_mwh": proposal_energy,
                "preferred_rate": preferred,
                "target_payback_years": target_payback,
                "development_years": max(
                    float(asset.extensions.get("development_years", 1.0) or 1.0)
                    for asset in members
                ),
                "success_probability": min(
                    float(asset.extensions.get("success_probability", 1.0))
                    for asset in members
                ),
                "investment_recommendation": recommendation,
                "source_agent_id": owner,
                "investment_owner_id": owner,
                "investment_eligibility_mode": mode,
            })
            return InvestmentProposal(
                proposal_id,
                market.year,
                owner,
                technology,
                addition,
                region,
                market.year + max(1, int(math.ceil(float(
                    project_extensions.get("development_years", 1.0) or 1.0
                )))),
                evidence={
                    "roi": roi,
                    "preferred_rate": preferred,
                    "payback_years": payback,
                    "target_payback_years": target_payback,
                    "recommendation_code": 3.0 if recommendation == "Invest_High" else 2.0,
                },
                extensions=project_extensions,
            )

        retirements: dict[str, float] = {}
        grouped: dict[tuple[str, str, str], list[AssetStateV2]] = defaultdict(list)
        ineligible_assets: list[dict[str, str]] = []
        for asset in state.assets:
            if asset.capacity_mw <= 0 or asset.status == "retired":
                continue
            extensions = dict(asset.extensions)
            owner = str(
                extensions.get("investment_owner_id")
                or extensions.get("source_agent_id")
                or ("" if asset.asset_id.startswith("commissioned:") else asset.asset_id)
            )
            if not owner or extensions.get("investment_eligible") is False:
                ineligible_assets.append({"asset_id": asset.asset_id, "reason": "no_investment_owner"})
                continue
            grouped[(owner, asset.technology, asset.region or "GB")].append(asset)

        ineligible_groups: list[dict[str, str]] = []
        for index, ((owner, technology, region), members) in enumerate(sorted(grouped.items())):
            mode = investment_mode(technology)
            if mode in {"denied", "site_data_required"}:
                ineligible_groups.append({
                    "investment_owner_id": owner,
                    "technology": technology,
                    "reason": mode,
                })
                continue
            capacity = sum(float(asset.capacity_mw) for asset in members)
            income = sum(
                float(market.market_income_gbp_by_agent.get(asset.asset_id, 0.0) or 0.0)
                for asset in members
            )
            if a4_costs is None and technology not in GROSS_PROFIT_TECHNOLOGIES:
                raise ValueError(
                    f"PSM {market.module_id} publishes no {AGENT_CASHFLOW_KEY}; the A4 thermal net revenue of "
                    f"{technology} (owner {owner}) needs its generated MWh and running cost"
                )
            a4 = a4_net_revenue_for_decidable_groups(
                [{"technology": technology, "members": [
                    {
                        "asset_id": asset.asset_id,
                        "income_gbp": float(market.market_income_gbp_by_agent.get(asset.asset_id, 0.0) or 0.0),
                        "extensions": asset.extensions,
                    }
                    for asset in members
                ]}],
                investment_mode,
                a4_costs or {},
            )
            operational = sum(float(a4[asset.asset_id]["operating_cost_gbp"]) for asset in members)
            net = income - operational
            if technology not in GROSS_PROFIT_TECHNOLOGIES:
                a4_operating[f"{owner}|{technology}|{region}"] = operational
                # A bid-at-cost thermal unit is paid its running cost: the
                # difference of two sums of the same flows is rounding, not a
                # loss (it would retire ~1e-12 MW). Snap it to zero.
                if abs(net) <= A4_NET_NOISE_RTOL * max(abs(income), operational):
                    net = 0.0
            replacement = sum(
                float(asset.extensions.get("total_capex_gbp", 0.0) or 0.0)
                for asset in members
            )
            cost_per_mw = replacement / capacity if capacity > 0 else 0.0
            roi = net / replacement if replacement > 0 else 0.0
            preferred = max(
                float(asset.extensions.get("preferred_rate", 0.08) or 0.08)
                for asset in members
            )
            life = min(
                float(asset.extensions.get("economic_lifetime_years", 25.0) or 25.0)
                for asset in members
            )
            target_payback = float(
                min(
                    float(asset.extensions.get("target_payback_years", life) or life)
                    for asset in members
                )
            )
            payback = replacement / net if net > 0 else math.inf
            if net < 0 and cost_per_mw > 0:
                requested_retirement = min(capacity, abs(net) * target_payback / cost_per_mw)
                for asset in members:
                    retirements[asset.asset_id] = requested_retirement * asset.capacity_mw / capacity
                continue
            recommendation = (
                "Invest_High" if roi > preferred
                else "Invest_Profit" if payback <= target_payback
                else "Do_Nothing"
            )
            if cost_per_mw <= 0 or recommendation == "Do_Nothing":
                continue
            requested = net / cost_per_mw
            if mode == "headroom_required" and technology in pooled_technologies:
                # P0-7 S7 (P5-02, corrected): collected, then scaled to the
                # technology caps and the shared power-battery pool together.
                pending.append({
                    "args": (index, owner, technology, region, members, capacity, cost_per_mw, life,
                             preferred, target_payback, recommendation, mode, roi, payback),
                    "requested": requested,
                })
                continue
            allowed = (
                remaining_caps.get(technology, 0.0)
                if mode == "headroom_required"
                else requested
            )
            addition = min(max(requested, 0.0), max(allowed, 0.0))
            if addition <= 0:
                continue
            if mode == "headroom_required":
                remaining_caps[technology] = max(0.0, allowed - addition)
            proposals.append(propose(
                index, owner, technology, region, members, capacity, cost_per_mw, life,
                preferred, target_payback, recommendation, mode, roi, payback, addition,
            ))
        if pending:
            requests = [
                {"request_id": str(row["args"][0]), "technology": row["args"][2],
                 "requested_mw": max(float(row["requested"]), 0.0)}
                for row in pending
            ]
            allocation = allocate_capped_requests(
                requests,
                technology_caps={tech: caps.get(tech, 0.0) for tech in pooled_technologies},
                pools=pools,
            )
            accepted = allocation["accepted_mw"]
            for row in pending:
                addition = accepted[str(row["args"][0])]
                if addition > 0:
                    proposals.append(propose(*row["args"], addition))
            for tech in pooled_technologies:
                used = math.fsum(accepted[str(row["args"][0])] for row in pending if row["args"][2] == tech)
                remaining_caps[tech] = max(0.0, caps.get(tech, 0.0) - used)
            proposals.sort(key=lambda proposal: int(proposal.proposal_id.rsplit(":", 1)[1]))
            pool_record = {
                "pools": {key: {"cap_mw": spec["cap_mw"], "technologies": list(spec["technologies"])}
                          for key, spec in pools.items()},
                "requested_mw": {row["request_id"]: row["requested_mw"] for row in requests},
                "accepted_mw": dict(accepted),
                "technology_scale": dict(allocation["technology_scale"]),
                "pool_scale": dict(allocation["pool_scale"]),
                "rule": "requests collected first, scaled to each technology cap, then to the shared pool (P5-02)",
            }
        return InvestmentDecision(
            f"{run.run_id}:investment:{market.year}", market.year, self.id,
            tuple(proposals), retirements,
            extensions={
                "native_typed_execution": True,
                "cem_model_identity": dict(cem_identity_summary()),
                "investment_policy": policy_summary(),
                "grouped_investment_owners": len(grouped),
                "ineligible_assets": ineligible_assets,
                "ineligible_groups": ineligible_groups,
                "initial_headroom_mw_by_technology": caps,
                "remaining_headroom_mw_by_technology": remaining_caps,
                **({"power_battery_pool": pool_record} if pool_record else {}),
                "a4_net_revenue": {
                    "rule": "thermal: income - generated MWh x (generation + fuel + carbon + unit_time); "
                            "VRE and storage: gross income (DECISIONS A4, A7)",
                    "money_basis": MONEY_BASIS,
                    "thermal_operating_cost_gbp_by_group": a4_operating,
                },
            },
        )


class SchemeCPlanningPipelineDefinition(_NativeDefinition):
    id, version = "planning-pipeline", "2.2.0"

    def advance_year(self, run: ResolvedRun, state: YearState) -> PlanningAdvanceResult:
        from ...doctoral_weather_mapping import commissioned_project_weather

        weather_updates = commissioned_project_weather(state)
        active: list[PlanningProject] = []
        commissioned: list[PlanningProject] = []
        failed: list[PlanningProject] = []
        deferred: list[PlanningProject] = []
        assets = list(state.assets)
        events: list[PlanningEvent] = []
        for project in state.planning_projects:
            if project.project_id in weather_updates:
                project = replace(project, extensions={
                    **project.extensions, **weather_updates[project.project_id],
                })
            if project.outcome in {"failed", "failed_planning"}:
                failed.append(project)
                continue
            if project.expected_completion_year > state.year:
                active.append(project)
                continue
            if investment_mode(project.technology) == "site_data_required":
                missing = missing_site_evidence(project.technology, project.extensions)
                if missing:
                    deferred_project = replace(
                        project,
                        status="deferred_missing_site_data",
                        outcome="deferred",
                    )
                    deferred.append(deferred_project)
                    events.append(PlanningEvent(
                        f"{run.run_id}:{state.year}:defer-site:{project.project_id}",
                        project.project_id,
                        state.year,
                        PlanningEventType.DEFERRED,
                        len(events),
                        reason_code=PlanningReasonCode.MISSING_SITE_OR_HYDROLOGY_DATA,
                        capacity_mw=project.capacity_mw,
                        region=project.region,
                        extensions={"missing_fields": list(missing)},
                    ))
                    continue
            commissioned_project = replace(project, status="commissioned", outcome="commissioned")
            commissioned.append(commissioned_project)
            asset_id = f"commissioned:{project.project_id}"
            record = commissioned_asset_record(
                project,
                asset_id=asset_id,
                commissioning_year=state.year,
            )
            commissioned_asset = AssetStateV2(
                asset_id, project.technology,
                project.capacity_mw,
                float(project.extensions.get("energy_capacity_mwh"))
                if project.extensions.get("energy_capacity_mwh") is not None else None,
                project.region,
                status="commissioned",
                extensions={
                    "source_project_id": project.project_id,
                    "commissioning_year": state.year,
                    "investment_owner_id": record.investment_owner_id,
                    "investment_eligible": record.investment_owner_id is not None,
                    **dict(project.extensions),
                    "commissioned_asset_record": record.to_dict(),
                    "causal_lineage": {
                        "project_id": project.project_id,
                        "commissioned_asset_id": asset_id,
                        "operating_state_year": state.year,
                    },
                },
            )
            validate_asset_economics(commissioned_asset)
            assets.append(commissioned_asset)
            events.append(PlanningEvent(
                f"{run.run_id}:{state.year}:commission:{project.project_id}",
                project.project_id,
                state.year,
                PlanningEventType.COMMISSIONED,
                len(events),
                reason_code=PlanningReasonCode.COMMISSIONED_TO_FLEET,
                capacity_mw=project.capacity_mw,
                region=project.region,
                extensions={
                    "commissioned_asset_id": asset_id,
                    "commissioned_asset_schema_version": record.schema_version,
                    "annualized_capital_cost_gbp": record.annualized_capital_cost_gbp,
                    "annual_fixed_opex_gbp": record.annual_fixed_opex_gbp,
                },
            ))
        next_active_pipeline = tuple(active) + tuple(deferred)
        operating = OperatingState(
            state.year,
            tuple(assets),
            next_active_pipeline,
            extensions={
                **dict(state.extensions),
                "cem_model_identity": dict(cem_identity_summary()),
            },
        )
        return PlanningAdvanceResult(
            state.year, operating, tuple(active), tuple(commissioned),
            tuple(failed), tuple(deferred), tuple(events),
        )

    def admit_projects(self, run: ResolvedRun, state: OperatingState, proposals: Sequence[InvestmentProposal]) -> PlanningAdmissionResult:
        mode = str(run.scientific_parameters.get("planning.success_mode", "expected_capacity"))
        mode = {
            "expected": "expected_capacity",
            "stochastic": "seeded_stochastic",
        }.get(mode, mode)
        if mode not in {"expected_capacity", "seeded_stochastic"}:
            raise ValueError(f"Unsupported planning success mode: {mode}")
        seed = int(run.scientific_parameters.get("planning.random_seed", 0) or 0)
        projects: list[PlanningProject] = []
        rejected: list[InvestmentProposal] = []
        events: list[PlanningEvent] = []
        for proposal in proposals:
            probability = float(proposal.extensions.get("success_probability", 1.0))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Planning success probability must be finite and between zero and one")
            digest = hashlib.sha256(
                f"{seed}:{proposal.proposal_id}".encode("utf-8")
            ).hexdigest()
            draw = int(digest[:13], 16) / float(16 ** 13 - 1)
            realised = mode == "seeded_stochastic"
            success = probability > 0 and (not realised or probability == 1 or draw < probability)
            if not success:
                rejected.append(proposal)
                events.append(PlanningEvent(
                    f"{run.run_id}:{state.year}:failed:{proposal.proposal_id}",
                    proposal.proposal_id,
                    state.year,
                    PlanningEventType.FAILED_PLANNING,
                    len(events),
                    reason_code=PlanningReasonCode.SUCCESS_PROBABILITY,
                    capacity_mw=proposal.capacity_mw,
                    region=proposal.region,
                    extensions={"random_draw": draw, "success_probability": probability},
                ))
                continue
            capacity = proposal.capacity_mw * probability if mode == "expected_capacity" else proposal.capacity_mw
            project_extensions = dict(proposal.extensions)
            if mode == "expected_capacity":
                # Extensive quantities belong to the expected operational
                # project. Keep per-MW prices, lifetime, rates and source
                # proposal unchanged; never apply the success factor twice.
                scaled_fields = ("energy_capacity_mwh", "energy_capacity_mwh_basis",
                    "total_capex_gbp", "annual_fixed_opex_gbp", "annualized_capital_cost_gbp",
                    "annual_operational_cost_gbp", "externally_funded_capital_gbp",
                    "profit_funded_capital_gbp")
                project_extensions["planning_unscaled_financial_commitment"] = {
                    key: project_extensions[key] for key in scaled_fields if key in project_extensions}
                for key in scaled_fields:
                    if project_extensions.get(key) is not None:
                        project_extensions[key] = float(project_extensions[key]) * probability
                project_extensions["planning_economics_basis"] = "expected_operational_capacity_not_realised_failure_cash"
                project_extensions["planning_capacity_factor_applied"] = probability
            project = PlanningProject(
                proposal.proposal_id.replace("proposal", "project"),
                f"Model decision: {proposal.agent_id}", "model_investment",
                proposal.technology, capacity, proposal.capacity_mw,
                proposal.region, "application_submitted", "active", proposal.year,
                proposal.expected_completion_year,
                mode,
                probability,
                random_draw=draw if realised else None,
                extensions=project_extensions,
            )
            projects.append(project)
            events.append(PlanningEvent(
                f"{run.run_id}:{state.year}:admit:{project.project_id}",
                project.project_id,
                state.year,
                PlanningEventType.ADMITTED_MODEL_INVESTMENT,
                len(events),
                reason_code=PlanningReasonCode.SOURCE_MODEL_INVESTMENT,
                capacity_mw=capacity,
                region=proposal.region,
            ))
        pipeline = tuple(state.active_planning_projects) + tuple(projects)
        return PlanningAdmissionResult(
            state.year, tuple(projects), tuple(rejected), pipeline, tuple(events)
        )


class SchemeCStateTransitionDefinition(_NativeDefinition):
    id, version = "scheme-c-state-transition", "2.1.0"

    def apply(self, run: ResolvedRun, current_state: YearState, planning: PlanningAdmissionResult, investment: InvestmentDecision) -> YearState:
        retirements = dict(investment.retirements_mw)
        next_year = current_state.year + 1
        transitioned_assets: list[AssetStateV2] = []
        for asset in current_state.assets:
            scheduled_year = asset.extensions.get("model_unavailable_from_year")
            scheduled_retirement = (
                scheduled_year is not None and next_year >= int(scheduled_year)
            )
            requested = float(retirements.get(asset.asset_id, 0.0) or 0.0)
            if scheduled_retirement:
                requested = max(requested, float(asset.capacity_mw))
            transitioned = resize_asset_economics(
                asset,
                asset.capacity_mw - requested,
            )
            if scheduled_retirement:
                transitioned = replace(
                    transitioned,
                    extensions={
                        **dict(transitioned.extensions),
                        "retired_effective_year": next_year,
                        "retirement_reason": "declared_nuclear_station_end",
                    },
                )
            transitioned_assets.append(transitioned)
        assets = tuple(transitioned_assets)
        return YearState(
            next_year,
            assets,
            tuple(planning.next_pipeline),
            cumulative_metrics=dict(current_state.cumulative_metrics),
            extensions={
                **dict(current_state.extensions),
                "native_typed_execution": True,
                "cem_model_identity": dict(cem_identity_summary()),
            },
        )
