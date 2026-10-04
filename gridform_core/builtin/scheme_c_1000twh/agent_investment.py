"""Scheme C four-tier agent investment rule extracted from Case 3."""

from __future__ import annotations

import math

from ...contracts import CapacityDecision, ModelState, PSMResult, YearContext


class SchemeCAgentInvestment:
    id = "agent-investment"
    version = "1000twh-2026.07.19"
    order = 10

    def decide(self, context: YearContext, state: ModelState, psm_result: PSMResult, previous_decisions):
        del previous_decisions
        capex = context.parameters.get("capital_costs_per_mw", {})
        preferred = context.parameters.get("preferred_rates", {})
        payback_targets = context.parameters.get("target_payback_years", {})
        support_income = context.parameters.get("agent_support_income_gbp", {})
        additions = {}
        retirements = {}
        evidence = {}
        for asset in state.assets:
            tech = asset.technology
            market_income = float(psm_result.market_income_gbp.get(asset.id, 0.0))
            total_income = market_income + float(support_income.get(asset.id, 0.0))
            operational_cost = float(asset.attributes.get("operational_cost_gbp", 0.0))
            net_revenue = total_income - operational_cost
            cost_per_mw = float(capex.get(tech, asset.attributes.get("capital_cost_per_mw", 0.0)) or 0.0)
            replacement_cost = asset.capacity_mw * cost_per_mw
            roi = net_revenue / replacement_cost if replacement_cost > 0 else math.nan
            payback = replacement_cost / net_revenue if net_revenue > 0 else math.inf
            preferred_rate = float(preferred.get(tech, 0.08))
            target = float(payback_targets.get(tech, payback_targets.get("default", 25)))
            if roi > preferred_rate:
                recommendation = "Invest_High"
            elif payback <= target:
                recommendation = "Invest_Profit"
            elif net_revenue < 0:
                recommendation = "Deplete"
            else:
                recommendation = "Do_Nothing"
            if recommendation in {"Invest_High", "Invest_Profit"} and cost_per_mw > 0:
                additions[asset.id] = max(0.0, net_revenue / cost_per_mw)
            elif recommendation == "Deplete" and cost_per_mw > 0:
                retirements[asset.id] = min(asset.capacity_mw, abs(net_revenue) * target / cost_per_mw)
            evidence[f"{asset.id}.roi"] = float(roi) if math.isfinite(roi) else 0.0
            evidence[f"{asset.id}.recommendation"] = {"Invest_High": 3, "Invest_Profit": 2, "Do_Nothing": 1, "Deplete": 0}[recommendation]
        return CapacityDecision(module_id=self.id, additions_mw=additions, retirements_mw=retirements, evidence=evidence)
