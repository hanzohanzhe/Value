"""R3-3 (DECISIONS A24-4): restart costs in the model's price base.

The A22 restart costs were compiled in 2024 GBP (reference statistics 4.2).
The model's money is start-year money (A6) and every shipped study starts in
2025, the year in which the dated cost inputs are declared, so the fuel and
carbon prices the restart cost is weighed against are 2025 money.  The table
keeps the author-reviewed 2024 values and uses them restated by the ONS CPI
ratio 2025 / 2024 (correction r33.restart-cost-price-base-2025; default PSM
6.6.0 and staged PSM 1.6.0, both opt-in under Q13).
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gridform_core import network_method_rules, revision_migration
from gridform_core.builtin.scheme_c_1000twh import native_corrected
from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM
from gridform_core.builtin.scheme_c_1000twh.staged_psm import StagedBidAtCostPSM

ROOT = Path(__file__).resolve().parents[1]
CORRECTION_ID = "r33.restart-cost-price-base-2025"


def _load_with(table: dict):
    """restart_table() of an edited copy of the table (cache bypassed)."""

    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "table.json"
        path.write_text(json.dumps(table), encoding="utf-8")
        with mock.patch.object(native_corrected, "RESTART_TABLE_PATH", path):
            native_corrected.restart_table.cache_clear()
            try:
                return native_corrected.restart_table()
            finally:
                native_corrected.restart_table.cache_clear()


class PriceBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = json.loads(native_corrected.RESTART_TABLE_PATH.read_text(encoding="utf-8"))

    def test_price_base_is_2025_by_the_cpi_ratio(self) -> None:
        base = self.table["price_base"]
        self.assertEqual((base["currency"], base["from_year"], base["to_year"]), ("GBP", 2024, 2025))
        self.assertIn("D7BT", base["index"])
        self.assertEqual((base["index_from_year"], base["index_to_year"]), (133.9, 138.4))
        self.assertEqual(base["factor"], round(138.4 / 133.9, 4))
        self.assertEqual(base["factor"], 1.0336)
        self.assertIn("2025 GBP", self.table["price_basis"])

    def test_costs_in_use_are_the_a22_values_restated(self) -> None:
        expected = {
            "CCGT": ({"hot": 110.0, "warm": 130.0, "cold": 150.0}, {"hot": 113.7, "warm": 134.4, "cold": 155.0}),
            "OCGT": ({"hot": 170.0, "warm": 170.0, "cold": 170.0}, {"hot": 175.7, "warm": 175.7, "cold": 175.7}),
            "biomass": ({"hot": 125.0, "warm": 125.0, "cold": 125.0}, {"hot": 129.2, "warm": 129.2, "cold": 129.2}),
        }
        for technology, (gbp2024, gbp2025) in expected.items():
            with self.subTest(technology=technology):
                row = self.table["technologies"][technology]
                self.assertEqual(row["restart_cost_gbp2024_per_mw"], gbp2024)
                self.assertEqual(row["restart_cost_gbp_per_mw"], gbp2025)
                for key, value in gbp2024.items():
                    self.assertEqual(round(value * 138.4 / 133.9, 1), gbp2025[key])
        # Every other value of the A22 table is unchanged.
        parameters = native_corrected.restart_parameters()
        self.assertEqual({name: (p.min_stable_fraction, p.min_down_time_h) for name, p in parameters.items()},
                         {"CCGT": (0.5, 6.0), "OCGT": (0.5, 0.5), "biomass": (0.35, 6.0)})
        self.assertEqual(self.table["rule"]["start_class_by_downtime_h"], {"hot_below_h": 12.0, "warm_up_to_h": 48.0})

    def test_loader_refuses_an_inconsistent_price_base(self) -> None:
        self.assertEqual(_load_with(copy.deepcopy(self.table))["table_id"], "value-thermal-restart-v1")
        stale = copy.deepcopy(self.table)
        stale["technologies"]["OCGT"]["restart_cost_gbp_per_mw"]["hot"] = 170.0  # 2024 value left in place
        with self.assertRaisesRegex(ValueError, "OCGT"):
            _load_with(stale)
        wrong_factor = copy.deepcopy(self.table)
        wrong_factor["price_base"]["factor"] = 1.05
        with self.assertRaisesRegex(ValueError, "factor"):
            _load_with(wrong_factor)
        # A table without a declared price base is read as it stands.
        plain = copy.deepcopy(self.table)
        del plain["price_base"]
        self.assertNotIn("price_base", _load_with(plain))

    def test_base_year_is_the_declared_base_of_the_cost_inputs(self) -> None:
        catalogue = json.loads((ROOT / "gridform_core" / "data" / "storage" / "storage_technology_catalogue.json")
                               .read_text(encoding="utf-8"))
        years = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "currency_base_year":
                        years.add(value)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(catalogue)
        self.assertEqual(years, {self.table["price_base"]["to_year"]})

    def test_rule_records_carry_the_new_table(self) -> None:
        sha = native_corrected.restart_table_sha256()
        record = network_method_rules.ECONOMIC.definition()["restart_table"]
        self.assertEqual(record, {"table_id": "value-thermal-restart-v1", "sha256": sha})
        summary = native_corrected.DownwardTally().summary(0.5)
        self.assertEqual(summary["restart_table_sha256"], sha)


class MethodChangeTests(unittest.TestCase):
    """Q13: the restated costs change corrected dispatch, so both PSMs bump with opt-in."""

    def test_both_psm_versions_bump_with_opt_in(self) -> None:
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        for module_id, versions, implementation in (
            ("value-bid-at-cost-psm", ("6.5.0", "6.6.0"), SchemeCNativePSM),
            ("value-staged-bid-at-cost-psm", ("1.5.0", "1.6.0"), StagedBidAtCostPSM),
        ):
            with self.subTest(module=module_id):
                entry = ledger["modules"][module_id]
                # Later packages (R4-1) may bump again: find the R3-3 bump.
                bump = next(item for item in entry["bumps"] if item["package"] == "R3-3")
                self.assertEqual((bump["from"], bump["to"]), versions)
                self.assertEqual(bump["correction_ids"], [CORRECTION_ID])
                self.assertTrue(bump["requires_user_opt_in"])
                manifest = json.loads((ROOT / "gridform_core" / "manifests" / f"{module_id}.json")
                                      .read_text(encoding="utf-8"))
                self.assertEqual(implementation.version, entry["current_version"])
                self.assertEqual(manifest["version"], entry["current_version"])
                kind, reason = revision_migration._module_change_kind(module_id, *versions)
                self.assertEqual(kind, "method_upgrade_required")
                self.assertIn(CORRECTION_ID, reason)

    def test_table_names_its_correction(self) -> None:
        table = native_corrected.restart_table()
        self.assertIn(CORRECTION_ID, table["table_revision"])
        self.assertIn("A24-4", table["status"])
        self.assertIn("r32.network-economic-downward-order", table["applies_to"])


if __name__ == "__main__":
    unittest.main()
