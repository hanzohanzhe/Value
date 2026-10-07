import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.comparison_identity import build_comparison_identity
from gridform_core.methodology import resolve_methodology
from gridform_core.results_summary import build_run_summary, compare_run_summaries


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ComparisonIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def fixture(self, name, *, storage="dynamic", data_sha="a" * 64, year=2025, parameter=1, solver="strict", source_sha="b" * 64, mode="full", periods=17520, extension=False, storage_source_sha="c" * 64):
        root = Path(self.temp.name) / name
        project = {"schema_version": "value.project/v1", "id": name, "name": name, "data_pack_id": name, "start_year": year, "end_year": year,
                   "modules": {"psm": "psm", "storage_cost": storage}, "parameters": {"scientific.parameter": parameter}, "runtime_options": {},
                   "selected_extensions": ["ext"] if extension else [], "solver_contract": {"policy": solver}}
        modules = [{"slot": slot, "module_id": module, "module_version": "1.0", "contract_version": "v1", "entry_point": "package:Module", "source_sha256": source_sha if slot == "psm" else storage_source_sha} for slot, module in project["modules"].items()]
        pack = {"id": name, "schema_version": "pack/v1", "country": "GB", "timezone": "UTC", "bindings": {"demand": {"sha256": data_sha, "uri": "files/demand.csv", "format": "csv", "unit": "MWh"}}}
        snapshot = {"state": "ready", "snapshot_id": name, "project_sha256": digest(project), "pack_manifest_sha256": digest(pack), "objects": [{"role": "demand", "sha256": data_sha, "pack_directory": "pack"}], "modules": modules}
        if extension:
            snapshot["extension_graph"] = {"extensions": [{"id": "ext", "version": "1", "manifest_sha256": "d" * 64}], "parameters": {}}
        status = {"id": name, "mode": mode, "run_policy": {"start_year": year, "end_year": year, "periods_per_year": periods}}
        # Runs recorded after X0 S9 carry their methodology in the method dimension.
        resolved = {"modules": {row["slot"]: {key: row[key] for key in ("module_id", "module_version", "contract_version")} for row in modules}, "scientific_parameters": {"scientific.parameter": parameter}, "runtime_controls": {},
                    "extensions": {"methodology": resolve_methodology().to_dict()}}
        for path, value in [("input-snapshot/project.json", project), ("input-snapshot/snapshot.json", snapshot), ("input-snapshot/pack/manifest.json", pack), ("status.json", status), ("model-output/resolved-run.json", resolved)]:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        return root

    def pair(self, **kwargs):
        a = build_run_summary(self.fixture("left"))
        b = build_run_summary(self.fixture("right", storage="legacy", **kwargs))
        return compare_run_summaries([a, b])

    def test_matching_data_different_pack_and_snapshot_names_are_same(self):
        result = self.pair()
        self.assertEqual(result["comparison_review"]["dimensions"]["data"]["status"], "same")
        self.assertTrue(result["clean_storage_policy_comparison"])

    def test_data_change_blocks_storage_attribution(self):
        result = self.pair(data_sha="e" * 64)
        self.assertFalse(result["clean_storage_policy_comparison"])
        self.assertIn("identity.data", result["changed_dimensions"])
        self.assertFalse(result["causal_claim_allowed"])

    def test_year_parameter_solver_scope_source_and_extensions_changes(self):
        for kwargs, dimension in [({"year": 2026}, "years"), ({"parameter": 2}, "config"), ({"solver": "loose"}, "config"), ({"periods": 48}, "scope"), ({"source_sha": "f" * 64}, "method"), ({"extension": True}, "method")]:
            with self.subTest(kwargs=kwargs):
                result = self.pair(**kwargs)
                self.assertFalse(result["clean_storage_policy_comparison"])
                self.assertEqual(result["comparison_review"]["dimensions"][dimension]["status"], "changed")

    def test_interpretation_distinguishes_same_unknown_single_and_multiple_changes(self):
        for mode, expected in [("tutorial", "matching_teaching_configuration"), ("value_101_day", "matching_teaching_configuration"), ("full", "matching_recorded_configuration")]:
            with self.subTest(mode=mode):
                left = build_run_summary(self.fixture("same-left-" + mode, mode=mode))
                right = build_run_summary(self.fixture("same-right-" + mode, mode=mode))
                result = compare_run_summaries([left, right])
                self.assertEqual(result["storage_pricing_interpretation"], expected)
                self.assertEqual(result["changed_dimensions"], {})
                self.assertFalse(result["causal_claim_allowed"])
                self.assertIn("matches", result["warning"])
                self.assertEqual(result["annual_metrics_withheld"], mode in {"tutorial", "value_101_day"})
        left = build_run_summary(self.fixture("changed-left"))
        right = build_run_summary(self.fixture("changed-right", parameter=2))
        result = compare_run_summaries([left, right])
        self.assertEqual(result["storage_pricing_interpretation"], "recorded_configuration_changed")
        self.assertNotIn("jointly", result["warning"])
        right = build_run_summary(self.fixture("multiple-right", parameter=2, year=2026))
        result = compare_run_summaries([left, right])
        self.assertEqual(result["storage_pricing_interpretation"], "multiple_dimensions_changed")
        missing = self.fixture("unknown-right")
        (missing / "model-output/resolved-run.json").unlink()
        result = compare_run_summaries([left, build_run_summary(missing)])
        self.assertEqual(result["storage_pricing_interpretation"], "configuration_evidence_unknown")
        self.assertFalse(result["causal_claim_allowed"])
        self.assertIn("incomplete", result["warning"])

    def test_missing_frozen_evidence_is_unknown(self):
        summary = {"run": {"mode": "full"}, "modules": {"storage_cost": "dynamic"}, "annual": []}
        other = copy.deepcopy(summary)
        other["modules"]["storage_cost"] = "legacy"
        result = compare_run_summaries([summary, other])
        self.assertFalse(result["clean_storage_policy_comparison"])
        self.assertFalse(result["causal_claim_allowed"])
        self.assertEqual(result["comparison_review"]["unknown_dimensions"], ["data", "method", "config", "years", "scope"])

    def test_missing_resolved_configuration_blocks_clean(self):
        left = build_run_summary(self.fixture("left"))
        root = self.fixture("right", storage="legacy")
        (root / "model-output/resolved-run.json").unlink()
        result = compare_run_summaries([left, build_run_summary(root)])
        self.assertIn("config", result["comparison_review"]["unknown_dimensions"])
        self.assertFalse(result["clean_storage_policy_comparison"])

    def test_bad_manifest_or_module_hash_is_unknown(self):
        for kind in ("manifest", "module"):
            with self.subTest(kind=kind):
                root = self.fixture(kind)
                path = root / "input-snapshot/snapshot.json"
                snapshot = json.loads(path.read_text())
                if kind == "manifest":
                    snapshot["pack_manifest_sha256"] = "f" * 64
                    dimension = "data"
                else:
                    snapshot["modules"][0].pop("source_sha256")
                    dimension = "method"
                path.write_text(json.dumps(snapshot))
                summary = build_run_summary(root)
                self.assertIsNone(summary["comparison_identity"]["dimensions"][dimension])
                self.assertFalse(compare_run_summaries([summary, summary])["comparison_review"]["evidence_complete"])

    def test_network_overlay_hashes_are_separate(self):
        root = self.fixture("overlay")
        snap_path = root / "input-snapshot/snapshot.json"
        snapshot = json.loads(snap_path.read_text())
        pack = {"bindings": {"ratings": {"sha256": "e" * 64, "format": "csv"}}}
        path = root / "input-snapshot/network-pack/manifest.json"
        path.parent.mkdir()
        path.write_text(json.dumps(pack))
        snapshot["network_pack_manifest_sha256"] = digest(pack)
        snapshot["objects"].append({"role": "ratings", "pack_directory": "network-pack", "sha256": "e" * 64})
        snap_path.write_text(json.dumps(snapshot))
        summary = build_run_summary(root)
        self.assertIn("network-pack", summary["comparison_identity"]["dimensions"]["data"])

    def test_status_identity_conflicts_scope_bool_and_malformed_config(self):
        for field, value in [("project_id", "another-study"), ("input_snapshot_id", "another-snapshot"), ("input_tree_sha256", "another-tree")]:
            with self.subTest(field=field):
                root = self.fixture(field)
                project_path = root / "input-snapshot/project.json"
                project = json.loads(project_path.read_text())
                snapshot_path = root / "input-snapshot/snapshot.json"
                snapshot = json.loads(snapshot_path.read_text())
                snapshot["input_tree_sha256"] = "a" * 64
                snapshot_path.write_text(json.dumps(snapshot))
                status_path = root / "status.json"
                status = json.loads(status_path.read_text())
                status[field] = value
                status_path.write_text(json.dumps(status))
                identity = build_run_summary(root)["comparison_identity"]
                self.assertTrue(all(value is None for value in identity["dimensions"].values()))
        root = self.fixture("boolean", periods=True)
        self.assertIsNone(build_run_summary(root)["comparison_identity"]["dimensions"]["scope"])
        for market in (42, ["invalid"], None):
            root = self.fixture("market" + str(market))
            path = root / "input-snapshot/project.json"
            project = json.loads(path.read_text())
            project["market_configuration"] = market
            path.write_text(json.dumps(project))
            path = root / "input-snapshot/snapshot.json"
            snapshot = json.loads(path.read_text())
            snapshot["project_sha256"] = digest(project)
            path.write_text(json.dumps(snapshot))
            identity = build_run_summary(root)["comparison_identity"]
            self.assertEqual(identity["dimensions"]["config"] is None, market is not None)

    def test_uppercase_hashes_are_normalized(self):
        left = build_run_summary(self.fixture("lower"))
        root = self.fixture("upper", data_sha="A" * 64, source_sha="B" * 64)
        right = build_run_summary(root)
        review = compare_run_summaries([left, right])["comparison_review"]
        self.assertEqual(review["changed_dimensions"], [])
        self.assertTrue(review["evidence_complete"])

    def test_project_tampering_and_resolved_module_disagreement_fail_closed(self):
        root = self.fixture("tamper")
        path = root / "input-snapshot/project.json"
        project = json.loads(path.read_text())
        project["parameters"] = {"scientific.parameter": 100}
        path.write_text(json.dumps(project))
        result = build_run_summary(root)
        self.assertTrue(all(value is None for value in result["comparison_identity"]["dimensions"].values()))
        root = self.fixture("resolved")
        path = root / "model-output/resolved-run.json"
        resolved = json.loads(path.read_text())
        resolved["modules"]["psm"]["module_version"] = "2"
        path.write_text(json.dumps(resolved))
        self.assertIsNone(build_run_summary(root)["comparison_identity"]["dimensions"]["method"])

    def test_one_day_lesson_recorded_extension_is_not_a_method_change(self):
        # F-D2 (DECISIONS A16-3): the one-day lesson runs the market step only,
        # so a recorded but never executed extension is not a method change.
        for mode, periods in (("value_101_day", 48), ("smoke", 2)):
            with self.subTest(mode=mode):
                left = build_run_summary(self.fixture("lesson-left-" + mode, mode=mode, periods=periods))
                right_root = self.fixture("lesson-right-" + mode, mode=mode, periods=periods, extension=True)
                project_path = right_root / "input-snapshot/project.json"
                project = json.loads(project_path.read_text())
                project["extension_parameters"] = {"ext": {"threshold": 3}}
                project_path.write_text(json.dumps(project))
                snapshot_path = right_root / "input-snapshot/snapshot.json"
                snapshot = json.loads(snapshot_path.read_text())
                snapshot["project_sha256"] = digest(project)
                snapshot_path.write_text(json.dumps(snapshot))
                right = build_run_summary(right_root)
                identity = right["comparison_identity"]
                result = compare_run_summaries([left, right])
                if mode == "value_101_day":
                    self.assertIsNone(identity["dimensions"]["method"]["extensions"])
                    self.assertEqual(identity["dimensions"]["config"]["extension_parameters"], {})
                    self.assertEqual(identity["non_executed_extensions"], {"reason_code": "extensions_not_executed_in_scope", "extensions": ["ext"]})
                    self.assertEqual(result["comparison_review"]["dimensions"]["method"]["status"], "same")
                    self.assertEqual(result["comparison_review"]["dimensions"]["config"]["status"], "same")
                    self.assertEqual(result["changed_dimensions"], {})
                    self.assertEqual(result["storage_pricing_interpretation"], "matching_teaching_configuration")
                else:
                    # Scopes that run extension hooks keep them in the method.
                    self.assertNotIn("non_executed_extensions", identity)
                    self.assertEqual(result["comparison_review"]["dimensions"]["method"]["status"], "changed")
                    self.assertEqual(result["comparison_review"]["dimensions"]["config"]["status"], "changed")


    # R1-4 (S-D9, F-D5): the warning names the changed dimension and the
    # differing paths instead of a fixed storage-policy sentence.
    def test_warning_names_the_changed_dimension_and_paths(self):
        left = build_run_summary(self.fixture("named-left"))
        data = compare_run_summaries([left, build_run_summary(self.fixture("named-data", data_sha="e" * 64))])
        self.assertEqual(data["changed_dimension_details"]["data"],
                         {"label": "data inputs", "name": "data inputs", "paths": ["pack.roles.demand"], "more_paths": 0})
        self.assertEqual(data["warning"], "Only one recorded dimension differs - data inputs: pack.roles.demand. The comparison "
                         "describes the effect of this one change.")
        self.assertNotIn("storage-policy", data["warning"])
        # S-低7(a) (R4, A27): a data change is not described as a storage-cost experiment.
        self.assertNotIn("storage-cost", data["warning"])
        extension = compare_run_summaries([left, build_run_summary(self.fixture("named-ext", extension=True))])
        self.assertEqual(extension["changed_dimension_details"]["method"]["paths"], ["extensions"])
        # AF3-2: no doubled parenthesis ("... methodology) (extensions)").
        self.assertIn("model method: extensions", extension["warning"])
        self.assertNotIn(") (", extension["warning"])
        both = compare_run_summaries([left, build_run_summary(self.fixture("named-both", parameter=2, year=2026))])
        self.assertEqual(set(both["changed_dimension_details"]), {"config", "years"})
        self.assertEqual(both["changed_dimension_details"]["years"]["paths"], ["end_year", "start_year"])
        self.assertIn("parameters.scientific.parameter", both["warning"])
        self.assertIn("jointly", both["warning"])
        same = compare_run_summaries([left, build_run_summary(self.fixture("named-same"))])
        self.assertEqual(same["changed_dimension_details"], {})

    # R3M-6: a storage-cost module edited in place (same id and version, new
    # source hash) is named by the field that changed and is the same
    # controlled storage-cost change as a module swap.
    def test_in_place_storage_module_edit_names_the_source_hash(self):
        for mode, periods, interpretation in [("value_101_day", 48, "controlled_teaching_configuration"), ("full", 17520, "controlled_storage_cost_module_change")]:
            with self.subTest(mode=mode):
                left = build_run_summary(self.fixture(f"src-left-{mode}", mode=mode, periods=periods))
                right = build_run_summary(self.fixture(f"src-right-{mode}", mode=mode, periods=periods, storage_source_sha="9" * 64))
                result = compare_run_summaries([left, right])
                self.assertEqual(result["changed_dimension_details"]["method"]["paths"], ["modules.storage_cost.source_sha256"])
                self.assertTrue(result["clean_storage_policy_comparison"])
                self.assertEqual(result["storage_pricing_interpretation"], interpretation)
                swap = compare_run_summaries([left, build_run_summary(self.fixture(f"swap-{mode}", mode=mode, periods=periods, storage="legacy"))])
                self.assertEqual(swap["changed_dimension_details"]["method"]["paths"], ["modules.storage_cost"])
                self.assertEqual(swap["storage_pricing_interpretation"], interpretation)

if __name__ == "__main__":
    unittest.main()
