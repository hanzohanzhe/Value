"""Qualification of the independent raw doctoral source reference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class ReferenceHarnessTests(unittest.TestCase):
    @staticmethod
    def harness():
        # Missing interface is only a harness RED, never scientific parity evidence.
        name = "tests.doctoral_reference_harness"
        if importlib.util.find_spec(name) is None:
            raise AssertionError("independent source reference harness is not implemented")
        from tests import doctoral_reference_harness
        return doctoral_reference_harness

    def test_loader_ignores_top_level_file_writes_and_unneeded_imports(self):
        harness = self.harness()
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist.txt"
            source = (
                "import definitely_not_an_installed_plotter\n"
                f"open({str(marker)!r}, 'w').write('unsafe')\n"
                "BASE = 3\n"
                "def helper(value):\n    return value * BASE\n"
                "def calculate(value):\n    return helper(value) + 1\n"
                "calculate(99)\n"
            )
            namespace = harness._load_source(source, ["calculate"], filename="fixture.py")
            self.assertEqual(namespace["calculate"](4), 13)
            self.assertFalse(marker.exists())
            self.assertNotIn("definitely_not_an_installed_plotter", namespace)

    def test_unresolved_dependency_fails_before_reference_call(self):
        harness = self.harness()
        with self.assertRaisesRegex(ValueError, "unresolved.*missing_price"):
            harness._load_source("def calculate(x):\n    return x * missing_price\n",
                                 ["calculate"], filename="fixture.py")

    def test_global_read_is_not_hidden_by_a_later_global_write(self):
        harness = self.harness()
        source = (
            "def calculate():\n    global missing_price\n"
            "    result = missing_price\n    missing_price = 3\n    return result\n"
        )
        with self.assertRaisesRegex(ValueError, "unresolved.*missing_price"):
            harness._load_source(source, ["calculate"], filename="fixture.py")

    def test_candidate_dependency_is_rejected_not_used_as_reference(self):
        harness = self.harness()
        source = "import gridform_core.candidate as candidate\ndef calculate(x):\n    return candidate.price(x)\n"
        with self.assertRaisesRegex(ValueError, "unsafe import dependency"):
            harness._load_source(source, ["calculate"], filename="fixture.py")

    def test_environment_is_a_frozen_explicit_fixture_input(self):
        harness = self.harness()
        environment = {"PHYSICAL_PERIOD_HOURS": "0.25"}
        namespace = harness.load_reference_symbols(["physical_period_hours"], environment=environment)
        environment["PHYSICAL_PERIOD_HOURS"] = "1"
        self.assertEqual(namespace["physical_period_hours"](), 0.25)
        self.assertFalse(hasattr(namespace["os"], "system"))

    def test_unsafe_definition_time_expressions_are_rejected(self):
        harness = self.harness()
        samples = [
            "def calculate(x=open('unsafe', 'w')):\n    return x\n",
            "@print('unsafe')\ndef calculate(x):\n    return x\n",
            "class calculate:\n    print('unsafe')\n",
            "BASE = open('unsafe', 'w')\ndef calculate():\n    return BASE\n",
        ]
        for source in samples:
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "unsafe"):
                harness._load_source(source, ["calculate"], filename="fixture.py")

    def test_transitive_inheritance_and_defaults_resolve_without_candidate(self):
        harness = self.harness()
        source = (
            "DEFAULT = 4\n"
            "class Parent:\n    def __init__(self, x=DEFAULT):\n        self.x = x\n"
            "class Child(Parent):\n    def result(self):\n        return self.x * 2\n"
        )
        namespace = harness._load_source(source, ["Child"], filename="fixture.py")
        self.assertEqual(namespace["Child"]().result(), 8)
        self.assertTrue(issubclass(namespace["Child"], namespace["Parent"]))

    def test_raw_reference_income_uses_separate_generator_storage_prices(self):
        namespace = self.harness().load_reference_symbols(["GasGenerator", "Battery", "acm_income",
                                                          "acm_income_balance"])
        generator = namespace["GasGenerator"]("gas", 1, 0, 0, 20, 20, 0, 0, 0, 0, 0, 0, 0)
        battery = namespace["Battery"]("store", 100, 20, 0, 0, 1, 1, 0)
        income = namespace["acm_income"]([[generator, 50, 10, 0]], [[battery, 4]], 70)
        balance = namespace["acm_income_balance"]([[generator, 2], [battery, 3]], 60, 80)
        self.assertEqual(income, {"gas": 250, "store": 140})
        self.assertEqual(balance, {"gas": 60, "store": 120})
        self.assertIn("decarbonization_cost_research", namespace["acm_income"].__code__.co_filename)
        self.assertIs(namespace["acm_income"].__globals__["Battery"], namespace["Battery"])

    def test_raw_batch_decay_and_charge_before_export(self):
        namespace = self.harness().load_reference_symbols()
        battery = namespace["Battery"]("store", 100, 20, 0, 0, 1, 1, 0, battery_type="1c")
        battery.set_stored_energy_var(0, 100)
        namespace["decay_func"](battery.stored_energy, battery.battery_type)
        self.assertAlmostEqual(battery.stored_energy[0], 99.9979, places=8)
        battery.stored_energy.clear()
        connection = namespace["Connection"]("export", 0, 0, 0)
        connection.transfer_constraint, connection.external_price = -100, 80
        electrolyzer = namespace["Electrolyzer"]("off", 0, 0, 0.65, 0, 0, 0, 0)
        result = namespace["store_service_three"](
            [], [[battery, 0, 0, 1, 1]], 7, 0, [], 30, [], [connection], electrolyzer)
        self.assertEqual(result[1], 20)
        self.assertEqual(battery.stored_energy, {7: 20})
        self.assertEqual(connection.sold_energy, 10)
        self.assertEqual(result[4], 0)
        self.assertEqual(result[7], 0)

    def test_raw_vre_threshold_retains_200_point_boundary(self):
        namespace = self.harness().load_reference_symbols(
            ["calculate_expansion_limit"], relative_path="run_investment_analysis.py")
        with tempfile.TemporaryDirectory() as directory:
            demand = Path(directory) / "demand.csv"
            profile = Path(directory) / "profile.csv"
            demand.write_text("demand\n" + "100\n" * 199, encoding="utf-8")
            profile.write_text("1\n" * 200, encoding="utf-8")
            self.assertEqual(namespace["calculate_expansion_limit"](demand, profile), 0)
            demand.write_text("demand\n" + "100\n" * 200, encoding="utf-8")
            self.assertAlmostEqual(namespace["calculate_expansion_limit"](demand, profile),
                                   100.0, delta=1e-6)

    def test_source_content_change_is_rejected_before_ast_execution(self):
        harness = self.harness()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "simulation_model.py"
            original = b"def answer():\n    return 41\n"
            source.write_bytes(original)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": harness.SOURCE_MANIFEST_SCHEMA,
                "source_root": str(root),
                "sources": {"simulation_model.py": {"sha256": hashlib.sha256(original).hexdigest()}},
            }), encoding="utf-8")
            harness.validate_source_manifest(manifest)
            source.write_bytes(original.replace(b"41", b"42"))
            with self.assertRaisesRegex(ValueError, "source identity"):
                harness.validate_source_manifest(manifest)

    def test_fresh_load_has_no_shared_reference_state(self):
        harness = self.harness()
        first = harness.load_reference_symbols(["Battery"])
        second = harness.load_reference_symbols(["Battery"])
        self.assertIsNot(first["Battery"], second["Battery"])
        self.assertNotIn("run_simulation", first)
        with self.assertRaisesRegex(ValueError, "not qualified"):
            harness.load_reference_symbols(["run_simulation"])


if __name__ == "__main__":
    unittest.main()
