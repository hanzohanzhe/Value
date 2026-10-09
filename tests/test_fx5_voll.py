"""Decision A16-5: VoLL is 17,000 GBP/MWh in both methodology profiles (FX5).

* Doctoral: the thesis cost-ledger constant 8000 (``case3.py`` /
  ``modular_case3.py`` DEFICIT_VALUE_PER_MWH, the native doctoral rule set and
  the original-thesis system-cost view) becomes 17000.  VoLL enters only the
  cost accounts there, so it is a universal accounting correction
  (``fx5.voll-17000``); the retained source ``compat/`` keeps 8000.
* Corrected and every module reading ``market.voll_gbp_per_mwh``: the registry
  default and every code fallback are 17000 (was 10000).
* A saved Study's derived market configuration that still carries the old
  default 10000 without an explicit parameter is re-projected, not refused.
"""

from __future__ import annotations

import inspect
import json
import re
import unittest
from pathlib import Path

from gridform_core import voll
from gridform_core.builtin.scheme_c_1000twh.native_market_rules import (
    CORRECTED,
    DOCTORAL,
    voll_gbp_per_mwh,
)
from gridform_core.study_market_config import resolve_market_configuration

ROOT = Path(__file__).resolve().parents[1]
SCHEME_C = ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh"
MODULES = {"psm": "value-staged-bid-at-cost-psm", "balancing": "value-copperplate-balancing"}


def _deficit_value(path: Path) -> int:
    match = re.search(r"^\s*DEFICIT_VALUE_PER_MWH = (\d+)", path.read_text(encoding="utf-8"), re.M)
    assert match is not None, path
    return int(match.group(1))


class AuthorValueTests(unittest.TestCase):
    def test_one_value_everywhere(self):
        self.assertEqual(voll.VOLL_GBP_PER_MWH, 17_000.0)
        self.assertEqual(voll.CORRECTION_ID, "fx5.voll-17000")

    def test_parameter_registry_default(self):
        from gridform_core.parameters import PARAMETERS

        definition = {item.id: item for item in PARAMETERS}["market.voll_gbp_per_mwh"]
        self.assertEqual(definition.default, 17_000.0)
        self.assertEqual(definition.unit, "GBP/MWh")

    def test_code_fallbacks_follow_the_registry(self):
        from gridform_core import canonical_psm_data

        for function in (canonical_psm_data.build_chronology, canonical_psm_data.build_doctoral_psm_input):
            self.assertEqual(inspect.signature(function).parameters["voll_gbp_per_mwh"].default, 17_000.0)
        # No module keeps the old default as a literal fallback.
        pattern = re.compile(r"voll[^\n]{0,80}(10_000|10000)\b", re.I)
        offenders = []
        for path in (ROOT / "gridform_core").rglob("*.py"):
            if "compat" in path.parts or path.name == "voll.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(offenders, [])


class DoctoralAccountingTests(unittest.TestCase):
    def test_native_rule_sets(self):
        self.assertEqual(DOCTORAL.reliability_voll, "constant_17000")
        self.assertEqual(voll_gbp_per_mwh(DOCTORAL, {"market.voll_gbp_per_mwh": 5.0}), 17_000.0)
        self.assertEqual(voll_gbp_per_mwh(CORRECTED, {}), 17_000.0)
        self.assertEqual(voll_gbp_per_mwh(CORRECTED, {"market.voll_gbp_per_mwh": 5.0}), 5.0)

    def test_thesis_code_cost_history_uses_17000_and_compat_keeps_8000(self):
        for name in ("case3.py", "modular_case3.py"):
            self.assertEqual(_deficit_value(SCHEME_C / "runtime_compat" / name), 17000, name)
            self.assertEqual(_deficit_value(SCHEME_C / "compat" / name), 8000, name)

    def test_runtime_overlay_declares_the_edit(self):
        overlay = json.loads((SCHEME_C / "RUNTIME_OVERLAY.json").read_text(encoding="utf-8"))
        files = {row["path"]: row for row in overlay["runtime_files"]}
        for name in ("case3.py", "modular_case3.py"):
            self.assertEqual(files[name]["kind"], "declared_runtime_edit")
            self.assertIn("fx5.voll-17000", files[name]["correction_ids"])

    def test_original_thesis_cost_view(self):
        from gridform_core import doctoral_ledgers

        self.assertEqual(doctoral_ledgers.LEGACY_DEFICIT_VALUE_GBP_PER_MWH, 17_000.0)
        view = doctoral_ledgers.build_system_cost_views(
            legacy_capital_cost_gbp=0, legacy_operating_cost_gbp=0, deficit_mwh=2,
            existing_decarb_levy_gbp=0, additional_decarb_levy_gbp=0, cm_levy_gbp=0,
            generated_mwh=10, resource_capital_cost_gbp=0, resource_operating_cost_gbp=0,
            resource_reliability_cost_gbp=0, served_mwh=10)
        self.assertEqual(view["legacy_deficit_cost_gbp"], 34_000.0)

    def test_per_period_value_on_the_half_hour_clock(self):
        # A16-5: 17,000 GBP/MWh is 8,500 GBP per MW of unserved demand and half-hour period.
        self.assertEqual(voll.VOLL_GBP_PER_MWH * 0.5, 8_500.0)


class VersionLedgerTests(unittest.TestCase):
    def test_parameter_readers_are_method_upgrades(self):
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        expected = {
            "value-bid-at-cost-psm": "6.2.0",
            "value-perfect-foresight-lp": "1.1.0",
            "value-staged-bid-at-cost-psm": "1.4.0",
            "value-reference-dc-network": "1.2.0",
            "value-doctoral-national-psm": "0.3.0",
        }
        for module_id, version in expected.items():
            # The FX5 bump of the module (later packages may bump it again, e.g. FX6).
            bump = next(item for item in ledger["modules"][module_id]["bumps"] if item["package"] == "FX5")
            self.assertEqual((bump["to"], bump["package"]), (version, "FX5"), module_id)
            self.assertEqual(bump["correction_ids"], ["fx5.voll-17000"])
            self.assertTrue(bump["requires_user_opt_in"], module_id)


class MarketConfigurationTests(unittest.TestCase):
    def test_default_projection(self):
        result = resolve_market_configuration(MODULES, {}, {})
        self.assertEqual(result["voll_gbp_per_mwh"], 17_000.0)

    def test_stale_old_default_is_reprojected(self):
        supplied = {**MODULES_FIELDS, "voll_gbp_per_mwh": 10_000.0}
        result = resolve_market_configuration(MODULES, {}, {}, supplied)
        self.assertEqual(result["voll_gbp_per_mwh"], 17_000.0)

    def test_explicit_parameter_stays_authoritative(self):
        supplied = {**MODULES_FIELDS, "voll_gbp_per_mwh": 10_000.0}
        result = resolve_market_configuration(MODULES, {"market.voll_gbp_per_mwh": 10_000.0}, {}, supplied)
        self.assertEqual(result["voll_gbp_per_mwh"], 10_000.0)
        with self.assertRaisesRegex(ValueError, "VOLL does not match"):
            resolve_market_configuration(MODULES, {"market.voll_gbp_per_mwh": 12_000.0}, {}, supplied)

    def test_other_stale_values_are_still_refused(self):
        supplied = {**MODULES_FIELDS, "voll_gbp_per_mwh": 9_000.0}
        with self.assertRaisesRegex(ValueError, "VOLL does not match"):
            resolve_market_configuration(MODULES, {}, {}, supplied)


MODULES_FIELDS = {
    "ahead_market_module_id": MODULES["psm"],
    "balancing_module_id": MODULES["balancing"],
    "weather_spatialisation_module_id": "",
}


if __name__ == "__main__":
    unittest.main()
