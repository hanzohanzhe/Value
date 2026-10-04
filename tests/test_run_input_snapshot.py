from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from gridform_core.run_snapshot import (
    SnapshotError,
    create_run_input_snapshot,
    verify_run_input_snapshot,
)
from gridform_core.project_revision import attach_revision_identity
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


SELECTION = {
    "psm": "value-perfect-foresight-lp",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}

ZONAL_ROLES = (
    "value.zonal.zones",
    "value.zonal.corridors",
    "value.zonal.cutsets",
    "value.zonal.asset-map",
    "value.zonal.demand",
    "value.zonal.ratings",
    "value.zonal.interconnector-landings",
    "value.zonal.spatial-audit",
)


def pack(root: Path, content: bytes = b"1\n2\n") -> Path:
    pack_root = root / "pack"
    data = pack_root / "files" / "demand.csv"
    data.parent.mkdir(parents=True)
    data.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    (pack_root / "manifest.json").write_text(json.dumps({
        "schema_version": "value.data-pack/v1",
        "id": "synthetic",
        "bindings": {
            "demand.real": {
                "uri": "files/demand.csv", "filename": "demand.csv",
                "format": "csv", "bytes": len(content), "sha256": digest,
            }
        },
    }), encoding="utf-8")
    return pack_root


def network_pack(root: Path) -> Path:
    pack_root = root / "network-pack"
    bindings = {}
    for index, role in enumerate(ZONAL_ROLES):
        content = json.dumps({"role": role, "index": index}).encode("utf-8")
        filename = f"role-{index}.json"
        path = pack_root / "files" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        bindings[role] = {
            "uri": f"files/{filename}",
            "filename": filename,
            "format": "json",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    (pack_root / "manifest.json").write_text(json.dumps({
        "schema_version": "value.data-pack/v1",
        "id": "signed-network-v1",
        "data_pack_type": "network_overlay",
        "bindings": bindings,
    }), encoding="utf-8")
    return pack_root


class RunInputSnapshotTests(unittest.TestCase):
    def test_zonal_overlay_is_frozen_and_verified_separately(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base_root = pack(root / "base-source")
            overlay_root = network_pack(root / "network-source")
            selected = {
                **SELECTION,
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
                "weather_spatializer": "value-representative-point-weather",
                "storage_cost": "dynamic-annual-storage-cost",
            }
            project = {
                "id": "zonal",
                "data_pack_id": "synthetic",
                "modules": selected,
                "selected_extensions": ["value-zonal-redispatch-extension"],
                "market_configuration": {"network_pack_id": "signed-network-v1"},
                "maturity_acknowledgements": {
                    "module:value-zonal-redispatch-balancing@3.0.0": "value.experimental-ack/v1",
                    "module:value-representative-point-weather@1.0.0": "value.experimental-ack/v1",
                    "extension:value-zonal-redispatch-extension@1.0.0": "value.experimental-ack/v1",
                },
                "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
            }
            registry = workspace_registry(root / "no-local-modules")
            base_manifest = json.loads(
                (base_root / "manifest.json").read_text(encoding="utf-8")
            )
            revision_manifest = resolve_zonal_pack_selection(
                project,
                base_pack_root=base_root,
                base_manifest=base_manifest,
                explicit_network_pack_root=overlay_root,
            ).revision_manifest
            project = attach_revision_identity(project, registry, revision_manifest)
            run = root / "runs" / "zonal"
            run.mkdir(parents=True)
            snapshot = create_run_input_snapshot(
                run_dir=run,
                project=project,
                pack_root=base_root,
                network_pack_root=overlay_root,
                registry=registry,
                selected=selected,
                object_root=root / "objects",
            )
            frozen_overlay = run / "input-snapshot" / "network-pack"
            self.assertTrue((frozen_overlay / "manifest.json").is_file())
            self.assertEqual(snapshot["network_pack_id"], "signed-network-v1")
            self.assertEqual(
                verify_run_input_snapshot(run / "input-snapshot", registry)["snapshot_id"],
                snapshot["snapshot_id"],
            )
            frozen_project = json.loads(
                (run / "input-snapshot" / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                frozen_project["solver_contract"],
                DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
            )
            self.assertEqual(
                frozen_project["revision_sha256"], project["revision_sha256"]
            )
            overlay_object = next(
                row for row in snapshot["objects"] if row["pack_kind"] == "network_overlay"
            )
            frozen_object = frozen_overlay / overlay_object["snapshot_uri"]
            frozen_object.chmod(stat.S_IREAD | stat.S_IWRITE)
            frozen_object.write_bytes(b"tampered")
            with self.assertRaisesRegex(SnapshotError, "missing or changed"):
                verify_run_input_snapshot(run / "input-snapshot", registry)

    def test_project_and_data_mutation_after_enqueue_do_not_change_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pack_root = pack(root)
            project = {"id": "p", "data_pack_id": "synthetic", "modules": SELECTION}
            run = root / "runs" / "r1"
            run.mkdir(parents=True)
            registry = workspace_registry(root / "no-local-modules")
            snapshot = create_run_input_snapshot(
                run_dir=run, project=project, pack_root=pack_root,
                registry=registry, selected=SELECTION,
                object_root=root / "objects",
            )
            project["id"] = "mutated"
            (pack_root / "files" / "demand.csv").write_bytes(b"changed")
            verified = verify_run_input_snapshot(run / "input-snapshot", registry)
            frozen_project = json.loads(
                (run / "input-snapshot" / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(frozen_project["id"], "p")
            self.assertEqual(verified["snapshot_id"], snapshot["snapshot_id"])
            self.assertEqual(
                (run / "input-snapshot" / "pack" / "files" / "demand__real" / "demand.csv").read_bytes(),
                b"1\n2\n",
            )

    def test_two_revisions_are_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry = workspace_registry(root / "no-local-modules")
            identities = []
            for index, content in enumerate((b"one", b"two"), 1):
                pack_root = pack(root / f"source-{index}", content)
                run = root / "runs" / f"r{index}"
                run.mkdir(parents=True)
                identities.append(create_run_input_snapshot(
                    run_dir=run,
                    project={"id": f"p{index}", "data_pack_id": "synthetic", "modules": SELECTION},
                    pack_root=pack_root,
                    registry=registry,
                    selected=SELECTION,
                    object_root=root / "objects",
                )["input_tree_sha256"])
            self.assertNotEqual(*identities)

    def test_bad_hash_never_promotes_an_incomplete_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pack_root = pack(root)
            manifest_path = pack_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["bindings"]["demand.real"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            run = root / "runs" / "bad"
            run.mkdir(parents=True)
            with self.assertRaisesRegex(SnapshotError, "changed before snapshot"):
                create_run_input_snapshot(
                    run_dir=run,
                    project={"id": "bad", "data_pack_id": "synthetic", "modules": SELECTION},
                    pack_root=pack_root,
                    registry=workspace_registry(root / "no-local-modules"),
                    selected=SELECTION,
                    object_root=root / "objects",
                )
            self.assertFalse((run / "input-snapshot").exists())


if __name__ == "__main__":
    unittest.main()

