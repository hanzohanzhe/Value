import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.data_pack_validation import validate_data_pack


def binding(root: Path, name: str, content: str, *, unit=None):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    value = {
        "uri": name.replace("\\", "/"),
        "format": path.suffix.lstrip("."),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if unit:
        value["unit"] = unit
    return value


class DataPackValidationTests(unittest.TestCase):
    def test_header_is_reported_separately_from_full_year_numeric_periods(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"id": "header-clock", "bindings": {
                "demand.real": binding(
                    root, "demand.csv", "value\n1\n2\n", unit="MWh/period"
                ),
            }}
            report = validate_data_pack(
                root,
                manifest,
                [{
                    "role": "demand.real", "required": True,
                    "formats": ["csv"], "unit": "MWh/period",
                }],
                full_year_periods=2,
            )
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["warnings"], [])
        details = report["bindings"][0]["details"]
        self.assertEqual(details["csv_rows_including_optional_header"], 3)
        self.assertEqual(details["csv_data_rows"], 2)

    def test_only_the_first_row_may_be_an_optional_header(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"id": "corrupt-clock", "bindings": {
                "demand.real": binding(
                    root,
                    "demand.csv",
                    "value\n1\nnot-a-period\n2\n3\n",
                    unit="MWh/period",
                ),
            }}
            report = validate_data_pack(
                root,
                manifest,
                [{
                    "role": "demand.real", "required": True,
                    "formats": ["csv"], "unit": "MWh/period",
                }],
                full_year_periods=3,
            )
        self.assertFalse(report["valid"])
        self.assertIn("after the optional header", " ".join(report["errors"]))

    def test_vre_minimum_counts_numeric_periods_not_the_header(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"id": "short-vre", "bindings": {
                "profiles.vre_solar": binding(
                    root, "solar.csv", "profile\n0.5\n"
                ),
            }}
            report = validate_data_pack(
                root,
                manifest,
                [{
                    "role": "profiles.vre_solar", "required": True,
                    "formats": ["csv"],
                }],
                full_year_periods=4,
            )
        self.assertFalse(report["valid"])
        self.assertIn("1 numeric periods", " ".join(report["errors"]))

    def test_small_good_pack_and_clock_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"id": "small", "bindings": {
                "demand.real": binding(root, "demand.csv", "value\n1\n2\n", unit="MWh/period"),
                "costs.capital": binding(root, "costs.json", json.dumps({"capital_costs_per_mw": {"solar": 1}})),
            }}
            slots = [
                {"role": "demand.real", "required": True, "formats": ["csv"], "unit": "MWh/period"},
                {"role": "costs.capital", "required": True, "formats": ["json"], "unit": "GBP/MW"},
            ]
            report = validate_data_pack(root, manifest, slots, full_year_periods=2)
        self.assertTrue(report["valid"], report["errors"])

    def test_missing_columns_duplicate_ids_bad_units_and_truncated_clock_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"id": "bad", "bindings": {
                "demand.real": binding(root, "demand.csv", "1\n", unit="MW"),
                "projects.repd": binding(root, "projects.csv", "project_id,technology,capacity_mw,development_status,region\na,solar,1,active,GB\na,solar,2,active,GB\n"),
            }}
            slots = [
                {"role": "demand.real", "required": True, "formats": ["csv"], "unit": "MWh/period"},
                {"role": "projects.repd", "required": True, "formats": ["csv"]},
            ]
            report = validate_data_pack(root, manifest, slots, full_year_periods=2)
        self.assertFalse(report["valid"])
        joined = " ".join(report["errors"])
        self.assertIn("at least 2", joined)
        self.assertIn("does not match", joined)
        self.assertIn("duplicate project IDs", joined)

    def test_path_escape_is_rejected_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "pack"
            root.mkdir()
            manifest = {"id": "bad", "bindings": {"x": {
                "uri": "../outside.csv", "format": "csv", "sha256": "0" * 64,
            }}}
            report = validate_data_pack(root, manifest, [{"role": "x", "required": True, "formats": ["csv"]}])
        self.assertFalse(report["valid"])
        self.assertIn("escapes", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
