from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core.carbon_factors import CarbonFactorDatabase
from scripts.build_carbon_factor_database import DATA_DIRECTORY, build_database


class CarbonFactorDatabaseTests(unittest.TestCase):
    def build_temporary_database(self, directory: str) -> Path:
        return build_database(Path(directory) / "carbon.sqlite")

    def test_seed_csv_files_are_rectangular(self) -> None:
        for name in ("datasets.csv", "sources.csv", "factor_catalog.csv", "methodology_rules.csv"):
            with (DATA_DIRECTORY / name).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertTrue(rows)
            self.assertTrue(all(len(row) == len(rows[0]) for row in rows), name)

    def test_database_builds_and_passes_integrity_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = self.build_temporary_database(directory)
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(connection.execute("SELECT count(*) FROM datasets").fetchone()[0], 5)
                self.assertGreaterEqual(connection.execute("SELECT count(*) FROM factors").fetchone()[0], 90)
                self.assertEqual(connection.execute("SELECT count(*) FROM methodology_rules").fetchone()[0], 8)
            finally:
                connection.close()

    def test_scheme_c_snapshot_and_neso_rows_remain_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = CarbonFactorDatabase(self.build_temporary_database(directory))
            legacy = database.get_unique(
                dataset_id="scheme_c_2026_07_18",
                technology="ccgt",
                factor_kind="direct_operational_intensity",
            )
            authority = database.get_unique(
                dataset_id="uk_authority_reference_2026_08_06",
                technology="ccgt",
                factor_kind="direct_operational_intensity",
            )
            self.assertEqual(legacy.value, 394)
            self.assertEqual(authority.value, 394)
            self.assertEqual(legacy.source_id, "local_scheme_c_config")
            self.assertEqual(authority.source_id, "neso_ci_2024")

    def test_authoritative_solar_requires_an_explicit_variant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = CarbonFactorDatabase(self.build_temporary_database(directory))
            with self.assertRaisesRegex(LookupError, "Specify the scientific variant"):
                database.get_unique(
                    dataset_id="uk_authority_reference_2026_08_06",
                    technology="solar",
                    factor_kind="lifecycle_intensity",
                )
            poly = database.get_unique(
                dataset_id="uk_authority_reference_2026_08_06",
                technology="solar",
                factor_kind="lifecycle_intensity",
                variant="UNECE_polySi_ground",
            )
            self.assertEqual((poly.value, poly.unit), (37, "gCO2e_per_kWh"))

    def test_transmission_references_are_inactive_project_proxies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.build_temporary_database(directory)
            connection = sqlite3.connect(path)
            try:
                rows = connection.execute(
                    "SELECT status, used_by_snapshot FROM factors WHERE dataset_id = ?",
                    ("uk_transmission_reference_2026_08_06",),
                ).fetchall()
            finally:
                connection.close()
            self.assertTrue(rows)
            self.assertTrue(all(status == "reference_only" and active == 0 for status, active in rows))

    def test_original_snapshot_fingerprints_are_recorded(self) -> None:
        manifest = json.loads((DATA_DIRECTORY / "snapshot_manifest.json").read_text(encoding="utf-8"))
        artifacts = {item["artifact_id"]: item for item in manifest["source_artifacts"]}
        self.assertEqual(
            artifacts["scheme_c_config"]["sha256"],
            hashlib.sha256(
                Path("gridform_core/builtin/scheme_c_1000twh/compat/config.py").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(
            artifacts["paper_factor_csv"]["sha256"],
            "0d8c576f354a868d65892870a66b629d64f39b329bf242b9360682f42d9d3996",
        )

    def test_ambiguous_legacy_storage_units_are_not_relabelled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = CarbonFactorDatabase(self.build_temporary_database(directory))
            row = database.get_unique(
                dataset_id="scheme_c_2026_07_18",
                technology="pumped_hydro",
                factor_kind="legacy_body_emission_scalar",
            )
            self.assertEqual(row.value, 40)
            self.assertEqual(row.unit, "legacy_model_scalar")
            self.assertEqual(row.status, "unresolved_unit")


if __name__ == "__main__":
    unittest.main()
