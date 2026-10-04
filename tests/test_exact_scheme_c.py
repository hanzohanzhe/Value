import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.exact_run import ExactRunRequest, run_exact_scheme_c


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_scheme_c_parity", ROOT / "scripts" / "compare_scheme_c_parity.py"
)
COMPARE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(COMPARE)


class ExactSchemeCParityComparisonTests(unittest.TestCase):
    def test_read_only_reference_files_have_not_changed(self):
        expected = {
            ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh" / "compat" / "case3.py":
                "68baa3c61630e3959087ba863e1ba697ec3e3c76a4eb1384d8751de4f9e77dd8",
            ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh" / "exact_run.py":
                "cd4373cf5979a88ab45c2878ddeaf8dbd06fa846c7bfd4e2e3dc62c29e35fc50",
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_fixture_compares_equal_to_itself(self):
        fixture = json.loads((ROOT / "tests" / "fixtures" / "scheme_c_2025_2026_authoritative.json").read_text(encoding="utf-8"))
        costs = []
        capacities = []
        investments = []
        for year, row in fixture["years"].items():
            costs.append({
                "Year": float(year),
                "Total_System_Cost_GBP": row["total_system_cost_gbp"],
                "Cost_per_MWh_GBP": row["cost_per_mwh_gbp"],
                "Total_Energy_Generated_MWh": row["total_energy_generated_mwh"],
            })
            capacities.append({
                "Year": float(year),
                "Solar_Capacity_MW": row["solar_capacity_mw"],
                "Onshore_Capacity_MW": row["onshore_capacity_mw"],
                "Offshore_Capacity_MW": row["offshore_capacity_mw"],
                "0.25c_battery_Capacity_MW": row["quarter_c_battery_capacity_mw"],
            })
            for technology, key in {
                "0.25c_battery": "quarter_c_battery_suggested_addition_mw",
                "solar": "solar_suggested_addition_mw",
                "onshore": "onshore_suggested_addition_mw",
                "offshore": "offshore_suggested_addition_mw",
            }.items():
                if key in row:
                    investments.append({"year": int(year), "technology": technology, "suggested_addition_mw": row[key]})
        report = COMPARE.compare({
            "system_cost_history": costs,
            "capacity_history": capacities,
            "investment_decisions": investments,
        }, fixture)
        self.assertTrue(report["passed"])

    @unittest.skipIf(sys.version_info[:2] == (3, 10), "runtime guard only applies outside the reference interpreter")
    def test_authoritative_run_refuses_unverified_python_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "require Python 3.10"):
                run_exact_scheme_c(ExactRunRequest(
                    pack_root=root / "pack",
                    output_dir=root / "output",
                    start_year=2025,
                    end_year=2026,
                    periods=2,
                ))


if __name__ == "__main__":
    unittest.main()
