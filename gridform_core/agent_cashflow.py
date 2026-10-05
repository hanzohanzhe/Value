"""Per-asset operating cashflow inputs of the CEM (``value.agent-cashflow/v1``, P0-7).

A PSM that can be combined with ``agent-investment`` publishes, in
``MarketYearResult.extensions['agent_cashflow']``, one row per operating asset
it dispatched as a generator: the MWh it generated in the year and the per-MWh
cost components of its running cost. ``agent-investment`` reads it for the
restored Scheme C thermal net revenue (decision A4, both profiles): net =
income - generated MWh x (generation + fuel + carbon + unit_time). VRE and
storage keep gross revenue as profit (A4/A7) and need no row.

Only the operating-cost term is carried here; income stays the PSM's
``market_income_gbp_by_agent`` (lead ruling 2026-10-05).
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .investment_accounts import A4_COST_FIELDS, finite_number

SCHEMA_VERSION = "value.agent-cashflow/v1"
EXTENSION_KEY = "agent_cashflow"
COMPONENT_FIELDS = A4_COST_FIELDS[1:]


def cashflow_row(
    technology: str, generated_mwh: float, components: Mapping[str, object], *, cost_basis: str,
) -> dict[str, object]:
    row: dict[str, object] = {"technology": str(technology),
                              "generated_mwh": finite_number(generated_mwh, "generated MWh", nonnegative=True)}
    for name in COMPONENT_FIELDS:
        row[name] = finite_number(components[name], name, nonnegative=True)
    row["cost_basis"] = str(cost_basis)
    return row


def allocate_object_cashflow(
    objects: Iterable[Mapping[str, object]],
    technology_by_asset: Mapping[str, str],
    *,
    cost_basis: str,
) -> dict[str, dict[str, object]]:
    """Allocate runtime generator objects to the operating assets they aggregate.

    Each object row has ``generated_mwh``, the four cost components and
    ``source_asset_capacity_mw`` (asset id -> MW represented by the object).
    An asset's MWh is its capacity share of each object's MWh; when it is
    split over objects with different costs, each component is the
    MWh-weighted mean (capacity-weighted when it generated nothing), so
    ``MWh x sum(components)`` is the sum of the objects' running costs.
    """
    energy: dict[str, float] = {}
    weighted: dict[str, dict[str, float]] = {}
    weights: dict[str, float] = {}
    capacity_weighted: dict[str, dict[str, float]] = {}
    for item in objects:
        sources = {str(key): float(value) for key, value in dict(item.get("source_asset_capacity_mw") or {}).items()
                   if float(value) > 0}
        denominator = sum(sources.values())
        if denominator <= 0:
            continue
        mwh = finite_number(item["generated_mwh"], "object generated MWh", nonnegative=True)
        for asset_id, capacity in sources.items():
            share = capacity / denominator
            asset_mwh = mwh * share
            energy[asset_id] = energy.get(asset_id, 0.0) + asset_mwh
            weights[asset_id] = weights.get(asset_id, 0.0) + capacity
            for name in COMPONENT_FIELDS:
                value = finite_number(item[name], name, nonnegative=True)
                weighted.setdefault(asset_id, {}).setdefault(name, 0.0)
                weighted[asset_id][name] += asset_mwh * value
                capacity_weighted.setdefault(asset_id, {}).setdefault(name, 0.0)
                capacity_weighted[asset_id][name] += capacity * value
    rows: dict[str, dict[str, object]] = {}
    for asset_id in sorted(energy):
        if asset_id not in technology_by_asset:
            continue
        if energy[asset_id] > 0:
            components = {name: weighted[asset_id][name] / energy[asset_id] for name in COMPONENT_FIELDS}
        else:
            components = {name: capacity_weighted[asset_id][name] / weights[asset_id] for name in COMPONENT_FIELDS}
        rows[asset_id] = cashflow_row(technology_by_asset[asset_id], energy[asset_id], components,
                                      cost_basis=cost_basis)
    return rows


def unit_cost_cashflow(
    generation_mwh_by_asset: Mapping[str, float],
    unit_cost_by_asset: Mapping[str, float],
    technology_by_asset: Mapping[str, str],
    *,
    cost_basis: str,
) -> dict[str, dict[str, object]]:
    """Rows from a PSM that knows one total running cost per MWh and asset.

    The total goes into ``generation_cost_gbp_per_mwh`` with zero fuel, carbon
    and unit-time parts; ``cost_basis`` says so. Assets without a unit cost
    get no row (a thermal asset without one then fails closed in decide()).
    """
    rows: dict[str, dict[str, object]] = {}
    for asset_id, technology in sorted(technology_by_asset.items()):
        if asset_id not in unit_cost_by_asset:
            continue
        components = {name: 0.0 for name in COMPONENT_FIELDS}
        components["generation_cost_gbp_per_mwh"] = float(unit_cost_by_asset[asset_id])
        rows[asset_id] = cashflow_row(technology, float(generation_mwh_by_asset.get(asset_id, 0.0) or 0.0),
                                      components, cost_basis=cost_basis)
    return rows


def extension(rows: Mapping[str, Mapping[str, object]], *, psm_module_id: str, cost_basis: str) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "identity": "asset", "psm_module_id": psm_module_id,
            "cost_basis": cost_basis, "income_source": "market_income_gbp_by_agent",
            "assets": {key: dict(value) for key, value in sorted(rows.items())}}


def cost_rows_for_a4(market_extensions: Mapping[str, object]) -> dict[str, dict[str, object]] | None:
    """The A4 cost rows of a market result, or None when the PSM publishes none."""
    payload = market_extensions.get(EXTENSION_KEY)
    if payload is None:
        return None
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"market extension {EXTENSION_KEY} is not {SCHEMA_VERSION}")
    assets = payload.get("assets")
    if not isinstance(assets, Mapping):
        raise ValueError(f"market extension {EXTENSION_KEY} has no asset rows")
    rows: dict[str, dict[str, object]] = {}
    for asset_id, row in assets.items():
        if not isinstance(row, Mapping):
            raise ValueError(f"agent cashflow row of {asset_id} is not a mapping")
        rows[str(asset_id)] = {key: value for key, value in row.items() if key != "cost_basis"}
    return rows
