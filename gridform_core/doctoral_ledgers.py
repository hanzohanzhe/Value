"""Explicit national doctoral cashflow and separately named reporting views.

Source rules: simulation_model.py 609-639, 2242-2260 and 2348-2356;
run_investment_analysis_case3_decarbonization_breakdown_cm.py 425-435,
686-700, 792-824, 867-874 and 1243-1268. Audited original hashes are
434f43ca9607ba1b9588826c924d48755965ad99bcf4b3dc0e13089a512e3da0
and e0e11057715f5f26a99e804fdd7d9fa386a9b744c85174965584695060d373c9.

No I/O or original-module imports. These helpers require resolved actual costs,
owner identity and policy allocations. They do not infer missing costs as zero,
determine CM eligibility, refresh dynamic CfD policy, value capital a second
time in agent profit, or certify storage carbon, annual or multiyear parity.
The original storage operating-cost convention must be supplied explicitly by
the caller, even when the source convention records it as zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from .voll import VOLL_GBP_PER_MWH

LEDGER_VERSION = "value.doctoral-explicit-ledgers/v1"
PERIOD_HOURS = 0.5
# A16-5 (fx5.voll-17000, universal accounting correction): the thesis code's
# 8000 GBP/MWh loss value is replaced by the author's VoLL of 17000 GBP/MWh.
LEGACY_DEFICIT_VALUE_GBP_PER_MWH = VOLL_GBP_PER_MWH
_CASH_FIELDS = (
    "market_income_gbp", "balancing_income_gbp", "redispatch_income_gbp",
    "cm_income_gbp", "decarb_income_gbp", "operating_cost_gbp", "net_profit_gbp",
)


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if isinstance(value, bool) or not math.isfinite(result) or nonnegative and result < 0:
        raise ValueError(f"{label} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _amounts(value: object, label: str, *, nonnegative: bool = False) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an explicit asset mapping")
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError(f"{label} requires nonempty string asset IDs")
    return {key: _number(amount, f"{label}[{key}]", nonnegative=nonnegative)
            for key, amount in value.items()}


def _coverage(mapping: Mapping, asset_ids: set[str], label: str, *, complete=True):
    unknown = set(mapping) - asset_ids
    missing = asset_ids - set(mapping) if complete else set()
    if unknown or missing:
        raise ValueError(f"{label} coverage: missing={sorted(missing)}, unknown={sorted(unknown)}")


def _field(value: object, name: str, default=None):
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _owners(state: object) -> dict[str, str]:
    assets = _field(state, "assets")
    if assets is None:
        raise ValueError("state requires explicit assets and owner identity")
    owners = {}
    for asset in assets:
        asset_id = _field(asset, "asset_id")
        extensions = _field(asset, "extensions", {}) or {}
        owner = extensions.get("investment_owner_id") or extensions.get("source_agent_id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in owners:
            raise ValueError(f"state requires unique asset IDs: {asset_id!r}")
        if not isinstance(owner, str) or not owner:
            raise ValueError(f"explicit investment owner missing for {asset_id}")
        owners[asset_id] = owner
    return owners


def operating_costs_from_generation(generation_by_asset: Mapping[str, float],
                                    gen_cost_gbp_per_mwh_by_asset: Mapping[str, float], *,
                                    generation_unit: str) -> dict:
    """Original generator operating cost: sum(period MW) * 0.5h * gen_cost.

    ``generation_unit`` is mandatory: ``mw_period_sum`` is the original summed
    period power, while ``mwh`` is already integrated physical energy. The raw
    generation fee is reported separately and is never mislabeled as GBP.
    Callers supply all generators, including explicitly zero generation.
    """
    if generation_unit not in {"mw_period_sum", "mwh"}:
        raise ValueError("generation_unit must be mw_period_sum or mwh")
    generation = _amounts(generation_by_asset, "generation", nonnegative=True)
    costs = _amounts(gen_cost_gbp_per_mwh_by_asset, "gen_cost_gbp_per_mwh", nonnegative=True)
    _coverage(costs, set(generation), "gen_cost_gbp_per_mwh")
    mwh = {asset: amount * PERIOD_HOURS if generation_unit == "mw_period_sum" else amount
           for asset, amount in generation.items()}
    physical = {asset: _number(amount * costs[asset], f"operating_cost[{asset}]")
                for asset, amount in mwh.items()}
    return {
        "operating_cost_gbp_by_asset": physical,
        "generation_mwh_by_asset": mwh,
        "raw_generation_fee_by_asset": {
            asset: amount / PERIOD_HOURS for asset, amount in physical.items()},
        "raw_generation_fee_unit": "sum_of_period_MW_times_GBP_per_MWh",
        "generation_input_unit": generation_unit,
        "period_hours": PERIOD_HOURS,
    }


def build_asset_accounts(market: object, state: object, policy: Mapping) -> dict[str, dict[str, float]]:
    """Build complete per-asset actual cashflow for the investment adapter.

    market is an explicit mapping or a MarketYearResult whose extensions contain
    ``doctoral_cashflow_inputs``. Mandatory complete asset maps are
    ``ahead_income_gbp_by_asset``, ``balancing_income_gbp_by_asset`` and
    ``operating_cost_gbp_by_asset``. Optional ``total_market_income_gbp_by_asset``
    is a reconciliation check only, never another income component.

    Policy requires scenario basic/with_cm/decarb. Active policy components must
    supply allocations explicitly; omitted assets in those allocations receive
    zero as a declared eligibility outcome. Basic disables both transfers.
    market_income_gbp in each result means AHEAD income only. net_revenue_gbp is
    an alias for net_profit_gbp for the existing investment adapter, not a second
    cashflow. Direct electrolysis and zonal redispatch are outside this contract.
    Coverage includes every asset in the provided state, including inactive
    assets. Pass explicit zero rows or a deliberately filtered operating state.
    """
    owners = _owners(state)
    ids = set(owners)
    data = market if isinstance(market, Mapping) else _field(market, "extensions", {}).get("doctoral_cashflow_inputs")
    if not isinstance(data, Mapping):
        raise ValueError("market requires explicit doctoral_cashflow_inputs")
    ahead = _amounts(data.get("ahead_income_gbp_by_asset"), "ahead_income")
    balancing = _amounts(data.get("balancing_income_gbp_by_asset"), "balancing_income")
    operating = _amounts(data.get("operating_cost_gbp_by_asset"), "operating_cost", nonnegative=True)
    for label, amounts in (("ahead_income", ahead), ("balancing_income", balancing), ("operating_cost", operating)):
        _coverage(amounts, ids, label)
    if "total_market_income_gbp_by_asset" in data:
        totals = _amounts(data["total_market_income_gbp_by_asset"], "total_market_income")
        _coverage(totals, ids, "total_market_income")
        for asset in ids:
            if abs(totals[asset] - ahead[asset] - balancing[asset]) > 0.0001:
                raise ValueError(f"income reconciliation failed for {asset}")
    if any(_amounts(data.get("redispatch_income_gbp_by_asset", {}), "redispatch_income").values()):
        raise ValueError("zonal redispatch is deferred; national accounts cannot accept its cashflow")
    scenario = policy.get("scenario")
    if scenario not in {"basic", "with_cm", "decarb"}:
        raise ValueError("policy scenario must be basic, with_cm or decarb")
    cm = _amounts(policy.get("cm_income_gbp_by_asset", {} if scenario == "basic" else None), "cm_income")
    decarb = _amounts(policy.get("decarb_income_gbp_by_asset", {} if scenario in {"basic", "with_cm"} else None), "decarb_income")
    _coverage(cm, ids, "cm_income", complete=False)
    _coverage(decarb, ids, "decarb_income", complete=False)
    if scenario == "basic" and any(cm.values()):
        raise ValueError("basic scenario disables CM income")
    if scenario in {"basic", "with_cm"} and any(decarb.values()):
        raise ValueError(f"{scenario} scenario disables decarbonization income")
    accounts = {}
    for asset in owners:
        row = {"market_income_gbp": ahead[asset], "balancing_income_gbp": balancing[asset],
               "redispatch_income_gbp": 0.0, "cm_income_gbp": cm.get(asset, 0.0),
               "decarb_income_gbp": decarb.get(asset, 0.0), "operating_cost_gbp": operating[asset]}
        row["net_profit_gbp"] = _number(
            row["market_income_gbp"] + row["balancing_income_gbp"] + row["cm_income_gbp"]
            + row["decarb_income_gbp"] - row["operating_cost_gbp"], f"net_profit[{asset}]")
        row["net_revenue_gbp"] = row["net_profit_gbp"]
        accounts[asset] = row
    return accounts


def build_agent_accounts(market: object, state: object, policy: Mapping) -> dict[str, dict[str, float]]:
    """Aggregate owner reporting, including all of an owner's technologies.

    Investment consumes build_asset_accounts instead: its own owner/technology
    grouping must not receive already aggregated owner rows a second time.
    """
    owners = _owners(state)
    assets = build_asset_accounts(market, state, policy)
    accounts = {}
    for asset, row in assets.items():
        owner = owners[asset]
        if owner not in accounts:
            accounts[owner] = {field: 0.0 for field in _CASH_FIELDS}
        for field in _CASH_FIELDS:
            accounts[owner][field] = _number(accounts[owner][field] + row[field], f"{owner}.{field}")
    for row in accounts.values():
        row["net_revenue_gbp"] = row["net_profit_gbp"]
    return accounts


def build_thesis96_asset_accounts(market: object, state: object, policy: Mapping) -> dict:
    """Annual cash bridge for final9.6 P547, with explicit non-overlapping costs.

    Period operating costs exclude annual fixed OPEX and capital. The source
    view remains untouched; this view deducts fixed OPEX and annual capital
    exactly once. Operating surplus stays separate from post-capital profit.
    A partial or unlabelled span is not eligible for annual policy/investment.
    """
    data = market if isinstance(market, Mapping) else _field(market, "extensions", {}).get("doctoral_cashflow_inputs")
    if not isinstance(data, Mapping):
        raise ValueError("thesis9.6 requires annual doctoral_cashflow_inputs")
    coverage = data.get("period_coverage", {})
    if (not isinstance(coverage, Mapping) or coverage.get("annual_complete") is not True
            or coverage.get("start_period_index") != 0 or coverage.get("end_period_index_exclusive") != 17520
            or coverage.get("period_count") != 17520 or data.get("period_hours") != 0.5
            or coverage.get("year") != _field(state, "year")):
        raise ValueError("thesis9.6 annual cashflow requires a complete 17520-period year")
    accounts = build_asset_accounts(data, state, policy)
    ancillary = _amounts(policy.get("ancillary_income_gbp_by_asset",
                         {} if policy.get("scenario") == "basic" else None), "ancillary_income")
    _coverage(ancillary, set(accounts), "ancillary_income", complete=False)
    for asset in _field(state, "assets"):
        name, ext = _field(asset, "asset_id"), _field(asset, "extensions", {})
        for field in ("annual_fixed_opex_gbp", "annualized_capital_cost_gbp"):
            if field not in ext:
                raise ValueError(f"thesis9.6 requires {name}.{field}")
        fixed = _number(ext["annual_fixed_opex_gbp"], "annual_fixed_opex", nonnegative=True)
        capital = _number(ext["annualized_capital_cost_gbp"], "annualized_capital_cost", nonnegative=True)
        row = accounts[name]
        variable = row["operating_cost_gbp"]
        surplus = row["net_revenue_gbp"] + ancillary.get(name, 0.0) - fixed
        profit = surplus - capital
        row.update({"variable_operating_cost_gbp": variable, "annual_fixed_opex_gbp": fixed,
            "operating_cost_gbp": variable + fixed, "annualized_capital_cost_gbp": capital,
            "ancillary_income_gbp": ancillary.get(name, 0.0), "operating_surplus_gbp": surplus,
            "net_revenue_gbp": surplus, "annual_profit_gbp": profit, "net_profit_gbp": profit,
            "payback_rate": profit / capital if capital > 0 else None})
    return accounts


def allocate_policy_transfers(*, scenario: str, cm_pot_gbp: float, decarb_pot_gbp: float,
                              cm_capacity_weights_mw: Mapping[str, float],
                              eligible_decarb_capacity_mw: Mapping[str, float]) -> dict:
    """Allocate explicit annual pots using source capacity-share arithmetic.

    Eligible capacities/de-rating weights are REQUIRED caller evidence, not
    inferred here. Dynamic CfD eligibility and CM technology qualification remain
    unassessed. Funds are revenues; no direct capacity addition is created.
    """
    if scenario not in {"basic", "with_cm", "decarb"}:
        raise ValueError("policy scenario must be basic, with_cm or decarb")
    cm = _number(cm_pot_gbp, "cm_pot_gbp", nonnegative=True)
    decarb = _number(decarb_pot_gbp, "decarb_pot_gbp", nonnegative=True)
    cm_weights = _amounts(cm_capacity_weights_mw, "cm_capacity_weights", nonnegative=True)
    decarb_weights = _amounts(eligible_decarb_capacity_mw, "eligible_decarb_capacity", nonnegative=True)
    if scenario == "basic":
        cm = 0.0
    if scenario in {"basic", "with_cm"}:
        decarb = 0.0

    def allocate(pot, weights):
        total = _number(sum(weights.values()), "total_policy_capacity", nonnegative=True)
        return ({asset: pot * weight / total for asset, weight in weights.items() if weight > 0}
                if total > 0 and pot > 0 else {})

    # Keep no-eligible-asset pots visible rather than claiming they were paid.
    cm_income = allocate(cm, cm_weights)
    decarb_income = allocate(decarb, decarb_weights)
    return {"scenario": scenario, "cm_income_gbp_by_asset": cm_income,
            "decarb_income_gbp_by_asset": decarb_income,
            "unallocated_cm_gbp": cm - sum(cm_income.values()),
            "unallocated_decarb_gbp": decarb - sum(decarb_income.values()),
            "eligibility_status": "caller_supplied_not_independently_evaluated"}


def allocate_thesis96_policy(state: object, *, scenario: str,
                            ancillary_budget_gbp: float, existing_decarb_budget_gbp: float,
                            additional_decarb_budget_gbp: float,
                            target_capacity_mw_by_technology: Mapping[str, float],
                            cm_derating_overrides: Mapping[str, float] | None = None) -> dict:
    """Final9.6 P630/P644/P645: annual transfers, not direct capacity additions.

    Budgets other than the thesis's fixed CM pot must be frozen caller inputs in
    2025 GBP. This function does not infer the historical CfD trend or target
    series. Basic disables additional mechanisms. Existing support enters only
    the system-cost view; only incremental support is investable. An unlisted
    storage technology requires an explicit, recorded de-rating decision.
    """
    from .doctoral_contract import load_thesis96_contract, thesis96_contract_identity
    scenarios = {"basic", "with_cm", "decarbonisation_base", "subsidy_as_usual", "governmental_target"}
    if scenario not in scenarios:
        raise ValueError("Unknown final9.6 policy scenario")
    ancillary = _number(ancillary_budget_gbp, "ancillary budget", nonnegative=True)
    existing = _number(existing_decarb_budget_gbp, "existing decarb budget", nonnegative=True)
    additional = _number(additional_decarb_budget_gbp, "additional decarb budget", nonnegative=True)
    targets = _amounts(target_capacity_mw_by_technology, "target capacities", nonnegative=True)
    overrides = _amounts(cm_derating_overrides or {}, "CM derating overrides", nonnegative=True)
    if any(value > 1 for value in overrides.values()):
        raise ValueError("CM derating must be between zero and one")
    contract = load_thesis96_contract()["policy"]
    derating = {**contract["cm_derating"], **overrides}
    vre = {"solar", "onshore", "offshore"}
    thermal = {"CCGT", "OCGT", "bio_and_waste", "Nuclear"}
    capacities, cm_weights, ancillary_weights, rows = {}, {}, {}, []
    seen = set()
    for asset in _field(state, "assets", ()):
        name, tech = _field(asset, "asset_id"), _field(asset, "technology")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Policy requires unique explicit asset IDs")
        seen.add(name)
        power = _number(_field(asset, "capacity_mw"), f"{name}.discharge MW", nonnegative=True)
        if _field(asset, "status") == "retired" or power == 0:
            continue
        capacities[tech] = capacities.get(tech, 0) + power
        rows.append((name, tech, power))
        storage = _field(asset, "energy_capacity_mwh") is not None
        if tech in thermal or storage:
            ancillary_weights[name] = power
            if scenario != "basic" and tech not in derating:
                raise ValueError(f"Missing final9.6 CM derating for {tech}; supply explicit frozen override")
        factor = derating.get(tech, 0)
        if factor > 0:
            cm_weights[name] = power * factor
    eligible = {}
    for name, tech, power in rows:
        if tech not in vre:
            continue
        if scenario == "governmental_target":
            if tech not in targets:
                raise ValueError(f"Missing governmental target capacity for {tech}")
            if capacities[tech] >= targets[tech]:
                continue
        eligible[name] = power
    basic = scenario == "basic"
    support_active = scenario in {"subsidy_as_usual", "governmental_target"}
    has_existing = scenario in {"decarbonisation_base", "subsidy_as_usual", "governmental_target"}
    active_cm = 0.0 if basic else contract["forward_annual_cm_budget_gbp"]
    active_ancillary = 0.0 if basic else ancillary
    active_additional = additional if support_active else 0.0
    # Reuse the reconciled arithmetic, with independently resolved eligibility.
    result = allocate_policy_transfers(scenario="basic" if basic else "decarb",
        cm_pot_gbp=active_cm, decarb_pot_gbp=active_additional,
        cm_capacity_weights_mw=cm_weights, eligible_decarb_capacity_mw=eligible)
    ancillary_alloc = allocate_policy_transfers(scenario="with_cm",
        cm_pot_gbp=active_ancillary, decarb_pot_gbp=0,
        cm_capacity_weights_mw=ancillary_weights, eligible_decarb_capacity_mw={})
    result.update({"policy_scenario": scenario,
        "ancillary_income_gbp_by_asset": ancillary_alloc["cm_income_gbp_by_asset"],
        "unallocated_ancillary_gbp": ancillary_alloc["unallocated_cm_gbp"],
        "cm_capacity_weights_mw": cm_weights,
        "ancillary_capacity_weights_mw": ancillary_weights,
        "eligible_decarb_capacity_mw": eligible if support_active else {},
        "cm_derating_overrides": overrides,
        "system_policy_costs_gbp": {"cm": active_cm, "ancillary": active_ancillary,
            "existing_decarb": existing if has_existing else 0.0,
            "additional_decarb": active_additional},
        "eligibility_status": "thesis_final9.6_with_explicit_overrides",
        "thesis_identity": thesis96_contract_identity()})
    return result


def build_system_cost_views(*, legacy_capital_cost_gbp: float, legacy_operating_cost_gbp: float,
                            deficit_mwh: float, existing_decarb_levy_gbp: float,
                            additional_decarb_levy_gbp: float, cm_levy_gbp: float,
                            generated_mwh: float, resource_capital_cost_gbp: float,
                            resource_operating_cost_gbp: float, resource_reliability_cost_gbp: float,
                            served_mwh: float) -> dict:
    """Original generation denominator and £17000 loss value beside resource view.

    The loss value was £8000 in the thesis code; decision A16-5 replaced it
    by the author's VoLL (accounting correction ``fx5.voll-17000``).

    The resource inputs are independently evaluated physical costs. Policy levies
    appear only in the original view; market payments are not resource costs.
    This function does not infer physical cost boundaries from the raw ledger.
    generated_mwh is the source's non-Battery gen_list total, which can include
    imports; it is not served demand or storage-discharge-inclusive generation.
    """
    values = {name: _number(value, name, nonnegative=True) for name, value in locals().copy().items()}
    lost = values["deficit_mwh"] * LEGACY_DEFICIT_VALUE_GBP_PER_MWH
    legacy = (values["legacy_capital_cost_gbp"] + values["legacy_operating_cost_gbp"] + lost
              + values["existing_decarb_levy_gbp"] + values["additional_decarb_levy_gbp"] + values["cm_levy_gbp"])
    resource = (values["resource_capital_cost_gbp"] + values["resource_operating_cost_gbp"]
                + values["resource_reliability_cost_gbp"])
    return {"legacy_system_cost_gbp": _number(legacy, "legacy_system_cost"),
            "legacy_cost_per_mwh_generated": legacy / values["generated_mwh"] if values["generated_mwh"] > 0 else 0.0,
            "legacy_deficit_cost_gbp": lost,
            "resource_system_cost_gbp": _number(resource, "resource_system_cost"),
            "resource_cost_per_mwh_served": resource / values["served_mwh"] if values["served_mwh"] > 0 else None,
            "resource_intensity_status": "evaluated" if values["served_mwh"] > 0 else "not_evaluated"}


def legacy_carbon_metric(source_rows: Sequence[Mapping], *, electrolyzer_body_emission: float) -> dict:
    """Retain the original scalar and original row multiplicity without a tonne label."""
    scalar = 0.0
    intensity = 0.0
    for row in source_rows:
        scalar += _number(row["carbon_emission"], "carbon_emission")
        quantity = _number(row["generation_source_quantity"], "generation_source_quantity")
        if "carbon_intensity" in row:
            intensity += _number(row["carbon_intensity"], "carbon_intensity") * quantity
    scalar += _number(electrolyzer_body_emission, "electrolyzer_body_emission")
    return {"legacy_carbon_metric": _number(scalar + intensity, "legacy_carbon_metric"),
            "unit_status": "unknown_source_scalar"}


def physical_carbon_view(generation_mwh_by_asset: Mapping[str, float],
                         kgco2e_per_mwh_by_asset: Mapping[str, float]) -> dict:
    """Explicit physical operational activity factors; no invented storage inventory."""
    generation = _amounts(generation_mwh_by_asset, "generation_mwh", nonnegative=True)
    factors = _amounts(kgco2e_per_mwh_by_asset, "kgco2e_per_mwh", nonnegative=True)
    _coverage(factors, set(generation), "physical_carbon_factor")
    carbon = {asset: _number(energy * factors[asset] / 1000, f"carbon[{asset}]")
              for asset, energy in generation.items()}
    return {"operational_tco2e_by_asset": carbon,
            "operational_tco2e": _number(sum(carbon.values()), "operational_tco2e"),
            "operational_scope": "only_explicit_activity_and_factors",
            "storage_carbon_status": "not_evaluated", "closing_storage_carbon_tco2e": None,
            "overall_carbon_status": "not_evaluated"}
