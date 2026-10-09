"""Methodology activation at the run entry and in every PSM.run (X0 S9)."""

from __future__ import annotations

import importlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core import methodology
from gridform_core.methodology import (
    PROFILE_PARAMETER,
    REFERENCE_PROFILE_ID,
    MethodologyMismatchError,
    MethodologyNotActiveError,
    ProfileCombinationError,
    activate,
    active_methodology,
    current_methodology,
    methodology_scoped,
    profile_scope,
    resolve_methodology,
)
from gridform_core.v2.module_manifest import builtin_registry, workspace_registry

ROOT = Path(__file__).resolve().parents[1]
CORRECTED = "value-corrected"


class Toy:
    seen: list = []

    @methodology_scoped
    def run(self, model_input):
        Toy.seen.append(current_methodology().profile_id)
        return current_methodology()


class ScopeTests(unittest.TestCase):
    def setUp(self):
        Toy.seen = []

    def test_nothing_is_active_outside_a_run(self):
        self.assertIsNone(active_methodology())
        with self.assertRaises(MethodologyNotActiveError):
            current_methodology()

    def test_scoped_run_activates_the_declared_profile_or_the_default(self):
        self.assertEqual(Toy().run(SimpleNamespace(parameters={PROFILE_PARAMETER: REFERENCE_PROFILE_ID})).profile_id, REFERENCE_PROFILE_ID)
        self.assertEqual(Toy().run(SimpleNamespace(parameters={})).profile_id, CORRECTED)
        self.assertEqual(Toy().run(object()).profile_id, CORRECTED)
        self.assertIsNone(active_methodology())

    def test_scoped_run_inside_an_active_run_must_match(self):
        with profile_scope(REFERENCE_PROFILE_ID):
            self.assertEqual(Toy().run(SimpleNamespace(parameters={})).profile_id, REFERENCE_PROFILE_ID)
            with self.assertRaises(MethodologyMismatchError):
                Toy().run(SimpleNamespace(parameters={PROFILE_PARAMETER: CORRECTED}))
        self.assertEqual(Toy.seen, [REFERENCE_PROFILE_ID])

    def test_nested_activation_of_another_profile_is_refused(self):
        with profile_scope(CORRECTED):
            with activate(resolve_methodology(CORRECTED)):
                self.assertEqual(current_methodology().profile_id, CORRECTED)
            with self.assertRaises(MethodologyMismatchError):
                with profile_scope(REFERENCE_PROFILE_ID):
                    pass
        self.assertIsNone(active_methodology())

    def test_every_registered_psm_run_is_methodology_scoped(self):
        registry = workspace_registry(Path("missing-modules-directory"), include_internal_experimental=True)
        psms = [manifest for manifest in registry.manifests().values() if manifest.slot == "psm"]
        self.assertEqual({manifest.id for manifest in psms}, {
            "value-bid-at-cost-psm", "value-staged-bid-at-cost-psm", "value-doctoral-national-psm",
            "value-perfect-foresight-lp", "value-reference-dc-network", "value-reference-ac-feasibility",
        })
        # The seventh PSM class of plan X0 S9, SchemeCPSM, is retired: it has no run().
        from gridform_core.builtin.scheme_c_1000twh.psm import SchemeCPSM

        self.assertFalse(hasattr(SchemeCPSM, "run"))
        for manifest in psms:
            module_name, symbol = manifest.implementation.split(":", 1)
            implementation = getattr(importlib.import_module(module_name), symbol)
            with self.subTest(psm=manifest.id):
                self.assertTrue(getattr(implementation.run, "__methodology_scoped__", False), manifest.implementation)

    def test_real_psm_refuses_a_mismatched_direct_call_before_any_work(self):
        from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

        psm = SchemeCNativePSM.__new__(SchemeCNativePSM)
        with profile_scope(CORRECTED):
            with self.assertRaises(MethodologyMismatchError):
                psm.run(SimpleNamespace(parameters={PROFILE_PARAMETER: REFERENCE_PROFILE_ID}))


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = Path(self.folder.name) / "out"
        self.output.mkdir()
        self.project = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))

    def test_run_entry_fails_closed_on_an_unsupported_combination_before_writing(self):
        from gridform_core.application import run_project_application

        project = methodology.with_profile(dict(self.project, modules={
            **self.project["modules"], "storage_cost": "dynamic-annual-storage-cost",
        }), REFERENCE_PROFILE_ID)
        with self.assertRaises(ProfileCombinationError) as caught:
            run_project_application(
                project, run_id="r", pack_root=ROOT / "data-packs" / "value-101-baseline-v1",
                output_dir=self.output, mode="smoke",
            )
        self.assertEqual(caught.exception.sub_reasons, ["module"])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertIsNone(active_methodology())

    def test_run_entry_refuses_a_profile_other_than_the_active_one(self):
        from gridform_core.application import run_project_application

        with profile_scope(CORRECTED):
            with self.assertRaises(MethodologyMismatchError):
                run_project_application(
                    methodology.with_profile(self.project, REFERENCE_PROFILE_ID), run_id="r",
                    pack_root=ROOT / "data-packs" / "value-101-baseline-v1", output_dir=self.output, mode="smoke",
                )
        self.assertEqual(list(self.output.iterdir()), [])

    def test_external_code_refuses_the_doctoral_run(self):
        from gridform_core.application import run_project_application

        with patch("gridform_core.methodology.external_code_entries", return_value=["module:local-thing"]):
            with self.assertRaises(ProfileCombinationError) as caught:
                run_project_application(
                    methodology.with_profile(self.project, REFERENCE_PROFILE_ID), run_id="r",
                    pack_root=ROOT / "data-packs" / "value-101-baseline-v1", output_dir=self.output, mode="smoke",
                )
        self.assertEqual(caught.exception.sub_reasons, ["external_code"])

    def test_reference_route_runs_only_the_frozen_profile(self):
        from gridform_core.builtin.scheme_c_1000twh.modular_run import ModularRunRequest, run_modular_scheme_c

        request = ModularRunRequest(
            pack_root=ROOT / "data-packs" / "value-101-baseline-v1", output_dir=self.output,
            module_ids={}, parameter_overrides={PROFILE_PARAMETER: CORRECTED}, explicit_reference_comparison=True,
        )
        with self.assertRaises(ProfileCombinationError) as caught:
            run_modular_scheme_c(request)
        self.assertEqual(caught.exception.sub_reasons, ["reference_path"])
        with profile_scope(CORRECTED), self.assertRaises(ProfileCombinationError):
            run_modular_scheme_c(ModularRunRequest(
                pack_root=ROOT / "data-packs" / "value-101-baseline-v1", output_dir=self.output,
                module_ids={}, explicit_reference_comparison=True,
            ))
        self.assertEqual(list(self.output.iterdir()), [])


class ConformanceTests(unittest.TestCase):
    def test_storage_cost_fixture_runs_under_every_profile(self):
        from gridform_core import module_conformance

        registry = builtin_registry()
        calls = []
        original = module_conformance._storage_cost_fixture

        def spy(instance, profile_id):
            calls.append(profile_id)
            self.assertIsNone(active_methodology())
            original(instance, profile_id)
            self.assertIsNone(active_methodology())

        with patch.object(module_conformance, "_storage_cost_fixture", side_effect=spy):
            with profile_scope(CORRECTED):  # an active run's profile does not leak into the fixture
                report = module_conformance.conformance_report(registry)
        storage = [row for row in report["modules"] if row["slot"] == "storage_cost"]
        self.assertTrue(storage)
        self.assertTrue(all(row["status"] == "passed" for row in storage), storage)
        self.assertEqual(sorted(set(calls)), sorted(methodology.profile_ids()))
        self.assertEqual(len(calls), len(storage) * len(methodology.profile_ids()))


if __name__ == "__main__":
    unittest.main()
