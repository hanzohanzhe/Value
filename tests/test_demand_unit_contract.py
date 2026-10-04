import hashlib
import tempfile
import unittest
from pathlib import Path

from gridform_core.data_adapters import AdapterSpec, ColumnRule, execute_adapter
from gridform_core.data_pack_validation import validate_data_pack


class DemandUnitContractTests(unittest.TestCase):
    def test_energy_to_power_requires_declared_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source.write_text("energy\n60\n")
            rule = ColumnRule("energy", "value", "MWh/period", "MW")
            spec = AdapterSpec("explicit", "1", "csv", "demand.forecast", "csv", (rule,))
            with self.assertRaisesRegex(ValueError, "explicit positive interval"):
                execute_adapter(source, spec, root / "normalized.csv")

    def test_legacy_label_requires_known_content_and_explicit_contract_is_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The compatibility fixture uses exact published bytes, not a spoofed hash.
            import json
            pack = Path(__file__).resolve().parents[1] / "data-packs/value-101-baseline-v1"
            source_binding = json.loads((pack / "manifest.json").read_text())["bindings"]["demand.forecast"]
            original = (pack / source_binding["uri"]).read_bytes()
            source = root / "demand.csv"
            source.write_bytes(original)
            binding = {"uri": "demand.csv", "format": "csv", "unit": "MWh/period", "sha256": hashlib.sha256(original).hexdigest()}
            manifest = {"bindings": {"demand.forecast": binding}}
            slots = [{"role": "demand.forecast", "required": True, "formats": ["csv"], "unit": "MW"}]
            report = validate_data_pack(root, manifest, slots)
            self.assertTrue(report["valid"], report["errors"])
            self.assertIn("interpreted as raw MW", " ".join(report["warnings"]))
            self.assertEqual(source.read_bytes(), original)
            source.write_text("value\n60\n")
            binding["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertFalse(validate_data_pack(root, manifest, slots, full_year_periods=1)["valid"])
            binding.update(unit="MW", input_unit_contract="value.demand-mw-half-hour/v1", interval_minutes=30)
            self.assertTrue(validate_data_pack(root, manifest, slots, full_year_periods=1)["valid"])
            binding["interval_minutes"] = 60
            self.assertFalse(validate_data_pack(root, manifest, slots, full_year_periods=1)["valid"])
            binding.update(interval_minutes=30, input_unit_contract="unknown")
            self.assertFalse(validate_data_pack(root, manifest, slots, full_year_periods=1)["valid"])
