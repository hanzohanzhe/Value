"""P0-8 S5: historical zonal solver contracts are read, never silently rewritten."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.frontend_contract import (
    ProjectSolverContractError,
    solver_contract_upgrade_preview,
    validate_project_solver_contract,
)
from gridform_core.module_quarantine import status_for_code
from gridform_core.project_revision import save_project_revision
from gridform_core.run_snapshot import METHOD_SUPERSEDED, SnapshotError
from gridform_core.v2.module_manifest import builtin_registry
from gridform_core.zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    V3_SOLVER_CONTRACT_VERSION,
    V3_SOLVER_SCHEMA_VERSION,
)

from tests.test_frozen_run_recovery import FrozenRunRecoveryTests


ROOT = Path(__file__).resolve().parents[1]
V3_DEFAULT = dict(
    DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
    schema_version=V3_SOLVER_SCHEMA_VERSION,
    contract_version=V3_SOLVER_CONTRACT_VERSION,
)


def c8_study() -> dict[str, object]:
    """The frozen VALUE 101 zonal Study of golden case C8 (saved with v3)."""

    project = json.loads(
        (ROOT / "tests" / "golden" / "projects" / "C8.json").read_text(encoding="utf-8")
    )
    project["maturity_acknowledgements"] = {
        key.replace("value-zonal-redispatch-balancing@3.0.0", "value-zonal-redispatch-balancing@4.0.0"): value
        for key, value in dict(project["maturity_acknowledgements"]).items()
    }
    return project


class StudyUpgradeTests(unittest.TestCase):
    def test_v3_study_needs_an_explicit_upgrade(self) -> None:
        project = c8_study()
        self.assertEqual(project["solver_contract"], V3_DEFAULT)
        with self.assertRaises(ProjectSolverContractError) as caught:
            validate_project_solver_contract(project, builtin_registry())
        self.assertEqual(caught.exception.code, "GF_SOLVER_CONTRACT_UPGRADE_REQUIRED")
        self.assertEqual(status_for_code("GF_SOLVER_CONTRACT_UPGRADE_REQUIRED"), 409)
        self.assertEqual(status_for_code(METHOD_SUPERSEDED), 409)

    def test_preview_lists_every_changed_setting_and_changes_nothing(self) -> None:
        project = c8_study()
        before = copy.deepcopy(project)
        preview = solver_contract_upgrade_preview(project)
        self.assertEqual(project, before)
        self.assertEqual(preview["classification"], "method_upgrade_required")
        self.assertEqual(preview["recorded_generation"], "v3")
        self.assertEqual(
            {row["field"] for row in preview["changes"]},
            {"schema_version", "contract_version"},
        )
        self.assertEqual(preview["proposed_solver_contract"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        self.assertIsNone(solver_contract_upgrade_preview(
            dict(project, solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        ))

    def test_explicit_upgrade_saves_a_new_revision_and_keeps_the_old_one(self) -> None:
        registry = builtin_registry()
        manifest = json.loads(
            (ROOT / "data-packs" / "value-101-baseline-v1" / "manifest.json").read_text(encoding="utf-8")
        )
        network = json.loads(
            (ROOT / "data-packs" / "value-101-network-v1" / "manifest.json").read_text(encoding="utf-8")
        )
        manifest = dict(manifest, bindings={**manifest["bindings"], **network["bindings"]})
        with tempfile.TemporaryDirectory() as folder:
            study = Path(folder) / "study"
            (study / "revisions").mkdir(parents=True)
            # A Study saved before P0-8 (v3 contract, revision 1).  It can no
            # longer be re-saved unchanged: saving validates the contract.
            first = dict(c8_study(), revision_sha256="d" * 64, revision_number=1)
            with self.assertRaises(ProjectSolverContractError):
                save_project_revision(
                    study, c8_study(), registry, manifest,
                    expected_base_revision=None,
                )
            old_bytes = json.dumps(first, indent=2).encode("utf-8")
            (study / "project.json").write_bytes(old_bytes)
            (study / "revisions" / f"{'d' * 64}.json").write_bytes(old_bytes)
            upgraded = dict(c8_study(), solver_contract=DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
            validate_project_solver_contract(upgraded, registry)
            second = save_project_revision(
                study, upgraded, registry, manifest,
                expected_base_revision=first["revision_sha256"],
            )
            self.assertEqual(second["revision_number"], 2)
            self.assertIn("solver_contract", second["change_summary"])
            self.assertEqual(second["parent_revision_sha256"], first["revision_sha256"])
            self.assertEqual(
                (study / "revisions" / f"{'d' * 64}.json").read_bytes(), old_bytes
            )
            kept = json.loads(old_bytes)
            self.assertEqual(kept["solver_contract"], V3_DEFAULT)


class RunMethodSupersededTests(FrozenRunRecoveryTests):
    """Reuse the real frozen-run fixture with a Run recorded under v3."""

    def setUp(self) -> None:
        super().setUp()
        self.fixture.mutate(
            self.snapshot, "project.json",
            lambda project: project.update(solver_contract=copy.deepcopy(V3_DEFAULT)),
        )
        self.fixture.rehash(self.snapshot)
        from gridform_core.frozen_input_integrity import verify_frozen_input_integrity

        self.integrity = verify_frozen_input_integrity(self.snapshot)
        self.status.update(
            input_snapshot_id=self.integrity["snapshot_id"],
            input_tree_sha256=self.integrity["input_tree_sha256"],
        )
        self.write_status()

    def test_exact_mode_refuses_with_a_coded_pointer_to_migration(self) -> None:
        report, _ = self.review(mode="strict")
        self.assertFalse(report["allowed"])
        coded = [row for row in report["blocking_reasons"] if row.startswith(METHOD_SUPERSEDED)]
        self.assertEqual(len(coded), 1)
        self.assertIn("migration", coded[0])
        self.assertEqual(report["solver_contract_upgrade"]["recorded_generation"], "v3")

    def test_migration_mode_previews_the_contract_change(self) -> None:
        report, context = self.review(mode="migration")
        change = next(row for row in report["changes"] if row["field"] == "solver_contract")
        self.assertEqual(change["recorded"], V3_DEFAULT)
        self.assertEqual(change["current"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        self.assertFalse(any(row.startswith(METHOD_SUPERSEDED) for row in report["blocking_reasons"]))
        self.assertEqual(context["candidate"]["solver_contract"], DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        recorded = json.loads((self.snapshot / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["solver_contract"], V3_DEFAULT)

    def test_snapshot_errors_carry_their_code(self) -> None:
        error = SnapshotError("x", METHOD_SUPERSEDED)
        self.assertEqual(error.code, METHOD_SUPERSEDED)
        self.assertIsNone(SnapshotError("y").code)


# The inherited FrozenRunRecoveryTests cases run in their own module.
for _name in [name for name in dir(FrozenRunRecoveryTests) if name.startswith("test_")]:
    if not hasattr(RunMethodSupersededTests, _name) or _name in RunMethodSupersededTests.__dict__:
        continue
    setattr(RunMethodSupersededTests, _name, None)
del FrozenRunRecoveryTests


if __name__ == "__main__":
    unittest.main()
