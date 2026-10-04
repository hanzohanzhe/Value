from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.module_bundle import build_module_bundle, validate_module_bundle
from gridform_core.module_installation import install_module_bundle
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
)
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "external_psm_bundle"
PACKAGE = "value_example_quantity_offer_psm"


class ModuleDeveloperExampleTests(unittest.TestCase):
    def tearDown(self) -> None:
        for name in list(sys.modules):
            if name == PACKAGE or name.startswith(PACKAGE + "."):
                sys.modules.pop(name, None)
        sys.path[:] = [
            value for value in sys.path
            if "example-thermal-quantity-offer-psm" not in str(value)
        ]

    def test_psm_tutorial_bundle_installs_and_executes_real_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="force-psm-101-") as temporary:
            root = Path(temporary)
            first = root / "first.zip"
            second = root / "second.zip"
            arguments = {
                "manifest_path": EXAMPLE / "value-module.json",
                "source_root": EXAMPLE / "src",
                "license_path": ROOT / "LICENSE",
                "readme_path": EXAMPLE / "README.md",
            }
            build_module_bundle(**arguments, destination=first)
            build_module_bundle(**arguments, destination=second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            validated = validate_module_bundle(first)
            self.assertEqual(
                validated.manifest["id"], "example-thermal-quantity-offer-psm"
            )

            modules = root / "modules"
            installation = install_module_bundle(
                first, trust_acknowledged=True, modules_root=modules
            )
            self.assertEqual(installation["conformance"]["status"], "passed")
            psm = workspace_registry(modules).resolve(
                "example-thermal-quantity-offer-psm", expected_slot="psm"
            )
            chronology = ChronologicalPSMData(
                period_ids=("p0", "p1"),
                demand_mwh=(50.0, 50.0),
                resources=(
                    DispatchResource(
                        "cheap", "gas", "thermal", 100.0, 10.0, (1.0, 1.0)
                    ),
                    DispatchResource(
                        "expensive", "gas", "thermal", 100.0, 30.0, (1.0, 1.0)
                    ),
                ),
                storage=(),
                voll_gbp_per_mwh=10_000.0,
            )
            result = psm.run(PSMInput(
                "psm-101", 2025, "fixture", OperatingState(2025, (), ()),
                0.5, {}, chronology=chronology,
            ))

            self.assertEqual(result.module_id, "example-thermal-quantity-offer-psm")
            self.assertAlmostEqual(result.generation_mwh_by_asset["cheap"], 90.0)
            self.assertAlmostEqual(result.generation_mwh_by_asset["expensive"], 10.0)
            self.assertAlmostEqual(result.total_operational_cost_gbp, 1_200.0, places=5)
            self.assertAlmostEqual(
                result.extensions["external_module"]["thermal_quantity_offer_fraction"],
                0.90,
            )
            self.assertTrue(all(
                abs(period.energy_balance_residual_mwh) < 1e-7
                for period in result.period_summaries
            ))

            project = json.loads(
                (ROOT / "tests" / "fixtures" / "prompt08_audit_project.json")
                .read_text(encoding="utf-8")
            )
            project.update({
                "id": "psm-101-study",
                "data_pack_id": "value-synthetic-contract-pack-v1",
            })
            project["modules"] = dict(project["modules"])
            project["modules"]["psm"] = "example-thermal-quantity-offer-psm"
            project["modules"].pop("storage_cost", None)
            project["modules"]["transition"] = "value-annual-state-transition"
            captured = io.StringIO()
            with redirect_stdout(captured), redirect_stderr(captured):
                application_result = run_project_application(
                    project,
                    run_id="psm-101-application",
                    pack_root=(
                        ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
                    ),
                    output_dir=root / "application-output",
                    mode="smoke",
                    registry=workspace_registry(modules),
                )
            market = application_result["orchestrator_results"][0]["market"]
            self.assertEqual(
                market["module_id"], "example-thermal-quantity-offer-psm"
            )
            self.assertEqual(
                market["extensions"]["external_module"]["offer_dimension"],
                "quantity",
            )


if __name__ == "__main__":
    unittest.main()
