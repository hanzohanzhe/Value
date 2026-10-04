"""P0-6 S1: default-PSM reproduction goldens captured at HEAD.

* the frozen 35aadb3 loop copy is verified against pinned source hashes;
* the 96-period synthetic golden is reproduced exactly by the live market
  functions through that loop (both storage-cost variants);
* the VALUE 101 48-period market.sqlite baseline is reproduced by a fresh run.
"""

from __future__ import annotations

import copy
import dataclasses
import fnmatch
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from gridform_core import market_ledger
from gridform_validation.golden import ZONE_STRENGTH, ZoneRules
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
    "storage_discharge_above_rated_power",
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


def _head_sources() -> list[str]:
    sources = []
    if harness.live_kernel_is_head():
        sources.append(harness.kernel_path().read_text(encoding="utf-8"))
    git_source = _git_head_source()
    if git_source is not None:
        sources.append(git_source)
    return sources


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
        candidates = _head_sources()
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

    def test_text_outside_the_verbatim_blocks_is_checked(self):
        text = harness.HEAD_COPY_PATH.read_text(encoding="utf-8")
        line = "    _p06_driver = __p06_synthetic_driver__\n"
        self.assertIn(line, text)
        for tampered in (
            text.replace(line, line + "    bidding_factor = 1.5\n", 1),
            text.replace("# Do not edit.", "# Edit freely.", 1),
            text + "\nbidding_factor = 1.5\n",
        ):
            self.assertNotEqual(text, tampered)
            with self.assertRaisesRegex(ValueError, "outside VERBATIM|sha256"):
                harness.verify_head_copy(tampered)

    def test_live_loop_renders_the_frozen_copy_from_the_head_source(self):
        candidates = _head_sources()
        if not candidates:
            self.skipTest("neither the live kernel nor git provides the 35aadb3 source")
        copy_text = harness.HEAD_COPY_PATH.read_text(encoding="utf-8")
        for source in candidates:
            ranges = harness.live_loop_ranges(source)
            self.assertEqual(ranges, {name: (first, last) for name, first, last, _ in harness.HEAD_SEGMENTS})
            self.assertEqual(harness.render_live_loop(source, label=harness.HEAD_COMMIT, header=harness.HEADER), copy_text)
        with self.assertRaises(LookupError):
            harness.live_loop_ranges("def run_simulation(periods):\n    return ()\n")


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
        gated = harness.gated_zones(self.golden, "frozen")
        differences = [
            item for item in harness.compare_with_golden(self.golden, self.observed) if item.zone in gated
        ]
        self.assertEqual(
            [], [item.describe() for item in differences[:30]],
            "the default PSM no longer reproduces the 35aadb3 synthetic golden (frozen loop)",
        )
        self.assertEqual(sorted(self.observed), sorted(harness.VARIANTS))

    def test_live_kernel_loop_reproduces_the_golden_exactly(self):
        # P0-6 S3 acceptance ('synthetic golden equal value by value') runs
        # through this loop.  If S3 moves the period body out of run_simulation
        # the anchors fail here: update LIVE_ANCHORS or pass a callable loop=.
        live = harness.observe(loop="live")
        gated = harness.gated_zones(self.golden, "live")
        differences = [item for item in harness.compare_with_golden(self.golden, live) if item.zone in gated]
        self.assertEqual(
            [], [item.describe() for item in differences[:30]],
            "the live kernel loop no longer reproduces the synthetic golden",
        )
        if harness.live_kernel_is_head():
            self.assertEqual([], harness.compare_with_golden(self.golden, live))

    def test_frozen_loop_accounting_is_gated_only_until_an_accounting_revision(self):
        self.assertEqual(harness.gated_zones(self.golden, "live"), ("trajectory", "accounting"))
        revised = copy.deepcopy(self.golden)
        self.assertEqual(len(revised["revisions"]), 1)
        self.assertEqual(harness.gated_zones(revised, "frozen"), ("trajectory", "accounting"))
        revised["revisions"].append({"index": 1, "correction_ids": ["p04.storage-charge-audit"], "patch": {}})
        self.assertEqual(harness.gated_zones(revised, "frozen"), ("trajectory",))
        self.assertEqual(harness.gated_zones(revised, "live"), ("trajectory", "accounting"))

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
        # HEAD 2815: a curtailment period whose ahead stage accepted no
        # storage still books the last balancing period's storage fee.
        ahead_storage = dict(zip(latest["kernel/declared::ahead.periods"], latest["kernel/declared::ahead.storage_accepted_mw"]))
        carry = facts["storage_fee_carry_into_curtailment"]
        self.assertTrue(set(range(41, 52, 2)) <= set(carry), carry)
        for period in carry:
            self.assertEqual(ahead_storage[period], 0.0)
            self.assertGreater(latest["kernel/run_simulation::storage_fees"][period], 0.0)
        # HEAD 1173 (P3-08): the skim zeroes a VRE whose availability is below
        # the skim, and that availability is booked nowhere.
        self.assertEqual(facts["vre_skim_leak"], [72, 73, 77])
        self.assertEqual(latest["kernel/state::offshore1.real_energy"][72], 0.0)
        self.assertEqual(latest["kernel/dispatch::<ExpensiverenewableGenerator:offshore1>"][72], 0.0)
        # P5-03: per-stage power reset; pumped hydro (15 MW) discharges 30 MW,
        # li_battery (20 MW) 28 MW.
        state = "market/market.sqlite::storage_state."
        for period in (40, 42, 44, 46):
            self.assertIn(period, facts["storage_discharge_above_rated_power"])
            self.assertEqual(latest[state + "pumpedhydro_battery.discharge_mwh"][period] / harness.PERIOD_HOURS, 30.0)
            self.assertEqual(latest[state + "pumpedhydro_battery.power_capacity_mw"][period], 15.0)
        self.assertEqual(latest[state + "li_battery.discharge_mwh"][90] / harness.PERIOD_HOURS, 28.0)
        self.assertEqual(latest[state + "li_battery.power_capacity_mw"][90], 20.0)

    def test_fixture_is_small_and_one_column_per_line(self):
        # Plan 4.6 S1 acceptance (< 300 KB) applies to the capture: scenario,
        # cases and revision 0.  Appended revisions have their own budget.
        self.assertLess(harness.revision_zero_bytes(self.golden), harness.REVISION_ZERO_BUDGET_BYTES)
        for revision in self.golden["revisions"][1:]:
            self.assertLessEqual(harness.revision_bytes(revision), harness.APPENDED_REVISION_BUDGET_BYTES)
        self.assertEqual(harness.GOLDEN_PATH.read_text(encoding="utf-8"), harness.dump_golden(self.golden))

    def test_revision_patches_are_dumped_one_column_per_line(self):
        observed = copy.deepcopy(self.observed)
        accounting = [key for key, zone in harness.pinned_zones(self.golden).items()
                      if zone == "accounting" and isinstance(observed["dynamic"][key], list)]
        self.assertGreater(len(accounting), 10)
        for variant in harness.VARIANTS:
            for key in accounting:
                values = observed[variant][key]
                observed[variant][key] = [value + 1.0 if isinstance(value, float) else value for value in values]
        revised = harness.append_revision(
            copy.deepcopy(self.golden), observed, reason="every accounting column", correction_ids=["p04.toy"],
            base_commit="t",
        )
        revision = revised["revisions"][1]
        self.assertLessEqual(harness.revision_bytes(revision), harness.APPENDED_REVISION_BUDGET_BYTES)
        text = harness.dump_golden(revised)
        self.assertEqual(json.loads(text), revised)
        self.assertEqual(harness.dump_golden(json.loads(text)), text)
        lines = text.splitlines()
        patch_start = lines.index('   "patch": {')
        patched = [key for columns in revision["patch"].values() for key in columns]
        self.assertGreater(len(patched), 40)  # numeric accounting columns of both variants
        for key in set(patched):
            matching = [line for line in lines[patch_start:] if line.startswith(f"     {json.dumps(key)}: ")]
            self.assertEqual(patched.count(key), len(matching), key)
        revision_start = lines.index("  {", lines.index(' "revisions": ['))
        self.assertTrue(all(len(line) < 4096 for line in lines[revision_start:patch_start]),
                        "revision metadata and delta stay one short entry per line")
        self.assertEqual(harness.revision_zero_bytes(revised), harness.revision_zero_bytes(self.golden))

    def test_an_oversized_revision_is_refused(self):
        observed = copy.deepcopy(self.observed)
        observed["dynamic"]["kernel/run_simulation::shortfall_mwh"] = [0.123456789] * 20000
        with self.assertRaisesRegex(ValueError, "appended-revision budget"):
            harness.append_revision(copy.deepcopy(self.golden), observed, reason="x", correction_ids=["a2.stress"],
                                    base_commit="t")

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
        # P3-14 / decision (d): the per-asset charge audit column (HEAD literal
        # 0.0) is accounting; discharge stays trajectory.
        for asset in ("li_battery", "pumpedhydro_battery", "thermal_battery"):
            self.assertEqual(zones[f"market/market.sqlite::storage_state.{asset}.charge_mwh"], "accounting", asset)
            self.assertEqual(zones[f"market/market.sqlite::storage_state.{asset}.discharge_mwh"], "trajectory", asset)
        # The real table column is zoned by zones.json alone (trajectory, as
        # in the X0 goldens) until the lead decides the X0 P3-14 question.
        self.assertEqual(harness.zone_of("market/market.sqlite::storage_state.charge_mwh"), "trajectory")
        self.assertEqual(harness.zone_of("market/market.sqlite::storage_state.discharge_mwh"), "trajectory")
        # Orders: bid/acceptance fields trajectory, cost/settlement accounting (P5-06).
        self.assertEqual(zones["market/market.sqlite::orders.trajectory_row_sha"], "trajectory")
        self.assertEqual(zones["market/market.sqlite::orders.accounting_row_sha"], "accounting")
        self.assertNotIn("market/market.sqlite::orders.row_sha", zones)
        self.assertEqual(
            set(harness.ORDER_TRAJECTORY_FIELDS) | set(harness.ORDER_ACCOUNTING_FIELDS),
            {field.name for field in dataclasses.fields(market_ledger.OrderLedgerRow)},
        )
        self.assertEqual(zones["kernel/storage_cost_report"], "accounting")
        for key, zone in zones.items():
            self.assertGreaterEqual(ZONE_STRENGTH[harness.zone_of(key)], ZONE_STRENGTH[zone], key)

    def test_local_rules_never_override_zones_json_for_real_columns(self):
        """zones.json is the single zone authority (P0_CONVENTIONS 2): the
        harness-local rules only match keys that exist only in this harness."""

        rules = ZoneRules.load(harness.ZONES_PATH)
        self.assertEqual(rules, harness._zones_json())
        real_keys = set(json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))["zones"])
        for relative in ("doctoral/D3.json", "corrected/C3.json"):
            golden = json.loads((ROOT / "tests" / "golden" / relative).read_text(encoding="utf-8"))
            real_keys |= set(golden["revisions"][-1]["digest"]["columns"])
        self.assertIn("market/market.sqlite::storage_state.charge_mwh", real_keys)
        self.assertIn("market/market.sqlite::clearing_outcomes.outcome_json", real_keys)
        for pattern, _, _ in harness.LOCAL_ZONE_RULES:
            matched = sorted(key for key in real_keys if fnmatch.fnmatchcase(key, pattern))
            self.assertEqual([], matched[:5], pattern)
        for key in real_keys:
            self.assertEqual(harness.zone_of(key), rules.zone(key), key)
        # Declared clearing inputs/outcomes: trajectory like their tables
        # (the derived unserved target falls under the A2 '*unserved*' rule).
        self.assertEqual(harness.zone_of("kernel/declared::ahead.storage_accepted_mw"), "trajectory")
        self.assertEqual(harness.zone_of("kernel/declared::ahead.input_payload_sha"), "trajectory")
        self.assertEqual(harness.zone_of("kernel/declared::ahead.unserved_target_mw"), "accounting")

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
        with self.assertRaisesRegex(ValueError, "live loop"):
            harness.append_revision(golden, observed, reason="x", correction_ids=["p06.x"], base_commit="t", loop="frozen")
        self.assertEqual(revised["revisions"][1]["loop"], "live")

    def test_planned_accounting_corrections_are_revisable(self):
        """P0-4 S4 (charge audit), P0-6 S4 (order cost) and S10 (recovery report) only touch accounting."""

        observed = copy.deepcopy(self.observed)
        for variant in harness.VARIANTS:
            columns = observed[variant]
            columns["market/market.sqlite::storage_state.li_battery.charge_mwh"][11] = 10.0
            columns["market/market.sqlite::orders.accounting_row_sha"][3] = "000000000000"
            columns["kernel/storage_cost_report"]["li_battery"]["recovery_adequacy"] = {"version": 2}
        revised = harness.append_revision(
            copy.deepcopy(self.golden), observed, reason="toy", correction_ids=["p04.storage-charge-audit"], base_commit="t",
        )
        self.assertEqual(len(revised["revisions"][1]["delta"]), 6)


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
        # Scoped to the paths the harness could write: other test modules run
        # concurrently in the same checkout (scripts/run_backend_tests.py).
        scope = ("gridform_core", "tests/fixtures")
        status_before = capture.worktree_status_sha256(scope)
        first = harness.columns_from_run(harness.run_case("legacy_tariff"))
        second = harness.columns_from_run(harness.run_case("legacy_tariff"))
        self.assertEqual(before, harness.tree_sha256(ROOT / "gridform_core"))
        self.assertEqual(status_before, capture.worktree_status_sha256(scope))
        self.assertEqual([], harness.compare_columns("legacy_tariff", first, second, {}))
        self.assertEqual(environment, {key: os.environ.get(key) for key in harness.LOOP_ENVIRONMENT})
        self.assertEqual(bidding, config.simulation_parameters.get("bidding_factor"))
        self.assertIs(runtime, module_context._runtime)
        self.assertIs(ledger, market_ledger._ACTIVE_LEDGER)

    def test_callable_loop_module_globals_are_restored(self):
        import types

        kernel = harness.kernel_module()
        frozen, _ = harness.compile_head_loop(kernel)
        reference = harness.columns_from_run(harness.run_case("dynamic", loop=frozen))
        # A callable whose globals are a real module's namespace, as a P0-6 S3
        # realise_period driver in the kernel would be.
        module = types.ModuleType("p06_probe_loop")
        module.__dict__.update({key: value for key, value in vars(kernel).items() if not key.startswith("__")})
        exec(compile(harness.HEAD_COPY_PATH.read_text(encoding="utf-8"), "p06_probe_loop", "exec"), module.__dict__)
        self.assertNotIn(harness.DRIVER_GLOBAL, module.__dict__)
        columns = harness.columns_from_run(harness.run_case("dynamic", loop=module.run_simulation))
        self.assertNotIn(harness.DRIVER_GLOBAL, module.__dict__)
        self.assertEqual([], harness.compare_columns("dynamic", reference, columns, {}))
        marker = object()
        module.__dict__[harness.DRIVER_GLOBAL] = marker
        harness.run_case("dynamic", loop=module.run_simulation)
        self.assertIs(module.__dict__[harness.DRIVER_GLOBAL], marker)
        self.assertNotIn(harness.DRIVER_GLOBAL, vars(kernel))

    def test_unknown_ledger_writers_fail_closed_with_a_named_error(self):
        ledger = harness.RecordingLedger()
        for name in ("record_storage_energy_audit", "record_surplus_routing", "declare_balance_boundary"):
            with self.assertRaisesRegex(NotImplementedError, name):
                getattr(ledger, name)
            with self.assertRaises(NotImplementedError):
                hasattr(ledger, name)
        self.assertFalse(hasattr(ledger, "flush"))

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
                    for zone, key, left, right in capture.e2e_differences(expected, actual, baseline["zones"])
                    if zone != "identity"
                ]
                self.assertEqual([], gated[:20], f"{case}: value_101_day market.sqlite differs from the HEAD baseline")


class E2EZoneGateTests(unittest.TestCase):
    def test_stored_baseline_zones_gate_and_only_tighten(self):
        capture = _capture_module()
        baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
        zones = baseline["zones"]
        price = "market/market.sqlite::period_summary.clearing_price_gbp_per_mwh"
        self.assertEqual(zones[price], "trajectory")
        self.assertEqual(zones["market/market.sqlite::storage_state.discharge_mwh"], "trajectory")
        # No harness-local rule for the real charge_mwh column: zones.json says trajectory.
        self.assertEqual(capture.gate_zone("market/market.sqlite::storage_state.charge_mwh", zones), "trajectory")
        # A later rule that weakens a stored trajectory column is ignored.
        from unittest import mock

        with mock.patch.object(capture, "e2e_zone", lambda key: "identity"):
            self.assertEqual(capture.gate_zone(price, zones), "trajectory")
            self.assertEqual(capture.gate_zone("market/market.sqlite::new_table.x", zones), "identity")
        with mock.patch.object(capture, "e2e_zone", lambda key: "trajectory"):
            self.assertEqual(capture.gate_zone("market/market.sqlite::period_summary.physical_resource_cost_gbp", zones), "trajectory")
        expected = {"tables": {"period_summary": {"rows": 1, "columns": {"clearing_price_gbp_per_mwh": "a"}}}, "metadata": {}}
        actual = {"tables": {"period_summary": {"rows": 1, "columns": {"clearing_price_gbp_per_mwh": "b"}}}, "metadata": {}}
        with mock.patch.object(capture, "e2e_zone", lambda key: "identity"):
            self.assertEqual(capture.e2e_differences(expected, actual, zones)[0][0], "trajectory")


if __name__ == "__main__":
    unittest.main()
