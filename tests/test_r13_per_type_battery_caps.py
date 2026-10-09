"""R1-3 (decision A20): per-type power-battery expansion caps in the corrected profile.

A20 withdrew the shared power-battery pool of P0-7 S7 (p07.power-battery-pool,
finding P5-02): each of the 0.25C, 0.5C and 1C batteries again gets its own cap
``expansion.storage_cap_fraction x power_room`` (0.2), as in the thesis design.
The P5-01 leftover headroom (p07.storage-leftover-headroom) is unchanged; the
doctoral profile keeps its 35aadb3 path (Q1).  A method change of the corrected
profile (Q13).

Toy: the 17520-period square wave of tests/test_p07_investment_corrections.py
gives power_room = 2000 MW, so each power battery cap is 400 MW.
"""
from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh import storage_headroom as sh
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import (
    SchemeCAgentInvestmentDefinition,
    power_battery_pool_in_force,
)
from gridform_core.methodology import REFERENCE_PROFILE_ID, default_profile_id, load_catalogue, resolve_methodology
from gridform_core.v2.contracts import ExpansionHeadroom, OperatingState
from tests.r71_planning_fixtures import with_planning
from tests.test_p07_investment_corrections import (
    PER_TYPE_CAPS,
    REC,
    YEAR,
    _market,
    _Policy,
    _run,
    _storage_market,
    pre_a20_corrected,
)

ROOT = Path(__file__).resolve().parents[1]
POOL = "p07.power-battery-pool"
CAP = 400.0  # 0.2 x power_room 2000 MW


class PerTypeBatteryCapTests(unittest.TestCase):
    """Trigger fixture of r13.per-type-battery-caps."""

    @classmethod
    def setUpClass(cls):
        cls.market = _storage_market(17520)

    def _headroom(self, profile_id: str) -> ExpansionHeadroom:
        return _Policy().evaluate(_run(profile_id), OperatingState(YEAR, (), ()), self.market)

    def _fleet(self, requests: dict[str, float]):
        assets, income = [], {}
        for tech, requested in requests.items():
            asset = REC._asset(f"{tech}-a", tech, 10.0, energy=10.0, investment_owner_id=f"owner-{tech}")
            assets.append(asset)
            # Storage keeps gross revenue = profit (A4), so the request is income / CAPEX per MW.
            income[asset.asset_id] = requested * float(asset.extensions["total_capex_gbp"]) / 10.0
        return with_planning(OperatingState(YEAR, tuple(assets), ())), income

    def _accepted(self, profile_id: str, requests: dict[str, float]) -> tuple[dict[str, float], object]:
        state, income = self._fleet(requests)
        headroom = _Policy().evaluate(_run(profile_id), OperatingState(YEAR, (), ()), self.market)
        decision = SchemeCAgentInvestmentDefinition().decide(
            _run(profile_id), state, _market(income, {}), (headroom,))
        return {p.technology: p.capacity_mw for p in decision.proposals}, decision

    def test_corrected_headroom_gives_each_power_battery_its_own_cap(self):
        row = self._headroom(default_profile_id())
        for tech in sh.POWER_BATTERIES:
            self.assertAlmostEqual(row.allowed_additions_mw[tech], CAP, delta=1e-6)
        self.assertNotIn("pools", row.extensions)
        self.assertFalse(row.extensions["pooled_power_batteries"])
        self.assertEqual(row.extensions["headroom_semantics"], sh.HEADROOM_SEMANTICS_PER_TYPE)
        self.assertEqual(row.extensions["power_battery_cap_rule"], sh.POWER_BATTERY_CAP_RULE_PER_TYPE)
        self.assertAlmostEqual(row.evidence["power_cap_mw_per_technology"], CAP, delta=1e-6)
        self.assertNotIn("power_pool_cap_mw", row.evidence)
        # The P5-01 leftover headroom itself is unchanged (power_room = 2000 MW).
        self.assertAlmostEqual(row.evidence["power_room_mw"], 2000.0, delta=1e-6)
        with pre_a20_corrected():
            pooled = self._headroom(default_profile_id())
        self.assertEqual(pooled.allowed_additions_mw, row.allowed_additions_mw)
        self.assertAlmostEqual(pooled.extensions["pools"][sh.POWER_BATTERY_POOL]["cap_mw"], CAP, delta=1e-6)
        self.assertEqual(pooled.extensions["headroom_semantics"], sh.HEADROOM_SEMANTICS)

    def test_requests_within_each_cap_are_accepted_in_full(self):
        # 300 + 200 + 100 = 600 MW: above the withdrawn 400 MW pool, within each 400 MW cap.
        requests = {"1c_battery": 300.0, "0.5c_battery": 200.0, "0.25c_battery": 100.0}
        accepted, decision = self._accepted(default_profile_id(), requests)
        for tech, value in requests.items():
            self.assertAlmostEqual(accepted[tech], value, delta=1e-9)
        self.assertAlmostEqual(math.fsum(accepted.values()), 600.0, delta=1e-9)
        self.assertNotIn("power_battery_pool", decision.extensions)
        with pre_a20_corrected():
            pooled, record = self._accepted(default_profile_id(), requests)
        self.assertAlmostEqual(pooled["1c_battery"], 200.0, delta=1e-9)
        self.assertAlmostEqual(pooled["0.5c_battery"], 400.0 / 3.0, delta=1e-9)
        self.assertAlmostEqual(pooled["0.25c_battery"], 200.0 / 3.0, delta=1e-9)
        self.assertIn("power_battery_pool", record.extensions)

    def test_each_type_is_capped_separately(self):
        requests = {"1c_battery": 500.0, "0.5c_battery": 450.0, "0.25c_battery": 100.0}
        accepted, decision = self._accepted(default_profile_id(), requests)
        self.assertAlmostEqual(accepted["1c_battery"], CAP, delta=1e-6)
        self.assertAlmostEqual(accepted["0.5c_battery"], CAP, delta=1e-6)
        self.assertAlmostEqual(accepted["0.25c_battery"], 100.0, delta=1e-9)
        remaining = decision.extensions["remaining_headroom_mw_by_technology"]
        self.assertAlmostEqual(remaining["1c_battery"], 0.0, delta=1e-6)
        self.assertAlmostEqual(remaining["0.25c_battery"], CAP - 100.0, delta=1e-6)
        # Together at most three caps (the thesis design), never more.
        self.assertLessEqual(math.fsum(accepted.values()), 3 * CAP + 1e-6)

    def test_corrected_run_refuses_a_pooled_row(self):
        state, income = self._fleet({"1c_battery": 300.0})
        row = ExpansionHeadroom("h", YEAR, "value-storage-expansion-policy", {tech: CAP for tech in sh.POWER_BATTERIES},
                                extensions={"headroom_semantics": sh.HEADROOM_SEMANTICS, "pools": {
                                    sh.POWER_BATTERY_POOL: {"cap_mw": CAP, "technologies": list(sh.POWER_BATTERIES)}}})
        with self.assertRaisesRegex(ValueError, "shared pools"):
            SchemeCAgentInvestmentDefinition().decide(_run(default_profile_id()), state, _market(income, {}), (row,))

    def test_doctoral_profile_is_unchanged(self):
        doctoral = resolve_methodology(REFERENCE_PROFILE_ID)
        self.assertFalse(doctoral.enabled(PER_TYPE_CAPS))
        self.assertFalse(doctoral.enabled(POOL))
        self.assertFalse(power_battery_pool_in_force(doctoral))
        row = self._headroom(REFERENCE_PROFILE_ID)
        self.assertTrue(all(value == 0.0 for value in row.allowed_additions_mw.values()))
        self.assertNotIn("pools", row.extensions)


class MethodChangeTests(unittest.TestCase):
    """Catalogue, VERSION_LEDGER and Q13 for the A20 revert."""

    def test_catalogue_switches(self):
        catalogue = load_catalogue()
        correction = catalogue.corrections[PER_TYPE_CAPS]
        self.assertTrue(correction.gated)
        self.assertEqual(correction.affects, ("trajectory",))
        self.assertIsNone(correction.advisory)
        # The withdrawn pool stays in the catalogue for the identity of P0-7..R1-2 Runs, without an advisory.
        self.assertIn(POOL, catalogue.corrections)
        self.assertIsNone(catalogue.corrections[POOL].advisory)
        corrected = resolve_methodology(default_profile_id())
        self.assertTrue(corrected.enabled(PER_TYPE_CAPS))
        self.assertTrue(corrected.enabled(POOL))
        self.assertFalse(power_battery_pool_in_force(corrected))
        self.assertTrue(corrected.enabled("p07.storage-leftover-headroom"))
        with pre_a20_corrected() as pooled:
            self.assertTrue(power_battery_pool_in_force(pooled))

    def test_version_ledger_bump_requires_opt_in(self):
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        module = ledger["modules"]["value-storage-expansion-policy"]
        bumps = [bump for bump in module["bumps"] if PER_TYPE_CAPS in bump["correction_ids"]]
        self.assertEqual(len(bumps), 1)
        self.assertEqual((bumps[0]["from"], bumps[0]["to"], bumps[0]["package"]), ("5.0.0", "5.1.0", "R1-3"))
        self.assertTrue(bumps[0]["requires_user_opt_in"])
        self.assertEqual(module["current_version"], "5.1.0")
        manifest = json.loads((ROOT / "gridform_core" / "manifests" / "value-storage-expansion-policy.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "5.1.0")
        self.assertEqual(_Policy.version, "5.1.0")

    def test_saved_corrected_study_needs_confirmation(self):
        from gridform_core import revision_migration
        from gridform_core.methodology import PROFILE_PARAMETER, resolve_project_methodology

        project = {"modules": {"storage_cap": "value-storage-expansion-policy"},
                   "parameters": {PROFILE_PARAMETER: default_profile_id()}}
        resolved = resolve_project_methodology(project)
        self.assertIn(PER_TYPE_CAPS, resolved.applied_correction_ids)
        before = [item for item in resolved.applied_correction_ids if item != PER_TYPE_CAPS]
        records = [item for item in resolved.applied_correction_records() if item["id"] != PER_TYPE_CAPS]
        row = revision_migration._applied_corrections_row(
            {"applied_correction_ids": before, "applied_corrections": records}, project)
        self.assertEqual(row["classification"], "method_upgrade_required")
        self.assertIn(PER_TYPE_CAPS, row["numeric_correction_ids"])


if __name__ == "__main__":
    unittest.main()
