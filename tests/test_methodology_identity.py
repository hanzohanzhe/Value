"""Methodology as part of the method identity (X0 S9, plan 3.5)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core import methodology
from gridform_core.comparison_identity import build_comparison_identity
from gridform_core.methodology import PROFILE_PARAMETER, REFERENCE_PROFILE_ID
from gridform_core.results_summary import build_run_summary, compare_run_summaries

ROOT = Path(__file__).resolve().parents[1]
CORRECTED = "value-corrected"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class IdentityFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_dir(self, name, *, profile=CORRECTED, storage="dynamic", record=True, bundle=None):
        root = Path(self.temp.name) / name
        parameters = {"scientific.parameter": 1}
        if profile is not None:
            parameters[PROFILE_PARAMETER] = profile
        project = {"schema_version": "value.project/v1", "id": name, "name": name, "data_pack_id": name,
                   "start_year": 2025, "end_year": 2025, "modules": {"psm": "psm", "storage_cost": storage},
                   "parameters": parameters, "runtime_options": {}}
        modules = [{"slot": slot, "module_id": module, "module_version": "1.0", "contract_version": "v1",
                    "entry_point": "package:Module", "source_sha256": "c" * 64} for slot, module in project["modules"].items()]
        pack = {"id": name, "schema_version": "pack/v1", "country": "GB", "timezone": "UTC",
                "bindings": {"demand": {"sha256": "a" * 64, "uri": "files/demand.csv", "format": "csv", "unit": "MWh"}}}
        snapshot = {"state": "ready", "snapshot_id": name, "project_sha256": digest(project), "pack_manifest_sha256": digest(pack),
                    "objects": [{"role": "demand", "sha256": "a" * 64, "pack_directory": "pack"}], "modules": modules}
        status = {"id": name, "mode": "full", "run_policy": {"start_year": 2025, "end_year": 2025, "periods_per_year": 17520}}
        resolved = {"modules": {row["slot"]: {key: row[key] for key in ("module_id", "module_version", "contract_version")} for row in modules},
                    "scientific_parameters": {"scientific.parameter": 1, PROFILE_PARAMETER: profile or CORRECTED},
                    "runtime_controls": {}}
        if record:
            resolved["extensions"] = {"methodology": methodology.resolve_methodology(profile).to_dict()}
        files = [("input-snapshot/project.json", project), ("input-snapshot/snapshot.json", snapshot),
                 ("input-snapshot/pack/manifest.json", pack), ("status.json", status), ("model-output/resolved-run.json", resolved)]
        if bundle:
            files.append(("execution-bundle.json", {"identity_sha256": bundle}))
        for path, value in files:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
        return root


class ProfileOnlyChangeTests(IdentityFixtures):
    def test_profile_only_change_is_an_isolated_method_change(self):
        left = build_run_summary(self.run_dir("left", profile=CORRECTED))
        right = build_run_summary(self.run_dir("right", profile=REFERENCE_PROFILE_ID))
        result = compare_run_summaries([left, right])
        review = result["comparison_review"]
        self.assertEqual(review["changed_dimensions"], ["method"])
        self.assertEqual(review["dimensions"]["config"]["status"], "same")
        self.assertTrue(review["isolated_change_allowed"])
        methods = review["dimensions"]["method"]["values"]
        self.assertEqual(methods[0]["methodology"]["profile_id"], CORRECTED)
        self.assertEqual(methods[1]["methodology"]["profile_id"], REFERENCE_PROFILE_ID)
        self.assertNotIn(PROFILE_PARAMETER, review["dimensions"]["config"]["values"][0]["parameters"])
        self.assertNotIn(PROFILE_PARAMETER, review["dimensions"]["config"]["values"][0]["scientific_parameters"])
        self.assertFalse(result["causal_claim_allowed"])

    def test_same_profile_is_same_method(self):
        left = build_run_summary(self.run_dir("a"))
        right = build_run_summary(self.run_dir("b"))
        review = compare_run_summaries([left, right])["comparison_review"]
        self.assertEqual(review["changed_dimensions"], [])

    def test_storage_change_across_profiles_is_not_a_clean_storage_comparison(self):
        same = compare_run_summaries([
            build_run_summary(self.run_dir("s1", storage="dynamic")),
            build_run_summary(self.run_dir("s2", storage="legacy")),
        ])
        self.assertTrue(same["clean_storage_policy_comparison"])
        crossed = compare_run_summaries([
            build_run_summary(self.run_dir("x1", storage="dynamic")),
            build_run_summary(self.run_dir("x2", storage="legacy", profile=REFERENCE_PROFILE_ID)),
        ])
        self.assertFalse(crossed["clean_storage_policy_comparison"])
        self.assertFalse(crossed["causal_claim_allowed"])


class PreProfileRunTests(IdentityFixtures):
    def test_pre_profile_run_with_execution_bundle_is_unrecorded_but_known(self):
        root = self.run_dir("old", profile=None, record=False, bundle="e" * 64)
        identity = build_comparison_identity(root, json.loads((root / "status.json").read_text()),
                                             json.loads((root / "model-output/resolved-run.json").read_text()))
        self.assertEqual(identity["dimensions"]["method"]["methodology"],
                         {"profile_id": "unrecorded", "execution_identity_sha256": "e" * 64})

    def test_pre_profile_run_without_execution_bundle_has_unknown_method(self):
        root = self.run_dir("older", profile=None, record=False)
        identity = build_comparison_identity(root, json.loads((root / "status.json").read_text()),
                                             json.loads((root / "model-output/resolved-run.json").read_text()))
        self.assertIsNone(identity["dimensions"]["method"])
        self.assertEqual(identity["unknown_reasons"]["method"], "methodology_unrecorded_without_execution_bundle")
        new = build_run_summary(self.run_dir("new"))
        old = build_run_summary(root)
        review = compare_run_summaries([new, old])["comparison_review"]
        self.assertIn("method", review["unknown_dimensions"])
        self.assertFalse(review["isolated_change_allowed"])


class RunRecordTests(unittest.TestCase):
    """A real doctoral smoke run records its methodology everywhere (resolved, provenance)."""

    def test_doctoral_smoke_run_records_the_profile(self):
        from gridform_core.application import run_project_application

        project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project = methodology.with_profile(project, REFERENCE_PROFILE_ID)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            output.mkdir()
            run_project_application(project, run_id="identity-smoke", pack_root=ROOT / "data-packs" / "value-101-baseline-v1",
                                    output_dir=output, mode="smoke")
            resolved = json.loads((output / "resolved-run.json").read_text(encoding="utf-8"))
            record = resolved["extensions"]["methodology"]
            expected = methodology.resolve_methodology(REFERENCE_PROFILE_ID)
            self.assertEqual({key: record[key] for key in expected.identity()}, expected.identity())
            self.assertEqual(record["reference_deviations"], [])
            self.assertEqual(resolved["scientific_parameters"][PROFILE_PARAMETER], REFERENCE_PROFILE_ID)
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["methodology"]["profile_id"], REFERENCE_PROFILE_ID)


class RealRunPairTests(unittest.TestCase):
    """M2 acceptance on real runs: golden D1 under both profiles differs only in the method dimension."""

    def test_d1_under_both_profiles_changes_only_the_method(self):
        from gridform_core.application import run_project_application
        from gridform_core.run_snapshot import create_run_input_snapshot
        from gridform_core.v2.module_manifest import workspace_registry

        pack_root = ROOT / "data-packs" / "value-101-baseline-v1"
        registry = workspace_registry(Path("missing-modules-directory"))
        base = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        summaries = []
        with tempfile.TemporaryDirectory() as folder:
            for name, profile in (("corrected", CORRECTED), ("doctoral", REFERENCE_PROFILE_ID)):
                project = methodology.with_profile(dict(base, id="d1-pair"), profile)
                run = Path(folder) / "runs" / name
                run.mkdir(parents=True)
                snapshot = create_run_input_snapshot(
                    run_dir=run, project=project, pack_root=pack_root, registry=registry,
                    selected=project["modules"], object_root=Path(folder) / "objects",
                )
                (run / "model-output").mkdir()
                # The worker runs on the frozen copy of the pack, never on the
                # source pack: the doctoral whitelist must identify that copy.
                run_project_application(project, run_id=name, pack_root=run / "input-snapshot" / "pack",
                                        output_dir=run / "model-output", mode="smoke")
                status = {"id": name, "project_id": project["id"], "mode": "smoke", "status": "completed",
                          "input_snapshot_id": snapshot.get("snapshot_id"),
                          "run_policy": {"start_year": base["start_year"], "end_year": base["start_year"],
                                         "periods_per_year": 48}}
                (run / "status.json").write_text(json.dumps(status), encoding="utf-8")
                summaries.append(build_run_summary(run))
        identities = [summary["comparison_identity"] for summary in summaries]
        for identity in identities:
            self.assertEqual(identity["unknown_reasons"], {})
        self.assertEqual([identity["dimensions"]["method"]["methodology"]["profile_id"] for identity in identities],
                         [CORRECTED, REFERENCE_PROFILE_ID])
        review = compare_run_summaries(summaries)["comparison_review"]
        self.assertEqual(review["changed_dimensions"], ["method"])
        self.assertEqual(review["unknown_dimensions"], [])
        self.assertTrue(review["isolated_change_allowed"])
        method = [identity["dimensions"]["method"] for identity in identities]
        self.assertEqual(method[0]["modules"], method[1]["modules"])
        self.assertEqual(method[0]["extensions"], method[1]["extensions"])


if __name__ == "__main__":
    unittest.main()
