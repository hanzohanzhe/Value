"""Reseal local UK research inputs as a minimal, VALUE-only research suite."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_bundle import build_data_bundle  # noqa: E402
from gridform_core.research_suite import build_research_suite  # noqa: E402
from gridform_core.value_uk import value_uk_study_templates  # noqa: E402
from gridform_core.zonal_contracts import (  # noqa: E402
    BoundaryRatingProfile,
    ETYSBoundary,
    InterconnectorLanding,
    NetworkZone,
    SpatialAudit,
    TransportCorridor,
    ZONAL_ROLES,
    ZonalAssetMapping,
    ZonalDemand,
    ZonalNetworkPack,
    load_zonal_network_pack,
)


BASE_PACK_ID = "value-uk-open-data-pack-v1"
NETWORK_PREFIX = "value-gb-zonal-network-v1"
STUDY_IDS = ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"]
ROLE_UNITS = {
    "value.zonal.cutsets": "MW",
    "value.zonal.demand": "MWh/period",
    "value.zonal.ratings": "per-unit availability",
    "value.zonal.spatial-audit": "MW",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _value_identity(value: Any) -> Any:
    if isinstance(value, dict):
        return {_value_identity(key): _value_identity(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_value_identity(item) for item in value]
    if isinstance(value, str):
        return (
            value.replace("FORCE", "VALUE")
            .replace("Force", "VALUE")
            .replace("force.", "value.")
            .replace("force-", "value-")
            .replace("gridform.data-pack/v1", "value.data-pack/v1")
        )
    return value


def _read_manifest(source: Path) -> dict[str, object]:
    path = source / "manifest.json"
    if not path.is_file():
        raise ValueError(f"Source data pack has no manifest.json: {source}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("bindings"), dict):
        raise ValueError(f"Source data pack has no binding map: {source}")
    return value


def _copy_binding_file(source_root: Path, source_binding: Mapping[str, object], target: Path) -> None:
    source = (source_root / str(source_binding.get("uri") or "")).resolve()
    source.relative_to(source_root.resolve())
    if not source.is_file():
        raise ValueError(f"Bound source object is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".json":
        loaded = json.loads(source.read_text(encoding="utf-8"))
        target.write_text(
            json.dumps(_value_identity(loaded), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        shutil.copy2(source, target)


def _reseal_base_pack(source: Path, target: Path) -> dict[str, object]:
    manifest = _value_identity(_read_manifest(source))
    source_bindings = dict(manifest["bindings"])
    bindings: dict[str, object] = {}
    for role, raw_binding in sorted(source_bindings.items()):
        if str(role).startswith(("value.zonal.", "force.zonal.")):
            continue
        binding = dict(raw_binding)
        relative = str(binding.get("uri") or "")
        destination = target / relative
        _copy_binding_file(source, binding, destination)
        binding.update({
            "role": role,
            "filename": destination.name,
            "uri": relative,
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        })
        bindings[str(role)] = binding
    if len(bindings) != 25:
        raise ValueError(f"VALUE-UK base pack must expose exactly 25 roles; found {len(bindings)}")
    manifest.update({
        "schema_version": "value.data-pack/v1",
        "id": BASE_PACK_ID,
        "name": "VALUE-UK open research data pack v1",
        "country": "GB",
        "timezone": "Europe/London",
        "period_hours": 0.5,
        "periods_per_year": 17_520,
        "annual_economics_eligible": True,
        "publication_status": "redistributable_per_object",
        "bindings": bindings,
    })
    for key in (
        "allowed_run_modes", "data_pack_type", "materialisation", "source_manifest_sha256",
        "teaching_only", "zonal_network_pack",
    ):
        manifest.pop(key, None)
    _atomic_json(target / "manifest.json", manifest)
    source_rights = source / "RIGHTS.json"
    if source_rights.is_file():
        rights = _value_identity(json.loads(source_rights.read_text(encoding="utf-8")))
    else:
        rights = {"source_notice": "See each manifest binding for its source, licence and attribution."}
    rights.update({
        "schema_version": "value.data-rights/v1",
        "data_pack_id": BASE_PACK_ID,
        "complete_bundle_redistribution": "redistributable_per_object",
        "licence_rule": "Each object retains the licence and attribution stated in manifest.json.",
    })
    _atomic_json(target / "RIGHTS.json", rights)
    (target / "ATTRIBUTION.md").write_text(
        "# VALUE-UK base data attribution\n\n"
        "Compiled by Hanzhe Xing from the sources, versions and transformations listed "
        "for each binding in `manifest.json`. Each upstream object retains its stated licence.\n",
        encoding="utf-8",
    )
    return manifest


def _network_rights(source: Path, network_pack_id: str) -> dict[str, object]:
    source_path = source / "RIGHTS.json"
    rows: list[dict[str, object]] = []
    if source_path.is_file():
        original = json.loads(source_path.read_text(encoding="utf-8"))
        rows = [dict(_value_identity(item)) for item in original.get("source_rights", [])]
    decisions = {
        "dso_areas": ("NESO Open Data Licence v1.0", "redistributable_with_attribution"),
        "era5_aggregated_profiles": ("CC-BY-4.0", "redistributable_derived_data_with_attribution"),
        "era5_representative_profiles": ("CC-BY-4.0", "redistributable_derived_data_with_attribution"),
        "etys_boundaries": ("CC-BY-4.0 owner-authored model parameters; NESO source pointer retained", "redistributable_parameters_source_pointer_only"),
        "interconnector_landings": ("NESO Open Data Licence v1.0", "redistributable_with_attribution"),
        "model_fleet": ("Apache-2.0", "redistributable_owner_licensed"),
        "neso_national_demand": ("NESO Open Data Licence v1.0", "redistributable_with_attribution"),
        "regional_demand_evidence": ("OGL-UK-3.0 with ONS, OS and Royal Mail notices", "redistributable_gb_only_with_attribution"),
        "repd": ("OGL-UK-3.0", "redistributable_with_attribution"),
    }
    for row in rows:
        role = str(row.get("role") or "")
        if role in decisions:
            row["licence"], row["redistribution_decision"] = decisions[role]
        row.pop("pinned_object", None)
    return {
        "schema_version": "value.data-rights/v1",
        "network_pack_id": network_pack_id,
        "complete_bundle_redistribution": "redistributable_per_object",
        "public_source_release_includes_complete_bundle": True,
        "included_content": "Eight derived VALUE zonal runtime objects only; no upstream workbook or raw source archive.",
        "source_rights": rows,
    }


def _network_id(source_manifest: Mapping[str, object]) -> str:
    old = str(source_manifest.get("id") or "")
    match = re.search(r"-([0-9a-f]{12})$", old)
    if match:
        return f"{NETWORK_PREFIX}-{match.group(1)}"
    encoded = json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{NETWORK_PREFIX}-{hashlib.sha256(encoded).hexdigest()[:12]}"


def _reseal_network_pack(source: Path, target: Path) -> tuple[dict[str, object], str]:
    source_manifest = _read_manifest(source)
    network_pack_id = _network_id(source_manifest)
    source_bindings = dict(source_manifest["bindings"])
    bindings: dict[str, object] = {}
    payloads: dict[str, Mapping[str, object]] = {}
    hashes: dict[str, str] = {}
    for role in ZONAL_ROLES:
        legacy_role = role.replace("value.zonal.", "force.zonal.", 1)
        raw_binding = source_bindings.get(role) or source_bindings.get(legacy_role)
        if not isinstance(raw_binding, Mapping):
            raise ValueError(f"Source network pack does not bind {role} or {legacy_role}")
        target_relative = f"files/zonal/{role}.json"
        target_path = target / target_relative
        _copy_binding_file(source, raw_binding, target_path)
        payload = json.loads(target_path.read_text(encoding="utf-8"))
        payloads[role] = payload
        hashes[role] = _sha256(target_path)
        binding = {
            "role": role,
            "uri": target_relative,
            "filename": target_path.name,
            "format": "json",
            "bytes": target_path.stat().st_size,
            "sha256": hashes[role],
            "licence": "mixed open licences and owner-authored derived parameters; see RIGHTS.json",
            "redistribution_class": "redistributable_per_object_with_attribution",
        }
        if role in ROLE_UNITS:
            binding["unit"] = ROLE_UNITS[role]
        bindings[role] = binding

    source_identity = dict(_value_identity(source_manifest.get("zonal_network_pack") or {}))
    provenance = dict(source_identity.get("provenance") or {})
    provenance.update({
        "resealer": "scripts/build_value_uk_research_suite.py@v1",
        "runtime_downloads": False,
        "included_runtime_roles": list(ZONAL_ROLES),
        "excluded_intermediate_artifacts": True,
    })
    provenance.pop("scientific_sha256", None)
    audit_payload = dict(payloads["value.zonal.spatial-audit"])
    audit_payload["source_sha256_by_role"] = hashes
    candidate = ZonalNetworkPack(
        network_pack_id=network_pack_id,
        scientific_sha256="",
        zones=tuple(NetworkZone.from_dict(item) for item in payloads["value.zonal.zones"].get("zones", ())),
        corridors=tuple(TransportCorridor.from_dict(item) for item in payloads["value.zonal.corridors"].get("corridors", ())),
        cutsets=tuple(ETYSBoundary.from_dict(item) for item in payloads["value.zonal.cutsets"].get("cutsets", ())),
        asset_mappings=tuple(ZonalAssetMapping.from_dict(item) for item in payloads["value.zonal.asset-map"].get("asset_mappings", ())),
        zonal_demand=ZonalDemand.from_dict(payloads["value.zonal.demand"].get("zonal_demand", {})),
        rating_profiles=tuple(BoundaryRatingProfile.from_dict(item) for item in payloads["value.zonal.ratings"].get("rating_profiles", ())),
        interconnector_landings=tuple(InterconnectorLanding.from_dict(item) for item in payloads["value.zonal.interconnector-landings"].get("interconnector_landings", ())),
        spatial_audit=SpatialAudit.from_dict(audit_payload),
        loss_capability_absent_reason="lossless_v1",
        geometry_artifact=None,
        provenance=provenance,
    )
    network = dataclasses.replace(candidate, scientific_sha256=candidate.compute_scientific_sha256())
    network.validate()
    manifest = {
        "schema_version": "value.data-pack/v1",
        "id": network_pack_id,
        "name": "VALUE GB fixed-zonal network input — ETYS 2025 B6/B7a",
        "country": "GB",
        "timezone": "Europe/London",
        "period_hours": 0.5,
        "periods_per_year": 17_520,
        "licence": "mixed open licences and CC-BY-4.0 owner-authored parameters; see RIGHTS.json",
        "data_pack_type": "network_overlay",
        "annual_economics_eligible": True,
        "scientific_baseline_eligible": False,
        "scientific_baseline_status": "post_thesis_experimental_network_method",
        "zonal_network_pack": {
            "network_pack_id": network_pack_id,
            "scientific_sha256": network.scientific_sha256,
            "loss_capability_absent_reason": network.loss_capability_absent_reason,
            "geometry_artifact": None,
            "provenance": provenance,
        },
        "bindings": bindings,
    }
    _atomic_json(target / "manifest.json", manifest)
    _atomic_json(target / "RIGHTS.json", _network_rights(source, network_pack_id))
    (target / "ATTRIBUTION.md").write_text(
        "# VALUE GB zonal input attribution\n\n"
        "Compiled by Hanzhe Xing from NESO Open Data, DESNZ and ONS Open Government "
        "Licence data, ERA5 CC BY 4.0 data and owner-authored model parameters. "
        "The exact sources and required notices are recorded in `RIGHTS.json`.\n\n"
        "Supported by National Energy SO Open Data. Contains OS data © Crown copyright "
        "and database right; contains Royal Mail data © Royal Mail copyright and database "
        "right; source: Office for National Statistics licensed under the Open Government "
        "Licence v3.0. Northern Ireland is excluded.\n",
        encoding="utf-8",
    )
    load_zonal_network_pack(target, manifest)
    return manifest, network_pack_id


def build_value_uk_research_suite(
    *,
    base_source: Path,
    network_source: Path,
    destination: Path,
    receipt_path: Path,
) -> dict[str, object]:
    base_source = Path(base_source).resolve()
    network_source = Path(network_source).resolve()
    source_hashes = [_tree_sha256(base_source), _tree_sha256(network_source)]
    destination = Path(destination).resolve()
    receipt_path = Path(receipt_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="value-uk-suite-") as folder:
        stage = Path(folder)
        base_root = stage / "base"
        network_root = stage / "network"
        base_root.mkdir()
        network_root.mkdir()
        _reseal_base_pack(base_source, base_root)
        _network_manifest, network_pack_id = _reseal_network_pack(network_source, network_root)
        base_bundle = stage / "base.data-bundle.zip"
        network_bundle = stage / "network.data-bundle.zip"
        base_result = build_data_bundle(pack_root=base_root, destination=base_bundle)
        network_result = build_data_bundle(pack_root=network_root, destination=network_bundle)
        studies_path = stage / "study-templates.json"
        _atomic_json(studies_path, {
            "schema_version": "value.study-templates/v1",
            "studies": list(value_uk_study_templates(BASE_PACK_ID, network_pack_id)),
        })
        rights_path = stage / "RIGHTS.json"
        _atomic_json(rights_path, {
            "schema_version": "value.research-suite-rights/v1",
            "suite_id": "value-uk-research-suite-v1",
            "components": [BASE_PACK_ID, network_pack_id],
            "redistribution": "per-object open licences and owner-authored CC-BY-4.0 parameters",
            "details": "Install and review the RIGHTS.json inside each component before reuse.",
        })
        attribution_path = stage / "ATTRIBUTION.md"
        attribution_path.write_text(
            "# VALUE-UK research suite attribution\n\n"
            "Compiled by Hanzhe Xing. Component-level sources, transformations, licences "
            "and attribution statements are retained inside both data bundles.\n",
            encoding="utf-8",
        )
        result = build_research_suite(
            base_bundle=base_bundle,
            network_bundle=network_bundle,
            studies_path=studies_path,
            rights_paths=(rights_path, attribution_path),
            destination=destination,
        )
    receipt = {
        "schema_version": "value.research-suite-build-receipt/v1",
        "suite_id": result["suite_id"],
        "path": str(destination),
        "bytes": result["bytes"],
        "sha256": result["sha256"],
        "source_tree_sha256": source_hashes,
        "component_pack_ids": [BASE_PACK_ID, network_pack_id],
        "component_bundle_sha256": [base_result["sha256"], network_result["sha256"]],
        "study_ids": STUDY_IDS,
        "source_directories_modified": False,
    }
    _atomic_json(receipt_path, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-source", required=True, type=Path)
    parser.add_argument("--network-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    arguments = parser.parse_args()
    result = build_value_uk_research_suite(
        base_source=arguments.base_source,
        network_source=arguments.network_source,
        destination=arguments.output,
        receipt_path=arguments.receipt,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
