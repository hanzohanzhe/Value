import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gridform_core.frozen_input_integrity import verify_frozen_input_integrity, FrozenInputIntegrityError
from gridform_core.run_snapshot import create_run_input_snapshot
from gridform_core.run_input_snapshot import freeze_resource_readiness
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.frontend_contract import builtin_maturity_acknowledgement_key
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS
from tests.test_run_input_snapshot import SELECTION, pack, network_pack


def h(value, ascii=False):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii).encode()).hexdigest()


def rehash_snapshot_identity(root):
    """Re-derive snapshot.json's manifest hashes, graph hash and snapshot id after a test edited the snapshot."""

    path = root / "snapshot.json"; snapshot = json.loads(path.read_bytes())
    for filename, field in (("project.json", "project_sha256"), ("pack/manifest.json", "pack_manifest_sha256"),
                            ("network-pack/manifest.json", "network_pack_manifest_sha256")):
        if (root / filename).exists():
            snapshot[field] = h(json.loads((root / filename).read_bytes()))
    graph = snapshot["module_resolution_graph"]
    payload = dict(graph["modules"])
    if "extension_graph" in graph:
        payload["$extensions"] = graph["extension_graph"]
    graph["graph_sha256"] = h(payload, True)
    identity = {key: snapshot[key] for key in ("project_sha256", "pack_manifest_sha256", "objects", "modules")}
    for key in ("network_pack_id", "network_pack_manifest_sha256", "extension_graph"):
        if key in snapshot:
            identity[key] = snapshot[key]
    snapshot["input_tree_sha256"] = snapshot["snapshot_id"] = h(identity)
    path.write_text(json.dumps(snapshot))


class FrozenInputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, network=False, resource=False, defaults=False):
        root = self.root / f"fixture-{len(list(self.root.iterdir()))}"
        root.mkdir()
        base = pack(root / "source")
        selected = dict(SELECTION)
        project = {"id": "study", "data_pack_id": "synthetic", "modules": dict(selected)}
        overlay = None
        if network:
            overlay = network_pack(root / "network-source")
            selected.update(psm="value-staged-bid-at-cost-psm", balancing="value-zonal-redispatch-balancing",
                            weather_spatializer="value-representative-point-weather", storage_cost="dynamic-annual-storage-cost")
            project.update(modules=dict(selected), selected_extensions=["value-zonal-redispatch-extension"],
                market_configuration={"network_pack_id": "signed-network-v1"},
                maturity_acknowledgements={
                    builtin_maturity_acknowledgement_key("module", "value-zonal-redispatch-balancing"): "value.experimental-ack/v1",
                    "module:value-representative-point-weather@1.0.0": "value.experimental-ack/v1",
                    "extension:value-zonal-redispatch-extension@1.0.0": "value.experimental-ack/v1"},
                solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        if defaults:
            project["modules"].pop("transition")
            project["modules"]["optional_unused"] = ""
            if network:
                project["modules"].pop("storage_cost")
        run = root / "run"; run.mkdir()
        create_run_input_snapshot(run_dir=run, project=project, pack_root=base,
            network_pack_root=overlay, selected=selected, registry=workspace_registry(root / "no-local"),
            object_root=root / "objects")
        snapshot = run / "input-snapshot"
        if resource:
            freeze_resource_readiness(snapshot, {"trace_profile": "full", "run_context_sha256": "a" * 64,
                "year_context_sha256": "b" * 64, "calibration_key": {}, "calibration_basis": {},
                "free_space_observation": {}, "quota_decision": {}, "selected_output_root": str(root)})
        return snapshot

    def mutate(self, root, name, callback):
        path = root / name
        value = json.loads(path.read_bytes()); callback(value)
        path.write_text(json.dumps(value))

    def rehash(self, root):
        rehash_snapshot_identity(root)

    def test_generated_base_network_resource_defaults_and_read_only_without_registry(self):
        for network, resource, defaults in ((False, False, False), (True, False, False), (True, True, True)):
            with self.subTest(network=network, resource=resource, defaults=defaults):
                root = self.fixture(network, resource, defaults)
                before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
                with patch("importlib.import_module", side_effect=AssertionError("no source loading")):
                    result = verify_frozen_input_integrity(root)
                self.assertEqual(result["project"]["id"], "study")
                self.assertEqual(bool(result["network_manifest"]), network)
                self.assertEqual(bool(result["resource_readiness"]), resource)
                self.assertEqual(len(result["canonical_roles"]), 9 if network else 1)
                if resource:
                    self.assertNotEqual(result["snapshot_id"], result["input_tree_sha256"])
                    self.assertNotEqual(result["base_input_tree_sha256"], result["input_tree_sha256"])
                after = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
                self.assertEqual(before, after)

    def test_historical_base_overlay_type_is_preserved_not_treated_as_corruption(self):
        root = self.fixture(network=True)
        self.mutate(root, "pack/manifest.json", lambda value: value.update(data_pack_type="network_overlay"))
        self.rehash(root)
        result = verify_frozen_input_integrity(root)
        self.assertEqual(result["base_manifest"]["data_pack_type"], "network_overlay")
        self.assertEqual(result["canonical_roles"][0]["pack_directory"], "network-pack")
        self.assertTrue(any(row["pack_kind"] == "base" for row in result["canonical_roles"]))

    def test_production_legacy_extension_projection_is_data_only_not_complete_declarations(self):
        root = self.fixture(network=True)
        def legacy(snapshot):
            graph = snapshot["extension_graph"]
            payload = {"extensions": list(graph["manifests"].values()),
                "parameters": graph["parameters"], "parameter_schema_hashes": graph["parameter_schema_hashes"],
                "hook_order": graph["hook_order"]}
            graph["graph_sha256"] = h(payload)
            graph.pop("manifests")
            graph.pop("hook_source_identities")
            snapshot["module_resolution_graph"]["extension_graph"] = graph
        self.mutate(root, "snapshot.json", legacy)
        self.rehash(root)
        result = verify_frozen_input_integrity(root)
        self.assertFalse(result["declaration_evidence"]["complete"])
        self.assertEqual(result["declaration_evidence"]["extension_graph_self_check"], "unavailable_legacy_projection")
        self.assertIn("extension_graph.manifests", result["declaration_evidence"]["missing_recorded_fields"])
        self.assertNotIn("manifests", result["snapshot"]["extension_graph"])
        self.assertEqual(len(result["canonical_roles"]), 9)
        self.mutate(root, "project.json", lambda value: value.update(selected_extensions=["other-extension"]))
        self.rehash(root)
        with self.assertRaises(FrozenInputIntegrityError):
            verify_frozen_input_integrity(root)

    def test_legacy_base_directory_defaults_keep_original_identity_payload(self):
        root = self.fixture()
        self.mutate(root, "snapshot.json", lambda value: [row.pop(field) for row in value["objects"] for field in ("pack_directory", "pack_kind")])
        self.rehash(root)
        self.assertEqual(verify_frozen_input_integrity(root)["canonical_roles"][0]["pack_directory"], "pack")

    def test_object_binding_coverage_uri_and_source_identity_fail_closed(self):
        for variant in ("missing", "duplicate", "escape", "directory", "source", "bytes", "unbound", "normalized"):
            with self.subTest(variant=variant):
                root = self.fixture()
                def change(snapshot):
                    row = snapshot["objects"][0]
                    if variant == "missing": snapshot["objects"] = []
                    elif variant == "duplicate": snapshot["objects"].append(copy.deepcopy(row))
                    elif variant == "escape": row["snapshot_uri"] = "../project.json"
                    elif variant == "directory": row["pack_directory"] = "../outside"
                    elif variant == "source": row["source_sha256"] = "d" * 64
                    elif variant == "bytes": row["bytes"] = True
                    elif variant == "unbound": row["role"] = "not-bound"
                    elif variant == "normalized": row["sha256"] = "e" * 64
                self.mutate(root, "snapshot.json", change)
                self.rehash(root)
                with self.assertRaises(FrozenInputIntegrityError): verify_frozen_input_integrity(root)

    def test_symlink_and_changed_data_rejected_but_hardlinks_allowed(self):
        root = self.fixture()
        result = verify_frozen_input_integrity(root)
        role = result["canonical_roles"][0]
        path = root / "pack" / role["uri"]
        # Production snapshots may hardlink content-addressed objects.
        self.assertGreaterEqual(path.stat().st_nlink, 1)
        path.unlink(); outside = self.root / "outside.csv"; outside.write_bytes(b"1\n2\n")
        path.symlink_to(outside)
        with self.assertRaises(FrozenInputIntegrityError): verify_frozen_input_integrity(root)
        path.unlink(); path.write_bytes(b"3\n4\n")
        with self.assertRaises(FrozenInputIntegrityError): verify_frozen_input_integrity(root)

    def test_module_scope_source_graph_and_extension_self_hash_rejected(self):
        for variant in ("project", "missing", "duplicate", "entry", "graph", "extension", "default_missing"):
            with self.subTest(variant=variant):
                root = self.fixture(network=variant in {"extension", "default_missing"}, defaults=variant == "default_missing")
                if variant == "project":
                    self.mutate(root, "project.json", lambda value: value["modules"].update(psm="other-method"))
                else:
                    def change(snapshot):
                        if variant == "missing": snapshot["modules"].pop()
                        elif variant == "duplicate": snapshot["modules"].append(copy.deepcopy(snapshot["modules"][0]))
                        elif variant == "entry": snapshot["modules"][0]["entry_point"] = "other:entry"
                        elif variant == "graph": snapshot["module_resolution_graph"]["modules"]["psm"]["source_sha256"] = "d" * 64
                        elif variant == "default_missing":
                            snapshot["modules"] = [row for row in snapshot["modules"] if row["slot"] != "storage_cost"]
                            snapshot["module_resolution_graph"]["modules"].pop("storage_cost")
                        else:
                            extension = snapshot["extension_graph"]
                            extension["graph_sha256"] = "f" * 64
                            snapshot["module_resolution_graph"]["extension_graph"] = extension
                    self.mutate(root, "snapshot.json", change)
                self.rehash(root)
                with self.assertRaises(FrozenInputIntegrityError): verify_frozen_input_integrity(root)

    def test_overall_input_identity_and_resource_file_tamper_rejected(self):
        for field in ("snapshot_id", "input_tree_sha256", "resource"):
            with self.subTest(field=field):
                root = self.fixture(network=True, resource=True)
                if field == "resource":
                    self.mutate(root, "resource-readiness.json", lambda value: value.update(trace_profile="summary"))
                else:
                    self.mutate(root, "snapshot.json", lambda value: value.update({field: "d" * 64}))
                with self.assertRaises(FrozenInputIntegrityError): verify_frozen_input_integrity(root)
