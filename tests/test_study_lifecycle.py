from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.study_lifecycle import (
    StudyLifecycleError,
    list_study_trash,
    move_study_to_trash,
    move_value_101_records_to_trash,
    restore_study,
    study_id_is_reserved,
)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class StudyLifecycleTests(unittest.TestCase):
    def roots(self, root: Path) -> tuple[Path, Path, Path]:
        projects = root / "projects"
        runs = root / "runs"
        trash = root / "trash"
        projects.mkdir()
        runs.mkdir()
        trash.mkdir()
        return projects, runs, trash

    def study(self, projects: Path, study_id: str = "study-a", name: str = "Study A") -> Path:
        study = projects / study_id
        write_json(
            study / "project.json",
            {
                "schema_version": "value.project/v1",
                "id": study_id,
                "name": name,
                "revision_sha256": "a" * 64,
                "revision_number": 2,
            },
        )
        write_json(study / "revisions" / "01.json", {"id": study_id, "revision_number": 1})
        write_json(study / "revisions" / "02.json", {"id": study_id, "revision_number": 2})
        return study

    def run_record(self, runs: Path, run_id: str, project_id: str, status: str) -> Path:
        root = runs / run_id
        write_json(
            root / "status.json",
            {"id": run_id, "project_id": project_id, "status": status},
        )
        return root

    def test_no_run_study_moves_all_revisions_and_restores_original_directory(self) -> None:
        """Catches implementations that move only project.json or cannot restore revisions."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            self.study(projects)

            record = move_study_to_trash(
                "study-a",
                projects_root=projects,
                runs_root=runs,
                trash_root=trash,
                reason="superseded experiment",
            )

            self.assertFalse((projects / "study-a").exists())
            stored = Path(str(record["stored_path"]))
            self.assertTrue((stored / "project.json").is_file())
            self.assertEqual(len(list((stored / "revisions").glob("*.json"))), 2)
            self.assertEqual(record["reason_code"], "user_requested")
            self.assertEqual(record["reason"], "superseded experiment")
            self.assertEqual(record["linked_run_count"], 0)
            self.assertTrue(study_id_is_reserved("study-a", projects_root=projects, trash_root=trash))

            restored = restore_study(
                str(record["trash_id"]),
                projects_root=projects,
                runs_root=runs,
                trash_root=trash,
            )

            self.assertEqual(restored["study_id"], "study-a")
            self.assertTrue((projects / "study-a" / "project.json").is_file())
            self.assertEqual(len(list((projects / "study-a" / "revisions").glob("*.json"))), 2)
            self.assertFalse(list_study_trash(projects, runs, trash))

    def test_historical_runs_require_exact_study_name_but_are_not_moved(self) -> None:
        """Catches deletion that bypasses high-risk confirmation or destroys Run evidence."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            self.study(projects, name="Historical Study")
            historical = self.run_record(runs, "run-finished", "study-a", "completed")

            with self.assertRaisesRegex(StudyLifecycleError, "exact Study name"):
                move_study_to_trash(
                    "study-a",
                    projects_root=projects,
                    runs_root=runs,
                    trash_root=trash,
                    confirmation_name="Historical study",
                )

            record = move_study_to_trash(
                "study-a",
                projects_root=projects,
                runs_root=runs,
                trash_root=trash,
                confirmation_name="Historical Study",
            )
            self.assertTrue((historical / "status.json").is_file())
            self.assertEqual(record["linked_run_ids"], ["run-finished"])
            self.assertEqual(record["linked_run_count"], 1)

    def test_active_run_blocks_move_before_any_files_change(self) -> None:
        """Catches deletion that can orphan an executing worker from its Study."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            self.study(projects)
            self.run_record(runs, "run-active", "study-a", "snapshotting")

            with self.assertRaisesRegex(StudyLifecycleError, "active Run"):
                move_study_to_trash(
                    "study-a",
                    projects_root=projects,
                    runs_root=runs,
                    trash_root=trash,
                    confirmation_name="Study A",
                )

            self.assertTrue((projects / "study-a" / "project.json").is_file())
            self.assertFalse(any(trash.rglob("trash-record.json")))

    def test_legacy_value_101_reset_entries_are_listed_without_rewriting_them(self) -> None:
        """Catches upgrades that make existing recoverable reset records invisible."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            legacy = trash / "value-101-reset" / "20260824-120000-000001"
            write_json(
                legacy / "studies" / "value-101-baseline" / "project.json",
                {
                    "id": "value-101-baseline",
                    "name": "VALUE 101 baseline",
                    "revision_sha256": "b" * 64,
                    "revision_number": 1,
                },
            )
            write_json(
                legacy / "runs" / "lesson-run" / "status.json",
                {"id": "lesson-run", "project_id": "value-101-baseline", "status": "completed"},
            )

            entries = list_study_trash(projects, runs, trash)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["study_id"], "value-101-baseline")
            self.assertEqual(entries[0]["linked_run_ids"], ["lesson-run"])
            self.assertTrue(entries[0]["legacy"])
            self.assertFalse((legacy / "trash-record.json").exists())
            self.assertTrue(
                study_id_is_reserved(
                    "value-101-baseline", projects_root=projects, trash_root=trash
                )
            )

    def test_value_101_reset_uses_audited_batch_and_restore_relinks_its_runs(self) -> None:
        """Catches reset implementations that use an incompatible or one-way trash path."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            study = self.study(projects, "value-101-baseline", "VALUE 101 baseline")
            run = self.run_record(runs, "lesson-run", "value-101-baseline", "completed")

            report = move_value_101_records_to_trash(
                [study],
                [run],
                projects_root=projects,
                runs_root=runs,
                trash_root=trash,
            )

            self.assertEqual(report["schema_version"], "value.study-trash-batch/v1")
            self.assertFalse(study.exists())
            self.assertFalse(run.exists())
            entries = list_study_trash(projects, runs, trash)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["linked_run_ids"], ["lesson-run"])
            self.assertFalse(entries[0]["legacy"])

            restore_study(
                str(entries[0]["trash_id"]),
                projects_root=projects,
                runs_root=runs,
                trash_root=trash,
            )

            self.assertTrue((projects / "value-101-baseline" / "project.json").is_file())
            restored_status = json.loads(
                (runs / "lesson-run" / "status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(restored_status["project_id"], "value-101-baseline")

    def test_restore_rejects_a_tampered_stored_path_outside_trash(self) -> None:
        """Catches a local audit edit that could move an arbitrary directory into Studies."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            outside = root / "outside"
            write_json(outside / "project.json", {"id": "study-a", "name": "Study A"})
            record_root = trash / "studies" / "study-study-a-20260825-120000-000001"
            write_json(
                record_root / "trash-record.json",
                {
                    "trash_id": record_root.name,
                    "study_id": "study-a",
                    "study_name": "Study A",
                    "stored_path": str(outside),
                    "stored_run_paths": {},
                },
            )

            with self.assertRaisesRegex(StudyLifecycleError, "outside recoverable trash"):
                restore_study(
                    record_root.name,
                    projects_root=projects,
                    runs_root=runs,
                    trash_root=trash,
                )

            self.assertTrue((outside / "project.json").is_file())
            self.assertFalse((projects / "study-a").exists())

    def test_value_101_reset_rejects_an_id_that_disagrees_with_its_directory(self) -> None:
        """Catches a malformed teaching record escaping its owned batch destination."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            study = projects / "value-101-baseline"
            write_json(study / "project.json", {"id": "different-id", "name": "Bad"})

            with self.assertRaisesRegex(StudyLifecycleError, "does not match"):
                move_value_101_records_to_trash(
                    [study], [], projects_root=projects, runs_root=runs, trash_root=trash
                )

            self.assertTrue((study / "project.json").is_file())
            self.assertFalse(any(trash.rglob("trash-record.json")))

    def test_batch_restore_fails_closed_when_a_linked_run_is_missing(self) -> None:
        """Catches a partial restore being reported as a complete recovery."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            study = self.study(projects, "value-101-baseline", "VALUE 101 baseline")
            run = self.run_record(runs, "lesson-run", "value-101-baseline", "completed")
            move_value_101_records_to_trash(
                [study], [run], projects_root=projects, runs_root=runs, trash_root=trash
            )
            entry = list_study_trash(projects, runs, trash)[0]
            Path(str(dict(entry["stored_run_paths"])["lesson-run"])).rename(
                root / "detached-run"
            )

            with self.assertRaisesRegex(StudyLifecycleError, "Stored Run"):
                restore_study(
                    str(entry["trash_id"]),
                    projects_root=projects,
                    runs_root=runs,
                    trash_root=trash,
                )

            self.assertFalse((projects / "value-101-baseline").exists())
            self.assertTrue(Path(str(entry["stored_path"])).is_dir())

    def test_batch_restore_rejects_an_omitted_stored_run(self) -> None:
        """Catches an edited inventory stranding a Run while marking the Study restored."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects, runs, trash = self.roots(root)
            study = self.study(projects, "value-101-baseline", "VALUE 101 baseline")
            run = self.run_record(runs, "lesson-run", "value-101-baseline", "completed")
            move_value_101_records_to_trash(
                [study], [run], projects_root=projects, runs_root=runs, trash_root=trash
            )
            entry = list_study_trash(projects, runs, trash)[0]
            record_path = (
                Path(str(entry["stored_path"])).parents[1]
                / "study-records"
                / "value-101-baseline.json"
            )
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["linked_run_ids"] = []
            record_path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(StudyLifecycleError, "Run inventory"):
                restore_study(
                    str(entry["trash_id"]),
                    projects_root=projects,
                    runs_root=runs,
                    trash_root=trash,
                )

            self.assertFalse((projects / "value-101-baseline").exists())
            self.assertTrue((Path(str(entry["stored_path"])).parents[1] / "runs" / "lesson-run").is_dir())


if __name__ == "__main__":
    unittest.main()
