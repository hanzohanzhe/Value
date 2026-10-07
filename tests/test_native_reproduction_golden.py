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
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

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
    "non_vre_surplus_exported",
    "stale_export_carry",
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
        # Revision 0 alone (P0-4 S4 and later append accounting revisions).
        revised = _revision_zero(self.golden)
        self.assertEqual(len(revised["revisions"]), 1)
        self.assertEqual(harness.gated_zones(revised, "frozen"), ("trajectory", "accounting"))
        revised["revisions"].append({"index": 1, "correction_ids": ["p04.storage-charge-audit"], "patch": {}})
        self.assertEqual(harness.gated_zones(revised, "frozen"), ("trajectory",))
        self.assertEqual(harness.gated_zones(revised, "live"), ("trajectory", "accounting"))

    def test_scenario_exercises_every_situation_named_by_the_plan(self):
        # The situations are 35aadb3 (HEAD) behaviour: revision 0 is the HEAD
        # capture.  R4-1 (A26) removed the storage power reset, so the latest
        # revision has every situation but the reset's two.
        head = harness.latest_columns(_revision_zero(self.golden))
        latest = harness.latest_columns(self.golden)
        removed_by_r41 = {"storage_discharge_above_rated_power", "storage_fee_carry_into_curtailment"}
        for variant in harness.VARIANTS:
            facts = harness.coverage_facts(head[variant], self.golden["scenario"])
            missing = [name for name in REQUIRED_SITUATIONS if not facts[name]]
            self.assertEqual([], missing, variant)
            self.assertTrue(set(facts["p3_01_toy_f120_r28"]) & set(facts["hidden_shortage_in_curtailment_branch"]))
            facts = harness.coverage_facts(latest[variant], self.golden["scenario"])
            missing = [name for name in REQUIRED_SITUATIONS if not facts[name] and name not in removed_by_r41]
            self.assertEqual([], missing, variant)
            self.assertEqual(facts["storage_discharge_above_rated_power"], [], variant)

    def test_r41_corrections_are_pinned_in_the_latest_revision(self):
        # DECISIONS A26 (R4-1): the trajectory re-baseline names the three
        # kernel corrections; in its columns no store discharges above its
        # rating or charges and discharges in one period, and the must-run
        # nuclear surplus that served the balancing requirement is not
        # counted twice (HEAD: +1.5 and +0.5 MWh in periods 19 and 21).
        rebaselines = [item for item in self.golden["revisions"] if item.get("trajectory_rebaseline")]
        self.assertEqual(len(rebaselines), 1)
        self.assertEqual(set(rebaselines[0]["correction_ids"]), set(harness.TRAJECTORY_REBASELINE_CORRECTIONS))
        head = harness.latest_columns(_revision_zero(self.golden))
        latest = harness.latest_columns(self.golden)
        summary = "market/market.sqlite::period_summary."
        state = "market/market.sqlite::storage_state."
        for variant in harness.VARIANTS:
            columns = latest[variant]
            facts = harness.coverage_facts(columns, self.golden["scenario"])
            batteries = sorted({key[len(state):].rsplit(".", 1)[0] for key in columns
                                if key.startswith(state) and key.endswith(".power_capacity_mw")})
            self.assertTrue(batteries)
            for name in batteries:
                charge = columns[f"{state}{name}.charge_mwh"]
                discharge = columns[f"{state}{name}.discharge_mwh"]
                power = columns[f"{state}{name}.power_capacity_mw"]
                for period in range(harness.PERIODS):
                    self.assertLessEqual(discharge[period], power[period] * harness.PERIOD_HOURS + 1e-9,
                                         (variant, name, period))
                    self.assertFalse(charge[period] > 1e-9 and discharge[period] > 1e-9, (variant, name, period))
            self.assertEqual([head[variant][summary + "raw_energy_balance_residual_mwh"][p] for p in (19, 21)],
                             [1.5, 0.5])
            for period in facts["nuclear_surplus_in_balancing"]:
                self.assertEqual(columns[summary + "raw_energy_balance_residual_mwh"][period], 0.0, (variant, period))

    def test_head_semantics_are_pinned_in_the_golden(self):
        # The 35aadb3 (HEAD) semantics are those of revision 0; R4-1 (A26)
        # re-baselined the trajectory once (test above).
        latest = harness.latest_columns(_revision_zero(self.golden))["dynamic"]
        summary = "market/market.sqlite::period_summary."
        facts = harness.coverage_facts(latest, self.golden["scenario"])
        # P3-01: the curtailment branch reports no blackout although the ahead
        # stage could not meet the forecast (HEAD 2765).
        for period in facts["hidden_shortage_in_curtailment_branch"]:
            self.assertEqual(latest[summary + "blackout_mwh"][period], 0.0)
        # HEAD 1463: VRE squeezed out by nuclear is neither dispatched nor
        # curtailed.  (curtailed_mwh can be positive in such a period: in 33
        # it is the non-VRE down-regulation of the nuclear surplus.)
        for period in facts["nuclear_blocking_vre_unrecorded"]:
            self.assertEqual(latest[summary + "vre_accepted_mwh"][period], 0.0)
            curtailed = latest["kernel/run_simulation::curtailed_energy_dict"][period]
            self.assertFalse(
                isinstance(curtailed, list)
                and any(str(item[0]).startswith("<ExpensiverenewableGenerator") for item in curtailed),
                period,
            )
        self.assertEqual(
            [p for p in facts["nuclear_blocking_vre_unrecorded"] if latest[summary + "curtailed_mwh"][p] != 0.0], [33],
        )
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
        # P5-03: per-stage power reset; pumped hydro (15 MW) discharges 30 MW
        # (two stages at full power; the exact doubles, e.g. 29.999999999999996
        # in 46, are pinned by the golden itself), li_battery (20 MW) 28 MW.
        state = "market/market.sqlite::storage_state."
        for period in (40, 42, 44, 46):
            self.assertIn(period, facts["storage_discharge_above_rated_power"])
            self.assertAlmostEqual(
                latest[state + "pumpedhydro_battery.discharge_mwh"][period] / harness.PERIOD_HOURS, 30.0, places=9)
            self.assertEqual(latest[state + "pumpedhydro_battery.power_capacity_mw"][period], 15.0)
        self.assertEqual(latest[state + "li_battery.discharge_mwh"][90] / harness.PERIOD_HOURS, 28.0)
        self.assertEqual(latest[state + "li_battery.power_capacity_mw"][90], 20.0)
        # Q7 path: with storage full (after the VRE-surplus segment) the
        # nuclear surplus of the curtailment branch is exported (32-35).
        nuclear_segment = [item for item in self.golden["scenario"]["segments"] if item["first_period"] == 32]
        self.assertEqual(len(nuclear_segment), 1)
        self.assertIn("nuclear surplus", nuclear_segment[0]["purpose"])
        self.assertEqual(facts["non_vre_surplus_exported"], [32, 33, 34, 35])
        for period in facts["non_vre_surplus_exported"]:
            self.assertGreater(latest[summary + "export_mwh"][period], 0.0)
        # New HEAD defect (third review of P0-6 S1, not in the 2026-10-04
        # review): on the curtailment path with a non-empty soldable list, a
        # connection with transfer >= 0 keeps the previous period's
        # sold_energy, a phantom export without a fee.  The doctoral rule
        # set reproduces it; the corrected rule set resets it (P0-6 S5).
        self.assertEqual(facts["stale_export_carry"], [29, 36, 37])
        france, norway = "kernel/state::Interconnect_France.", "kernel/state::Interconnect_Norway."
        transfers = {name: self.golden["scenario"]["interconnectors"][name]["transfer_constraint_mw"]
                     for name in harness.CONNECTION_NAMES}
        self.assertEqual(transfers["Interconnect_France"][29], 0.0)
        self.assertEqual(latest[france + "sold_energy"][28], 15.0)
        self.assertEqual(latest[france + "sold_energy"][29], 15.0)
        self.assertEqual(latest[norway + "sold_energy"][29], 0)
        self.assertEqual(latest["kernel/run_simulation::interconnector_exports_list"][29], 15.0)
        self.assertEqual(latest[summary + "export_mwh"][29], 7.5)
        self.assertEqual(latest["kernel/run_simulation::sold_fees"][29], 0)
        self.assertEqual(transfers["Interconnect_Norway"][36], 0.0)
        self.assertEqual(latest[norway + "sold_energy"][36], 6.0)

    def test_fixture_is_small_and_one_column_per_line(self):
        # Plan 4.6 S1 acceptance (< 300 KB) applies to the capture: scenario,
        # cases and revision 0.  Appended revisions have their own budget.
        self.assertLess(harness.revision_zero_bytes(self.golden), harness.REVISION_ZERO_BUDGET_BYTES)
        for revision in self.golden["revisions"][1:]:
            self.assertLessEqual(harness.revision_bytes(revision), harness.revision_budget_bytes(revision))
        self.assertEqual(harness.GOLDEN_PATH.read_text(encoding="utf-8"), harness.dump_golden(self.golden))

    def test_revision_patches_are_dumped_one_column_per_line(self):
        observed = copy.deepcopy(self.observed)
        golden = _frozen_base(self.golden, self.observed)
        accounting = [key for key, zone in harness.pinned_zones(golden).items()
                      if zone == "accounting" and isinstance(observed["dynamic"][key], list)]
        self.assertGreater(len(accounting), 10)
        for variant in harness.VARIANTS:
            for key in accounting:
                values = observed[variant][key]
                observed[variant][key] = [value + 1.0 if isinstance(value, float) else value for value in values]
        revised = harness.append_revision(
            golden, observed, reason="every accounting column", correction_ids=["p04.toy"],
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
        self.assertEqual(harness.revision_zero_bytes(revised), harness.revision_zero_bytes(golden))

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
        # The e2e baseline has no zone rule of its own: for every key it
        # produces, the stored zone, the capture script's zone and zones.json
        # agree (metadata rows are identity, as metadata.key/value in X0).
        capture = _capture_module()
        baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
        e2e_keys = set()
        for digest in baseline["cases"].values():
            e2e_keys |= set(capture.e2e_entries(digest))
        self.assertEqual(e2e_keys, set(baseline["zones"]))
        for key in sorted(e2e_keys):
            self.assertEqual((baseline["zones"][key], capture.e2e_zone(key)), (rules.zone(key), rules.zone(key)), key)
        metadata = sorted(key for key in e2e_keys if key.startswith("market/market.sqlite::metadata."))
        self.assertGreaterEqual(len(metadata), 16)
        self.assertEqual({baseline["zones"][key] for key in metadata}, {"identity"})
        # Declared clearing inputs/outcomes: trajectory like their tables
        # (the derived unserved target falls under the A2 '*unserved*' rule).
        self.assertEqual(harness.zone_of("kernel/declared::ahead.storage_accepted_mw"), "trajectory")
        self.assertEqual(harness.zone_of("kernel/declared::ahead.input_payload_sha"), "trajectory")
        self.assertEqual(harness.zone_of("kernel/declared::ahead.unserved_target_mw"), "accounting")

    def test_revision_accepts_accounting_and_refuses_trajectory_changes(self):
        golden = _frozen_base(self.golden, self.observed)
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
        # DECISIONS A26: only the kernel corrections may re-baseline the
        # trajectory, with trajectory=True, once each.
        with self.assertRaisesRegex(ValueError, "not A26 kernel corrections"):
            harness.append_revision(golden, trajectory, reason="x", correction_ids=["p06.x"], base_commit="t",
                                    trajectory=True)
        rebased = harness.append_revision(golden, trajectory, reason="x", correction_ids=["r41.down-regulation-taken-once"],
                                          base_commit="t", trajectory=True)
        self.assertTrue(rebased["revisions"][1]["trajectory_rebaseline"])
        again = copy.deepcopy(trajectory)
        again["legacy_tariff"]["market/market.sqlite::period_summary.accepted_supply_mwh"][5] += 1.0
        with self.assertRaisesRegex(ValueError, "already re-baselined"):
            harness.append_revision(rebased, again, reason="x", correction_ids=["r41.down-regulation-taken-once"],
                                    base_commit="t", trajectory=True)
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
            _frozen_base(self.golden, self.observed), observed, reason="toy", correction_ids=["p04.storage-charge-audit"],
            base_commit="t",
        )
        self.assertEqual(len(revised["revisions"][1]["delta"]), 6)


def _revision_zero(golden):
    """The golden with revision 0 only (the 35aadb3 capture)."""

    copied = copy.deepcopy(golden)
    copied["revisions"] = copied["revisions"][:1]
    return copied


def _frozen_base(golden, observed):
    """A one-revision golden that the frozen-loop observation reproduces in every zone.

    Before R4-1 this was revision 0; the A26 trajectory re-baseline changed
    the dispatch, so the frozen loop (HEAD ledger boundary) now reproduces
    neither revision 0 nor the latest accounting columns.  The revision tests
    only need a base their own injected changes are the sole differences from.
    """

    copied = _revision_zero(golden)
    observed_keys = {key for columns in observed.values() for key in columns}
    copied["zones"] = {key: zone for key, zone in harness.pinned_zones(golden).items() if key in observed_keys}
    copied["cases"] = {case: {"columns": copy.deepcopy(dict(columns))} for case, columns in observed.items()}
    return copied


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
        golden = _revision_zero(harness.load_golden())
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
        # (record_storage_audit and record_surplus_routing are recorded since
        # P0-4 S4/S5; any other writer still fails closed.)
        for name in ("record_storage_energy_audit", "record_unknown_writer", "declare_unknown_boundary"):
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
        # Scope: the P0-6 S3 identity check.  No revision path: the first X0
        # D3/C3 revision (P0-4 S4-S6, A2, P0-5a) retires this test, and X0 is
        # the gate for value_101_day from then on.
        retired = capture.e2e_retirement()
        if retired:
            self.skipTest(f"{harness.E2E_BASELINE_PATH.name} retired: {retired}")
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


class CaptureProvenanceTests(unittest.TestCase):
    def test_capture_refuses_a_dirty_checkout_and_records_the_tooling(self):
        from unittest import mock

        capture = _capture_module()
        output = harness.GOLDEN_PATH
        relative = output.relative_to(ROOT).as_posix()
        status = (f" D {relative}\n M tests/native_reproduction_harness.py\n?? scratch.txt\n"
                  " M gridform_core/market_ledger.py\n")
        with mock.patch.object(capture, "_git", lambda *arguments: status):
            with self.assertRaisesRegex(SystemExit, "uncommitted changes outside the recorded tooling"):
                capture.capture_provenance(capture.SYNTHETIC_TOOLING, (output,), allow_dirty=False)
            record = capture.capture_provenance(capture.SYNTHETIC_TOOLING, (output,), allow_dirty=True)
        self.assertEqual(record["checkout_state"], "dirty")
        self.assertEqual(record["dirty_paths"], ["gridform_core/market_ledger.py", "scratch.txt"])
        self.assertEqual(record["uncommitted_tooling"], ["tests/native_reproduction_harness.py"])
        # Uncommitted tooling alone is allowed: its content is recorded and
        # the provenance test requires a commit with exactly that content.
        status = f" D {relative}\n M tests/native_reproduction_harness.py\n"
        with mock.patch.object(capture, "_git", lambda *arguments: status):
            record = capture.capture_provenance(capture.SYNTHETIC_TOOLING, (output,), allow_dirty=False)
        self.assertEqual(record["checkout_state"], "clean")
        self.assertEqual(record["uncommitted_tooling"], ["tests/native_reproduction_harness.py"])
        with mock.patch.object(capture, "_git", lambda *arguments: f" D {relative}\n"):
            record = capture.capture_provenance(capture.SYNTHETIC_TOOLING, (output,), allow_dirty=False)
        self.assertEqual(record["checkout_state"], "clean")
        self.assertNotIn("uncommitted_tooling", record)
        self.assertEqual(set(record["capture_tooling"]), set(capture.SYNTHETIC_TOOLING))
        self.assertEqual(
            record["capture_tooling"]["tests/native_reproduction_harness.py"],
            harness.sha256_text((ROOT / "tests" / "native_reproduction_harness.py").read_text(encoding="utf-8")),
        )
        for path in capture.E2E_TOOLING:
            self.assertTrue((ROOT / path).is_file(), path)


    def test_fixtures_were_captured_clean_from_committed_tooling(self):
        """Provenance by content: some commit reachable from HEAD holds exactly
        the tooling recorded in each fixture (base_commit is informational and
        does not survive the integration rebase)."""

        capture = _capture_module()
        golden = harness.load_golden()
        e2e = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
        for name, fixture, tooling in (
            ("synthetic", golden, capture.SYNTHETIC_TOOLING),
            ("e2e", e2e, capture.E2E_TOOLING),
        ):
            source = fixture["source"]
            self.assertEqual(source["checkout_state"], "clean", name)
            self.assertEqual(set(source["capture_tooling"]), set(tooling), name)
            try:
                commit = capture.find_tooling_commit(source["capture_tooling"])
            except LookupError as error:
                # No git (an archive copy): the recorded hashes remain the record.
                self.skipTest(f"git unavailable: {error}")
            if commit is None:
                # The capture and its tooling are about to be committed together
                # (pre-commit gate run): the checkout itself must then hold the
                # recorded tooling.  In any committed checkout this is the same
                # as HEAD matching, so it adds no way around the commit check.
                current = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in tooling}
                self.assertEqual(
                    current, source["capture_tooling"],
                    f"{name}: neither a commit reachable from HEAD nor the checkout has the recorded tooling",
                )

    def test_find_tooling_commit_matches_content_and_fails_closed(self):
        capture = _capture_module()
        try:
            head = {path: hashlib.sha256(subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT,
                                                         capture_output=True, check=True).stdout).hexdigest()
                    for path in capture.SYNTHETIC_TOOLING}
            found = capture.find_tooling_commit(head)
        except (OSError, subprocess.CalledProcessError, LookupError) as error:
            self.skipTest(f"git unavailable: {error}")
        self.assertIsNotNone(found)
        listing = subprocess.run(["git", "show", f"{found}:{capture.SYNTHETIC_TOOLING[0]}"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        self.assertEqual(hashlib.sha256(listing).hexdigest(), head[capture.SYNTHETIC_TOOLING[0]])
        tampered = dict(head)
        tampered[capture.SYNTHETIC_TOOLING[0]] = "0" * 64
        self.assertIsNone(capture.find_tooling_commit(tampered))
        from unittest import mock

        with mock.patch.object(capture, "_git", lambda *arguments: None):
            with self.assertRaises(LookupError):
                capture.find_tooling_commit(head)


class E2ERetirementTests(unittest.TestCase):
    MARKET_KEY = "market/market.sqlite::period_summary.storage_charge_mwh"

    @staticmethod
    def _digest(changes: dict[str, str]) -> dict[str, Any]:
        columns = {
            E2ERetirementTests.MARKET_KEY: {"count": 48, "sha256": "a" * 32, "zone": "trajectory"},
            "market/market.sqlite::metadata.value": {"count": 15, "sha256": "b" * 32, "zone": "identity"},
            "planning/project-index.sqlite::projects.capacity_mw": {"count": 3, "sha256": "c" * 32,
                                                                   "zone": "trajectory"},
        }
        for key, sha in changes.items():
            columns[key] = {**columns[key], "sha256": sha}
        return {"columns": columns}

    def _successors(self, directory: Path, revisions: dict[str, list[dict[str, str]]]) -> dict[str, Path]:
        paths = {}
        for case, changes in revisions.items():
            path = directory / f"{case}.json"
            path.write_text(json.dumps({"case": case, "revisions": [
                {"revision": index, "correction_ids": [] if index == 0 else ["p04.storage-charge-audit"],
                 "findings": [], "digest": self._digest(change)}
                for index, change in enumerate(changes)
            ]}), encoding="utf-8")
            paths[case] = path
        return paths

    def test_an_x0_revision_that_changes_market_sqlite_retires_the_baseline(self):
        capture = _capture_module()
        self.assertEqual(set(capture.E2E_SUCCESSORS), set(capture.E2E_CASES))
        for case, path in capture.E2E_SUCCESSORS.items():
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["case"], case)
        with tempfile.TemporaryDirectory(prefix="p06-retire-") as temporary:
            directory = Path(temporary)
            base = [{}]
            self.assertIsNone(capture.e2e_retirement(self._successors(directory, {"D3": base, "C3": base})))
            # Revisions that leave the gated market.sqlite keys alone do not retire it.
            planning = [{}, {"planning/project-index.sqlite::projects.capacity_mw": "d" * 32}]
            identity = [{}, {"market/market.sqlite::metadata.value": "e" * 32}]
            for other in (planning, identity):
                self.assertIsNone(capture.e2e_retirement(self._successors(directory, {"D3": other, "C3": base})))
            for revised in ("D3", "C3"):
                counts = {"D3": base, "C3": base, revised: [*planning, {self.MARKET_KEY: "f" * 32}]}
                reason = capture.e2e_retirement(self._successors(directory, counts))
                self.assertIsNotNone(reason)
                self.assertIn(f"X0 golden {revised}", reason)
                self.assertIn("revision 2", reason)
                self.assertIn("p04.storage-charge-audit", reason)
                self.assertIn(self.MARKET_KEY, reason)
            wrong = self._successors(directory, {"D3": base})
            with self.assertRaisesRegex(ValueError, "expected 'C3'"):
                capture.e2e_retirement({"C3": wrong["D3"]})

    def test_added_or_removed_market_columns_count_as_changes(self):
        capture = _capture_module()
        previous = self._digest({})
        current = copy.deepcopy(previous)
        current["columns"]["market/market.sqlite::stress_events.shortfall_mwh"] = {
            "count": 1, "sha256": "0" * 32, "zone": "accounting"}
        self.assertEqual(capture.market_ledger_changes(previous, current),
                         ["market/market.sqlite::stress_events.shortfall_mwh"])
        del current["columns"][self.MARKET_KEY]
        self.assertIn(self.MARKET_KEY, capture.market_ledger_changes(previous, current))

    def test_check_e2e_reports_retirement_without_running(self):
        import contextlib
        import io
        from unittest import mock

        capture = _capture_module()
        output = io.StringIO()
        with mock.patch.object(capture, "e2e_retirement", lambda: "X0 golden D3 has revision 1"), \
                mock.patch.object(capture, "run_e2e_case", side_effect=AssertionError("must not run")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(capture.main(["check-e2e"]), 0)
        self.assertIn("e2e baseline retired: X0 golden D3 has revision 1", output.getvalue())


class E2EZoneGateTests(unittest.TestCase):
    def test_new_ledger_metadata_rows_are_identity_and_never_gated(self):
        """P0-6 S2 writes the market_rule_set record into the ledger metadata
        and C20 adds leftover_relationship: identity changes, not failures."""

        capture = _capture_module()
        baseline = json.loads(harness.E2E_BASELINE_PATH.read_text(encoding="utf-8"))
        expected = baseline["cases"]["D3"]
        actual = copy.deepcopy(expected)
        actual["metadata"]["market_rule_set"] = '{"id": "doctoral-lineage-0.6.0a2"}'
        actual["metadata"]["leftover_relationship"] = '"separate_prebalancing"'
        actual["metadata"]["curtailment_semantics"] = '"changed"'
        differences = capture.e2e_differences(expected, actual, baseline["zones"])
        self.assertEqual(
            sorted(key for _, key, _, _ in differences),
            ["market/market.sqlite::metadata.#rows", "market/market.sqlite::metadata.curtailment_semantics",
             "market/market.sqlite::metadata.leftover_relationship", "market/market.sqlite::metadata.market_rule_set"],
        )
        self.assertEqual({zone for zone, _, _, _ in differences}, {"identity"})

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
