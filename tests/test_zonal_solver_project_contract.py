from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from gridform_core.frontend_contract import resolve_study_draft
from gridform_core.project_revision import (
    attach_revision_identity,
    derive_zonal_execution_project,
    project_fingerprint,
)
from gridform_core.v2.module_manifest import builtin_registry
from gridform_core.zonal_pack_selection import ZonalPackSelection
from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


ROOT = Path(__file__).resolve().parents[1]
SOLVER_ACK_KEY = "solver-contract:value-zonal-redispatch-balancing@2.0.0"
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


class ZonalSolverProjectContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = builtin_registry()
        self.pack = json.loads(
            (
                ROOT
                / "data-packs"
                / "value-synthetic-contract-pack-v1"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.source_bytes = (
            ROOT / "publication" / "prompt104-zonal-study.json"
        ).read_bytes()
        network_manifest = {
            "schema_version": "value.data-pack/v1",
            "id": "force-zonal-contract-test-overlay-v1",
            "data_pack_type": "network_overlay",
            "bindings": {
                role: {"uri": f"files/{index}.json"}
                for index, role in enumerate(ZONAL_ROLES)
            },
        }
        self.revision_manifest = ZonalPackSelection(
            ROOT,
            self.pack,
            ROOT,
            network_manifest,
            str(network_manifest["id"]),
        ).revision_manifest
        self.baseline, self.evidence = derive_zonal_execution_project(
            self.source_bytes,
            registry=self.registry,
            data_pack_manifest=self.revision_manifest,
        )

    def resolve(self, project: dict[str, object]) -> dict[str, object]:
        return resolve_study_draft(
            project,
            registry=self.registry,
            module_catalog=[
                row.to_dict() for row in self.registry.manifests().values()
            ],
            base_dataset_slots=(),
            available_data_roles=tuple(
                (self.revision_manifest.get("bindings") or {}).keys()
            ),
        )

    def test_solver_contract_changes_project_fingerprint(self) -> None:
        custom = copy.deepcopy(self.baseline)
        custom["solver_contract"]["dual_feasibility_tolerance"] = 1e-8

        self.assertNotEqual(
            project_fingerprint(self.baseline, self.registry, self.revision_manifest),
            project_fingerprint(custom, self.registry, self.revision_manifest),
        )

    def test_identity_rejects_missing_required_extension_data_roles(self) -> None:
        operations = {
            "project_fingerprint": lambda: project_fingerprint(
                self.baseline, self.registry, self.pack
            ),
            "attach_revision_identity": lambda: attach_revision_identity(
                self.baseline, self.registry, self.pack
            ),
            "derive_zonal_execution_project": lambda: derive_zonal_execution_project(
                self.source_bytes,
                registry=self.registry,
                data_pack_manifest=self.pack,
            ),
        }

        for name, operation in operations.items():
            with self.subTest(operation=name), self.assertRaisesRegex(
                ValueError, "Extension data roles are not ready"
            ):
                operation()

    def test_custom_contract_requires_single_save_acknowledgement(self) -> None:
        project = copy.deepcopy(self.baseline)
        project["solver_contract"]["dual_feasibility_tolerance"] = 1e-8

        missing = self.resolve(project)
        self.assertIn(
            "GF_SOLVER_CONTRACT_ACK_REQUIRED",
            {row["code"] for row in missing["errors"]},
        )
        project["maturity_acknowledgements"][SOLVER_ACK_KEY] = (
            "value.solver-contract-ack/v1"
        )
        accepted = self.resolve(project)
        self.assertNotIn(
            "GF_SOLVER_CONTRACT_ACK_REQUIRED",
            {row["code"] for row in accepted["errors"]},
        )
        canonical = accepted["normalised_project"]["solver_contract"]
        self.assertIs(canonical["is_builtin_default"], False)
        self.assertIs(canonical["requires_acknowledgement"], True)

    def test_browser_cannot_spoof_derived_validation_flags(self) -> None:
        project = copy.deepcopy(self.baseline)
        project["solver_contract"]["dual_feasibility_tolerance"] = 1e-8
        project["solver_contract"]["is_builtin_default"] = True
        project["solver_contract"]["requires_acknowledgement"] = False

        result = self.resolve(project)

        canonical = result["normalised_project"]["solver_contract"]
        self.assertIs(canonical["is_builtin_default"], False)
        self.assertIs(canonical["requires_acknowledgement"], True)
        self.assertIn(
            "GF_SOLVER_CONTRACT_ACK_REQUIRED",
            {row["code"] for row in result["errors"]},
        )

    def test_copperplate_rejects_zonal_solver_contract(self) -> None:
        project = copy.deepcopy(self.baseline)
        project["modules"]["balancing"] = "value-copperplate-balancing"

        result = self.resolve(project)

        self.assertIn(
            "GF_SOLVER_CONTRACT_MODULE_MISMATCH",
            {row["code"] for row in result["errors"]},
        )

    def test_zonal_module_requires_a_solver_contract(self) -> None:
        project = copy.deepcopy(self.baseline)
        project.pop("solver_contract")

        result = self.resolve(project)

        self.assertIn(
            "GF_SOLVER_CONTRACT_REQUIRED",
            {row["code"] for row in result["errors"]},
        )

    def test_old_study_derivation_is_explicit_and_preserves_source_bytes(self) -> None:
        self.assertEqual(
            self.evidence,
            {
                "schema_version": "value.study-execution-derivation/v1",
                "source_sha256": hashlib.sha256(self.source_bytes).hexdigest(),
                "reason": "zonal-module-2.0-solver-contract-migration",
                "derived_revision_sha256": self.baseline["revision_sha256"],
            },
        )
        self.assertEqual(
            self.baseline["solver_contract"],
            DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        )
        self.assertNotIn(
            "module:value-zonal-redispatch-balancing@1.0.0",
            self.baseline["maturity_acknowledgements"],
        )
        self.assertEqual(
            self.baseline["maturity_acknowledgements"][
                "module:value-zonal-redispatch-balancing@2.0.0"
            ],
            "value.experimental-ack/v1",
        )
        self.assertEqual(
            (ROOT / "publication" / "prompt104-zonal-study.json").read_bytes(),
            self.source_bytes,
            "derivation must not mutate retained Prompt 104 bytes",
        )


if __name__ == "__main__":
    unittest.main()
