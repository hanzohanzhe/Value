"""Stage independent canonical products from verified frozen Run input bytes.

No Study/product publication, registry lookup, historical environment recovery or
model execution occurs here. The publisher must verify the returned inventory.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.pack_source_identity import (
    RECOVERY_BINDING_HISTORY_FIELDS, RECOVERY_BINDING_PROVENANCE_FIELD, RECOVERY_ORIGIN_FIELD,
    RECOVERY_ORIGIN_SCHEMA, RECOVERY_QUALIFICATION_FIELDS, recovery_history_binding_field,
)
from gridform_core.zonal_contracts import ZONAL_ROLES, load_zonal_network_pack
from gridform_core.data_workbench.overlay_editor import reconstruct


class FrozenInputRecoveryError(ValueError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA = re.compile(r"^[0-9a-fA-F]{64}$")
# Shared with the whitelist identity resolver (gridform_core.pack_source_identity),
# which identifies a recovered base pack by verified content identity with the
# source pack recorded in its origin (decision Q3).
QUALIFICATION_FIELDS = RECOVERY_QUALIFICATION_FIELDS
BINDING_HISTORY_FIELDS = RECOVERY_BINDING_HISTORY_FIELDS


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _check_id(value, label):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise FrozenInputRecoveryError(f"{label} must be a safe new data-pack ID")


def _network_role(role):
    return role in ZONAL_ROLES or role.startswith("value.network.")


def _manifest(source, new_id, source_id, source_snapshot_id, source_manifest_sha256, timestamp, *, network):
    manifest = copy.deepcopy(source)
    history = {field: manifest.pop(field) for field in QUALIFICATION_FIELDS if field in manifest}
    manifest.update(id=new_id, name=f"Recovered {'network' if network else 'BASE'} inputs from {source_id}",
                    data_pack_type="network_overlay" if network else "base", created_at=timestamp, updated_at=timestamp,
                    scientific_baseline_eligible=False, scientific_baseline_status="recovered_inputs_pending_scientific_validation",
                    scientific_validation_status="not_evaluated", contract_validation_status="not_evaluated")
    manifest["copy_origin"] = {"schema_version": "value.data-pack-copy/v1", "source_data_pack_id": source["id"],
                               "source_manifest_sha256": source_manifest_sha256, "created_at": timestamp}
    manifest[RECOVERY_ORIGIN_FIELD] = {"schema_version": RECOVERY_ORIGIN_SCHEMA,
        "source_run_id": source_id, "source_snapshot_id": source_snapshot_id,
        "source_pack_id": source["id"], "source_manifest_sha256": source_manifest_sha256,
        "source_data_pack_type": source.get("data_pack_type"), "source_qualification": history,
        "historical_metadata_only": True, "historical_source_and_environment_restored": False}
    manifest.pop("network_overlay", None)
    if not network:
        manifest.pop("zonal_network_pack", None)
    manifest["bindings"] = {}
    return manifest


def recovered_manifests(verified: dict, *, source_run_id: str, base_pack_id: str, network_pack_id: str | None,
                        timestamp: str, base_manifest_sha256: str, network_manifest_sha256: str | None) -> dict:
    """The recovered product manifests and role rows of a verified snapshot, without copying bytes.

    Used by staging and, with placeholder IDs, by the recovery review, so the
    review checks the methodology whitelist on the manifests recovery writes.
    """
    original_base, original_network = verified["base_manifest"], verified["network_manifest"]
    base_manifest = _manifest(original_base, base_pack_id, source_run_id, verified["snapshot_id"],
        base_manifest_sha256, timestamp, network=False)
    network_manifest = (_manifest(original_network, network_pack_id, source_run_id, verified["snapshot_id"],
        network_manifest_sha256, timestamp, network=True) if original_network else None)
    recovered = []
    projected_out = []
    network_roles = {row["role"] for row in verified["canonical_roles"]
                     if row["pack_directory"] == "network-pack" and _network_role(row["role"])}
    for row in verified["canonical_roles"]:
        directory, role = row["pack_directory"], row["role"]
        if ((directory == "pack" and original_network and role in network_roles)
                or (directory == "network-pack" and role not in network_roles)):
            projected_out.append(copy.deepcopy(row))
            continue
        manifest, original = ((base_manifest, original_base) if directory == "pack"
            else (network_manifest, original_network))
        binding = copy.deepcopy(original["bindings"][role])
        history = {field: binding.pop(field) for field in list(binding) if recovery_history_binding_field(field)}
        binding.update(role=role, uri=row["uri"], sha256=row["sha256"], bytes=row["bytes"],
                       binding_revision=row["sha256"], imported_at=timestamp)
        binding[RECOVERY_BINDING_PROVENANCE_FIELD] = {"schema_version": "value.frozen-binding-recovery/v1",
            "source_run_id": source_run_id, "source_snapshot_id": verified["snapshot_id"],
            "source_pack_directory": directory, "source_role": role,
            "source_sha256": row["source_sha256"], "normalized_sha256": row["normalized_sha256"],
            "transformation_id": row["transformation_id"], "historical_metadata": history,
            "historical_metadata_only": True,
            "historical_uri_files_restored": False, "active_bytes_are_normalized": True}
        manifest["bindings"][role] = binding
        recovered.append({**copy.deepcopy(row), "recovered_product": "base" if directory == "pack" else "network",
                          "recovered_pack_id": manifest["id"]})
    return {"base_manifest": base_manifest, "network_manifest": network_manifest,
            "canonical_roles": recovered, "projected_out_roles": projected_out}


def stage_recovered_inputs(source_run_root: Path, staging_root: Path, *, base_pack_id: str,
                           network_pack_id: str | None, source_snapshot_id: str) -> dict:
    """Return UUID staging products; caller owns publication and method-mode policy."""
    _check_id(base_pack_id, "BASE identity")
    if network_pack_id is not None:
        _check_id(network_pack_id, "Network identity")
        if network_pack_id == base_pack_id:
            raise FrozenInputRecoveryError("BASE and network products require distinct new IDs")
    if not isinstance(source_snapshot_id, str) or not SHA.fullmatch(source_snapshot_id):
        raise FrozenInputRecoveryError("Provide the exact recorded source snapshot ID")
    source_run_root, staging_root = Path(source_run_root).absolute(), Path(staging_root).absolute()
    if source_run_root == staging_root or source_run_root in staging_root.parents:
        raise FrozenInputRecoveryError("Recovery staging must remain outside the source Run")
    if any(path.is_symlink() for path in (staging_root, *staging_root.parents)):
        raise FrozenInputRecoveryError("Recovery staging must not contain symbolic links")
    source = source_run_root / "input-snapshot"
    stage = None
    try:
        verified = verify_frozen_input_integrity(source)
        if verified["snapshot_id"] != source_snapshot_id.lower():
            raise FrozenInputRecoveryError("Source snapshot identity changed; prepare recovery again")
        original_base, original_network = verified["base_manifest"], verified["network_manifest"]
        if (original_network is None) != (network_pack_id is None):
            raise FrozenInputRecoveryError("Recovered network selection must match the source snapshot")
        source_ids = {original_base["id"]}
        if original_network:
            source_ids.add(original_network["id"])
        if base_pack_id in source_ids or network_pack_id in source_ids:
            raise FrozenInputRecoveryError("Recovery requires new IDs; original products cannot be replaced")
        # Validate mechanical network content before changing its declared ID.
        if original_network:
            # Recovering a historical Run reads its frozen pack (P0-8 S11).
            load_zonal_network_pack(source / "network-pack", original_network, topology_policy="audit")
        staging_root.mkdir(parents=True, exist_ok=True)
        candidate = staging_root / uuid.uuid4().hex
        candidate.mkdir()
        stage = candidate
        timestamp = datetime.now(timezone.utc).isoformat()
        base_root = stage / "base"; base_root.mkdir()
        network_root = stage / "network" if original_network else None
        if network_root:
            network_root.mkdir()
        projected = recovered_manifests(
            verified, source_run_id=source_run_root.name, base_pack_id=base_pack_id,
            network_pack_id=network_pack_id, timestamp=timestamp,
            base_manifest_sha256=_digest(source / "pack/manifest.json"),
            network_manifest_sha256=_digest(source / "network-pack/manifest.json") if original_network else None)
        base_manifest, network_manifest = projected["base_manifest"], projected["network_manifest"]
        recovered, projected_out = projected["canonical_roles"], projected["projected_out_roles"]
        for row in recovered:
            directory = row["pack_directory"]
            product_root = base_root if directory == "pack" else network_root
            # Preserve exact relative data names, with safe paths already proved
            # by the integrity verifier. copyfile creates independent inodes.
            destination = product_root / row["uri"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / directory / row["uri"], destination)
            if destination.stat().st_nlink != 1 or destination.stat().st_size != row["bytes"] or _digest(destination) != row["sha256"]:
                raise FrozenInputRecoveryError("Copied canonical data does not match its recorded bytes")
        if network_manifest:
            identity = copy.deepcopy(original_network["zonal_network_pack"])
            original_identity = copy.deepcopy(identity)
            identity["network_pack_id"] = network_pack_id
            identity["geometry_artifact"] = None
            identity["provenance"] = {"status": "recovered_inputs_pending_scientific_validation", "runtime_downloads": False,
                "source_run_id": source_run_root.name, "source_snapshot_id": verified["snapshot_id"],
                "historical_identity_metadata": original_identity, "historical_metadata_only": True}
            network_manifest["zonal_network_pack"] = identity
            network = reconstruct(network_root, network_manifest)
            identity["scientific_sha256"] = network.compute_scientific_sha256()
            load_zonal_network_pack(network_root, network_manifest, topology_policy="audit")
        _write(base_root / "manifest.json", base_manifest)
        if network_manifest:
            _write(network_root / "manifest.json", network_manifest)
        record = {"schema_version": "value.frozen-input-recovery-stage/v1", "source_run_id": source_run_root.name,
            "source_snapshot_id": verified["snapshot_id"], "source_input_tree_sha256": verified["input_tree_sha256"],
            "source_project": verified["project"], "source_manifests": {"base": original_base, "network": original_network},
            "declaration_evidence": verified["declaration_evidence"], "canonical_roles": recovered,
            "projected_out_roles": projected_out, "historical_metadata_only": True,
            "study_saved": False, "run_started": False}
        _write(stage / "recovery.json", record)
        # Re-read all frozen source data/metadata, not merely its status label.
        after = verify_frozen_input_integrity(source)
        if after != verified or after["snapshot_id"] != source_snapshot_id.lower():
            raise FrozenInputRecoveryError("Source inputs changed while staging; prepare recovery again")
        inventory = {path.relative_to(stage).as_posix(): {"sha256": _digest(path), "bytes": path.stat().st_size}
                     for path in stage.rglob("*") if path.is_file()}
        return {**record, "stage_root": stage, "base_root": base_root, "network_root": network_root,
                "base_manifest": base_manifest, "network_manifest": network_manifest, "inventory": inventory,
                "limitations": verified["limitations"] + ["Products are staged only; no scientific endorsement or historical runtime recovery."]}
    except Exception as exc:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        if isinstance(exc, FrozenInputRecoveryError):
            raise
        raise FrozenInputRecoveryError(f"Frozen inputs were not staged: {exc}") from exc
