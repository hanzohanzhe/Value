"""Source-backed Scheme C investment rules, with explicit approved exceptions.

Source: doctoral Case 3 ``analyze_investment_case3`` (896--904,
991--1029, 1168--1216), and ``critical_capacity_for_threshold`` (1743--1768).
The original files are an independent test oracle, never runtime dependencies.
Negative proposals survive positive scaling (approved defect correction);
nuclear remains exogenous and electrolyser direct-load investment is excluded.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Mapping, Sequence

import numpy as np


POLICY_VERSION = "doctoral-investment-d1-2026.09.06"
THESIS96_POLICY_VERSION = "doctoral-thesis-final9.6-investment/v1"
THESIS96_SHA256 = "47983aea5c201549cb3b212c554e5f04cfcfb5d7fce413fb5a28ddd939b16d22"
VRE_TECHNOLOGIES = ("solar", "onshore", "offshore")
STORAGE_TECHNOLOGIES = ("1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery")
THERMAL_HIGH_TECHNOLOGIES = ("CCGT", "OCGT", "bio_and_waste")
SOURCE_TARGET_PAYBACK_YEARS = {
    "default": 25.0, "solar": 25.0, "onshore": 30.0, "offshore": 30.0,
    "gas": 20.0, "bio_and_waste": 20.0, "battery": 10.0,
    "1c_battery": 10.0, "0.5c_battery": 10.0, "0.25c_battery": 10.0,
    "electrolyzer": 10.0,
}


def _finite(value: object, label: str, *, nonnegative: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"doctoral investment {label} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _trace(values: Sequence[float] | None, label: str, length: int | None = None) -> np.ndarray:
    if values is None:
        raise ValueError(f"doctoral investment requires observed {label}")
    result = np.asarray(values, dtype=float)
    if (result.ndim != 1 or result.size == 0 or not np.all(np.isfinite(result))
            or np.any(result < 0) or (length is not None and result.size != length)):
        raise ValueError(f"doctoral investment invalid or misaligned {label}")
    return result


def critical_capacity_for_threshold(
    demand: Sequence[float], profile: Sequence[float], *, negative_threshold: int = 200,
) -> float:
    """Original thirty-step bisection; no subtraction of current VRE capacity.

    ``demand`` and ``profile * capacity_mw`` must use the same period quantity,
    as in the original demand/profile CSVs. The threshold counts periods, not
    hours. An unreachable threshold returns zero, matching the original code.
    Unlike the source CSV adapter, this typed boundary rejects length mismatch.
    """
    demand_array = _trace(demand, "demand")
    profile_array = _trace(profile, "generation per MW profile", len(demand_array))
    if isinstance(negative_threshold, bool) or int(negative_threshold) != negative_threshold or negative_threshold <= 0:
        raise ValueError("doctoral negative-period threshold must be a positive integer")
    left, right = 0.0, float(max(demand_array)) * 10.0
    critical_capacity = 0.0
    for _ in range(30):
        mid = (left + right) / 2.0
        if int(np.sum(demand_array - mid * profile_array < 0)) >= negative_threshold:
            critical_capacity, right = mid, mid
        else:
            left = mid
    return critical_capacity


def vre_annual_expansion_cap(
    demand: Sequence[float], profile: Sequence[float], *, negative_threshold: int = 200,
    cap_fraction: float = 0.20,
) -> float:
    """Annual addition ceiling, not a total fleet target or residual headroom."""
    fraction = _finite(cap_fraction, "VRE cap fraction", nonnegative=True)
    return fraction * critical_capacity_for_threshold(demand, profile, negative_threshold=negative_threshold)


def thesis96_vre_annual_expansion_cap(
    demand_mwh: Sequence[float], operational_vre_available_mwh: Sequence[float],
    generation_per_mw_mwh: Sequence[float], *, negative_threshold: int = 200,
    cap_fraction: float = 0.20,
) -> float:
    """Final9.6 Chapter 4, P560/P567: additional VRE meets *net* demand.

    Use all physically available operational VRE, not only accepted generation;
    each technology uses its current capacity-weighted generation/MW profile.
    Already-negative periods count towards the same 200-period boundary. The
    old source bisection remains above for source-parity comparisons only.
    """
    demand = _trace(demand_mwh, "demand_mwh")
    available = _trace(operational_vre_available_mwh, "operational VRE availability", len(demand))
    profile = _trace(generation_per_mw_mwh, "generation per MW", len(demand))
    if isinstance(negative_threshold, bool) or int(negative_threshold) != negative_threshold or negative_threshold <= 0:
        raise ValueError("doctoral negative-period threshold must be a positive integer")
    fraction = _finite(cap_fraction, "VRE cap fraction", nonnegative=True)
    net = demand - available
    already_negative = int(np.count_nonzero(net < 0))
    if already_negative >= negative_threshold:
        return 0.0
    # Each positive profile contributes one transition at net/profile MW.
    # The threshold order statistic is the exact boundary of the source's
    # monotone count, without an arbitrary max(demand)*10 search ceiling.
    transitions = net[(net >= 0) & (profile > 0)] / profile[(net >= 0) & (profile > 0)]
    needed = int(negative_threshold) - already_negative
    if len(transitions) < needed:
        return 0.0  # No finite boundary under this profile; keep source convention.
    critical = float(np.partition(transitions, needed - 1)[needed - 1])
    return fraction * critical


def target_payback_years(technology: str, configured: Mapping[str, float] | None = None) -> float:
    """Investment target is independent of physical/economic lifetime.

    CCGT/OCGT retain the source default 25; the distinct literal ``gas`` key is
    20. Hydrogen storage likewise retains the source default of 25 years.
    """
    targets = dict(SOURCE_TARGET_PAYBACK_YEARS)
    if configured is not None:
        targets.update(configured)
    result = _finite(targets.get(technology, targets["default"]), "target payback")
    if result <= 0:
        raise ValueError("doctoral target payback must be positive")
    return result


def classify_investment(net_revenue: float, replacement_capital: float, preferred_rate: float, target_payback: float) -> str:
    """Preserve original strict ROI, inclusive payback, then loss ordering."""
    net = _finite(net_revenue, "net revenue")
    capital = _finite(replacement_capital, "replacement capital", nonnegative=True)
    preferred = _finite(preferred_rate, "preferred rate", nonnegative=True)
    target = _finite(target_payback, "target payback", nonnegative=True)
    roi = net / capital if capital > 0 else math.nan
    payback = capital / net if net > 0 else math.inf
    if roi > preferred:
        return "Invest_High"
    if payback <= target:
        return "Invest_Profit"
    if net < 0:
        return "Deplete"
    return "Do_Nothing"


def _excluded(technology: str) -> bool:
    lowered = technology.lower()
    return lowered == "nuclear" or "electrolyzer" in lowered or "electrolyser" in lowered


def evaluate_investment_accounts(
    accounts: Sequence[Mapping[str, object]], annual_caps: Mapping[str, float],
) -> list[dict[str, object]]:
    """Propose all agents, then apply the original technology-wide scaling.

    Inputs contain account_id, technology, current_capacity_mw, net_revenue_gbp,
    capital_cost_per_mw_gbp, replacement_capital_gbp, preferred_rate and the
    independent target_payback_years. Input agent order is preserved. The output
    records original requests, cap, scale, profit floor, acceptance and exit.
    """
    caps = {str(key): max(0.0, _finite(value, f"{key} annual cap")) for key, value in annual_caps.items()}
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for account in accounts:
        account_id = str(account["account_id"])
        if not account_id or account_id in seen:
            raise ValueError("doctoral investment account IDs must be nonempty and unique")
        seen.add(account_id)
        tech = str(account["technology"])
        capacity = _finite(account["current_capacity_mw"], "current capacity", nonnegative=True)
        net = _finite(account["net_revenue_gbp"], "net revenue")
        capex = _finite(account["capital_cost_per_mw_gbp"], "CAPEX per MW", nonnegative=True)
        capital = _finite(account.get("replacement_capital_gbp", capacity * capex), "replacement capital", nonnegative=True)
        preferred = _finite(account.get("preferred_rate", 0.08), "preferred rate", nonnegative=True)
        target = _finite(account.get("target_payback_years", target_payback_years(tech)), "target payback", nonnegative=True)
        recommendation = classify_investment(net, capital, preferred, target)
        profit_addition = net / capex if net > 0 and capex > 0 else 0.0
        requested, retirement = 0.0, 0.0
        excluded = _excluded(tech) or account.get("investment_eligible") is False
        if not excluded and capacity > 0:
            if recommendation == "Invest_High":
                if tech in THERMAL_HIGH_TECHNOLOGIES:
                    factor = _finite(account.get("thermal_high_factor", 1.01), "thermal High factor", nonnegative=True)
                    requested = max(0.0, capacity * factor - capacity)
                elif tech in STORAGE_TECHNOLOGIES:
                    requested = max(caps.get(tech, 0.0), profit_addition)
                else:
                    requested = profit_addition
            elif recommendation == "Invest_Profit":
                requested = profit_addition
            elif recommendation == "Deplete" and capex > 0:
                retirement = min(capacity, abs(net) * target / capex)
        results.append({
            "account_id": account_id, "technology": tech, "recommendation": recommendation,
            "current_capacity_mw": capacity, "net_revenue_gbp": net,
            "replacement_capital_gbp": capital, "capital_cost_per_mw_gbp": capex,
            "roi": net / capital if capital > 0 else None,
            "payback_years": capital / net if net > 0 else None,
            "preferred_rate": preferred, "target_payback_years": target,
            "requested_addition_mw": requested, "profit_floor_mw": profit_addition if not excluded else 0.0,
            "annual_cap_mw": caps.get(tech) if tech in (*VRE_TECHNOLOGIES, *STORAGE_TECHNOLOGIES) else None,
            "scale_factor": 1.0, "accepted_addition_mw": requested,
            "retirement_mw": retirement, "excluded_by_policy": excluded,
        })
    for tech in (*VRE_TECHNOLOGIES, *STORAGE_TECHNOLOGIES):
        selected = [row for row in results if row["technology"] == tech and not row["excluded_by_policy"]
                    and (tech not in STORAGE_TECHNOLOGIES or row["recommendation"] == "Invest_High")]
        total = sum(float(row["requested_addition_mw"]) for row in selected)
        if total <= 0:
            continue
        allowed = min(total, caps.get(tech, 0.0))
        if tech in STORAGE_TECHNOLOGIES:
            allowed = max(sum(float(row["profit_floor_mw"]) for row in selected), allowed)
        scale = allowed / total
        for row in selected:
            accepted = float(row["requested_addition_mw"]) * scale
            if tech in STORAGE_TECHNOLOGIES:
                accepted = max(accepted, float(row["profit_floor_mw"]))
            row["scale_factor"], row["accepted_addition_mw"] = scale, accepted
            # The source overwrote negative changes here. Retirement deliberately
            # remains independent under the user's approved defect correction.
    return results


def evaluate_thesis96_investment_accounts(
    accounts: Sequence[Mapping[str, object]], annual_caps: Mapping[str, float],
) -> list[dict[str, object]]:
    """Final9.6 P547-549/P567/P575, explicitly distinct from old-source ROI.

    Operating surplus is revenue less *all* OPEX, before annualised capital.
    Annual profit is surplus less annualised capital; payback_rate is annual
    profit / annualised capital. High VRE raises funds to its capacity share of
    the technology cap. Profit VRE invests retained profit up to that share.
    Thermal High 1%, storage High/Profit and loss-based retirement amounts retain
    the approved source rules where the thesis supplies no replacement formula.
    No project is commissioned here and no money is converted directly to MW
    without the declared per-MW capital cost.
    """
    caps = {str(tech): _finite(value, f"{tech} cap", nonnegative=True)
            for tech, value in annual_caps.items()}
    parsed = []
    seen = set()
    capacity_by_tech = defaultdict(float)

    def required(row, field, *, nonnegative=False):
        if field not in row or isinstance(row[field], bool):
            raise ValueError(f"thesis9.6 investment requires {field}")
        return _finite(row[field], field, nonnegative=nonnegative)

    for account in accounts:
        identity = str(account.get("account_id") or "")
        tech = str(account.get("technology") or "")
        if not identity or identity in seen or not tech:
            raise ValueError("thesis9.6 requires unique account IDs and technology")
        seen.add(identity)
        capacity = required(account, "current_capacity_mw", nonnegative=True)
        surplus = required(account, "operating_surplus_gbp")
        annual_capital = required(account, "annualized_capital_cost_gbp", nonnegative=True)
        capex = required(account, "capital_cost_per_mw_gbp", nonnegative=True)
        preferred = required(account, "preferred_rate", nonnegative=True)
        if annual_capital <= 0 or capex <= 0:
            raise ValueError("thesis9.6 requires positive annualized capital and CAPEX per MW")
        target = required(account, "target_payback_years", nonnegative=True)
        if target <= 0:
            raise ValueError("thesis9.6 requires a positive retirement target")
        profit = surplus - annual_capital
        rate = profit / annual_capital
        # Compare amounts at the threshold, avoiding floating cancellation in
        # (surplus - capital) / capital around an exactly equal hurdle rate.
        if surplus > annual_capital * (1.0 + preferred):
            recommendation = "Invest_High"
        elif profit > 0:
            recommendation = "Invest_Profit"
        elif surplus < 0:
            recommendation = "Deplete"
        else:
            recommendation = "Do_Nothing"
        excluded = _excluded(tech) or account.get("investment_eligible") is False
        row = {"account_id": identity, "technology": tech, "recommendation": recommendation,
               "current_capacity_mw": capacity, "operating_surplus_gbp": surplus,
               "net_revenue_gbp": surplus, "annualized_capital_cost_gbp": annual_capital,
               "annual_profit_gbp": profit, "payback_rate": rate,
               "roi": rate, "roi_basis": "annual_profit_over_annualized_capital",
               "payback_years": None, "preferred_rate": preferred, "target_payback_years": target,
               "replacement_capital_gbp": required(account, "replacement_capital_gbp", nonnegative=True),
               "capital_cost_per_mw_gbp": capex, "excluded_by_policy": excluded,
               "profit_floor_mw": max(0.0, profit) / capex if not excluded else 0.0,
               "annual_cap_mw": caps.get(tech), "scale_factor": 1.0,
               "requested_addition_mw": 0.0, "accepted_addition_mw": 0.0,
               "retirement_mw": 0.0, "investment_basis": "thesis_final9.6"}
        parsed.append(row)
        capacity_by_tech[tech] += capacity

    for row in parsed:
        tech, capacity = row["technology"], row["current_capacity_mw"]
        share = capacity / capacity_by_tech[tech] if capacity_by_tech[tech] > 0 else 0.0
        cap_share = caps.get(tech, 0.0) * share
        row["operational_capacity_share"] = share
        row["individual_cap_mw"] = cap_share if tech in VRE_TECHNOLOGIES else caps.get(tech)
        if not row["excluded_by_policy"] and capacity > 0:
            if row["recommendation"] == "Deplete":
                row["retirement_mw"] = min(capacity, -row["operating_surplus_gbp"]
                    * row["target_payback_years"] / row["capital_cost_per_mw_gbp"])
            elif row["recommendation"] == "Invest_High":
                if tech in VRE_TECHNOLOGIES:
                    row["requested_addition_mw"] = cap_share
                elif tech in THERMAL_HIGH_TECHNOLOGIES:
                    row["requested_addition_mw"] = capacity * 0.01
                elif tech in STORAGE_TECHNOLOGIES:
                    row["requested_addition_mw"] = max(caps.get(tech, 0.0), row["profit_floor_mw"])
            elif row["recommendation"] == "Invest_Profit":
                row["requested_addition_mw"] = (min(cap_share, row["profit_floor_mw"])
                    if tech in VRE_TECHNOLOGIES else row["profit_floor_mw"])
        row["accepted_addition_mw"] = row["requested_addition_mw"]
    for tech in STORAGE_TECHNOLOGIES:
        high = [row for row in parsed if row["technology"] == tech
                and row["recommendation"] == "Invest_High" and not row["excluded_by_policy"]]
        total = sum(row["requested_addition_mw"] for row in high)
        if total > 0:
            allowed = max(sum(row["profit_floor_mw"] for row in high), min(total, caps.get(tech, 0.0)))
            # Reserve binding profit floors, then re-scale the other requests.
            # max(floor, request*one_global_scale) can overspend the shared cap
            # when only one owner's floor binds. The source-parity function
            # remains unchanged; this fixes that allocation in the thesis view.
            pending, reserved = list(high), 0.0
            while pending:
                weight = sum(row["requested_addition_mw"] for row in pending)
                scale = max(0.0, (allowed - reserved) / weight) if weight else 0.0
                bound = [row for row in pending
                         if row["requested_addition_mw"] * scale < row["profit_floor_mw"]]
                if not bound:
                    for row in pending:
                        row["accepted_addition_mw"] = row["requested_addition_mw"] * scale
                    break
                for row in bound:
                    row["accepted_addition_mw"] = row["profit_floor_mw"]
                    reserved += row["profit_floor_mw"]
                    pending.remove(row)
            for row in high:
                row["scale_factor"] = row["accepted_addition_mw"] / row["requested_addition_mw"]
    for row in parsed:
        spent = row["accepted_addition_mw"] * row["capital_cost_per_mw_gbp"]
        retained = min(max(row["annual_profit_gbp"], 0.0), spent)
        row["profit_funded_addition_mw"] = retained / row["capital_cost_per_mw_gbp"]
        row["externally_funded_capital_gbp"] = spent - retained
    return parsed


def storage_expansion_from_traces(
    accepted_vre_mwh: Sequence[float], demand_mwh: Sequence[float], *,
    storage_charge_mwh: Sequence[float], leftover_excess_mwh: Sequence[float],
    storage_discharge_mwh: Sequence[float], prices: Sequence[float] | None = None,
    cap_row: Mapping[str, float] | None = None, cap_fraction: float = 0.20,
) -> dict[str, object]:
    """Use actual post-charge excess and observed discharge in preserved kernel.

    All traces are period MWh. No demand/VRE difference fallback is allowed at
    this boundary. The complete virtual-pool spectrum accompanies the limits.
    """
    from .storage import storage_expansion_cap as kernel

    demand = _trace(demand_mwh, "demand MWh")
    vre = _trace(accepted_vre_mwh, "accepted VRE MWh", len(demand))
    charge = _trace(storage_charge_mwh, "storage charge MWh", len(demand))
    leftover = _trace(leftover_excess_mwh, "post-charge leftover excess MWh", len(demand))
    discharge = _trace(storage_discharge_mwh, "storage discharge MWh", len(demand))
    fraction = _finite(cap_fraction, "storage cap fraction", nonnegative=True)
    excess, deficit, mode = kernel.build_deficit_for_cap(
        vre, demand, excess_generation=leftover, storage_discharge=discharge,
        store_charge=charge, cap_row=dict(cap_row or {}), credit_mode="scheme_c")
    spectrum = kernel.aligned_utilisation_spectrum(excess, deficit)
    limits = kernel.calculate_storage_expansion_limits_from_profiles(
        vre, demand, prices=prices, cap_row=dict(cap_row or {}), excess_generation=leftover,
        storage_discharge=discharge, store_charge=charge, credit_mode="scheme_c")
    base_fraction = float(kernel.CAP_FRACTION)
    if base_fraction <= 0:
        raise ValueError("doctoral storage kernel fraction must be positive")
    return {"limits_mw": {key: float(value) * (fraction / base_fraction) for key, value in limits.items()},
            "spectrum": spectrum, "excess_mwh": excess.tolist(), "deficit_mwh": deficit.tolist(),
            "credit_mode": mode, "cap_fraction": fraction, "policy_version": POLICY_VERSION}


def _asset_net_revenue(asset_id: str, accounts: Mapping[str, Mapping[str, float]]) -> float:
    """A zero is valid evidence; an absent account is not a zero-profit asset."""
    if asset_id not in accounts:
        raise ValueError(f"doctoral investment missing per-asset cashflow: {asset_id}")
    row = accounts[asset_id]
    if "net_revenue_gbp" in row:
        return _finite(row["net_revenue_gbp"], f"{asset_id} cashflow net revenue")
    if "market_income_gbp" not in row or "operational_cost_gbp" not in row:
        raise ValueError(f"doctoral investment incomplete per-asset cashflow: {asset_id}")
    return (_finite(row["market_income_gbp"], f"{asset_id} cashflow income")
            - _finite(row["operational_cost_gbp"], f"{asset_id} cashflow operating cost"))


def decide_doctoral_investment(run, state, market, headroom, accounts=None):
    """Typed lifecycle adapter with one financial decision per source owner.

    ``accounts`` is keyed by physical asset ID, with ``net_revenue_gbp`` or
    both ``market_income_gbp`` and ``operational_cost_gbp``. If omitted, the
    exact same mapping is required in market.extensions['doctoral_accounts_by_asset'].
    No national aggregate, gross market-income fallback or missing-account zero
    is admitted. The caller supplies the selected physical market's accounts.

    Ownership order follows first occurrence in state.assets. All physical
    members of (owner, technology) first pool cashflow/capital for classification
    and technology-wide allocation. Only then are accepted additions distributed
    over the owner's represented regions by existing capacity, and retirements
    over member assets. An owner therefore cannot spend one profit repeatedly.
    """
    from ...asset_economics import build_asset_economic_extensions
    from ...cem_identity import cem_identity_summary
    from ...cem_investment_policy import investment_mode, policy_summary
    from ...v2.contracts import InvestmentDecision, InvestmentProposal
    from .endogenous_planning import endogenous_planning_terms

    basis = str(run.scientific_parameters.get("doctoral.investment_basis", "source"))
    if basis not in {"source", "thesis_final9.6"}:
        raise ValueError(f"Unknown doctoral investment basis: {basis}")
    thesis96 = basis == "thesis_final9.6"
    policy_version = THESIS96_POLICY_VERSION if thesis96 else POLICY_VERSION

    caps: dict[str, float] = {}
    rows = (headroom,) if hasattr(headroom, "allowed_additions_mw") else headroom
    for limit in rows:
        for tech, value in limit.allowed_additions_mw.items():
            amount = max(0.0, _finite(value, f"{tech} annual cap"))
            caps[tech] = min(caps.get(tech, amount), amount)
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    ineligible_assets: list[dict[str, str]] = []
    ineligible_groups: list[dict[str, str]] = []
    for asset in state.assets:
        if asset.capacity_mw <= 0 or asset.status == "retired":
            continue
        ext = asset.extensions
        owner = str(ext.get("investment_owner_id") or ext.get("source_agent_id")
                    or ("" if asset.asset_id.startswith("commissioned:") else asset.asset_id))
        if not owner or ext.get("investment_eligible") is False or _excluded(asset.technology):
            ineligible_assets.append({"asset_id": asset.asset_id, "reason": "excluded_or_missing_owner"})
            continue
        grouped[(owner, asset.technology)].append(asset)

    source_accounts = accounts if accounts is not None else market.extensions.get("doctoral_accounts_by_asset")
    financial_rows: list[dict[str, object]] = []
    groups_by_id: dict[str, tuple[str, str, list]] = {}
    for index, ((owner, technology), members) in enumerate(grouped.items()):
        mode = investment_mode(technology)
        if mode in {"denied", "site_data_required"}:
            ineligible_groups.append({"investment_owner_id": owner, "technology": technology, "reason": mode})
            continue
        if not isinstance(source_accounts, Mapping):
            raise ValueError("doctoral investment requires complete per-asset cashflow")
        capacity = sum(float(asset.capacity_mw) for asset in members)
        if thesis96:
            if any(asset.asset_id not in source_accounts or "operating_surplus_gbp" not in source_accounts[asset.asset_id]
                   for asset in members):
                raise ValueError("thesis9.6 requires complete operating_surplus_gbp accounts after all OPEX")
            net = sum(_finite(source_accounts[asset.asset_id]["operating_surplus_gbp"], "operating surplus") for asset in members)
        else:
            net = sum(_asset_net_revenue(asset.asset_id, source_accounts) for asset in members)
        capital = sum(_finite(asset.extensions["total_capex_gbp"], f"{asset.asset_id} total capital", nonnegative=True) for asset in members)
        capex = sum(
            (float(asset.extensions.get("capital_cost_per_mw", 0.0))
             or float(asset.extensions["total_capex_gbp"]) / float(asset.capacity_mw))
            * float(asset.capacity_mw) for asset in members
        ) / capacity
        preferred = max(float(asset.extensions.get("preferred_rate", 0.08)) for asset in members)
        target = min(float(asset.extensions.get("target_payback_years", target_payback_years(technology))) for asset in members)
        account_id = f"{index}:{owner}:{technology}"
        financial_rows.append({
            "account_id": account_id, "technology": technology,
            "current_capacity_mw": capacity, "net_revenue_gbp": net,
            "capital_cost_per_mw_gbp": capex, "replacement_capital_gbp": capital,
            "preferred_rate": preferred, "target_payback_years": target,
        })
        if thesis96:
            if any("annualized_capital_cost_gbp" not in asset.extensions for asset in members):
                raise ValueError("thesis9.6 requires annualized_capital_cost_gbp for every investment asset")
            financial_rows[-1].update({"operating_surplus_gbp": net,
                "annualized_capital_cost_gbp": sum(_finite(asset.extensions["annualized_capital_cost_gbp"],
                    "annualized capital", nonnegative=True) for asset in members)})
        groups_by_id[account_id] = (owner, technology, members)

    outcomes = (evaluate_thesis96_investment_accounts(financial_rows, caps) if thesis96 else
                evaluate_investment_accounts(financial_rows, caps))
    proposals: list[InvestmentProposal] = []
    retirements: dict[str, float] = {}
    accepted_by_tech: dict[str, float] = defaultdict(float)
    for outcome in outcomes:
        owner, technology, members = groups_by_id[str(outcome["account_id"])]
        capacity = float(outcome["current_capacity_mw"])
        addition = float(outcome["accepted_addition_mw"])
        retirement = float(outcome["retirement_mw"])
        outcome["investment_owner_id"] = owner
        outcome["member_asset_ids"] = [asset.asset_id for asset in members]
        if retirement > 0:
            for asset in members:
                retirements[asset.asset_id] = retirement * float(asset.capacity_mw) / capacity
        if addition <= 0:
            continue
        accepted_by_tech[technology] += addition
        regional_members: dict[str, list] = defaultdict(list)
        for asset in members:
            regional_members[asset.region or "GB"].append(asset)
        for region_index, (region, regional) in enumerate(regional_members.items()):
            region_capacity = sum(float(asset.capacity_mw) for asset in regional)
            region_addition = addition * region_capacity / capacity
            duration = (sum(float(asset.energy_capacity_mwh or 0.0) for asset in regional) / region_capacity
                        if any(asset.energy_capacity_mwh is not None for asset in regional) else None)
            energy = region_addition * duration if duration is not None else None
            life = min(float(asset.extensions.get("economic_lifetime_years", 25.0)) for asset in regional)
            capex = float(outcome["capital_cost_per_mw_gbp"])
            proposal_id = f"{run.run_id}:{market.year}:{outcome['account_id']}:{region_index}"
            # r71 (A33, P4-05): pack timeline and regional success rate, not
            # min/max over member-asset extensions that were never set.
            terms = endogenous_planning_terms(state.extensions.get("planning_parameters"), technology=technology,
                                              owner=owner, decision_year=market.year)
            fixed_om = sum(float(asset.extensions.get("annual_fixed_opex_gbp", 0.0)) for asset in regional)
            extensions = build_asset_economic_extensions(
                technology, region_addition, energy_capacity_mwh=energy,
                capital_costs_per_mw={technology: capex}, lifetimes={technology: life, "default": life},
                discount_rate=max(float(asset.extensions.get("capital_discount_rate", 0.05)) for asset in regional),
                source_record_id=proposal_id, capital_cost_per_mw_override=capex,
                annual_fixed_opex_gbp_override=fixed_om * region_addition / region_capacity,
            )
            extensions.update({
                "energy_capacity_mwh": energy, "preferred_rate": outcome["preferred_rate"],
                "target_payback_years": outcome["target_payback_years"],
                "success_probability": terms["success_rate"], "timeline_months": terms["timeline_months"],
                "success_rate_source": terms["success_rate_source"], "endogenous_planning_terms": terms,
                "investment_recommendation": outcome["recommendation"],
                "source_agent_id": owner, "investment_owner_id": owner,
                "investment_eligibility_mode": investment_mode(technology),
                "doctoral_investment_policy": policy_version,
                "doctoral_investment_basis": basis,
                "doctoral_account_id": outcome["account_id"],
                "source_asset_ids": [asset.asset_id for asset in regional],
            })
            if thesis96:
                regional_share = region_addition / addition
                external = float(outcome["externally_funded_capital_gbp"]) * regional_share
                extensions.update({
                    "profit_funded_capital_gbp": float(extensions["total_capex_gbp"]) - external,
                    "externally_funded_capital_gbp": external,
                    "funding_status": "planned_not_drawn",
                    "funding_annualization_status": "separate_equity_loan_basis_not_yet_integrated",
                    "planned_loan_rate": 0.05,
                    "planned_loan_tenor_years": life,
                })
            proposals.append(InvestmentProposal(
                proposal_id, market.year, owner, technology, region_addition, region,
                int(terms["completion_year"]),
                evidence={
                    "roi": float(outcome["roi"] or 0.0),
                    "preferred_rate": float(outcome["preferred_rate"]),
                    "payback_years": float(outcome["payback_years"] or 0.0),
                    "target_payback_years": float(outcome["target_payback_years"]),
                    "requested_addition_mw": float(outcome["requested_addition_mw"]),
                    "account_accepted_addition_mw": addition,
                    "scale_factor": float(outcome["scale_factor"]),
                    "region_capacity_share": region_capacity / capacity,
                    "recommendation_code": 3.0 if outcome["recommendation"] == "Invest_High" else 2.0,
                }, extensions=extensions))
    return InvestmentDecision(
        f"{run.run_id}:investment:{market.year}", market.year, "agent-investment",
        tuple(proposals), retirements, extensions={
            "native_typed_execution": True, "cem_model_identity": dict(cem_identity_summary()),
            "investment_policy": policy_summary(), "doctoral_policy_version": policy_version,
            "investment_basis": basis,
            "grouped_investment_owners": len(grouped), "ineligible_assets": ineligible_assets,
            "ineligible_groups": ineligible_groups, "initial_headroom_mw_by_technology": caps,
            "remaining_headroom_mw_by_technology": {
                tech: max(0.0, cap - accepted_by_tech.get(tech, 0.0)) for tech, cap in caps.items()},
            "doctoral_investment_accounts": outcomes,
            "cashflow_basis": "explicit_selected_market_per_asset_accounts",
            "approved_retirement_fix": "negative_events_independent_of_positive_scaling",
        })
