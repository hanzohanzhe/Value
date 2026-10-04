"""Dependency-free convex bid-at-cost economic-dispatch benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def solve_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    demand = float(fixture["demand_mwh"])
    offers = sorted(
        fixture["offers"],
        key=lambda row: (float(row["marginal_cost_gbp_per_mwh"]), str(row["asset_id"])),
    )
    remaining = demand
    dispatch: dict[str, float] = {}
    physical_cost = 0.0
    clearing_price = 0.0
    for offer in offers:
        accepted = min(max(remaining, 0.0), float(offer["capacity_mwh"]))
        dispatch[str(offer["asset_id"])] = accepted
        physical_cost += accepted * float(offer["marginal_cost_gbp_per_mwh"])
        if accepted > 0:
            clearing_price = float(offer["marginal_cost_gbp_per_mwh"])
        remaining -= accepted
    blackout = max(remaining, 0.0)
    accepted_supply = sum(dispatch.values())
    return {
        "dispatch_mwh": dispatch,
        "accepted_supply_mwh": accepted_supply,
        "blackout_mwh": blackout,
        "energy_balance_residual_mwh": accepted_supply + blackout - demand,
        "clearing_price_gbp_per_mwh": clearing_price,
        "physical_resource_cost_gbp": physical_cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    result = solve_fixture(fixture)
    print(json.dumps(result, indent=2))
    expected = fixture["expected"]
    raise SystemExit(0 if result == expected else 1)


if __name__ == "__main__":
    main()
