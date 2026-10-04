"""Pure investment-decision arithmetic for the VALUE v2 CEM (P0-7).

Nothing here reads contracts, registries, files or global state, so every
function can be tested and audited on plain numbers. The module has three
parts:

1. ``require_agent_cashflow``: the fail-closed boundary for per-asset cashflow
   inputs (a missing asset, field, NaN, infinity, boolean or negative cost is
   an error, never a zero).
2. ``scheme_c_investment_net_revenue``: the Scheme C investment net revenue
   restored by decision A4. Thermal assets deduct ``generated MWh x gen_cost``
   where gen_cost is generation + fuel + carbon + unit-time cost, as in
   ``runtime_compat/modular_investment_support.py:2150-2152, 2246-2247``.
   Thermal is decided by technology first (``THERMAL_TECHNOLOGIES``: gas and
   biomass), then by a fuel or carbon cost for any other technology. VRE and
   storage keep gross revenue as profit (thesis assumption: CAPEX and
   depreciation only, no OPEX). Every income and cost component is a
   required argument: a left-out component is an error, never a zero.
   ``a4_net_revenue_for_decidable_groups`` applies it only to groups whose
   investment mode can reach a decision (mode filter first).
3. The ``head_*`` functions: the investment rule of the v2
   ``SchemeCAgentInvestmentDefinition.decide`` at 35aadb3, decomposed without
   any change of arithmetic or evaluation order. ``head_decide_accounts``
   recomposes them; ``tests/test_p07_head_decide_record.py`` proves the
   recomposition is bit-identical to the recorded HEAD ``decide()`` outputs.
   P0-7 S4 replaces the body of ``decide()`` with these functions.

Plus ``allocate_capped_requests`` (technology cap, then pool cap, each by
proportional scaling) for the corrected power-battery pool (P5-02).

Money convention (decision A6, P4-02 removed from scope): every amount is in
constant base-year GBP and investment decisions are undiscounted by design.
The ROI / payback tiers below are the model's rule, not an approximation of an
NPV test, and no NPV, IRR or annuity hurdle is introduced.
"""

from __future__ import annotations

import math
import numbers
from typing import Callable, Iterable, Mapping, Sequence

SCHEMA_VERSION = "value.investment-accounts/v1"
MONEY_BASIS = "constant_base_year_gbp_undiscounted"

# HEAD v2 decide() fallbacks (v2_module_definitions.py at 35aadb3).
HEAD_DEFAULT_PREFERRED_RATE = 0.08
HEAD_DEFAULT_ECONOMIC_LIFETIME_YEARS = 25.0
HEAD_HEADROOM_MODE = "headroom_required"
HEAD_SKIPPED_MODES = frozenset({"denied", "site_data_required"})

NET_REVENUE_BASIS_THERMAL = "scheme_c_income_less_energy_times_gen_cost"
NET_REVENUE_BASIS_GROSS = "gross_revenue_is_profit"

# Decision A4 technology classes. THERMAL_TECHNOLOGIES equals the thermal
# literal of canonical_psm_data._doctoral_marginal_cost (read with ast in the
# tests; that file stays byte-identical to 35aadb3 because it feeds the doctoral
# weather identity hash) and the explicit_uncapped modes of
# data/cem/investment_eligibility.json. Other thermal sets exist for other
# purposes and are not this one: doctoral_ledgers (CM/ancillary weights,
# includes Nuclear) and doctoral_policy.THERMAL_HIGH_TECHNOLOGIES.
THERMAL_TECHNOLOGIES = frozenset({"CCGT", "OCGT", "gas", "bio_and_waste"})
VRE_TECHNOLOGIES = frozenset({"solar", "onshore", "offshore"})
STORAGE_TECHNOLOGIES = frozenset({"1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"})
GROSS_PROFIT_TECHNOLOGIES = VRE_TECHNOLOGIES | STORAGE_TECHNOLOGIES

RECOMMENDATIONS = ("Invest_High", "Invest_Profit", "Do_Nothing", "Deplete")


# ---------------------------------------------------------------------------
# Fail-closed numeric boundary
# ---------------------------------------------------------------------------

def finite_number(value: object, label: str, *, nonnegative: bool = False) -> float:
    """Return ``value`` as a finite float or raise ``ValueError``.

    Any real number is accepted, including numpy scalars (``np.int64``,
    ``np.float32``) from pandas or sqlite aggregates. Booleans (Python and
    numpy) and non-numeric values are rejected rather than coerced.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{label} must be a number, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if nonnegative and result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def require_agent_cashflow(
    cashflow: object,
    asset_ids: Iterable[str],
    *,
    fields: Sequence[str] = ("market_income_gbp", "operating_cost_gbp"),
    nonnegative_fields: Sequence[str] = ("operating_cost_gbp",),
) -> dict[str, dict[str, float]]:
    """Validate per-asset cashflow rows; an absent row is never a zero.

    ``cashflow`` maps asset id to a row of numbers. Every requested asset must
    have a row with every field in ``fields``; each value must be a finite
    number, and fields in ``nonnegative_fields`` must not be negative. Income
    may be negative (negative prices). Returns the parsed rows for the
    requested assets only.
    """
    if not isinstance(cashflow, Mapping):
        raise ValueError("agent cashflow must be a mapping keyed by asset id")
    unknown = set(nonnegative_fields) - set(fields)
    if unknown:
        raise ValueError("nonnegative cashflow fields must be required fields: " + ", ".join(sorted(unknown)))
    parsed: dict[str, dict[str, float]] = {}
    for asset_id in asset_ids:
        key = str(asset_id)
        if key not in cashflow:
            raise ValueError(f"agent cashflow missing for asset {key}")
        row = cashflow[key]
        if not isinstance(row, Mapping):
            raise ValueError(f"agent cashflow row for asset {key} must be a mapping")
        values: dict[str, float] = {}
        for field in fields:
            if field not in row:
                raise ValueError(f"agent cashflow for asset {key} lacks {field}")
            values[field] = finite_number(
                row[field], f"agent cashflow {key}.{field}",
                nonnegative=field in nonnegative_fields,
            )
        parsed[key] = values
    return parsed


# ---------------------------------------------------------------------------
# Scheme C investment net revenue (decision A4)
# ---------------------------------------------------------------------------

def deducts_energy_cost(
    *, technology: str, fuel_cost_gbp_per_mwh: float, carbon_cost_gbp_per_mwh: float,
) -> bool:
    """A4: whether an asset nets its energy cost from its investment revenue.

    * ``THERMAL_TECHNOLOGIES`` (gas, biomass) always deduct, even when a data
      set carries zero fuel and carbon cost: the generation and unit-time
      parts of gen_cost are still owed.
    * VRE and storage never deduct (gross revenue is profit). A fuel or carbon
      cost on them contradicts the thesis assumption and is an error.
    * Any other technology deducts when it has a fuel or carbon cost (e.g.
      coal). Without one, A4 defines no basis and the call fails closed; at
      HEAD such technologies (Nuclear, hydro, unknown) never reach a proposal
      because their investment mode is denied or site_data_required.

    Ordering rule (P0-7 S4): A4 net revenue is computed only for groups whose
    investment mode is not in ``HEAD_SKIPPED_MODES`` (denied,
    site_data_required). The mode filter runs first; computing A4 for the
    whole fleet would raise here for Nuclear, Hydro_natural_flow and
    pumped_hydro. ``a4_net_revenue_for_decidable_groups`` applies that order.
    """
    if not isinstance(technology, str) or not technology:
        raise ValueError("A4 net revenue needs a technology name")
    fuel = finite_number(fuel_cost_gbp_per_mwh, "fuel cost", nonnegative=True)
    carbon = finite_number(carbon_cost_gbp_per_mwh, "carbon cost", nonnegative=True)
    if technology in GROSS_PROFIT_TECHNOLOGIES:
        if fuel > 0 or carbon > 0:
            raise ValueError(
                f"{technology} keeps gross revenue as profit (A4) but carries a fuel or carbon cost")
        return False
    if technology in THERMAL_TECHNOLOGIES:
        return True
    if fuel > 0 or carbon > 0:
        return True
    raise ValueError(f"A4 defines no net revenue basis for {technology} without a fuel or carbon cost")


def scheme_c_investment_net_revenue(
    *,
    technology: str,
    electricity_income_gbp: float,
    hydrogen_income_gbp: float,
    generated_mwh: float,
    generation_cost_gbp_per_mwh: float,
    fuel_cost_gbp_per_mwh: float,
    carbon_cost_gbp_per_mwh: float,
    unit_time_cost_gbp_per_mwh: float,
) -> dict[str, object]:
    """Annual investment net revenue under the restored Scheme C rule.

    Every argument is required and has no default, for every technology: a
    left-out income or cost component is a ``TypeError``, never a zero
    (review M0-P0-7-S1 round 2). A zero must be passed explicitly, e.g. the
    zero fuel and carbon cost of a VRE asset or the zero hydrogen income of an
    asset without electrolysis.

    Source (runtime_compat/modular_investment_support.py): line 2151 books
    ``energy x PHYSICAL_PERIOD_HOURS x gen_cost`` per generator, where energy is
    the summed per-period MW; ``generated_mwh`` here is already that energy in
    MWh. Lines 2246-2247 give ``net = electricity + hydrogen - operating``.
    The source ``gen_cost`` of Gas/BiomassGenerator is generation + carbon +
    fuel + unit-time cost (runtime_compat/modular_simulation_model.py:480, 561;
    compat/modular_simulation_model.py:422, 503 in the preserved copy).

    The basis is chosen by ``deducts_energy_cost`` (technology first). VRE,
    whose source gen_cost is 0.0001, and storage keep gross revenue as profit,
    so their operating cost here is exactly zero.
    """
    income = finite_number(electricity_income_gbp, "electricity income")
    hydrogen = finite_number(hydrogen_income_gbp, "hydrogen income")
    energy = finite_number(generated_mwh, "generated MWh", nonnegative=True)
    generation = finite_number(generation_cost_gbp_per_mwh, "generation cost", nonnegative=True)
    fuel = finite_number(fuel_cost_gbp_per_mwh, "fuel cost", nonnegative=True)
    carbon = finite_number(carbon_cost_gbp_per_mwh, "carbon cost", nonnegative=True)
    unit_time = finite_number(unit_time_cost_gbp_per_mwh, "unit-time cost", nonnegative=True)
    total_income = income + hydrogen
    if deducts_energy_cost(technology=technology, fuel_cost_gbp_per_mwh=fuel, carbon_cost_gbp_per_mwh=carbon):
        gen_cost = generation + carbon + fuel + unit_time
        operating = energy * gen_cost
        basis = NET_REVENUE_BASIS_THERMAL
    else:
        gen_cost = None
        operating = 0.0
        basis = NET_REVENUE_BASIS_GROSS
    return {
        "technology": technology,
        "electricity_income_gbp": income,
        "hydrogen_income_gbp": hydrogen,
        "total_income_gbp": total_income,
        "generated_mwh": energy,
        "gen_cost_gbp_per_mwh": gen_cost,
        "operating_cost_gbp": operating,
        "net_revenue_gbp": total_income - operating,
        "basis": basis,
    }


def a4_net_revenue_for_decidable_groups(
    groups: Sequence[Mapping[str, object]],
    mode_of: Callable[[str], str],
    cashflow_inputs: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    """A4 net revenue for the members of the groups that can reach a decision.

    ``groups`` come from ``head_group_assets`` (each member has an
    ``asset_id``). The investment-mode filter runs first: a group whose mode
    is in ``HEAD_SKIPPED_MODES`` (Nuclear, hydro, coal, unknown technologies)
    is skipped before any A4 call, and cashflow rows of its assets are
    ignored. Every member of every other group needs a cashflow row carrying
    all arguments of ``scheme_c_investment_net_revenue`` except the
    technology; a missing row is a ``ValueError``, never a zero. A row may
    name its technology, which must then equal the group's. Returns the A4
    result row by asset id.
    """
    if not isinstance(cashflow_inputs, Mapping):
        raise ValueError("A4 cashflow inputs must be a mapping keyed by asset id")
    result: dict[str, dict[str, object]] = {}
    for group in groups:
        technology = str(group["technology"])
        if mode_of(technology) in HEAD_SKIPPED_MODES:
            continue
        for member in group["members"]:  # type: ignore[union-attr]
            asset_id = str(member["asset_id"])
            row = cashflow_inputs.get(asset_id)
            if not isinstance(row, Mapping):
                raise ValueError(f"A4 cashflow inputs missing for asset {asset_id}")
            arguments = dict(row)
            named = arguments.pop("technology", technology)
            if named != technology:
                raise ValueError(f"A4 cashflow row of {asset_id} names {named}, its group is {technology}")
            result[asset_id] = scheme_c_investment_net_revenue(technology=technology, **arguments)
    return result


# ---------------------------------------------------------------------------
# HEAD v2 decide() rule, decomposed (doctoral-lineage freeze, 35aadb3)
# ---------------------------------------------------------------------------

def merge_headroom_caps(rows: Iterable[Mapping[str, object]]) -> dict[str, float]:
    """Per technology, the smallest clamped allowance over all headroom rows."""
    caps: dict[str, float] = {}
    for row in rows:
        for technology, value in row.items():
            value = max(0.0, float(value))
            caps[technology] = min(caps.get(technology, value), value)
    return caps


def head_investment_owner(asset_id: str, extensions: Mapping[str, object]) -> str:
    """Owner key; commissioned assets without a recorded owner have none."""
    return str(
        extensions.get("investment_owner_id")
        or extensions.get("source_agent_id")
        or ("" if asset_id.startswith("commissioned:") else asset_id)
    )


def head_income_lookup(income_by_agent: Mapping[str, object], asset_id: str) -> float:
    """HEAD treats a missing or falsy income entry as zero (P0-7 S4 fails closed)."""
    return float(income_by_agent.get(asset_id, 0.0) or 0.0)


def head_group_assets(
    assets: Iterable[Mapping[str, object]], income_by_agent: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Group live assets by (owner, technology, region) in HEAD order.

    ``assets`` rows carry ``asset_id``, ``technology``, ``capacity_mw``,
    ``status``, ``region`` and ``extensions`` (an ``AssetStateV2.to_dict()``
    has them all). Returns the groups sorted by key, each with its members and
    their HEAD income, and the ineligible assets in input order.
    """
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    ineligible: list[dict[str, str]] = []
    for asset in assets:
        asset_id = str(asset["asset_id"])
        if float(asset["capacity_mw"]) <= 0 or asset.get("status") == "retired":  # type: ignore[arg-type]
            continue
        extensions: Mapping[str, object] = dict(asset.get("extensions") or {})  # type: ignore[call-overload]
        owner = head_investment_owner(asset_id, extensions)
        if not owner or extensions.get("investment_eligible") is False:
            ineligible.append({"asset_id": asset_id, "reason": "no_investment_owner"})
            continue
        key = (owner, str(asset["technology"]), str(asset.get("region") or "GB"))
        grouped.setdefault(key, []).append({
            "asset_id": asset_id,
            "capacity_mw": asset["capacity_mw"],
            "income_gbp": head_income_lookup(income_by_agent, asset_id),
            "extensions": extensions,
        })
    groups = [
        {"owner": owner, "technology": technology, "region": region, "members": members}
        for (owner, technology, region), members in sorted(grouped.items())
    ]
    return groups, ineligible


def head_group_account(members: Sequence[Mapping[str, object]]) -> dict[str, float]:
    """Financial account of one (owner, technology, region) group.

    Each member provides ``capacity_mw``, ``income_gbp`` and ``extensions``.
    Sums run in member order with ``sum()``, exactly as HEAD does.
    """
    def ext(member: Mapping[str, object]) -> Mapping[str, object]:
        return member["extensions"]  # type: ignore[return-value]

    capacity = sum(float(member["capacity_mw"]) for member in members)  # type: ignore[arg-type]
    income = sum(float(member["income_gbp"]) for member in members)  # type: ignore[arg-type]
    operational = sum(
        float(ext(member).get("annual_operational_cost_gbp", 0.0) or 0.0)  # type: ignore[arg-type]
        for member in members
    )
    net = income - operational
    replacement = sum(
        float(ext(member).get("total_capex_gbp", 0.0) or 0.0)  # type: ignore[arg-type]
        for member in members
    )
    cost_per_mw = replacement / capacity if capacity > 0 else 0.0
    roi = net / replacement if replacement > 0 else 0.0
    preferred = max(
        float(ext(member).get("preferred_rate", HEAD_DEFAULT_PREFERRED_RATE) or HEAD_DEFAULT_PREFERRED_RATE)  # type: ignore[arg-type]
        for member in members
    )
    life = min(
        float(ext(member).get("economic_lifetime_years", HEAD_DEFAULT_ECONOMIC_LIFETIME_YEARS)  # type: ignore[arg-type]
              or HEAD_DEFAULT_ECONOMIC_LIFETIME_YEARS)
        for member in members
    )
    target_payback = float(
        min(
            float(ext(member).get("target_payback_years", life) or life)  # type: ignore[arg-type]
            for member in members
        )
    )
    payback = replacement / net if net > 0 else math.inf
    return {
        "capacity_mw": capacity,
        "income_gbp": income,
        "operational_cost_gbp": operational,
        "net_revenue_gbp": net,
        "replacement_capital_gbp": replacement,
        "cost_per_mw_gbp": cost_per_mw,
        "roi": roi,
        "preferred_rate": preferred,
        "economic_lifetime_years": life,
        "target_payback_years": target_payback,
        "payback_years": payback,
    }


def head_is_deplete(net_revenue: float, cost_per_mw: float) -> bool:
    """HEAD checks a loss before the tiers, and only with a positive unit cost."""
    return net_revenue < 0 and cost_per_mw > 0


def head_tier(roi: float, preferred_rate: float, payback_years: float, target_payback_years: float) -> str:
    """Strict ROI test, then inclusive payback test (undiscounted, A6)."""
    if roi > preferred_rate:
        return "Invest_High"
    if payback_years <= target_payback_years:
        return "Invest_Profit"
    return "Do_Nothing"


def head_recommendation(account: Mapping[str, float]) -> str:
    if head_is_deplete(account["net_revenue_gbp"], account["cost_per_mw_gbp"]):
        return "Deplete"
    return head_tier(
        account["roi"], account["preferred_rate"],
        account["payback_years"], account["target_payback_years"],
    )


def head_retirement_mw(net_revenue: float, capacity_mw: float, target_payback_years: float, cost_per_mw: float) -> float:
    """Loss times target payback, converted to MW at the group unit cost."""
    return min(capacity_mw, abs(net_revenue) * target_payback_years / cost_per_mw)


def head_requested_addition_mw(net_revenue: float, cost_per_mw: float) -> float:
    """HEAD sizes every proposal as net revenue over unit capital cost."""
    return net_revenue / cost_per_mw


def head_greedy_allocation(
    requested_mw: float, technology: str, mode: str, remaining_caps: dict[str, float],
) -> float:
    """First-come allocation against the shared technology headroom.

    Mutates ``remaining_caps`` for headroom-limited technologies and returns
    the accepted addition (zero or negative means no proposal).
    """
    allowed = remaining_caps.get(technology, 0.0) if mode == HEAD_HEADROOM_MODE else requested_mw
    addition = min(max(requested_mw, 0.0), max(allowed, 0.0))
    if addition <= 0:
        return addition
    if mode == HEAD_HEADROOM_MODE:
        remaining_caps[technology] = max(0.0, allowed - addition)
    return addition


def head_decide_accounts(
    groups: Sequence[Mapping[str, object]],
    caps: Mapping[str, float],
    mode_of: Callable[[str], str],
) -> dict[str, object]:
    """Recompose HEAD decide() over pre-grouped plain data.

    ``groups`` must be in HEAD order (sorted by (owner, technology, region));
    each has ``owner``, ``technology``, ``region`` and ``members`` (see
    ``head_group_account``, plus ``asset_id``). Returns one outcome per group,
    the per-asset retirements and the remaining headroom.
    """
    remaining = dict(caps)
    outcomes: list[dict[str, object]] = []
    retirements: dict[str, float] = {}
    for index, group in enumerate(groups):
        technology = str(group["technology"])
        members: Sequence[Mapping[str, object]] = group["members"]  # type: ignore[assignment]
        outcome: dict[str, object] = {
            "index": index, "owner": group["owner"], "technology": technology,
            "region": group["region"], "mode": mode_of(technology),
            "recommendation": None, "requested_addition_mw": None,
            "accepted_addition_mw": 0.0, "retirement_mw": 0.0, "account": None,
        }
        outcomes.append(outcome)
        if outcome["mode"] in HEAD_SKIPPED_MODES:
            outcome["skipped"] = outcome["mode"]
            continue
        account = head_group_account(members)
        outcome["account"] = account
        recommendation = head_recommendation(account)
        outcome["recommendation"] = recommendation
        if recommendation == "Deplete":
            requested_retirement = head_retirement_mw(
                account["net_revenue_gbp"], account["capacity_mw"],
                account["target_payback_years"], account["cost_per_mw_gbp"],
            )
            outcome["retirement_mw"] = requested_retirement
            for member in members:
                retirements[str(member["asset_id"])] = (
                    requested_retirement * float(member["capacity_mw"]) / account["capacity_mw"]  # type: ignore[arg-type]
                )
            continue
        if account["cost_per_mw_gbp"] <= 0 or recommendation == "Do_Nothing":
            continue
        requested = head_requested_addition_mw(account["net_revenue_gbp"], account["cost_per_mw_gbp"])
        outcome["requested_addition_mw"] = requested
        addition = head_greedy_allocation(requested, technology, str(outcome["mode"]), remaining)
        if addition > 0:
            outcome["accepted_addition_mw"] = addition
    return {"outcomes": outcomes, "retirements_mw": retirements,
            "initial_caps": dict(caps), "remaining_caps": remaining}


# ---------------------------------------------------------------------------
# Proportional capped allocation (corrected power-battery pool, P5-02)
# ---------------------------------------------------------------------------

def allocate_capped_requests(
    requests: Sequence[Mapping[str, object]],
    *,
    technology_caps: Mapping[str, float] | None = None,
    pools: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Scale requests to the technology caps, then to the shared pool caps.

    ``requests`` rows have a unique ``request_id``, a ``technology`` and a
    nonnegative ``requested_mw``. A technology absent from ``technology_caps``
    is not capped at that stage. ``pools`` maps a pool id to ``cap_mw`` and the
    ``technologies`` it covers; a technology may belong to at most one pool.
    Each stage multiplies before dividing (``request * cap / total``, total
    summed left to right in request order) so equal shares come out exact.
    Every stage then ends with its sum, left to right in request order and as
    ``math.fsum``, at or below the cap: rounding of the proportional shares can
    overshoot by an ulp, and so can ``math.fsum`` of requests whose left-to-right
    sum fits the cap exactly; the clamp takes the excess back from the largest
    share (a change of a few ulp, never below zero). A stage that fits only
    under the left-to-right sum is clamped but not scaled, and its reported
    factor is 1.0. The guarantee covers exactly these two summations: another
    order (``numpy.sum`` pairwise, pandas) can still land a rounding step above the
    cap, so a strict check must use ``sum`` in request order or
    ``math.fsum``, or allow a few ulp. Returns accepted MW by request id and
    the scale factors applied per technology and per pool.
    """
    tech_caps = {
        str(tech): finite_number(value, f"{tech} technology cap", nonnegative=True)
        for tech, value in dict(technology_caps or {}).items()
    }
    pool_of: dict[str, str] = {}
    pool_caps: dict[str, float] = {}
    for pool_id, spec in dict(pools or {}).items():
        pool_caps[str(pool_id)] = finite_number(spec.get("cap_mw"), f"{pool_id} pool cap", nonnegative=True)
        for tech in spec.get("technologies") or ():  # type: ignore[union-attr]
            if str(tech) in pool_of:
                raise ValueError(f"technology {tech} belongs to more than one pool")
            pool_of[str(tech)] = str(pool_id)
    order: list[str] = []
    technology: dict[str, str] = {}
    accepted: dict[str, float] = {}
    for row in requests:
        request_id = str(row.get("request_id") or "")
        if not request_id or request_id in technology:
            raise ValueError("capped allocation requires unique nonempty request ids")
        technology[request_id] = str(row.get("technology") or "")
        if not technology[request_id]:
            raise ValueError(f"request {request_id} lacks a technology")
        accepted[request_id] = finite_number(row.get("requested_mw"), f"request {request_id}", nonnegative=True)
        order.append(request_id)

    def stage_total(members: list[str]) -> float:
        values = [accepted[key] for key in members]
        return max(sum(values), math.fsum(values))

    def scale(members: list[str], cap: float) -> float:
        if stage_total(members) <= cap:
            return 1.0
        total = sum(accepted[key] for key in members)
        factor = 1.0
        if total > cap:
            for key in members:
                accepted[key] = accepted[key] * cap / total
            factor = cap / total
        # Otherwise only math.fsum exceeds the cap (the left-to-right sum fits):
        # no proportional scaling, the clamp alone takes back the ulp overshoot.
        for _ in range(64):
            excess = stage_total(members) - cap
            if excess <= 0:
                break
            largest = max(members, key=lambda key: accepted[key])
            value = accepted[largest]
            accepted[largest] = max(0.0, min(value - excess, math.nextafter(value, 0.0)))
        else:  # pragma: no cover - each pass removes at least one ulp of the excess
            raise ArithmeticError("capped allocation could not be clamped to its cap")
        return factor

    technology_scale: dict[str, float] = {}
    for tech in dict.fromkeys(technology[key] for key in order):
        if tech in tech_caps:
            technology_scale[tech] = scale([key for key in order if technology[key] == tech], tech_caps[tech])
    pool_scale: dict[str, float] = {}
    for pool_id, cap in pool_caps.items():
        members = [key for key in order if pool_of.get(technology[key]) == pool_id]
        pool_scale[pool_id] = scale(members, cap) if members else 1.0
    return {"accepted_mw": {key: accepted[key] for key in order},
            "technology_scale": technology_scale, "pool_scale": pool_scale}
