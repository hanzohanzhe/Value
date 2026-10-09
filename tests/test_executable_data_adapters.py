from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.data_adapters import AdapterSpec, ColumnRule, execute_adapter, preview_csv
from gridform_core.data_import import promote_binding_revision


class ExecutableDataAdapterTests(unittest.TestCase):
    def test_foreign_columns_units_and_technology_labels_are_normalized(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "foreign.csv"
            source.write_text(
                "project,size_kw,tech,area\nA,2500,PV,North\nB,1000,WIND,South\n",
                encoding="utf-8",
            )
            specification = AdapterSpec(
                "synthetic-project-adapter",
                "1.0.0",
                "csv",
                "projects.repd",
                "csv",
                (
                    ColumnRule("project", "project_id"),
                    ColumnRule("size_kw", "capacity_mw", "kW", "MW"),
                    ColumnRule("tech", "technology"),
                    ColumnRule("area", "region"),
                ),
                {"PV": "solar", "WIND": "onshore"},
                "technology",
            )
            preview = preview_csv(source, specification, limit=1)
            self.assertEqual(preview["sample"][0]["capacity_mw"], 2.5)
            self.assertEqual(preview["sample"][0]["technology"], "solar")
            result = execute_adapter(source, specification, root / "normalized.csv")
            self.assertEqual(result.rows, 2)
            self.assertIn("A,2.5,solar,North", result.normalized_path.read_text(encoding="utf-8"))

    def test_ambiguous_unit_conversion_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "data.csv"
            source.write_text("value\n2\n", encoding="utf-8")
            specification = AdapterSpec(
                "bad-units", "1.0.0", "csv", "demand.real", "csv",
                (ColumnRule("value", "demand_mwh", "tonnes", "MWh"),),
            )
            with self.assertRaisesRegex(ValueError, "Ambiguous unit conversion"):
                execute_adapter(source, specification, Path(folder) / "out.csv")

    def test_failed_import_preserves_previous_manifest_and_file(self):
        with tempfile.TemporaryDirectory() as folder:
            pack = Path(folder) / "pack"
            old = pack / "files" / "projects__repd" / "old.csv"
            old.parent.mkdir(parents=True)
            old.write_text(
                "project_id,technology,capacity_mw,development_status,region\n"
                "old,solar,1,active,GB\n",
                encoding="utf-8",
            )
            old_sha = hashlib.sha256(old.read_bytes()).hexdigest()
            manifest = {
                "id": "pack",
                "bindings": {"projects.repd": {
                    "uri": old.relative_to(pack).as_posix(), "filename": "old.csv",
                    "format": "csv", "sha256": old_sha, "bytes": old.stat().st_size,
                }},
            }
            manifest_path = pack / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            original_manifest = manifest_path.read_bytes()
            staged = Path(folder) / "bad.csv"
            staged.write_text(
                "project_id,technology,capacity_mw,development_status,region\n"
                "duplicate,solar,1,active,GB\n"
                "duplicate,solar,2,active,GB\n",
                encoding="utf-8",
            )
            slots = [{
                "role": "projects.repd", "formats": ["csv"], "required": True,
            }]
            with self.assertRaisesRegex(ValueError, "duplicate project IDs"):
                promote_binding_revision(
                    pack_root=pack, manifest=manifest, role="projects.repd",
                    staged_file=staged, filename="bad.csv", file_format="csv",
                    dataset_slots=slots, imported_at="2026-08-08T00:00:00Z",
                )
            self.assertEqual(manifest_path.read_bytes(), original_manifest)
            self.assertEqual(old.read_text(encoding="utf-8").splitlines()[-1], "old,solar,1,active,GB")


if __name__ == "__main__":
    unittest.main()



class AdapterCellProblemTests(unittest.TestCase):
    """R1-4 (S-D7): cell problems are collected by row and column; no output is written."""

    def test_empty_cells_are_listed_with_the_other_problems(self):
        # L-1 (four-role R1 retest): an empty cell was let through while other
        # cells failed, so the user needed a second round to see it.
        from gridform_core.data_adapters import AdapterValueError

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "data.csv"
            source.write_text("period,value\n1,bad\n2,\n3,2\n4,abc\n", encoding="utf-8")
            specification = AdapterSpec(
                "cells", "1.0.0", "csv", "demand.real", "csv",
                (ColumnRule("value", "demand_mw", "GW", "MW"),),
            )
            output = Path(folder) / "out.csv"
            with self.assertRaises(AdapterValueError) as raised:
                execute_adapter(source, specification, output)
            self.assertEqual(raised.exception.problem_count, 3)
            self.assertEqual([(row["row"], row["problem"]) for row in raised.exception.problems],
                             [(1, "not a number"), (2, "missing"), (4, "not a number")])
            # Without other problems an empty cell is left to the whole-file validation.
            source.write_text("period,value\n1,1\n2,\n3,2\n", encoding="utf-8")
            self.assertEqual(execute_adapter(source, specification, output).rows, 3)

    def test_cell_problems_are_collected_and_spec_errors_still_raise_at_once(self):
        from gridform_core.data_adapters import AdapterValueError

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "data.csv"
            source.write_text("value\nbad\n2\nalso-bad\n", encoding="utf-8")
            specification = AdapterSpec(
                "cells", "1.0.0", "csv", "demand.real", "csv",
                (ColumnRule("value", "demand_mw", "GW", "MW"),),
            )
            output = Path(folder) / "out.csv"
            with self.assertRaises(AdapterValueError) as raised:
                execute_adapter(source, specification, output)
            self.assertEqual(raised.exception.problem_count, 2)
            self.assertEqual([(row["row"], row["line"], row["column"]) for row in raised.exception.problems],
                             [(1, 2, "value"), (3, 4, "value")])
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".csv.tmp").exists())
            with self.assertRaises(AdapterValueError):
                preview_csv(source, specification, limit=1)
            source.write_text("value\n1001\n", encoding="utf-8")
            kilowatts = AdapterSpec(
                "cells", "1.0.0", "csv", "demand.real", "csv",
                (ColumnRule("value", "demand_mw", "kW", "MW"),),
            )
            result = execute_adapter(source, kilowatts, output)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines()[1], "1.0010000000000001")
            execute_adapter(source, kilowatts, output, significant_digits=15)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines()[1], "1.001")
            self.assertEqual(result.rows, 1)
            with self.assertRaises(ValueError):
                execute_adapter(source, specification, output, significant_digits=0)
