"""P0-6 S1: default-PSM reproduction goldens captured at HEAD.

* the frozen 35aadb3 loop copy is verified against pinned source hashes;
* the 96-period synthetic golden is reproduced exactly by the live market
  functions through that loop (both storage-cost variants);
* the VALUE 101 48-period market.sqlite baseline is reproduced by a fresh run.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import native_reproduction_harness as harness

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SITUATIONS = (
    "curtailment_branch",
    "balancing_branch",
    "nuclear_blocking_vre_unrecorded",
    "nuclear_surplus",
    "nuclear_surplus_in_balancing",
    "export_consumes_surplus",
    "forecast_above_ahead_supply",
    "hidden_shortage_in_curtailment_branch",
    "p3_01_toy_f120_r28",
    "balancing_deficit",
    "storage_charge",
    "storage_discharge",
    "balancing_storage_discharge",
    "storage_fee_carry_into_curtailment",
    "thermal_down_regulation",
    "imports",
    "electrolysis",
    "vre_skim_leak",
    "compatibility_adjustment",
)


def _capture_module():
    spec = importlib.util.spec_from_file_location(
        "capture_native_reproduction_golden", ROOT / "scripts" / "capture_native_reproduction_golden.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git_head_source() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "show", f"{harness.HEAD_COMMIT}:{harness.KERNEL_RELPATH}"],
            cwd=ROOT, capture_output=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.decode("utf-8")


class HeadSourceIdentityTests(unittest.TestCase):
    def test_copy_segments_have_the_pinned_35aadb3_hashes(self):
        record = harness.verify_head_copy()
        self.assertEqual(record["kernel_sha256"], harness.HEAD_KERNEL_SHA256)
        self.assertEqual(sorted(record["segments"]), ["A", "C", "E"])
        golden = harness.load_golden()
        self.assertEqual(golden["source"]["copy_sha256"], record["copy_sha256"])
        self.assertEqual(golden["source"]["segments"], record["segments"])

    def test_copy_is_the_rendering_of_the_pinned_source(self):
        candidates = []
        if harness.live_kernel_is_head():
            candidates.append(harness.kernel_path().read_text(encoding="utf-8"))
        git_source = _git_head_source()
        if git_source is not None:
            candidates.append(git_source)
        if not candidates:
            self.skipTest("neither the live kernel nor git provides the 35aadb3 source")
        for source in candidates:
            self.assertEqual(harness.render_head_copy(source), harness.HEAD_COPY_PATH.read_text(encoding="utf-8"))

    def test_live_kernel_still_contains_the_copied_lines_while_unchanged(self):
        if not harness.live_kernel_is_head():
            self.skipTest("kernel has diverged from 35aadb3 (P0-6 S2+); the synthetic golden is the oracle")
        source = harness.kernel_path().read_text(encoding="utf-8")
        copied = harness.copied_segments(harness.HEAD_COPY_PATH.read_text(encoding="utf-8"))
        for name, first, last, _ in harness.HEAD_SEGMENTS:
            self.assertEqual(copied[name], harness.segment_text(source, first, last), name)

    def test_edited_copy_or_source_is_rejected(self):
        text = harness.HEAD_COPY_PATH.read_text(encoding="utf-8")
        tampered = text.replace("total_storage_fee_balance = 0", "total_storage_fee_balance = 0.0", 1)
        self.assertNotEqual(text, tampered)
        with self.assertRaisesRegex(ValueError, "segment A"):
            harness.verify_head_copy(tampered)
        with self.assertRaisesRegex(ValueError, "segments"):
            harness.verify_head_copy(text.replace("# >>> VERBATIM C", "# >>> VERBATIM X", 1))
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            harness.render_head_copy("def run_simulation():\n    pass\n")


class SyntheticGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = harness.load_golden()
        cls.observed = harness.observe()

    def test_scenario_inputs_are_frozen(self):
        scenario = harness.build_scenario()
        self.assertEqual(scenario, self.golden["scenario"])
        self.assertEqual(harness.sha256_text(json.dumps(scenario, sort_keys=True)), self.golden["scenario_sha256"])
        self.assertEqual(scenario["periods"], 96)
        self.assertEqual(self.golden["loop_environment"], harness.LOOP_ENVIRONMENT)

    def test_live_market_functions_reproduce_the_golden_exactly(self):
        differences = harness.compare_with_golden(self.golden, self.observed)
        self.assertEqual(
            [], [item.describe() for item in differences[:30]],
            "the default PSM no longer reproduces the 35aadb3 synthetic golden",
        )
        self.assertEqual(sorted(self.observed), sorted(harness.VARIANTS))

    def test_scenario_exercises_every_situation_named_by_the_plan(self):
        latest = harness.latest_columns(self.golden)
        for variant in harness.VARIANTS:
            facts = harness.coverage_facts(latest[variant], self.golden["scenario"])
            missing = [name for name in REQUIRED_SITUATIONS if not facts[name]]
            self.assertEqual([], missing, variant)
            self.assertTrue(set(facts["p3_01_toy_f120_r28"]) & set(facts["hidden_shortage_in_curtailment_branch"]))

    def test_head_semantics_are_pinned_in_the_golden(self):
        latest = harness.latest_columns(self.golden)["dynamic"]
        summary = "market/market.sqlite::period_summary."
        facts = harness.coverage_facts(latest, self.golden["scenario"])
        # P3-01: the curtailment branch reports no blackout although the ahead
        # stage could not meet the forecast (HEAD 2765).
        for period in facts["hidden_shortage_in_curtailment_branch"]:
            self.assertEqual(latest[summary + "blackout_mwh"][period], 0.0)
        # HEAD 1463: VRE squeezed out by nuclear is neither dispatched nor curtailed.
        for period in facts["nuclear_blocking_vre_unrecorded"]:
            self.assertEqual(latest[summary + "vre_accepted_mwh"][period], 0.0)
            self.assertEqual(latest[summary + "curtailed_mwh"][period], 0.0)
        # HEAD 2815: a curtailment period still carries the last balancing storage fee.
        carry = facts["storage_fee_carry_into_curtailment"]
        self.assertTrue(any(latest["kernel/run_simulation::storage_fees"][p] > 0 for p in carry))

    def test_fixture_is_small_and_one_column_per_line(self):
        size = harness.GOLDEN_PATH.stat().st_size
        self.assertLess(size, 300 * 1024)
        self.assertEqual(harness.GOLDEN_PATH.read_text(encoding="utf-8"), harness.dump_golden(self.golden))

    def test_zones_are_pinned_and_q12_columns_are_trajectory(self):
        zones = harness.pinned_zones(self.golden)
        summary = "market/market.sqlite::period_summary."
        for column in ("accepted_supply_mwh", "vre_accepted_mwh", "curtailed_mwh", "excess_mwh",
                       "blackout_mwh", "clearing_price_gbp_per_mwh", "storage_charge_mwh"):
            self.assertEqual(zones[summary + column], "trajectory", column)
        for column in ("energy_balance_residual_mwh", "compatibility_adjustment_mwh",
                       "raw_energy_balance_residual_mwh", "physical_resource_cost_gbp"):
            self.assertEqual(zones[summary + column], "accounting", column)
        self.assertEqual(zones["kernel/run_simulation::storage_fees"], "accounting")
        self.assertEqual(zones["kernel/dispatch::<NuclearGenerator:Nuclear>"], "trajectory")
        self.assertEqual(zones["market/market.sqlite::storage_state.li_battery.state_of_charge_mwh"], "trajectory")
        strength = {"identity": 0, "accounting": 1, "trajectory": 2}
        for key, zone in zones.items():
            self.assertGreaterEqual(strength[harness.zone_of(key)], strength[zone], key)

    def test_revision_accepts_accounting_and_refuses_trajectory_changes(self):
        golden = copy.deepcopy(self.golden)
        observed = copy.deepcopy(self.observed)
        residual = "market/market.sqlite::period_summary.raw_energy_balance_residual_mwh"
        observed["dynamic"][residual][0] = 123.0
        observed["dynamic"]["kernel/run_simulation::shortfall_mwh"] = [0.0] * 96
        with self.assertRaisesRegex(ValueError, "correction id"):
            harness.append_revision(golden, observed, reason="x", correction_ids=["Bad Id"], base_commit="t")
        revised = harness.append_revision(
            golden, observed, reason="accounting fix", correction_ids=["p04.surplus-node-boundary"], base_commit="t",
        )
        self.assertEqual(len(revised["revisions"]), 2)
        self.assertEqual(revised["revisions"][1]["zones"], {"kernel/run_simulation::shortfall_mwh": "accounting"})
        self.assertEqual([], harness.compare_with_golden(revised, observed))
        self.assertEqual(golden["cases"], revised["cases"])  # revision 0 is never rewritten
        trajectory = copy.deepcopy(self.observed)
        trajectory["legacy_tariff"]["market/market.sqlite::period_summary.accepted_supply_mwh"][5] += 1.0
        with self.assertRaisesRegex(ValueError, "frozen"):
            harness.append_revision(golden, trajectory, reason="x", correction_ids=["p06.x"], base_commit="t")


class GoldenSensitivityTests(unittest.TestCase):
    def test_a_one_ulp_bid_perturbation_is_detected_in_the_trajectory_zone(self):
        from unittest import mock

        kernel = harness.kernel_module()
        original = kernel.ahead_market_bidding

        def perturbed(*arguments, **keywords):
            arguments = list(arguments)
            arguments[9] = arguments[9] * (1.0 + 2.0 ** -52)  # bidding_factor
            return original(*arguments, **keywords)

        with mock.patch.object(kernel, "ahead_market_bidding", perturbed):
            observed = harness.observe(["dynamic"])
        golden = harness.load_golden()
        golden["cases"] = {"dynamic": golden["cases"]["dynamic"]}
        differences = harness.compare_with_golden(golden, observed)
        self.assertTrue(any(item.zone == "trajectory" for item in differences))
        self.assertIn("kernel/run_simulation::avg_electricity_prices", {item.key for item in differences})


class HarnessIsolationTests(unittest.TestCase):
    def test_run_leaves_source_tree_and_process_state_untouched(self):
        from gridform_core import market_ledger
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat import config, module_context

        environment = {key: os.environ.get(key) for key in harness.LOOP_ENVIRONMENT}
        bidding = config.simulation_parameters.get("bidding_factor")
        runtime = module_context._runtime
        ledger = market_ledger._ACTIVE_LEDGER
        capture = _capture_module()
        before = harness.tree_sha256(ROOT / "gridform_core")
        status_before = capture.worktree_status_sha256()
        first = harness.columns_from_run(harness.run_case("legacy_tariff"))
        second = harness.columns_from_run(harness.run_case("legacy_tariff"))
        self.assertEqual(before, harness.tree_sha256(ROOT / "gridform_core"))
        self.assertEqual(status_before, capture.worktree_status_sha256())
        self.assertEqual([], harness.compare_columns("legacy_tariff", first, second, {}))
        self.assertEqual(environment, {key: os.environ.get(key) for key in harness.LOOP_ENVIRONMENT})
        self.assertEqual(bidding, config.simulation_parameters.get("bidding_factor"))
        self.assertIs(runtime, module_context._runtime)
        self.assertIs(ledger, market_ledger._ACTIVE_LEDGER)

    def test_runtime_attributes_reach_the_module_runtime_and_are_restored(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat import module_context

        seen = []
        kernel = harness.kernel_module()
        original = kernel.ahead_market_bidding

        def spy(*arguments, **keywords):
            seen.append(getattr(module_context._runtime, "market_rules", None))
            return original(*arguments, **keywords)

        marker = object()
        runtime = module_context._runtime
        from unittest import mock

        with mock.patch.object(kernel, "ahead_market_bidding", spy):
            harness.run_case("dynamic", runtime_attributes={"market_rules": marker})
        self.assertEqual(len(seen), harness.PERIODS)
        self.assertTrue(all(item is marker for item in seen))
        self.assertIs(runtime, module_context._runtime)


class Value101BaselineTests(unittest.TestCase):
    def test_fresh_48_period_runs_match_the_head_baseline(self):
        capture = _capture_module()
        baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(sorted(baseline["cases"]), ["C3", "D3"])
        with tempfile.TemporaryDirectory(prefix="p06-e2e-test-") as temporary:
            for case, expected in baseline["cases"].items():
                self.assertEqual(expected["tables"]["period_summary"]["rows"], 48)
                actual = capture.run_e2e_case(case, Path(temporary))
                gated = [
                    f"[{zone}] {key}: {left!r} -> {right!r}"
                    for zone, key, left, right in capture.e2e_differences(expected, actual)
                    if zone != "identity"
                ]
                self.assertEqual([], gated[:20], f"{case}: value_101_day market.sqlite differs from the HEAD baseline")


if __name__ == "__main__":
    unittest.main()
