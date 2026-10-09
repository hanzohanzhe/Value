"""Build the VALUE-UK two-pack research suite.

Each component is either resealed from a local source pack (``--base-source``,
``--network-source``: VALUE identity, only the runtime roles) or taken as an
already published data bundle, byte for byte (``--base-bundle``,
``--network-bundle``: no re-wrapping, so the suite's component SHA-256 is the
published bundle's).  ``--suite-id``, ``--base-pack-id`` (resealed base only;
checked against a published base bundle) and ``--study-id-suffix`` make a
second suite on another base pack reproducible, e.g. the GBP1-public2 suite
(DECISIONS A34)::

    build_value_uk_research_suite.py \
        --base-bundle value-uk-open-data-pack-public2-2026-10-09.zip \
        --network-bundle value-gb-zonal-network-v1-c9e841112c40-2026-10-04.zip \
        --suite-id value-uk-research-suite-v1-public2 --study-id-suffix=-public2 \
        --study-name-suffix " (GBP1 public2)" --output suite.zip --receipt receipt.json

The two Study templates always come from
``gridform_core.value_uk.value_uk_study_templates(base_pack_id, network_pack_id)``.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_bundle import build_data_bundle, validate_data_bundle  # noqa: E402
from gridform_core.research_suite import DEFAULT_SUITE_ID, build_research_suite  # noqa: E402
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
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
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


def _reseal_base_pack(source: Path, target: Path, pack_id: str = BASE_PACK_ID) -> dict[str, object]:
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
        "id": pack_id,
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
        "data_pack_id": pack_id,
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
    load_zonal_network_pack(target, manifest, topology_policy="enforce")
    return manifest, network_pack_id


def _bundle_manifest(bundle: Path) -> dict[str, object]:
    with zipfile.ZipFile(bundle) as archive:
        value = json.loads(archive.read("manifest.json").decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Data bundle manifest is not a JSON object: {bundle}")
    return value


def _published_bundle(bundle: Path, *, network: bool) -> tuple[str, dict[str, object]]:
    """Validate a published data bundle that is used as it is (no re-wrapping)."""

    validated = validate_data_bundle(Path(bundle))
    manifest = _bundle_manifest(Path(bundle))
    is_overlay = manifest.get("data_pack_type") == "network_overlay"
    if network and not is_overlay:
        raise ValueError(f"Network bundle is not a network_overlay data product: {bundle}")
    if not network and is_overlay:
        raise ValueError(f"Base bundle is a network_overlay, not a base data pack: {bundle}")
    return str(validated.descriptor["pack_id"]), {
        "mode": "published_bundle",
        "path": str(Path(bundle).resolve()),
        "bundle_sha256": validated.bundle_sha256,
        "bundle_bytes": validated.bundle_bytes,
    }


def _suffixed_templates(
    base_pack_id: str, network_pack_id: str, *, study_id_suffix: str, study_name_suffix: str,
) -> list[dict[str, object]]:
    studies = [dict(item) for item in value_uk_study_templates(base_pack_id, network_pack_id)]
    for study in studies:
        study["id"] = f"{study['id']}{study_id_suffix}"
        study["name"] = f"{study['name']}{study_name_suffix}"
        if not SAFE_ID.fullmatch(str(study["id"])):
            raise ValueError(f"Study ID is not a safe immutable identifier: {study['id']!r}")
    return studies


def build_value_uk_research_suite(
    *,
    destination: Path,
    receipt_path: Path,
    base_source: Path | None = None,
    network_source: Path | None = None,
    base_bundle: Path | None = None,
    network_bundle: Path | None = None,
    base_pack_id: str | None = None,
    suite_id: str = DEFAULT_SUITE_ID,
    study_id_suffix: str = "",
    study_name_suffix: str = "",
) -> dict[str, object]:
    if (base_source is None) == (base_bundle is None):
        raise ValueError("Give exactly one of base_source (reseal) and base_bundle (published, used as is)")
    if (network_source is None) == (network_bundle is None):
        raise ValueError("Give exactly one of network_source (reseal) and network_bundle (published, used as is)")
    if base_pack_id is not None and not SAFE_ID.fullmatch(base_pack_id):
        raise ValueError(f"Base pack ID is not a safe immutable identifier: {base_pack_id!r}")
    if not SAFE_ID.fullmatch(suite_id):
        raise ValueError(f"Suite ID is not a safe immutable identifier: {suite_id!r}")
    destination = Path(destination).resolve()
    receipt_path = Path(receipt_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hashes: list[str | None] = [None, None]
    with tempfile.TemporaryDirectory(prefix="value-uk-suite-") as folder:
        stage = Path(folder)
        if base_bundle is not None:
            resolved_base_id, base_input = _published_bundle(Path(base_bundle), network=False)
            if base_pack_id is not None and base_pack_id != resolved_base_id:
                raise ValueError(
                    f"--base-pack-id {base_pack_id!r} does not match the published base bundle {resolved_base_id!r}"
                )
            base_bundle_path = Path(base_bundle).resolve()
        else:
            base_source = Path(base_source).resolve()  # type: ignore[arg-type]
            source_hashes[0] = _tree_sha256(base_source)
            resolved_base_id = base_pack_id or BASE_PACK_ID
            base_root = stage / "base"
            base_root.mkdir()
            _reseal_base_pack(base_source, base_root, resolved_base_id)
            base_bundle_path = stage / "base.data-bundle.zip"
            build_data_bundle(pack_root=base_root, destination=base_bundle_path)
            base_input = {"mode": "resealed_source", "path": str(base_source), "source_tree_sha256": source_hashes[0]}
        if network_bundle is not None:
            network_pack_id, network_input = _published_bundle(Path(network_bundle), network=True)
            network_bundle_path = Path(network_bundle).resolve()
        else:
            network_source = Path(network_source).resolve()  # type: ignore[arg-type]
            source_hashes[1] = _tree_sha256(network_source)
            network_root = stage / "network"
            network_root.mkdir()
            _network_manifest, network_pack_id = _reseal_network_pack(network_source, network_root)
            network_bundle_path = stage / "network.data-bundle.zip"
            build_data_bundle(pack_root=network_root, destination=network_bundle_path)
            network_input = {"mode": "resealed_source", "path": str(network_source), "source_tree_sha256": source_hashes[1]}
        studies = _suffixed_templates(
            resolved_base_id, network_pack_id,
            study_id_suffix=study_id_suffix, study_name_suffix=study_name_suffix,
        )
        studies_path = stage / "study-templates.json"
        _atomic_json(studies_path, {
            "schema_version": "value.study-templates/v1",
            "studies": studies,
        })
        rights_path = stage / "RIGHTS.json"
        _atomic_json(rights_path, {
            "schema_version": "value.research-suite-rights/v1",
            "suite_id": suite_id,
            "components": [resolved_base_id, network_pack_id],
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
            base_bundle=base_bundle_path,
            network_bundle=network_bundle_path,
            studies_path=studies_path,
            rights_paths=(rights_path, attribution_path),
            destination=destination,
            suite_id=suite_id,
        )
        component_bundle_sha256 = [
            validate_data_bundle(base_bundle_path).bundle_sha256,
            validate_data_bundle(network_bundle_path).bundle_sha256,
        ]
    receipt = {
        "schema_version": "value.research-suite-build-receipt/v1",
        "suite_id": result["suite_id"],
        "path": str(destination),
        "bytes": result["bytes"],
        "sha256": result["sha256"],
        "source_tree_sha256": source_hashes,
        "component_inputs": {"base": base_input, "network": network_input},
        "component_pack_ids": [resolved_base_id, network_pack_id],
        "component_bundle_sha256": component_bundle_sha256,
        "study_ids": [str(study["id"]) for study in studies],
        "source_directories_modified": False,
    }
    _atomic_json(receipt_path, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base = parser.add_mutually_exclusive_group(required=True)
    base.add_argument("--base-source", type=Path, help="local base pack to reseal with VALUE identity")
    base.add_argument("--base-bundle", type=Path, help="published base data bundle, used byte for byte")
    network = parser.add_mutually_exclusive_group(required=True)
    network.add_argument("--network-source", type=Path, help="local zonal network pack to reseal")
    network.add_argument("--network-bundle", type=Path, help="published network data bundle, used byte for byte")
    parser.add_argument("--base-pack-id", help=f"resealed base pack ID (default {BASE_PACK_ID}); checked against --base-bundle")
    parser.add_argument("--suite-id", default=DEFAULT_SUITE_ID, help=f"research-suite ID (default {DEFAULT_SUITE_ID})")
    parser.add_argument("--study-id-suffix", default="", help="appended to both Study IDs, e.g. -public2")
    parser.add_argument("--study-name-suffix", default="", help="appended to both Study names")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    arguments = parser.parse_args()
    result = build_value_uk_research_suite(
        base_source=arguments.base_source,
        network_source=arguments.network_source,
        base_bundle=arguments.base_bundle,
        network_bundle=arguments.network_bundle,
        base_pack_id=arguments.base_pack_id,
        suite_id=arguments.suite_id,
        study_id_suffix=arguments.study_id_suffix,
        study_name_suffix=arguments.study_name_suffix,
        destination=arguments.output,
        receipt_path=arguments.receipt,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
