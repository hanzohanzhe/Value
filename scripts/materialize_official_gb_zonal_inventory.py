"""Materialize the nine normalized Prompt 98 roles from pinned local evidence.

This command performs no network access and does not sign or install a network
pack.  Raw objects remain in the local Data Workbench object store; only
normalized, reviewable artifacts are written under ``inventories``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_workbench.official_gb_candidate import (  # noqa: E402
    build_candidate_zones,
    build_weather_bundles,
    compile_network_candidate_payload,
    compile_postcode_demand_weights,
    normalize_dso_source,
    normalize_interconnector_register,
    normalize_repd_source,
    normalize_scheme_c_fleet,
    normalize_scheme_c_national_demand,
    read_etys_2025_capabilities,
    read_etys_boundary_geometry,
)
from gridform_core.data_workbench.registry import (  # noqa: E402
    JsonSourceRegistry,
    package_registry_root,
)
from gridform_core.data_workbench.state import resolve_data_workbench_root  # noqa: E402


SOURCE_REVISIONS = {
    "neso.dno-license-areas": "2024-05-03",
    "neso.etys-boundary-gis": "ETYS-GIS-2024-Mar25",
    "neso.etys-capabilities": "ETYS-2025",
    "neso.fes-gsp-regional-demand": "FES-2024-active-power",
    "desnz.postcode-electricity-consumption": "DESNZ-postcode-electricity-2024",
    "ons.postcode-directory": "ONSPD-May-2026-corrected-2026-06-04",
    "neso.interconnector-register": "NESO-interconnector-register-2026-08-18",
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="",
    )


def _csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({str(key) for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _raw_objects(state_root: Path) -> tuple[dict[str, Path], list[dict[str, object]]]:
    registry = JsonSourceRegistry(package_registry_root("uk-network"))
    definitions = {item.source_id: item for item in registry.list_sources()}
    paths: dict[str, Path] = {}
    ledger: list[dict[str, object]] = []
    for source_id, revision_id in SOURCE_REVISIONS.items():
        receipt_path = state_root / "receipts" / source_id / f"{revision_id}.json"
        if not receipt_path.is_file():
            raise FileNotFoundError(f"Pinned receipt is missing: {source_id}/{revision_id}")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        object_path = state_root / "objects" / str(receipt["object_key"])
        if not object_path.is_file() or _sha(object_path) != str(receipt["sha256"]):
            raise ValueError(f"Pinned raw object identity failed: {source_id}/{revision_id}")
        source = definitions[source_id]
        paths[source_id] = object_path
        ledger.append(
            {
                "source_id": source_id,
                "revision_id": revision_id,
                "sha256": receipt["sha256"],
                "byte_size": receipt["byte_size"],
                "landing_page": source.landing_page,
                "licence": source.licence_expected,
                "redistribution_decision": source.redistribution_policy.replace("-", "_"),
                "decision_basis": "Prompt 98 conservative object-level review",
                "raw_receipt_decision_at_fetch": receipt["redistribution_decision"],
            }
        )
    return paths, ledger


def _inventory_row(
    *,
    role: str,
    path: Path,
    inventory_root: Path,
    authoritative_url: str,
    publisher: str,
    title: str,
    publication_date: str,
    source_version: str,
    licence: str,
    licence_url: str,
    redistribution_decision: str,
    transformation_step: str,
    coordinate_reference_system: str | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "required": True,
        "authoritative_url": authoritative_url,
        "publisher": publisher,
        "title": title,
        "publication_date": publication_date,
        "source_version": source_version,
        "licence": licence,
        "licence_url": licence_url,
        "redistribution_decision": redistribution_decision,
        "local_path": path.relative_to(inventory_root).as_posix(),
        "sha256": _sha(path),
        "access_result": "present",
        "transformation_step": transformation_step,
        "coordinate_reference_system": coordinate_reference_system,
    }


def materialize(
    *,
    state_root: Path,
    demand_source: Path,
    repd_source: Path,
    wind_nc: Path,
    solar_nc: Path,
    inventory_key: str,
    selected_boundaries: Sequence[str] = ("B6", "B7a"),
) -> dict[str, object]:
    state_root = Path(state_root).resolve()
    inventory_path = state_root / "inventories" / inventory_key
    normalized = inventory_path.with_suffix("")
    normalized.mkdir(parents=True, exist_ok=True)
    raw, rights_ledger = _raw_objects(state_root)

    dso_raw = json.loads(raw["neso.dno-license-areas"].read_text(encoding="utf-8"))
    dso = normalize_dso_source(dso_raw, source_crs="EPSG:27700")
    etys_geometry = read_etys_boundary_geometry(
        raw["neso.etys-boundary-gis"], source_crs="EPSG:3857"
    )
    zone_candidate = build_candidate_zones(
        dso["display_geojson"],
        etys_geometry,
        selected_boundary_ids=selected_boundaries,
        minimum_piece_share=0.01,
    )
    capability = read_etys_2025_capabilities(raw["neso.etys-capabilities"])
    capabilities = {str(item["boundary_id"]): item for item in capability["boundaries"]}
    network = compile_network_candidate_payload(
        zone_candidate["zone_geojson"], zone_candidate["cut_proposals"], capabilities
    )

    dso_path = normalized / "dso-zones.geojson"
    etys_path = normalized / "etys-network.json"
    _json(dso_path, network["dso_geojson"])
    _json(etys_path, network["etys_payload"])

    demand_rows = normalize_scheme_c_national_demand(demand_source)
    demand_path = normalized / "national-demand.csv"
    _csv(demand_path, demand_rows, ("period_id", "national_demand_mwh"))
    measured = compile_postcode_demand_weights(
        raw["desnz.postcode-electricity-consumption"],
        raw["ons.postcode-directory"],
        network["dso_geojson"],
    )
    regional_rows = [
        {
            "period_id": "*",
            "zone_id": zone_id,
            "weight": weight,
            "method": measured["method_by_zone"][zone_id],
        }
        for zone_id, weight in measured["weights"].items()
    ]
    regional_path = normalized / "regional-demand-weights.csv"
    _csv(regional_path, regional_rows, ("period_id", "zone_id", "weight", "method"))

    fleet = normalize_scheme_c_fleet(network["dso_geojson"])
    fleet_path = normalized / "model-fleet.csv"
    _csv(fleet_path, fleet["rows"])
    repd = normalize_repd_source(repd_source)
    repd_path = normalized / "repd-normalized.csv"
    _csv(repd_path, repd["rows"])
    interconnectors = normalize_interconnector_register(
        raw["neso.interconnector-register"], network["dso_geojson"]
    )
    interconnector_path = normalized / "interconnector-landings.csv"
    _csv(interconnector_path, interconnectors["rows"])

    weather = build_weather_bundles(
        fleet["rows"],
        repd["rows"],
        network["dso_geojson"],
        wind_nc=wind_nc,
        solar_nc=solar_nc,
        period_ids=tuple(str(item["period_id"]) for item in demand_rows),
    )
    representative_path = normalized / "weather-representative.json"
    aggregated_path = normalized / "weather-aggregated.json"
    _json(representative_path, weather["representative"])
    _json(aggregated_path, weather["aggregated"])

    review = {
        "schema_version": "value.prompt98-official-normalization-review/v1",
        "status": "normalized_candidate_inputs_awaiting_pack_build_and_owner_review",
        "selected_boundary_ids": list(selected_boundaries),
        "zone_count_without_fallback": zone_candidate["zone_count"],
        "zone_count_with_fallback": zone_candidate["zone_count"] + 1,
        "dso_overlap_resolution": dso["overlap_resolution"],
        "merged_boundary_sliver_count": zone_candidate["merged_sliver_count"],
        "network_review": network["review"],
        "demand_review": measured,
        "demand_source": {
            "path_redacted": demand_source.name,
            "sha256": _sha(demand_source),
            "field": "ND",
            "period_hours": 0.5,
        },
        "repd_review": {
            "source_sha256": _sha(repd_source),
            "normalized_rows": len(repd["rows"]),
            "excluded_by_reason": repd["excluded_by_reason"],
        },
        "interconnector_review": interconnectors,
        "weather_review": {
            "source_sha256": weather["source_sha256"],
            "fallback_groups": weather["fallback_groups"],
            "representative_profiles": len(weather["representative"]["profiles"]),
            "aggregated_profiles": len(weather["aggregated"]["profiles"]),
        },
        "fes_evolution": {
            "source_sha256": _sha(raw["neso.fes-gsp-regional-demand"]),
            "status": "retained_as_calibration_evidence_not_applied",
            "reason": "no_reviewed_gsp_to_candidate_zone_crosswalk",
            "base_weight_method": "measured_2024_postcode_consumption",
        },
        "rights_ledger": rights_ledger,
        "owner_signoff": "pending",
    }
    review_path = normalized / "normalization-review.json"
    _json(review_path, review)

    inventory_root = inventory_path.parent
    objects = [
        _inventory_row(
            role="dso_areas", path=dso_path, inventory_root=inventory_root,
            authoritative_url="https://www.neso.energy/data-portal/gis-boundaries-gb-dno-license-areas",
            publisher="National Energy System Operator", title="GB DNO licence areas — normalized candidate zones",
            publication_date="2024-05-03", source_version="2024-05-03+B6-B7a-candidate",
            licence="NESO Open Data Licence", licence_url="https://www.neso.energy/data-portal/neso-open-licence",
            redistribution_decision="redistributable", transformation_step="overlap-resolved DSO base plus provisional B6/B7a splits",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="etys_boundaries", path=etys_path, inventory_root=inventory_root,
            authoritative_url="https://www.neso.energy/data-portal/etys-gb-transmission-system-boundaries",
            publisher="National Energy System Operator", title="ETYS 2025 B6/B7a candidate cut sets and capabilities",
            publication_date="2025", source_version="ETYS-2025+GIS-Mar25",
            licence="Mixed NESO source treatment; capability workbook pointer only", licence_url="https://www.neso.energy/data-portal/neso-open-licence",
            redistribution_decision="pointer_only", transformation_step="selected geometry, computational MST and 2025 capability normalization",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="neso_national_demand", path=demand_path, inventory_root=inventory_root,
            authoritative_url="https://www.neso.energy/data-portal/historic-demand-data",
            publisher="National Energy System Operator / retained VALUE extract", title="2022 GB national demand ND half-hour energy",
            publication_date="2022", source_version=_sha(demand_source)[:16],
            licence="Local research input; source attribution retained", licence_url="https://www.neso.energy/data-portal/neso-open-licence",
            redistribution_decision="local_use_only", transformation_step="ND MW multiplied by 0.5 h",
        ),
        _inventory_row(
            role="regional_demand_evidence", path=regional_path, inventory_root=inventory_root,
            authoritative_url="https://www.gov.uk/government/statistics/postcode-level-electricity-statistics-2024",
            publisher="DESNZ and ONS", title="Measured 2024 postcode electricity allocated to candidate zones",
            publication_date="2025-12-18", source_version="DESNZ-2024+ONSPD-May-2026",
            licence="OGL v3.0 with ONSPD notices", licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            redistribution_decision="local_use_only", transformation_step="streamed postcode join and point-in-polygon aggregation",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="model_fleet", path=fleet_path, inventory_root=inventory_root,
            authoritative_url="https://github.com/hx279", publisher="Hanzhe Xing",
            title="Copied VALUE active fleet normalized for Prompt 98", publication_date="2026-08-21",
            source_version="scheme-c-copied-runtime-config", licence="Apache-2.0", licence_url="https://www.apache.org/licenses/LICENSE-2.0",
            redistribution_decision="redistributable", transformation_step="capacity-unit conversion and zone assignment",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="repd", path=repd_path, inventory_root=inventory_root,
            authoritative_url="https://www.gov.uk/government/publications/renewable-energy-planning-database-monthly-extract",
            publisher="DESNZ", title="REPD Q2 July 2025 normalized spatial audit", publication_date="2025-07",
            source_version=_sha(repd_source)[:16], licence="Local research copy; redistribution review retained", licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            redistribution_decision="local_use_only", transformation_step="technology/status filter and BNG-to-WGS84 conversion",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="interconnector_landings", path=interconnector_path, inventory_root=inventory_root,
            authoritative_url="https://www.neso.energy/data-portal/interconnector-register", publisher="National Energy System Operator",
            title="Built VALUE-country interconnector landing candidate", publication_date="2026-08-18",
            source_version="NESO-interconnector-register-2026-08-18", licence="NESO Open Data Licence",
            licence_url="https://www.neso.energy/data-portal/neso-open-licence", redistribution_decision="redistributable",
            transformation_step="latest built stage, directional current capability and curated landing crosswalk",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="era5_representative_profiles", path=representative_path, inventory_root=inventory_root,
            authoritative_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels", publisher="Copernicus Climate Change Service",
            title="VALUE representative-coordinate ERA5 availability", publication_date="2022",
            source_version=f"wind:{_sha(wind_nc)[:12]}+solar:{_sha(solar_nc)[:12]}", licence="Local installed ERA5 research inputs",
            licence_url="https://cds.climate.copernicus.eu/terms", redistribution_decision="local_use_only",
            transformation_step="nearest grid, copied VALUE curves, hourly-to-half-hour repeat",
            coordinate_reference_system="EPSG:4326",
        ),
        _inventory_row(
            role="era5_aggregated_profiles", path=aggregated_path, inventory_root=inventory_root,
            authoritative_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels", publisher="Copernicus Climate Change Service",
            title="Operational-REPD MW-weighted zonal ERA5 availability", publication_date="2022",
            source_version=f"wind:{_sha(wind_nc)[:12]}+solar:{_sha(solar_nc)[:12]}+repd:{_sha(repd_source)[:12]}",
            licence="Local installed ERA5 and REPD research inputs", licence_url="https://cds.climate.copernicus.eu/terms",
            redistribution_decision="local_use_only", transformation_step="operational REPD zone/technology MW-weighted nearest-grid profiles",
            coordinate_reference_system="EPSG:4326",
        ),
    ]
    inventory = {
        "schema_version": "value.gb-zonal-source-inventory/v1",
        "inventory_id": "official-gb-zonal-b6-b7a-candidate-20260821",
        "candidate_only": True,
        "owner_signoff": "pending",
        "objects": objects,
        "review_artifact": review_path.relative_to(inventory_root).as_posix(),
    }
    _json(inventory_path, inventory)
    return {
        "schema_version": "value.prompt98-materialization-result/v1",
        "status": "normalized_inventory_ready_for_unsigned_candidate_build",
        "inventory": str(inventory_path),
        "inventory_id": inventory["inventory_id"],
        "zone_count_with_fallback": review["zone_count_with_fallback"],
        "selected_boundary_ids": list(selected_boundaries),
        "periods": len(demand_rows),
        "fleet_rows": len(fleet["rows"]),
        "repd_rows": len(repd["rows"]),
        "interconnector_rows": len(interconnectors["rows"]),
        "weather_fallback_groups": len(weather["fallback_groups"]),
        "owner_signoff": "pending",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=resolve_data_workbench_root())
    parser.add_argument("--demand", type=Path, required=True)
    parser.add_argument("--repd", type=Path, required=True)
    parser.add_argument("--wind-nc", type=Path, required=True)
    parser.add_argument("--solar-nc", type=Path, required=True)
    parser.add_argument("--inventory-key", default="official-uk-network-v1.json")
    parser.add_argument("--selected-boundary", action="append", dest="boundaries")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = materialize(
        state_root=args.state_root,
        demand_source=args.demand,
        repd_source=args.repd,
        wind_nc=args.wind_nc,
        solar_nc=args.solar_nc,
        inventory_key=args.inventory_key,
        selected_boundaries=tuple(args.boundaries or ("B6", "B7a")),
    )
    encoded = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
