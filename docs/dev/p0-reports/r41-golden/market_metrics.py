"""Market-level before/after metrics of a kept golden run output (read-only)."""
import json, sqlite3, sys
from pathlib import Path

def metrics(out: Path) -> dict:
    db = sqlite3.connect(f"file:{(out / 'market' / 'market.sqlite').as_posix()}?mode=ro&immutable=1", uri=True)
    years = {}
    for row in db.execute(
        "SELECT year, COUNT(*), SUM(real_demand_mwh), SUM(accepted_supply_mwh), SUM(storage_charge_mwh), "
        "SUM(storage_discharge_mwh), SUM(curtailed_mwh), SUM(excess_mwh), SUM(import_mwh), SUM(export_mwh), "
        "SUM(flexible_demand_mwh), SUM(vre_accepted_mwh), SUM(physical_resource_cost_gbp), SUM(market_payment_gbp), "
        "SUM(blackout_mwh), AVG(clearing_price_gbp_per_mwh) FROM period_summary GROUP BY year ORDER BY year"):
        keys = ("periods", "demand_mwh", "accepted_supply_mwh", "storage_charge_mwh", "storage_discharge_mwh",
                "curtailed_mwh", "excess_mwh", "import_mwh", "export_mwh", "flexible_demand_mwh", "vre_accepted_mwh",
                "physical_resource_cost_gbp", "market_payment_gbp", "recorded_blackout_mwh", "mean_period_price_gbp_per_mwh")
        years[str(row[0])] = dict(zip(keys, row[1:]))
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "balance_boundary_period" in tables:
        for year, short, stress, double in db.execute(
                "SELECT year, SUM(shortfall_mwh), SUM(stress_flag), SUM(non_vre_double_counted_mwh) FROM balance_boundary_period GROUP BY year"):
            years[str(year)].update(a2_shortfall_mwh=short, stress_periods=stress, non_vre_double_counted_mwh=double)
    if "stress_event" in tables:
        for year, n in db.execute("SELECT year, COUNT(*) FROM stress_event GROUP BY year"):
            years[str(year)]["stress_events"] = n
    if "surplus_routing" in tables:
        for year, cur, sto in db.execute("SELECT year, SUM(curtailed_mwh), SUM(to_storage_mwh) FROM surplus_routing WHERE source_class='in_dispatch' GROUP BY year"):
            years[str(year)].update(routing_in_dispatch_curtailed_mwh=cur, routing_in_dispatch_to_storage_mwh=sto)
    gen = {}
    for year, tech, mwh in db.execute("SELECT year, technology, SUM(energy_mwh) FROM physical_dispatch WHERE flow_type IN ('generation','storage_discharge','import') GROUP BY year, technology"):
        gen.setdefault(str(year), {})[tech] = mwh
    for year in years:
        years[year]["generation_by_technology_mwh"] = gen.get(year, {})
    val = json.loads((out / "validation" / "scientific-validation.json").read_text())
    oracle = json.loads((out / "validation" / "energy-balance-oracle.json").read_text())
    checks = {c["id"]: {k: c.get(k) for k in ("status", "count")} for c in oracle.get("checks", [])}
    storage = {c["id"]: {k: c.get(k) for k in ("status", "count")} for c in (oracle.get("storage") or {}).get("checks", [])}
    return {
        "years": years,
        "validation": {k: val.get(k) for k in ("energy_balance_status", "storage_invariant_status", "run_invariant_status",
                                               "scientific_validation_status")},
        "raw_invariants": (val.get("raw_invariants") or {}).get("status"),
        "declared_deviations_matched": [m.get("deviation_ids") for m in ((val.get("declared_deviations") or {}).get("matched") or [])],
        "oracle_status": oracle.get("status"),
        "oracle_checks": checks,
        "storage_checks": storage,
    }

print(json.dumps({label: metrics(Path(path)) for label, path in zip(sys.argv[1::2], sys.argv[2::2])}, indent=1, sort_keys=True))
