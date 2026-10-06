import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.study_derivation import StudyDerivationError, derive_study
from gridform_core.project_revision import save_project_revision
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


class Registry:
    def __init__(self):
        self.source_sha = "a" * 64

    def manifest(self, module_id, expected_slot=None):
        return SimpleNamespace(
            id=module_id, version="1.0", contract_version="value.module/v1",
            requires_capabilities=(),
            solver_contract={"defaults": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()}
            if expected_slot == "balancing" else {},
        )

    def resolve_selection(self, modules, **kwargs):
        payload = {
            "modules": {slot: {"module_id": module_id, "source_sha256": self.source_sha}
                        for slot, module_id in modules.items()},
            "source_sha256": self.source_sha,
            "selected_extensions": list(kwargs.get("selected_extensions", ())),
            "extension_parameters": kwargs.get("extension_parameters", {}),
        }
        payload["graph_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        return SimpleNamespace(to_dict=lambda: copy.deepcopy(payload))


class StudyDerivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.projects, self.packs = self.root / "projects", self.root / "data-packs"
        self.registry = Registry()
        for pack_id in ("baseline-pack", "new-pack"):
            path = self.packs / pack_id
            path.mkdir(parents=True)
            (path / "input.csv").write_text("a\n1\n")
            manifest = {
                "schema_version": "value.data-pack/v1", "id": pack_id,
                "bindings": {"demand": {
                    "uri": "input.csv", "sha256": hashlib.sha256(b"a\n1\n").hexdigest(),
                }},
            }
            (path / "manifest.json").write_text(json.dumps(manifest))
        self.source = {
            "schema_version": "value.project/v1", "id": "baseline", "name": "Baseline",
            "data_pack_id": "baseline-pack", "start_year": 2025, "end_year": 2027,
            "purpose": "Controlled study", "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
            },
            "selected_extensions": ["example-extension"],
            "extension_parameters": {"network.limit": 5},
            "maturity_acknowledgements": {"module@1.0": "ack"},
            "market_configuration": {"network_pack_id": "signed-network", "zonal_demand_mode": "scenario_scaled_zonal_shares"},
            "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
            "parameters": {"planning.random_seed": 7},
            "runtime_options": {"runtime.market_trace_level": "full"},
            "extensions": {"value_101": {"origin": "teaching"}},
        }
        self.source["module_resolution_graph"] = self.graph(self.source)
        self.source = save_project_revision(
            self.projects / "baseline", self.source, self.registry, self.pack("baseline-pack"),
        )
        self.before = (self.projects / "baseline" / "project.json").read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def pack(self, pack_id):
        return json.loads((self.packs / pack_id / "manifest.json").read_text())

    def graph(self, candidate):
        return self.registry.resolve_selection(
            candidate["modules"], selected_extensions=candidate["selected_extensions"],
            extension_parameters=candidate["extension_parameters"],
        ).to_dict()

    def validate(self, candidate):
        normalised = copy.deepcopy(candidate)
        normalised["module_resolution_graph"] = self.graph(candidate)
        return {"valid": True, "errors": [], "normalised_project": normalised}

    def derive(self, intent="reproduce", pack="baseline-pack", **kwargs):
        request = {
            "intent": intent, "name": "Independent Study",
            "data_pack_id": pack, "source_revision_sha256": self.source["revision_sha256"],
        }
        request.update(kwargs.pop("request", {}))
        return derive_study(
            "baseline", request, projects_root=self.projects, packs_root=self.packs,
            registry=self.registry, validate_project=kwargs.pop("validate_project", self.validate),
            revision_manifest=lambda candidate, manifest: manifest,
            is_reserved=kwargs.pop("is_reserved", lambda study_id: False),
            suffix_factory=lambda: "1234567890", **kwargs,
        )

    def test_reproduction_preserves_configuration_and_source(self):
        response = self.derive()
        result = response["project"]
        self.assertTrue(response["ok"])
        self.assertFalse(response["run_started"])
        self.assertEqual(result["id"], "independent-study-1234567890")
        for key in ("modules", "parameters", "runtime_options", "solver_contract",
                    "maturity_acknowledgements", "extension_parameters", "selected_extensions",
                    "market_configuration", "purpose", "start_year", "end_year"):
            self.assertEqual(result[key], self.source[key], key)
        # M-D8: the course origin names this Study's parent; it is metadata,
        # not revision content, so a reproduction keeps the source revision.
        self.assertEqual(result["extensions"]["value_101"], {
            "origin": "teaching", "parent_project_id": "baseline", "changed_dimensions": [],
            "derivation_intent": "reproduce"})
        self.assertEqual(result["revision_sha256"], self.source["revision_sha256"])
        self.assertIsNone(result["parent_revision_sha256"])
        self.assertEqual(result["derivation"]["source_revision_sha256"], self.source["revision_sha256"])
        self.assertEqual(result["derivation"]["source_module_graph_sha256"], self.graph(self.source)["graph_sha256"])
        self.assertEqual((self.projects / "baseline" / "project.json").read_bytes(), self.before)
        saved = json.loads((self.projects / result["id"] / "project.json").read_text())
        self.assertEqual(saved, result)

    def test_data_changes_only_pack_and_keeps_network_method(self):
        result = self.derive("data", "new-pack")["project"]
        self.assertEqual(result["data_pack_id"], "new-pack")
        self.assertNotEqual(result["revision_sha256"], self.source["revision_sha256"])
        for key in self.source:
            # fingerprint_basis is revision bookkeeping, like revision_sha256 (X0 S11).
            if key not in {"id", "name", "data_pack_id", "revision_sha256", "fingerprint_basis", "updated_at", "change_summary",
                           "extensions"}:
                self.assertEqual(result[key], self.source[key], key)
        self.assertEqual(result["extensions"]["value_101"]["changed_dimensions"], ["data_pack_id"])
        self.assertEqual(result["extensions"]["value_101"]["parent_project_id"], "baseline")
        self.assertEqual((self.projects / "baseline" / "project.json").read_bytes(), self.before)
        for intent, pack in (("data", "baseline-pack"), ("reproduce", "new-pack")):
            with self.subTest(intent=intent), self.assertRaises(StudyDerivationError) as error:
                self.derive(intent, pack)
            self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_PACK_MISMATCH")

    def test_stale_or_drifted_source_is_rejected(self):
        with self.assertRaises(StudyDerivationError) as error:
            self.derive(request={"source_revision_sha256": "0" * 64})
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_STALE_REVISION")
        # Module sources or the installed pack changed since the save: a revision
        # migration (X0 S11), classified, not a content drift.
        self.registry.source_sha = "b" * 64
        with self.assertRaises(StudyDerivationError) as error:
            self.derive()
        self.assertEqual(error.exception.code, "GF_STUDY_REVISION_MIGRATION_REQUIRED")
        self.assertEqual(error.exception.revision_migration["classification"], "code_identity_upgrade")
        self.assertIn("/api/projects/baseline/revision-migration", str(error.exception))
        self.registry.source_sha = "a" * 64
        manifest_path = self.packs / "baseline-pack" / "manifest.json"
        manifest = self.pack("baseline-pack")
        manifest_path.write_text(json.dumps({**manifest, "updated_at": "drifted"}))
        with self.assertRaises(StudyDerivationError) as error:
            self.derive("data", "new-pack")
        self.assertEqual(error.exception.code, "GF_STUDY_REVISION_MIGRATION_REQUIRED")
        self.assertEqual(error.exception.revision_migration["classification"], "data_changed")
        manifest_path.write_text(json.dumps(manifest))
        # An unsaved edit of the source Study itself stays a drift.
        source_path = self.projects / "baseline" / "project.json"
        edited = json.loads(source_path.read_text())
        source_path.write_text(json.dumps({**edited, "start_year": 2030}))
        with self.assertRaises(StudyDerivationError) as error:
            self.derive()
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_SOURCE_DRIFT")
        source_path.write_bytes(self.before)
        manifest_path.write_text(json.dumps(manifest))
        (self.packs / "baseline-pack" / "input.csv").write_text("mutated")
        with self.assertRaises(StudyDerivationError) as error:
            self.derive()
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_SOURCE_DRIFT")
        self.assertEqual(list(self.projects.iterdir()), [self.projects / "baseline"])

    def test_invalid_conflict_or_save_failure_leaves_no_partial_study(self):
        with self.assertRaises(StudyDerivationError) as error:
            self.derive(request={"intent": []})
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_REQUEST_INVALID")
        with self.assertRaises(StudyDerivationError) as error:
            self.derive(validate_project=lambda candidate: {"valid": False, "errors": ["Bad data"]})
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_INVALID")
        with self.assertRaises(StudyDerivationError) as error:
            self.derive(is_reserved=lambda study_id: True)
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_ID_CONFLICT")
        def fail_save(staging, *args):
            (staging / "project.json").write_text("partial")
            raise ValueError("Failed before promotion")
        with self.assertRaises(StudyDerivationError) as error:
            self.derive(save_revision=fail_save)
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_SAVE_FAILED")
        self.assertEqual(list(self.projects.iterdir()), [self.projects / "baseline"])
        self.assertFalse(list(self.root.glob(".study-derive-*")))
        collision = self.projects / "independent-study-1234567890"
        collision.mkdir()
        (collision / "sentinel").write_text("Keep me")
        with self.assertRaises(StudyDerivationError) as error:
            self.derive()
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_ID_CONFLICT")
        self.assertEqual((collision / "sentinel").read_text(), "Keep me")

    def method_request(self):
        return {"slot": "psm", "module_id": "candidate-psm",
                "candidate_identity_sha256": "c" * 64,
                "maturity_acknowledgements": {"module:candidate-psm@1.0": "explicit-ack"}}

    @patch("backend.study_derivation.module_candidate_identity", return_value="c" * 64)
    def test_method_variant_changes_one_slot_and_keeps_source(self, identity):
        response = self.derive("edit_module", request=self.method_request())
        result = response["project"]
        self.assertFalse(response["run_started"])
        self.assertEqual(result["modules"], {**self.source["modules"], "psm": "candidate-psm"})
        for key in ("parameters", "runtime_options", "solver_contract", "extension_parameters",
                    "selected_extensions", "market_configuration", "purpose",
                    "start_year", "end_year", "data_pack_id"):
            self.assertEqual(result[key], self.source[key], key)
        self.assertEqual(result["extensions"]["value_101"]["changed_dimensions"], ["modules.psm"])
        self.assertEqual(result["extensions"]["value_101"]["derivation_intent"], "edit_module")
        self.assertEqual(result["maturity_acknowledgements"], {
            **self.source["maturity_acknowledgements"], "module:candidate-psm@1.0": "explicit-ack",
        })
        self.assertNotEqual(result["revision_sha256"], self.source["revision_sha256"])
        self.assertEqual(result["derivation"]["method_change"], {
            "slot": "psm", "source_module_id": self.source["modules"]["psm"],
            "module_id": "candidate-psm", "candidate_identity_sha256": "c" * 64,
        })
        self.assertEqual(identity.call_count, 3)
        self.assertEqual((self.projects / "baseline" / "project.json").read_bytes(), self.before)

    @patch("backend.study_derivation.module_candidate_identity", return_value="c" * 64)
    def test_method_variant_rejects_unreviewed_identity_or_other_changes(self, identity):
        for changes, code in (
            ({"candidate_identity_sha256": "d" * 64}, "GF_STUDY_METHOD_IDENTITY_CHANGED"),
            ({"module_id": self.source["modules"]["psm"]}, "GF_STUDY_METHOD_REQUEST_INVALID"),
            ({"slot": "new-slot"}, "GF_STUDY_METHOD_REQUEST_INVALID"),
            ({"maturity_acknowledgements": {"module@1.0": "overwritten"}}, "GF_STUDY_METHOD_ACK_INVALID"),
            ({"data_pack_id": "new-pack"}, "GF_STUDY_DERIVATION_PACK_MISMATCH"),
        ):
            with self.subTest(changes=changes), self.assertRaises(StudyDerivationError) as error:
                self.derive("edit_module", request={**self.method_request(), **changes})
            self.assertEqual(error.exception.code, code)
        for field, value in (("parameters", {"hidden": 7}),
                             ("modules", {"psm": "candidate-psm"})):
            def normalise_extra(candidate):
                normalised = copy.deepcopy(candidate)
                normalised[field] = value
                return self.validate(normalised)
            with self.subTest(field=field), self.assertRaises(StudyDerivationError) as error:
                self.derive("edit_module", request=self.method_request(), validate_project=normalise_extra)
            self.assertEqual(error.exception.code, "GF_STUDY_METHOD_SCOPE_CHANGED")
        def drift_other_graph(candidate):
            result = self.validate(candidate)
            result["normalised_project"]["module_resolution_graph"]["modules"]["balancing"]["source_sha256"] = "z" * 64
            return result
        with self.assertRaises(StudyDerivationError) as error:
            self.derive("edit_module", request=self.method_request(), validate_project=drift_other_graph)
        self.assertEqual(error.exception.code, "GF_STUDY_METHOD_SCOPE_CHANGED")
        identity.side_effect = ["c" * 64, "d" * 64]
        with self.assertRaises(StudyDerivationError) as error:
            self.derive("edit_module", request=self.method_request())
        self.assertEqual(error.exception.code, "GF_STUDY_METHOD_IDENTITY_CHANGED")
        self.assertEqual(list(self.projects.iterdir()), [self.projects / "baseline"])
        self.assertEqual((self.projects / "baseline" / "project.json").read_bytes(), self.before)

    @patch("backend.study_derivation.module_candidate_identity", return_value="c" * 64)
    def test_method_variant_requires_fresh_ack_even_if_source_retains_it(self, identity):
        key = "module:candidate-psm@1.0"
        self.source["maturity_acknowledgements"][key] = "explicit-ack"
        self.source = save_project_revision(
            self.projects / "baseline", self.source, self.registry, self.pack("baseline-pack"),
            expected_base_revision=self.source["revision_sha256"],
        )
        def require_ack(candidate):
            if candidate["maturity_acknowledgements"].get(key) != "explicit-ack":
                return {"valid": False, "errors": ["Experimental acknowledgement required"]}
            return self.validate(candidate)
        with self.assertRaises(StudyDerivationError) as error:
            self.derive("edit_module", request={**self.method_request(), "maturity_acknowledgements": {}},
                        validate_project=require_ack)
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_INVALID")
        self.assertEqual(list(self.projects.iterdir()), [self.projects / "baseline"])

    @patch("backend.study_derivation.module_candidate_identity", return_value="c" * 64)
    def test_method_variant_rejects_local_drift_before_promotion(self, identity):
        def drift_after_save(staging, *args):
            result = save_project_revision(staging, *args)
            self.registry.source_sha = "d" * 64
            return result
        with self.assertRaises(StudyDerivationError) as error:
            self.derive("edit_module", request=self.method_request(), save_revision=drift_after_save)
        self.assertEqual(error.exception.code, "GF_STUDY_DERIVATION_METHOD_DRIFT")
        self.assertEqual(list(self.projects.iterdir()), [self.projects / "baseline"])
        self.assertFalse(list(self.root.glob(".study-derive-*")))
        self.assertEqual((self.projects / "baseline" / "project.json").read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
