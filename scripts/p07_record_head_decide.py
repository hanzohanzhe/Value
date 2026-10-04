#!/usr/bin/env python3
"""Record HEAD ``SchemeCAgentInvestmentDefinition.decide()`` inputs and outputs.

P0-7 S1 (M0 freeze point). Every scenario is built here once, its inputs are
stored fully expanded (asset economics included), and the HEAD decision is
stored next to them in ``tests/fixtures/p07/head_decide_record.json``. The test
``tests/test_p07_head_decide_record.py`` rebuilds the contracts from the stored
inputs only, so later changes to asset economics or this script cannot move
the frozen inputs.

Recording is refused unless the decide() source files are byte-identical to
their blobs at the freeze commit (35aadb3). ``--check`` re-runs the scenarios
and compares with the stored record without writing.

Each scenario also carries the cashflow inputs that decide() does not read at
HEAD (dispatched MWh and per-MWh cost components) and the hand-computed
expectations of the restored Scheme C thermal net revenue (decision A4): gas
and biomass net ``energy x (generation + fuel + carbon + unit-time cost)``;
VRE and storage keep gross revenue as profit. P0-7 S4 consumes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECORD_PATH = ROOT / "tests" / "fixtures" / "p07" / "head_decide_record.json"
RECORD_SCHEMA = "value.p07-head-decide-record/v1"
FREEZE_COMMIT = "35aadb3"
HEAD_SOURCES = (
    "gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py",
    "gridform_core/asset_economics.py",
    "gridform_core/cem_investment_policy.py",
    "gridform_core/data/cem/investment_eligibility.json",
    "gridform_core/v2/contracts.py",
)
# Identity-zone content: changes with any code change, never compared.
IDENTITY_EXTENSION_KEYS = ("cem_model_identity",)
YEAR = 2030


def canonical(value):
    """JSON-safe copy; non-finite floats become tagged strings."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"$nonfinite": repr(value)}
    if isinstance(value, dict):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def decanonical(value):
    if isinstance(value, dict):
        if set(value) == {"$nonfinite"}:
            return float(value["$nonfinite"])
        return {key: decanonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decanonical(item) for item in value]
    return value


def decision_record(decision) -> dict:
    payload = decision.to_dict()
    extensions = dict(payload.get("extensions") or {})
    for key in IDENTITY_EXTENSION_KEYS:
        extensions.pop(key, None)
    payload["extensions"] = extensions
    return canonical(payload)


def _economics(technology, capacity, *, capex_per_mw=None, life=25.0, energy=None, **extra):
    from gridform_core.asset_economics import build_asset_economic_extensions

    values = build_asset_economic_extensions(
        technology, capacity, energy_capacity_mwh=energy,
        capital_costs_per_mw={technology: capex_per_mw} if capex_per_mw is not None else {},
        lifetimes={technology: life, "default": life}, discount_rate=0.05,
        source_record_id=f"p07-fixture:{technology}",
    )
    if energy is not None:
        values["energy_capacity_mwh"] = float(energy)
    values.update(extra)
    return values


def _asset(asset_id, technology, capacity, *, region="GB", status="operating", energy=None, **economics):
    from gridform_core.v2.contracts import AssetStateV2

    extensions = _economics(technology, capacity, energy=energy, **economics) if capacity > 0 else dict(economics)
    return AssetStateV2(asset_id, technology, capacity, energy, region, status=status, extensions=extensions)


def _thermal(energy_mwh, *, generation=0.0, fuel=0.0, carbon=0.0, unit_time=0.0):
    return {"generated_mwh": energy_mwh, "generation_cost_gbp_per_mwh": generation,
            "fuel_cost_gbp_per_mwh": fuel, "carbon_cost_gbp_per_mwh": carbon,
            "unit_time_cost_gbp_per_mwh": unit_time}


def scenarios():
    """Scenario specs. Expected A4 values are hand-computed literals."""
    ccgt = dict(capex_per_mw=1_000_000.0, life=25.0, preferred_rate=0.08, target_payback_years=25.0,
                investment_owner_id="owner-ccgt")
    ccgt_cost = _thermal(182_500.0, fuel=35.0, carbon=22.0, unit_time=3.0)  # gen_cost 60 GBP/MWh
    return [
        {
            "id": "ccgt_price_equals_mc",
            "purpose": "P4-01/A4 toy: CCGT dispatched 182,500 MWh at a price equal to its gen_cost of 60 GBP/MWh. "
                       "HEAD (gross) builds 10.95 MW Invest_High; restored Scheme C net is 0 -> no proposal.",
            "assets": [_asset("ccgt-a", "CCGT", 100.0, **ccgt)],
            "income": {"ccgt-a": 10_950_000.0},
            "headroom": [],
            "cashflow_inputs": {"ccgt-a": {"electricity_income_gbp": 10_950_000.0, **ccgt_cost}},
            "a4_expected": {"ccgt-a": {"basis": "scheme_c_income_less_energy_times_gen_cost",
                                       "gen_cost_gbp_per_mwh": 60.0, "operating_cost_gbp": 10_950_000.0,
                                       "net_revenue_gbp": 0.0}},
            "a4_expected_decision": {"groups": {"owner-ccgt|CCGT|GB": {"recommendation": "Do_Nothing",
                                                                       "accepted_addition_mw": 0.0,
                                                                       "retirement_mw": 0.0}}},
        },
        {
            "id": "ccgt_price_50",
            "purpose": "A4 toy: same CCGT at 50 GBP/MWh (10 below gen_cost). HEAD builds 9.125 MW Invest_High; "
                       "restored net is -1,825,000 -> Deplete, retire 1,825,000 x 25 / 1e6 = 45.625 MW.",
            "assets": [_asset("ccgt-a", "CCGT", 100.0, **ccgt)],
            "income": {"ccgt-a": 9_125_000.0},
            "headroom": [],
            "cashflow_inputs": {"ccgt-a": {"electricity_income_gbp": 9_125_000.0, **ccgt_cost}},
            "a4_expected": {"ccgt-a": {"basis": "scheme_c_income_less_energy_times_gen_cost",
                                       "gen_cost_gbp_per_mwh": 60.0, "operating_cost_gbp": 10_950_000.0,
                                       "net_revenue_gbp": -1_825_000.0}},
            "a4_expected_decision": {"groups": {"owner-ccgt|CCGT|GB": {"recommendation": "Deplete",
                                                                       "accepted_addition_mw": 0.0,
                                                                       "retirement_mw": 45.625}}},
        },
        {
            "id": "gas_and_biomass_fuel_carbon",
            "purpose": "A4: 'gas' with fuel+carbon cost and biomass with fuel cost only both deduct energy x gen_cost; "
                       "OCGT with carbon cost only also deducts. Group defaults (preferred 0.08, target = life).",
            "assets": [
                _asset("gas-1", "gas", 200.0, capex_per_mw=700_000.0, investment_owner_id="owner-gas"),
                _asset("bio-1", "bio_and_waste", 50.0, capex_per_mw=3_000_000.0, investment_owner_id="owner-bio"),
                _asset("ocgt-1", "OCGT", 20.0, capex_per_mw=500_000.0, life=30.0, investment_owner_id="owner-ocgt"),
            ],
            "income": {"gas-1": 30_000_000.0, "bio-1": 24_000_000.0, "ocgt-1": 1_600_000.0},
            "headroom": [],
            "cashflow_inputs": {
                "gas-1": {"electricity_income_gbp": 30_000_000.0,
                          **_thermal(400_000.0, fuel=40.0, carbon=20.0, unit_time=2.0)},
                "bio-1": {"electricity_income_gbp": 24_000_000.0,
                          **_thermal(300_000.0, fuel=30.0, unit_time=5.0)},
                "ocgt-1": {"electricity_income_gbp": 1_600_000.0,
                           **_thermal(10_000.0, generation=1.0, carbon=90.0, unit_time=9.0)},
            },
            "a4_expected": {
                "gas-1": {"basis": "scheme_c_income_less_energy_times_gen_cost", "gen_cost_gbp_per_mwh": 62.0,
                          "operating_cost_gbp": 24_800_000.0, "net_revenue_gbp": 5_200_000.0},
                "bio-1": {"basis": "scheme_c_income_less_energy_times_gen_cost", "gen_cost_gbp_per_mwh": 35.0,
                          "operating_cost_gbp": 10_500_000.0, "net_revenue_gbp": 13_500_000.0},
                "ocgt-1": {"basis": "scheme_c_income_less_energy_times_gen_cost", "gen_cost_gbp_per_mwh": 100.0,
                           "operating_cost_gbp": 1_000_000.0, "net_revenue_gbp": 600_000.0},
            },
            "a4_expected_decision": {"groups": {
                # 5.2e6 / 1.4e8 = 0.0371 <= 0.08; payback 26.92 > 25 -> Do_Nothing
                "owner-gas|gas|GB": {"recommendation": "Do_Nothing", "accepted_addition_mw": 0.0, "retirement_mw": 0.0},
                # 13.5e6 / 1.5e8 = 0.09 > 0.08 -> Invest_High, 13.5e6 / 3e6 = 4.5 MW
                "owner-bio|bio_and_waste|GB": {"recommendation": "Invest_High", "accepted_addition_mw": 4.5,
                                               "retirement_mw": 0.0},
                # 6e5 / 1e7 = 0.06 <= 0.08; payback 16.67 <= 30 -> Invest_Profit, 6e5 / 5e5 = 1.2 MW
                "owner-ocgt|OCGT|GB": {"recommendation": "Invest_Profit", "accepted_addition_mw": 1.2,
                                       "retirement_mw": 0.0},
            }},
        },
        {
            "id": "vre_gross_shared_headroom",
            "purpose": "A4: VRE keeps gross revenue = profit (source gen_cost 0.0001 is not deducted). HEAD allocates "
                       "the shared solar headroom 12 greedily in owner order (10 then 2); onshore headroom is the "
                       "minimum over two headroom rows.",
            "assets": [
                _asset("solar-a", "solar", 10.0, capex_per_mw=600_000.0, investment_owner_id="owner-a"),
                _asset("solar-b", "solar", 10.0, capex_per_mw=600_000.0, investment_owner_id="owner-b"),
                _asset("onshore-a", "onshore", 30.0, capex_per_mw=1_200_000.0, life=30.0,
                       investment_owner_id="owner-a"),
            ],
            "income": {"solar-a": 6_000_000.0, "solar-b": 6_000_000.0, "onshore-a": 7_200_000.0},
            "headroom": [
                {"module_id": "vre-expansion-cap", "allowed": {"solar": 12.0, "onshore": 50.0}},
                {"module_id": "network-headroom", "allowed": {"onshore": 4.0}},
            ],
            "cashflow_inputs": {
                "solar-a": {"electricity_income_gbp": 6_000_000.0, **_thermal(100_000.0, generation=0.0001)},
                "solar-b": {"electricity_income_gbp": 6_000_000.0, **_thermal(100_000.0, generation=0.0001)},
                "onshore-a": {"electricity_income_gbp": 7_200_000.0, **_thermal(90_000.0, generation=0.0001)},
            },
            "a4_expected": {
                key: {"basis": "gross_revenue_is_profit", "gen_cost_gbp_per_mwh": None,
                      "operating_cost_gbp": 0.0, "net_revenue_gbp": income}
                for key, income in (("solar-a", 6_000_000.0), ("solar-b", 6_000_000.0), ("onshore-a", 7_200_000.0))
            },
            "a4_expected_decision": "unchanged_from_head",
        },
        {
            "id": "storage_gross_headroom",
            "purpose": "A4: storage keeps gross revenue = profit. HEAD storage headroom of 0 (the P5-01 condition) "
                       "blocks the 1C battery; the 0.25C battery is clipped to its headroom of 3 MW.",
            "assets": [
                _asset("bat-1c", "1c_battery", 50.0, energy=50.0, investment_owner_id="owner-store"),
                _asset("bat-025c", "0.25c_battery", 40.0, energy=160.0, investment_owner_id="owner-store"),
            ],
            "income": {"bat-1c": 3_000_000.0, "bat-025c": 2_000_000.0},
            "headroom": [
                {"module_id": "storage-expansion-scheme-c",
                 "allowed": {"1c_battery": 0.0, "0.5c_battery": 0.0, "0.25c_battery": 3.0,
                             "hydrogen_battery": 0.0}},
            ],
            "cashflow_inputs": {
                "bat-1c": {"electricity_income_gbp": 3_000_000.0, **_thermal(40_000.0)},
                "bat-025c": {"electricity_income_gbp": 2_000_000.0, **_thermal(30_000.0)},
            },
            "a4_expected": {
                key: {"basis": "gross_revenue_is_profit", "gen_cost_gbp_per_mwh": None,
                      "operating_cost_gbp": 0.0, "net_revenue_gbp": income}
                for key, income in (("bat-1c", 3_000_000.0), ("bat-025c", 2_000_000.0))
            },
            "a4_expected_decision": "unchanged_from_head",
        },
        {
            "id": "loss_profit_and_recorded_opex",
            "purpose": "HEAD tiers: solar with negative income -> Deplete (retire min(cap, loss x target / unit cost)); "
                       "onshore at payback 8 <= target 10 with preferred 0.20 -> Invest_Profit; CCGT whose "
                       "extensions carry annual_operational_cost_gbp (never written in production at HEAD) nets it.",
            "assets": [
                _asset("solar-loss", "solar", 20.0, capex_per_mw=600_000.0, target_payback_years=25.0,
                       investment_owner_id="owner-loss"),
                _asset("onshore-profit", "onshore", 10.0, capex_per_mw=1_200_000.0, life=30.0,
                       preferred_rate=0.20, target_payback_years=10.0, investment_owner_id="owner-profit"),
                _asset("ccgt-opex", "CCGT", 100.0, capex_per_mw=1_000_000.0, preferred_rate=0.08,
                       target_payback_years=25.0, annual_operational_cost_gbp=10_950_000.0,
                       investment_owner_id="owner-opex"),
            ],
            "income": {"solar-loss": -200_000.0, "onshore-profit": 1_500_000.0, "ccgt-opex": 10_950_000.0},
            "headroom": [{"module_id": "vre-expansion-cap", "allowed": {"solar": 100.0, "onshore": 100.0}}],
            "cashflow_inputs": {
                "solar-loss": {"electricity_income_gbp": -200_000.0, **_thermal(20_000.0, generation=0.0001)},
                "onshore-profit": {"electricity_income_gbp": 1_500_000.0, **_thermal(30_000.0, generation=0.0001)},
                "ccgt-opex": {"electricity_income_gbp": 10_950_000.0, **ccgt_cost},
            },
            "a4_expected": {
                "solar-loss": {"basis": "gross_revenue_is_profit", "gen_cost_gbp_per_mwh": None,
                               "operating_cost_gbp": 0.0, "net_revenue_gbp": -200_000.0},
                "onshore-profit": {"basis": "gross_revenue_is_profit", "gen_cost_gbp_per_mwh": None,
                                   "operating_cost_gbp": 0.0, "net_revenue_gbp": 1_500_000.0},
                "ccgt-opex": {"basis": "scheme_c_income_less_energy_times_gen_cost", "gen_cost_gbp_per_mwh": 60.0,
                              "operating_cost_gbp": 10_950_000.0, "net_revenue_gbp": 0.0},
            },
            "a4_expected_decision": "s4_defines_source_of_operating_cost",
        },
        {
            "id": "eligibility_and_grouping",
            "purpose": "HEAD grouping: one owner with CCGT in two regions -> two groups/proposals; two solar assets "
                       "of one owner in one region -> one decision; nuclear denied; natural-flow hydro needs site "
                       "data; commissioned asset without owner, investment_eligible False, retired, zero-capacity "
                       "and unknown-technology assets; an eligible asset absent from the income map counts as zero.",
            "assets": [
                _asset("ccgt-north", "CCGT", 60.0, region="North", capex_per_mw=1_000_000.0,
                       investment_owner_id="owner-x"),
                _asset("ccgt-south", "CCGT", 40.0, region="South", capex_per_mw=1_000_000.0,
                       investment_owner_id="owner-x"),
                _asset("solar-x1", "solar", 10.0, capex_per_mw=600_000.0, investment_owner_id="owner-x"),
                _asset("commissioned:model:solar-x2", "solar", 5.0, capex_per_mw=600_000.0,
                       investment_owner_id="owner-x"),
                _asset("nuclear-1", "Nuclear", 1000.0, capex_per_mw=5_000_000.0, life=60.0),
                _asset("hydro-1", "Hydro_natural_flow", 100.0, capex_per_mw=2_000_000.0, life=50.0),
                _asset("commissioned:repd:ext", "onshore", 15.0, capex_per_mw=1_200_000.0),
                _asset("solar-ineligible", "solar", 8.0, capex_per_mw=600_000.0, investment_eligible=False),
                _asset("solar-retired", "solar", 8.0, capex_per_mw=600_000.0, status="retired"),
                _asset("solar-zero", "solar", 0.0, investment_owner_id="owner-zero"),
                _asset("coal-1", "coal", 100.0, capex_per_mw=1_500_000.0),
                _asset("bio-silent", "bio_and_waste", 30.0, capex_per_mw=3_000_000.0),
            ],
            "income": {"ccgt-north": 9_000_000.0, "ccgt-south": 2_000_000.0, "solar-x1": 900_000.0,
                       "commissioned:model:solar-x2": 450_000.0, "nuclear-1": 400_000_000.0,
                       "hydro-1": 50_000_000.0, "commissioned:repd:ext": 3_000_000.0,
                       "solar-ineligible": 1_000_000.0, "solar-retired": 1_000_000.0,
                       "coal-1": 30_000_000.0},
            "headroom": [{"module_id": "vre-expansion-cap", "allowed": {"solar": 1.0, "onshore": 100.0}}],
            "cashflow_inputs": {},
            "a4_expected": {},
            "a4_expected_decision": "not_applicable",
        },
    ]


def build_run(run_id: str):
    from gridform_core.v2.contracts import ModuleSelection, ResolvedRun

    modules = {
        slot: ModuleSelection(slot, module, "test", f"value.{slot}/v2")
        for slot, module in {"psm": "value-bid-at-cost-psm", "pipeline": "planning-pipeline",
                             "investment": "agent-investment"}.items()
    }
    return ResolvedRun(run_id, "p07-project", "p07-scenario", "p07-pack", YEAR, YEAR + 1,
                       modules, {"clock.period_hours": 0.5}, {})


def build_inputs(spec):
    """Contract objects from a scenario spec (used for recording)."""
    from gridform_core.v2.contracts import ExpansionHeadroom, MarketYearResult, OperatingState

    run = build_run(f"p07-head:{spec['id']}")
    state = OperatingState(YEAR, tuple(spec["assets"]), ())
    market = MarketYearResult(f"p07-market:{spec['id']}", YEAR, "value-bid-at-cost-psm", "5.1.0", {},
                              dict(spec["income"]), 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0)
    headroom = tuple(
        ExpansionHeadroom(f"p07-headroom:{spec['id']}:{index}", YEAR, row["module_id"], dict(row["allowed"]))
        for index, row in enumerate(spec["headroom"])
    )
    return run, state, market, headroom


def inputs_from_record(entry):
    """Contract objects rebuilt from stored JSON only (used by tests)."""
    from gridform_core.v2.contracts import (
        AssetStateV2, ExpansionHeadroom, MarketYearResult, OperatingState, ResolvedRun,
    )

    payload = decanonical(entry["inputs"])
    run = ResolvedRun.from_dict(payload["run"])
    state = OperatingState(payload["year"], tuple(AssetStateV2.from_dict(row) for row in payload["assets"]), ())
    market = MarketYearResult.from_dict(payload["market"])
    headroom = tuple(ExpansionHeadroom.from_dict(row) for row in payload["headroom"])
    return run, state, market, headroom


def source_hashes() -> dict[str, str]:
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in HEAD_SOURCES}


def freeze_hashes() -> dict[str, str]:
    result = {}
    for path in HEAD_SOURCES:
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{FREEZE_COMMIT}:{path}"],
                              check=True, capture_output=True).stdout
        result[path] = hashlib.sha256(blob).hexdigest()
    return result


def build_record() -> dict:
    from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCAgentInvestmentDefinition

    entries = []
    for spec in scenarios():
        run, state, market, headroom = build_inputs(spec)
        decision = SchemeCAgentInvestmentDefinition().decide(run, state, market, headroom)
        entries.append({
            "id": spec["id"],
            "purpose": spec["purpose"],
            "inputs": canonical({
                "run": run.to_dict(), "year": YEAR,
                "assets": [asset.to_dict() for asset in state.assets],
                "market": market.to_dict(),
                "headroom": [row.to_dict() for row in headroom],
            }),
            "cashflow_inputs": spec["cashflow_inputs"],
            "a4_expected": spec["a4_expected"],
            "a4_expected_decision": spec["a4_expected_decision"],
            "head_decision": decision_record(decision),
        })
    return {
        "schema_version": RECORD_SCHEMA,
        "freeze_commit": FREEZE_COMMIT,
        "decide": "gridform_core.builtin.scheme_c_1000twh.v2_module_definitions."
                  "SchemeCAgentInvestmentDefinition.decide (agent-investment 2.2.0)",
        "head_sources_sha256": source_hashes(),
        "identity_extension_keys_excluded": list(IDENTITY_EXTENSION_KEYS),
        "money_basis": "constant_base_year_gbp_undiscounted (decision A6)",
        "a4_rule": "thermal (fuel or carbon cost > 0): net = electricity + hydrogen income - generated_mwh x "
                   "(generation + fuel + carbon + unit_time cost); VRE and storage: net = gross income",
        "scenarios": entries,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the stored record; write nothing")
    args = parser.parse_args(argv)
    current, frozen = source_hashes(), freeze_hashes()
    drift = sorted(path for path in HEAD_SOURCES if current[path] != frozen[path])
    if drift:
        print("decide() sources differ from the freeze commit " + FREEZE_COMMIT + ": " + ", ".join(drift),
              file=sys.stderr)
        return 2
    record = build_record()
    text = json.dumps(record, indent=1, sort_keys=True, allow_nan=False) + "\n"
    if args.check:
        stored = RECORD_PATH.read_text(encoding="utf-8")
        if stored != text:
            print("stored HEAD decide record differs from a fresh recording", file=sys.stderr)
            return 1
        print("HEAD decide record reproduces")
        return 0
    if RECORD_PATH.exists():
        print(f"refusing to overwrite {RECORD_PATH.relative_to(ROOT)}; the HEAD record is written once",
              file=sys.stderr)
        return 2
    RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECORD_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {RECORD_PATH.relative_to(ROOT)} ({len(record['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
