"""Deterministically build public data-pack artefacts.

The default command rebuilds only the CC0 synthetic pack, which is reproducible
in a clean checkout.  The source-plan-only UK bill is an explicit maintenance
operation because the checked-in UK bill is a local audit projection and must
not be overwritten on a machine that does not hold the separately distributed
UK pack.
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.catalog import DATASET_SLOTS  # noqa: E402


SYNTHETIC = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
PUBLICATION = ROOT / "publication"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def write_csv(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_synthetic() -> dict[str, object]:
    periods = 17_520
    hourly = 8_760
    files: dict[str, tuple[str, str, str | None]] = {}
    def register(role: str, filename: str, file_format: str, unit: str | None = None) -> Path:
        path = SYNTHETIC / "files" / role.replace(".", "__") / filename
        files[role] = (path.relative_to(SYNTHETIC).as_posix(), file_format, unit)
        return path
    demand = [["mwh"]] + [[round(25 + 5 * math.sin(index * 2 * math.pi / 48), 6)] for index in range(periods)]
    for role in ("demand.forecast", "demand.real"):
        write_csv(register(role, f"{role.split('.')[-1]}.csv", "csv", "MW"), demand)
    for country in ("france", "belgium", "netherlands", "norway", "ireland"):
        write_csv(register(f"market.{country}.profile", f"{country}-profile.csv", "csv"), [["mwh"], *([[2.0]] * 48)])
        write_csv(register(f"market.{country}.price", f"{country}-price.csv", "csv"), [["gbp_per_mwh"], *([[80.0]] * 48)])
    profiles = {
        "profiles.vre_solar": [max(0.0, math.sin((index % 24 - 6) * math.pi / 12)) * 0.5 for index in range(hourly)],
        "profiles.vre_onshore": [0.35 + 0.1 * math.sin(index * 2 * math.pi / 168) for index in range(hourly)],
        "profiles.vre_offshore": [0.5 + 0.08 * math.cos(index * 2 * math.pi / 168) for index in range(hourly)],
    }
    for role, values in profiles.items():
        write_csv(register(role, f"{role.split('.')[-1]}.csv", "csv"), [[round(value, 8)] for value in values])
    for role in ("weather.wind", "weather.solar"):
        write_text(register(role, f"{role.split('.')[-1]}.zarr", "zarr"), "synthetic container placeholder; chronological profile is bound separately\n")
    fleet = {
        "generators": {
            "CCGT": {"capacity_limit": 40, "fuel_cost": 55, "carbon_price": 15, "gen_cost": 0.1, "capital_cost": 40000000},
            "OCGT": {"capacity_limit": 10, "fuel_cost": 85, "carbon_price": 20, "gen_cost": 0.1, "capital_cost": 10000000},
            "Nuclear": {"capacity_limit": 5, "fuel_cost": 10, "carbon_price": 0, "gen_cost": 0, "capital_cost": 5000000},
            "Hydro_natural_flow": {"capacity_limit": 2, "fuel_cost": 0, "carbon_price": 0, "gen_cost": 0, "capital_cost": 2000000}
        },
        "batteries": {}, "connections": {}, "electrolyzer": {}, "locations": ["GB"]
    }
    write_text(register("fleet.generators", "fleet.json", "json"), canonical_json(fleet))
    costs = {"capital_costs_per_mw": {"solar": 700000, "onshore": 1500000, "offshore": 3000000, "CCGT": 1000000, "OCGT": 800000, "battery": 400000}}
    write_text(register("costs.capital", "costs.json", "json", "GBP/MW"), canonical_json(costs))
    write_csv(register("projects.repd", "projects.csv", "csv"), [["project_id", "technology", "capacity_mw", "development_status", "region"], ["synthetic-project", "solar", 1, "Application Submitted", "GB"]])
    write_csv(register("source.repd_raw", "repd.csv", "csv"), [["Ref ID", "Site Name", "Technology Type", "Installed Capacity (MWelec)", "Development Status", "Country", "Planning Application Submitted", "Planning Permission Granted", "Under Construction", "Operational"], ["synthetic-project", "Synthetic site", "Solar Photovoltaics", 1, "Application Submitted", "England", "01/01/2025", "", "", ""]])
    write_text(register("policy.support", "policy.json", "json"), canonical_json({"synthetic": True, "mechanisms": []}))
    timelines = {"development_stage_timelines": {"solar": {"total_median": 12}}, "development_timelines": {"solar": 12, "onshore": 24, "offshore": 48, "battery": 12}}
    write_text(register("planning.timelines", "timelines.json", "json"), canonical_json(timelines))
    write_csv(register("planning.success_rates", "success.csv", "csv"), [["Technology", "Region", "Success_Rate"], ["solar", "GB", 0.5], ["onshore", "GB", 0.5], ["offshore", "GB", 0.5], ["battery", "GB", 0.5]])
    config = {
        "simulation_parameters": {"periods": periods, "bidding_factor": 1.0},
        "investment_parameters": {"target_payback_years": {"default": 25}},
        "investment_methodology_external": {"preferred_rates": {}},
        "repd_filtering": {"apply_zombie_filter": True, "zombie_status_stale_year": 2015, "minimum_project_size_mw": 0.1, "max_completion_year": 2040},
        "storage_cap_fraction": 0.2, "physical_period_hours": 0.5,
    }
    write_text(register("config.model_parameters", "parameters.json", "json"), canonical_json(config))
    bindings = {}
    for role, (uri, file_format, unit) in sorted(files.items()):
        path = SYNTHETIC / uri
        bindings[role] = {
            "role": role, "uri": uri, "filename": path.name, "format": file_format,
            "bytes": path.stat().st_size, "sha256": sha(path), "unit": unit,
            "source_url": "generated://value-synthetic-contract-pack-v1",
            "source_version": "generator-v1", "access_date": "2026-08-08",
            "licence": "CC0-1.0", "attribution": "VALUE synthetic contract pack by Hanzhe Xing; attribution is requested for scientific traceability but is not a CC0 condition",
            "redistribution_class": "redistributable_cc0",
            "transformation_version": "scripts/build_publication_data_packs.py@v1",
        }
    manifest = {
        "schema_version": "value.data-pack/v1", "id": "value-synthetic-contract-pack-v1",
        "name": "VALUE synthetic contract pack (not a real power system)", "country": "SYNTHETIC",
        "timezone": "UTC", "period_hours": 0.5, "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T00:00:00Z", "publication_status": "redistributable",
        "licence": "CC0-1.0", "copyright_affirmer": "Hanzhe Xing",
        "bindings": bindings,
    }
    write_text(SYNTHETIC / "manifest.json", canonical_json(manifest))
    return manifest


def build_uk_bill() -> dict[str, object]:
    source_plan = json.loads((PUBLICATION / "uk-source-plan.json").read_text(encoding="utf-8"))
    rules = source_plan["role_rules"]
    sources = source_plan["source_catalog"]
    rows = []
    for slot in DATASET_SLOTS:
        role = slot["role"]
        rule = rules.get(role, {})
        source = sources.get(rule.get("source_id"), {})
        rows.append({
            "canonical_role": role, "required": bool(slot.get("required")),
            "downstream_module_use": slot["group"], "source_id": rule.get("source_id"),
            "source_publisher": source.get("publisher"), "source_url": source.get("source_url"),
            "exact_licence": source.get("exact_licence"), "attribution": source.get("attribution"),
            "access_date": source_plan["audit_date"], "source_version": source.get("source_version"),
            "source_sha256": None, "normalized_sha256": None,
            "transformation_version": rule.get("transformation"), "unit_time_mapping": slot.get("unit"),
            "redistribution_class": rule.get("redistribution_class", source_plan["default_status"]),
            "included_in_redistributable_archive": False,
            "blocking_reason": "This source plan contains no copied UK object; run audit_local_uk_data_pack.py for local hashes and keep publication approval separate.",
        })
    bill = {
        "schema_version": "value.bill-of-data/v1", "pack_id": source_plan["pack_id"],
        "version": source_plan["version"], "publication_status": "NO-GO_INCOMPLETE",
        "roles_expected": len(DATASET_SLOTS), "roles_redistributable": 0,
        "archive_created": False, "objects": rows,
    }
    write_text(PUBLICATION / "value-uk-open-data-pack" / "bill-of-data.json", canonical_json(bill))
    return bill


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-uk-source-plan-bill",
        action="store_true",
        help=(
            "replace the audited UK bill with a source-plan-only NO-GO bill; "
            "this is a deliberate maintenance action, not a CI operation"
        ),
    )
    args = parser.parse_args(argv)
    manifest = build_synthetic()
    result: dict[str, object] = {
        "synthetic_bindings": len(manifest["bindings"]),
        "uk_bill_written": False,
    }
    if args.write_uk_source_plan_bill:
        bill = build_uk_bill()
        result.update({
            "uk_bill_written": True,
            "uk_bill_roles": bill["roles_expected"],
            "uk_publication_status": bill["publication_status"],
        })
    print(canonical_json(result))


if __name__ == "__main__":
    main()
