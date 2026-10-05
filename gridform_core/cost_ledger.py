"""Versioned CEM resource-cost accounting for public VALUE results."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

from .v2.contracts import MarketYearResult


COST_LEDGER_SCHEMA = "value.annual-cost-ledger/v2"
CEM_SYSTEM_COST_DEFINITION = "value.cem-system-resource-cost/v1"
# Cost ledger v2 (P0-7 S8): the headline capital is the PSM's annualised
# capital and FOM less (a) VRE and storage fixed OPEX, which decision A7 folds
# into their levelised CAPEX (both profiles), and (b) under the corrected
# profile, the existing-stock compatibility capital of run-of-river hydro
# (P4-03, ~GBP 10.96bn/year on the UK pack), each kept as a memo line.
COMPATIBILITY_CAPITAL_LINE = "existing_stock_compatibility.annualised_capital"
VRE_STORAGE_FOM_LINE = "vre_storage.fixed_opex_in_levelised_capex"


@dataclass(frozen=True)
class CostLine:
    id: str
    view: str
    amount_gbp: float | None
    classification: str
    source: str
    included_in_cem_system_cost: bool
    reason: str | None = None


@dataclass(frozen=True)
class AnnualCostLedger:
    year: int
    cem_system_cost_gbp: float | None
    cem_system_cost_gbp_per_mwh_served: float | None
    demand_served_mwh: float
    gross_generation_mwh: float
    physical_reconciliation_residual_gbp: float | None
    lines: tuple[CostLine, ...]
    legacy_system_cost_gbp: float | None = None
    legacy_cost_per_mwh_generated: float | None = None
    headline_capital_gbp: float | None = None
    compatibility_capital_gbp: float | None = None
    compatibility_capital_in_headline: bool | None = None
    vre_storage_fixed_opex_excluded_gbp: float | None = None
    schema_version: str = COST_LEDGER_SCHEMA
    definition_id: str = CEM_SYSTEM_COST_DEFINITION
    status: str = "reconciled"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _finite_nonnegative(value: object, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return number


def _finite(value: object, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def build_cem_cost_ledger(
    market: MarketYearResult,
    *,
    legacy_system_cost_gbp: float | None = None,
    legacy_cost_per_mwh_generated: float | None = None,
    tolerance_gbp: float = 1e-4,
    exclude_compatibility_capital: bool = False,
) -> AnnualCostLedger:
    """Build the headline CEM resource-cost view without settlement double counting.

    A PSM may provide a named operating-cost breakdown in
    ``extensions.physical_operating_cost_components_gbp``. When it does not, the
    already-typed operational total remains one explicit, opaque resource line.
    """

    capital = _finite_nonnegative(
        market.total_levelized_capital_cost_gbp,
        "total_levelized_capital_cost_gbp",
    )
    operating = _finite_nonnegative(
        market.total_operational_cost_gbp,
        "total_operational_cost_gbp",
    )
    demand = _finite_nonnegative(market.total_demand_mwh, "total_demand_mwh")
    blackout = _finite_nonnegative(market.total_blackout_mwh, "total_blackout_mwh")
    generation = _finite_nonnegative(market.total_generation_mwh, "total_generation_mwh")
    served = max(demand - blackout, 0.0)

    network_costs = market.extensions.get("network_resource_costs_gbp")
    network_capex = network_fom = network_policy = 0.0
    if isinstance(network_costs, Mapping):
        network_capex = _finite_nonnegative(
            network_costs.get("annualized_capex_gbp", 0.0),
            "network annualized CAPEX",
        )
        network_fom = _finite_nonnegative(
            network_costs.get("fixed_opex_gbp", 0.0),
            "network fixed OPEX",
        )
        network_policy = _finite_nonnegative(
            network_costs.get("policy_support_gbp", 0.0),
            "network policy support",
        )
    network_resource_cost = network_capex + network_fom
    if network_resource_cost > capital + tolerance_gbp:
        raise ValueError("Network CAPEX/FOM exceeds the typed annual capital total")
    non_network_capital = max(capital - network_resource_cost, 0.0)
    components = market.extensions.get("capital_cost_components_gbp")
    compatibility = vre_storage_fom = None
    excluded = 0.0
    memo_lines: list[CostLine] = []
    if isinstance(components, Mapping):
        compatibility = _finite_nonnegative(
            components.get("existing_stock_compatibility_capital_gbp", 0.0),
            "existing-stock compatibility capital",
        )
        vre_storage_fom = _finite_nonnegative(
            components.get("vre_storage_fixed_opex_gbp", 0.0), "VRE and storage fixed OPEX",
        )
        excluded = vre_storage_fom + (compatibility if exclude_compatibility_capital else 0.0)
        if excluded > non_network_capital + tolerance_gbp:
            raise ValueError("Excluded capital memo items exceed the typed annual capital total")
        memo_lines.append(CostLine(
            VRE_STORAGE_FOM_LINE,
            "memo",
            vre_storage_fom,
            "memo_folded_into_levelised_capex",
            "MarketYearResult.extensions.capital_cost_components_gbp.vre_storage_fixed_opex_gbp",
            False,
            "Decision A7: VRE and storage fixed OPEX is part of their levelised CAPEX; not added again.",
        ))
        memo_lines.append(CostLine(
            COMPATIBILITY_CAPITAL_LINE,
            "memo",
            compatibility,
            "memo_excluded_from_headline" if exclude_compatibility_capital
            else "memo_included_in_commissioned_fleet_capital",
            "MarketYearResult.extensions.capital_cost_components_gbp.existing_stock_compatibility_capital_gbp",
            False,
            "Run-of-river hydro existing-stock compatibility capital (P4-03): "
            + ("excluded from the headline." if exclude_compatibility_capital
               else "of which, already inside the commissioned-fleet capital line (doctoral headline unchanged)."),
        ))
    headline_fleet_capital = max(non_network_capital - excluded, 0.0)
    lines: list[CostLine] = [
        CostLine(
            "commissioned_fleet.annualised_capital",
            "physical_resource_cost",
            headline_fleet_capital,
            "commissioned_cem_generation_and_storage_fleet",
            "MarketYearResult.total_levelized_capital_cost_gbp less declared network resource costs"
            + (" and the memo items below" if excluded else ""),
            True,
        )
    ]
    if isinstance(network_costs, Mapping):
        lines.extend((
            CostLine(
                "network.commissioned_assets.annualised_capex",
                "physical_resource_cost",
                network_capex,
                "commissioned_network_stock",
                "MarketYearResult.extensions.network_resource_costs_gbp",
                True,
            ),
            CostLine(
                "network.commissioned_assets.fixed_opex",
                "physical_resource_cost",
                network_fom,
                "commissioned_network_stock",
                "MarketYearResult.extensions.network_resource_costs_gbp",
                True,
            ),
            CostLine(
                "network.policy_support",
                "policy_transfer",
                network_policy,
                "transfer_not_resource_cost",
                "MarketYearResult.extensions.network_resource_costs_gbp",
                False,
                "Network policy support is a transfer and is not counted again as a resource cost.",
            ),
        ))
    breakdown = market.extensions.get("physical_operating_cost_components_gbp")
    operating_sum = 0.0
    if isinstance(breakdown, Mapping) and breakdown:
        for key, value in sorted(breakdown.items(), key=lambda item: str(item[0])):
            amount = _finite_nonnegative(value, f"physical operating component {key}")
            operating_sum += amount
            lines.append(CostLine(
                f"operation.{key}",
                "physical_resource_cost",
                amount,
                "psm_physical_operation",
                "MarketYearResult.extensions.physical_operating_cost_components_gbp",
                True,
            ))
        if not math.isclose(operating_sum, operating, rel_tol=1e-9, abs_tol=tolerance_gbp):
            raise ValueError(
                "Named PSM operating-cost components do not reconcile to the typed "
                f"operational total: {operating_sum} != {operating}"
            )
    else:
        operating_sum = operating
        lines.append(CostLine(
            "operation.psm_resource_cost",
            "physical_resource_cost",
            operating,
            "psm_physical_operation_unallocated",
            "MarketYearResult.total_operational_cost_gbp",
            True,
            "The PSM did not provide a finer physical operating-cost breakdown.",
        ))

    zonal_accounting = market.extensions.get("zonal_accounting_gbp")
    for key, view, classification in (
        ("market_settlement_gbp", "market_settlement", "payment_not_resource_cost"),
        ("policy_transfer_gbp", "policy_transfer", "transfer_not_resource_cost"),
        ("consumer_cost_gbp", "consumer_facing", "consumer_account"),
        ("pipeline_committed_cost_gbp", "pipeline_commitment", "not_yet_commissioned"),
        ("informational_residual_value_gbp", "asset_value", "not_current_resource_cost"),
    ):
        if isinstance(zonal_accounting, Mapping) and key in {
            "market_settlement_gbp", "policy_transfer_gbp"
        }:
            # The staged-market ledger replaces the older aggregate transfer
            # fields with national, redispatch and policy accounts.
            continue
        raw = market.extensions.get(key)
        if raw is None:
            continue
        lines.append(CostLine(
            key,
            view,
            _finite_nonnegative(raw, key),
            classification,
            f"MarketYearResult.extensions.{key}",
            False,
        ))

    lines.extend(memo_lines)
    headline_capital = capital - (non_network_capital - headline_fleet_capital)
    system_cost = headline_capital + operating_sum
    if isinstance(zonal_accounting, Mapping):
        declared_system = _finite_nonnegative(
            zonal_accounting.get("system_resource_cost_gbp", system_cost),
            "zonal system resource cost",
        )
        if not math.isclose(declared_system, capital + operating_sum, rel_tol=1e-9, abs_tol=tolerance_gbp):
            raise ValueError(
                "Zonal system resource cost does not reconcile to commissioned-fleet "
                "CAPEX/FOM plus final physical operating cost"
            )
        for key, view, classification, reason in (
            (
                "transmission_constraint_resource_cost_gbp",
                "constraint_cost_attribution",
                "already_within_final_physical_resource_cost",
                "Difference between matched zonal and realised-copperplate physical cost; not added again.",
            ),
            (
                "national_settlement_gbp",
                "national_market_settlement",
                "payment_not_resource_cost",
                "Ahead schedule paid at the national clearing price.",
            ),
            (
                "redispatch_settlement_gbp",
                "redispatch_settlement",
                "payment_not_resource_cost",
                "Signed pay-as-bid accepted adjustment cashflow.",
            ),
            (
                "policy_transfer_gbp",
                "policy_transfer",
                "transfer_not_resource_cost",
                "Policy transfer is kept separate from physical resource cost.",
            ),
            (
                "boundary_shadow_value_gbp",
                "boundary_shadow_diagnostic",
                "diagnostic_not_cash_cost",
                "Diagnostic marginal value in the accepted-bid objective; not a zonal price or observed cash cost.",
            ),
        ):
            if zonal_accounting.get(key) is None:
                continue
            lines.append(CostLine(
                id=f"zonal.{key}",
                view=view,
                amount_gbp=_finite(zonal_accounting[key], key),
                classification=classification,
                source=f"MarketYearResult.extensions.zonal_accounting_gbp.{key}",
                included_in_cem_system_cost=False,
                reason=reason,
            ))

    included = sum(
        float(line.amount_gbp or 0.0)
        for line in lines
        if line.included_in_cem_system_cost
    )
    residual = included - system_cost
    status = "reconciled" if abs(residual) <= tolerance_gbp else "failed"
    return AnnualCostLedger(
        year=market.year,
        cem_system_cost_gbp=system_cost,
        cem_system_cost_gbp_per_mwh_served=(system_cost / served if served > 0 else None),
        demand_served_mwh=served,
        gross_generation_mwh=generation,
        physical_reconciliation_residual_gbp=residual,
        lines=tuple(lines),
        legacy_system_cost_gbp=(
            float(legacy_system_cost_gbp) if legacy_system_cost_gbp is not None else None
        ),
        legacy_cost_per_mwh_generated=(
            float(legacy_cost_per_mwh_generated)
            if legacy_cost_per_mwh_generated is not None else None
        ),
        headline_capital_gbp=headline_capital,
        compatibility_capital_gbp=compatibility,
        compatibility_capital_in_headline=(
            None if compatibility is None else not exclude_compatibility_capital
        ),
        vre_storage_fixed_opex_excluded_gbp=vre_storage_fom,
        status=status,
        notes=(
            "Storage offers and market payments are recovery/settlement mechanisms, not additional physical cost.",
            "Uncommissioned pipeline projects and informational residual values are excluded.",
        ),
    )


def write_cost_ledgers(path: Path, ledgers: list[AnnualCostLedger]) -> Path:
    payload = {
        "schema_version": COST_LEDGER_SCHEMA,
        "definition_id": CEM_SYSTEM_COST_DEFINITION,
        "years": [ledger.to_dict() for ledger in ledgers],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path
