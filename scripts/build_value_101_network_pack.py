"""Build the deterministic CC0 VALUE 101 three-zone network teaching pack."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.canonical_psm_data import native_initial_state
from gridform_core.zonal_contracts import (
    BoundaryRatingProfile,
    CutsetMember,
    ETYSBoundary,
    InterconnectorLanding,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZONAL_ROLES,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
)


NETWORK_PACK_ID = "value-101-network-v1"
BUILDER_VERSION = "scripts/build_value_101_network_pack.py@v2"
CREATED_AT = "2026-08-24T00:00:00Z"
PERIOD_HOURS = 0.5
PERIODS_PER_YEAR = 17_520


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(value), encoding="utf-8", newline="")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_demand_mwh(base_root: Path, manifest: dict[str, object]) -> list[float]:
    binding = dict(dict(manifest["bindings"])["demand.real"])
    rows = csv.reader((base_root / str(binding["uri"])).read_text(encoding="utf-8").splitlines())
    values: list[float] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            values.append(float(row[0]) * PERIOD_HOURS)
        except (ValueError, IndexError):
            if row_number == 1:
                continue
            raise ValueError(
                f"demand.real contains a non-numeric or missing value at row {row_number}"
            ) from None
    if len(values) < PERIODS_PER_YEAR:
        raise ValueError(
            "VALUE 101 network fixture requires a complete 17,520-period "
            "baseline demand year"
        )
    return values[:PERIODS_PER_YEAR]


def _interconnector_capacity_mw(base_root: Path, manifest: dict[str, object]) -> float:
    """Largest |France flow| (MW) of the base pack on the run clock."""

    from gridform_core.data_method import policy_for_profile, read_role

    policy = policy_for_profile(None, manifest)
    flow = read_role(base_root, manifest, "market.france.profile", policy, periods=PERIODS_PER_YEAR).values
    return float(max(abs(float(value)) for value in flow))


def _read_profile(base_root: Path, manifest: dict[str, object], role: str) -> list[float]:
    binding = dict(dict(manifest["bindings"])[role])
    rows = csv.reader((base_root / str(binding["uri"])).read_text(encoding="utf-8").splitlines())
    values: list[float] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            values.append(float(row[0]))
        except (ValueError, IndexError):
            if row_number == 1:
                continue
            raise ValueError(
                f"{role} contains a non-numeric or missing value at row {row_number}"
            ) from None
    if len(values) < PERIODS_PER_YEAR:
        raise ValueError(
            f"VALUE 101 network fixture requires a complete 17,520-period "
            f"baseline profile for {role}"
        )
    return values[:PERIODS_PER_YEAR]


def _role_payloads(
    base_root: Path,
    base_manifest: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    state = native_initial_state(base_root, 2025)
    active = {asset.asset_id: asset for asset in state.assets}
    required = {"CCGT", "onshore_Portsmouth", "solar_Portsmouth", "1c_battery"}
    if set(active) != required:
        raise ValueError(f"Unexpected VALUE 101 active fleet: {sorted(active)}")

    zones = (
        NetworkZone("north", "North", "Synthetic northern zone", "SYNTHETIC"),
        NetworkZone("central", "Central", "Synthetic central zone", "SYNTHETIC"),
        NetworkZone("south", "South", "Synthetic southern zone", "SYNTHETIC"),
    )
    corridors = (
        TransportCorridor("north-central", "north", "central", "from_to_positive"),
        TransportCorridor("central-south", "central", "south", "from_to_positive"),
    )
    periods = tuple(
        f"{year}:{period}"
        for year in (2025, 2026)
        for period in range(PERIODS_PER_YEAR)
    )
    north_rating = tuple(0.8 if period.endswith(":31") else 1.0 for period in periods)
    south_rating = tuple(0.9 if period.endswith(":30") else 1.0 for period in periods)
    ratings = (
        BoundaryRatingProfile("north-maintenance", periods, north_rating),
        BoundaryRatingProfile("south-maintenance", periods, south_rating),
    )
    cutsets = (
        ETYSBoundary(
            "VALUE101-NC", "North to Central teaching boundary",
            (CutsetMember("north-central", 1),), 2.0, 1.5,
            "north-maintenance", "independent_source",
        ),
        ETYSBoundary(
            "VALUE101-CS", "Central to South teaching boundary",
            (CutsetMember("central-south", 1),), 10.0, 7.0,
            "south-maintenance", "independent_source",
        ),
    )
    mappings = (
        ZonalAssetMapping("onshore_Portsmouth", "north", "generator", "onshore", 1.0, "teaching_assignment"),
        ZonalAssetMapping("solar_Portsmouth", "north", "generator", "solar", 1.0, "teaching_assignment"),
        ZonalAssetMapping("1c_battery", "central", "storage", "1c_battery", 1.0, "teaching_assignment"),
        ZonalAssetMapping("CCGT", "south", "generator", "CCGT", 1.0, "teaching_assignment"),
        ZonalAssetMapping("import:france", "south", "boundary_interconnector", "interconnector", 1.0, "landing_zone"),
        ZonalAssetMapping(
            "value101-solar-planning", "south", "generator", "solar", 1.0,
            "synthetic_project_location",
        ),
    )
    national_one_year = _read_demand_mwh(base_root, base_manifest)
    national = tuple(national_one_year + national_one_year)
    by_zone = {"north": [], "central": [], "south": []}
    for value in national:
        north = value * 0.05
        central = value * 0.15
        by_zone["north"].append(north)
        by_zone["central"].append(central)
        by_zone["south"].append(value - north - central)
    zonal_demand = ZonalDemand(periods, by_zone, national)
    capacities = {
        "CCGT": float(active["CCGT"].capacity_mw),
        "onshore": float(active["onshore_Portsmouth"].capacity_mw),
        "solar": float(active["solar_Portsmouth"].capacity_mw),
        "1c_battery": float(active["1c_battery"].capacity_mw),
        # P0-5a S10 (P6-12): the landing capacity is the base pack's France
        # flow envelope read through the shared reader (12 MW), not a constant.
        "interconnector": _interconnector_capacity_mw(base_root, base_manifest),
    }
    audit = SpatialAudit(
        (
            "onshore_Portsmouth", "solar_Portsmouth", "1c_battery", "CCGT",
            "import:france",
        ),
        capacities,
        capacities,
        1e-9,
    )
    landings = (
        InterconnectorLanding("france", "import:france", "south", "signed_profile_envelope"),
    )

    payloads: dict[str, object] = {
        "value.zonal.zones": {"schema_version": "value.network-zone-collection/v1", "zones": [row.to_dict() for row in zones]},
        "value.zonal.corridors": {"schema_version": "value.transport-corridor-collection/v1", "corridors": [row.to_dict() for row in corridors]},
        "value.zonal.cutsets": {"schema_version": "value.etys-cutset-collection/v1", "cutsets": [row.to_dict() for row in cutsets]},
        "value.zonal.asset-map": {"schema_version": "value.zonal-asset-map-collection/v1", "asset_mappings": [row.to_dict() for row in mappings]},
        "value.zonal.demand": {"schema_version": "value.zonal-demand-collection/v1", "zonal_demand": zonal_demand.to_dict()},
        "value.zonal.ratings": {"schema_version": "value.boundary-rating-profile-collection/v1", "rating_profiles": [row.to_dict() for row in ratings]},
        "value.zonal.interconnector-landings": {"schema_version": "value.interconnector-landing-collection/v1", "interconnector_landings": [row.to_dict() for row in landings]},
        "value.zonal.spatial-audit": audit.to_dict(),
    }

    solar = _read_profile(base_root, base_manifest, "profiles.vre_solar")[31]
    wind = _read_profile(base_root, base_manifest, "profiles.vre_onshore")[31]
    north_generation = (
        capacities["solar"] * solar + capacities["onshore"] * wind
    ) * PERIOD_HOURS
    north_demand = national_one_year[31] * 0.05
    known = {
        "period_id": "2025:31",
        "unconstrained_north_generation_mwh": north_generation,
        "north_demand_mwh": north_demand,
        "unconstrained_north_export_mwh": max(north_generation - north_demand, 0.0),
        "north_central_limit_mwh": 2.0 * 0.8 * PERIOD_HOURS,
        "hand_check": "north VRE availability minus north demand exceeds the maintained north-central transfer envelope",
    }
    minimum_onshore_only_export = min(
        capacities["onshore"] * value * PERIOD_HOURS
        - demand * 0.05
        for value, demand in zip(
            _read_profile(base_root, base_manifest, "profiles.vre_onshore"),
            national_one_year,
        )
    )
    return payloads, {
        **known,
        "normal_north_central_limit_mwh": 2.0 * PERIOD_HOURS,
        "minimum_onshore_only_north_export_mwh": minimum_onshore_only_export,
        "all_periods_have_north_export_congestion": (
            minimum_onshore_only_export > 2.0 * PERIOD_HOURS
        ),
    }


def build_network_pack(base_root: Path, destination: Path) -> dict[str, object]:
    """Derive one complete base-plus-overlay pack without altering the baseline."""

    base_root = Path(base_root).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(base_root, destination)
    base_manifest = json.loads((base_root / "manifest.json").read_text(encoding="utf-8"))
    payloads, known = _role_payloads(base_root, base_manifest)

    bindings = json.loads(json.dumps(base_manifest["bindings"]))
    zonal_hashes: dict[str, str] = {}
    for role in ZONAL_ROLES:
        relative = f"files/zonal/{role}.json"
        path = destination / relative
        _write_json(path, payloads[role])
        digest = _sha256(path)
        zonal_hashes[role] = digest
        bindings[role] = {
            "role": role,
            "uri": relative,
            "filename": path.name,
            "format": "json",
            "bytes": path.stat().st_size,
            "sha256": digest,
            "licence": "CC0-1.0",
            "redistribution_class": "redistributable_cc0",
            "source_url": f"generated://value-101/{NETWORK_PACK_ID}/{role}",
            "source_version": "value-101-network-generator-v1",
            "transformation_version": BUILDER_VERSION,
            "access_date": "2026-08-24",
        }

    role_objects = payloads
    audit_payload = dict(role_objects["value.zonal.spatial-audit"])
    audit_payload["source_sha256_by_role"] = zonal_hashes
    model = ZonalNetworkPack(
        NETWORK_PACK_ID,
        "",
        tuple(NetworkZone.from_dict(row) for row in role_objects["value.zonal.zones"]["zones"]),
        tuple(TransportCorridor.from_dict(row) for row in role_objects["value.zonal.corridors"]["corridors"]),
        tuple(ETYSBoundary.from_dict(row) for row in role_objects["value.zonal.cutsets"]["cutsets"]),
        tuple(ZonalAssetMapping.from_dict(row) for row in role_objects["value.zonal.asset-map"]["asset_mappings"]),
        ZonalDemand.from_dict(role_objects["value.zonal.demand"]["zonal_demand"]),
        tuple(BoundaryRatingProfile.from_dict(row) for row in role_objects["value.zonal.ratings"]["rating_profiles"]),
        tuple(InterconnectorLanding.from_dict(row) for row in role_objects["value.zonal.interconnector-landings"]["interconnector_landings"]),
        SpatialAudit.from_dict(audit_payload),
        "lossless_v1",
        provenance={
            "status": "synthetic_teaching_fixture",
            "builder_version": BUILDER_VERSION,
            "runtime_downloads": False,
            "base_pack_id": "value-101-baseline-v1",
        },
    )
    model = replace(model, scientific_sha256=model.compute_scientific_sha256())
    model.validate()

    manifest = json.loads(json.dumps(base_manifest))
    manifest.update({
        "id": NETWORK_PACK_ID,
        "name": "VALUE 101 fixed three-zone network teaching data",
        "data_pack_type": "network_overlay",
        "updated_at": CREATED_AT,
        "bindings": bindings,
        "periods_per_year": PERIODS_PER_YEAR,
        "annual_economics_eligible": True,
        "scientific_baseline_eligible": False,
        "allowed_run_modes": [
            "smoke", "two_year_smoke", "value_101_day", "two_year",
        ],
        "zonal_network_pack": {
            "network_pack_id": NETWORK_PACK_ID,
            "scientific_sha256": model.scientific_sha256,
            "loss_capability_absent_reason": "lossless_v1",
            "geometry_artifact": None,
            "provenance": dict(model.provenance),
        },
    })
    _write_json(destination / "manifest.json", manifest)
    _write_json(destination / "derivation.json", {
        "schema_version": "value.data-pack-derivation/v1",
        "parent_pack_id": "value-101-baseline-v1",
        "transform": "add a fixed lossless three-zone transport and redispatch overlay",
        "affected_roles": list(ZONAL_ROLES),
        "unchanged_role_hashes_match": True,
        "known_congestion_fixture": known,
        "excluded_methods": [
            "DC load flow", "AC power flow", "N-1 security", "transmission expansion",
        ],
        "builder_version": BUILDER_VERSION,
        "licence": "CC0-1.0",
    })
    (destination / "LICENSE").write_text(
        "CC0 1.0 Universal — this deterministic synthetic teaching pack is dedicated to the public domain.\n",
        encoding="utf-8", newline="",
    )
    return {
        "pack_id": NETWORK_PACK_ID,
        "scientific_sha256": model.scientific_sha256,
        "tree_sha256": _tree_sha256(destination),
        "known_congestion_fixture": known,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path(__file__).resolve().parents[1] / "data-packs" / "value-101-baseline-v1",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "data-packs" / NETWORK_PACK_ID,
    )
    args = parser.parse_args()
    print(_canonical(build_network_pack(args.base, args.output)), end="")


if __name__ == "__main__":
    main()
