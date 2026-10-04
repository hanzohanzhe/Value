import os
import random
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from gridform_core.market_ledger import SQLiteMarketLedger, set_active_market_ledger
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model import (
    Battery,
    ExpensiverenewableGenerator,
    GasGenerator,
    ahead_market_bidding,
)
from gridform_validation.force_clearing_oracle import validate_declared_database
from scripts.audit_prompt107_vre_attribution import (
    CommandSpec,
    SHORT_COMMAND_IDS,
    build_short_command_registry,
    build_short_report,
    parse_test_counts,
    run_registered_command,
)


def _passing_prompt107_records():
    registry = build_short_command_registry()
    counts = {
        "focused_scientific_verification": {"passed": 47},
        "sqlite_fixture_checks": {"passed": 17},
        "retained_scheme_c_hashes": {"passed": 1},
        "python_full_suite": {"run": 552, "passed": 531, "skipped": 21},
        "frontend_lint": {},
        "frontend_build": {},
        "frontend_e2e": {"passed": 25, "skipped": 0},
    }
    records = {
        command_id: {
            "command_id": command_id,
            "argv": list(spec.argv),
            "shell": False,
            "capture_output": True,
            "exit_code": 0,
            "elapsed_seconds": 0.01,
            "timeout_seconds": spec.timeout_seconds,
            "final_output_lines": (
                ["Build complete. Run `vinext start` to start the production server."]
                if command_id == "frontend_build" else []
            ),
            "parsed_counts": counts[command_id],
            "optional_skip_reasons": (
                ["verified local pack is required"] * 21
                if command_id == "python_full_suite" else []
            ),
            "unexpected_skip_reasons": [],
            "execution_error": None,
        }
        for command_id, spec in registry.items()
    }
    records["focused_scientific_verification"][
        "maximum_identity_residual_mwh"
    ] = 0.0
    return records


class ForceActualRandomClearingTests(unittest.TestCase):
    def test_prompt107_auditor_records_final_40_lines_and_parsed_counts(self):
        command = CommandSpec(
            command_id="fixture",
            argv=(
                sys.executable,
                "-c",
                "print('\\n'.join(f'line-{i}' for i in range(45))); "
                "print('12 passed, 2 skipped in 0.01s')",
            ),
            count_style="pytest",
        )
        record = run_registered_command(command)
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(len(record["final_output_lines"]), 40)
        self.assertEqual(record["final_output_lines"][0], "line-6")
        self.assertEqual(record["parsed_counts"]["passed"], 12)
        self.assertEqual(record["parsed_counts"]["skipped"], 2)
        self.assertGreaterEqual(record["elapsed_seconds"], 0.0)

    def test_prompt107_auditor_registry_and_no_go_rules_are_complete(self):
        registry = build_short_command_registry()
        self.assertEqual(tuple(registry), SHORT_COMMAND_IDS)
        passing = _passing_prompt107_records()
        report = build_short_report(passing)
        self.assertEqual(report["decision"], "GO")
        self.assertEqual(report["annual_gate"], "not_run_in_short_gate")
        self.assertEqual(report["short_gate"]["status"], "passed")

        missing = dict(passing)
        missing.pop(SHORT_COMMAND_IDS[-1])
        self.assertEqual(build_short_report(missing)["decision"], "NO-GO")

        failed = {key: dict(value) for key, value in passing.items()}
        failed[SHORT_COMMAND_IDS[0]]["exit_code"] = 1
        self.assertEqual(build_short_report(failed)["decision"], "NO-GO")

    def test_prompt107_auditor_rejects_fabricated_stale_or_reordered_records(self):
        mutations = {}

        fake_argv = _passing_prompt107_records()
        fake_argv["frontend_lint"] = dict(fake_argv["frontend_lint"])
        fake_argv["frontend_lint"]["argv"] = ["fixture"]
        mutations["fake argv"] = fake_argv

        fake_id = _passing_prompt107_records()
        fake_id["sqlite_fixture_checks"] = dict(fake_id["sqlite_fixture_checks"])
        fake_id["sqlite_fixture_checks"]["command_id"] = "stale-command"
        mutations["fake command id"] = fake_id

        stale_timeout = _passing_prompt107_records()
        stale_timeout["frontend_e2e"] = dict(stale_timeout["frontend_e2e"])
        stale_timeout["frontend_e2e"]["timeout_seconds"] = 1
        mutations["stale timeout"] = stale_timeout

        reordered_source = _passing_prompt107_records()
        reversed_ids = tuple(reversed(SHORT_COMMAND_IDS))
        mutations["reordered records"] = {
            command_id: reordered_source[command_id] for command_id in reversed_ids
        }

        for name, records in mutations.items():
            with self.subTest(name=name):
                report = build_short_report(records)
                self.assertEqual(report["decision"], "NO-GO")

    def test_prompt107_auditor_rejects_zero_low_or_inconsistent_test_counts(self):
        mutations = {}
        for command_id, field, value in (
            ("focused_scientific_verification", "passed", 46),
            ("sqlite_fixture_checks", "passed", 16),
            ("retained_scheme_c_hashes", "passed", 0),
            ("python_full_suite", "run", 551),
            ("frontend_e2e", "passed", 24),
        ):
            records = _passing_prompt107_records()
            records[command_id] = dict(records[command_id])
            records[command_id]["parsed_counts"] = dict(
                records[command_id]["parsed_counts"]
            )
            records[command_id]["parsed_counts"][field] = value
            mutations[f"{command_id} {field}"] = records

        inconsistent = _passing_prompt107_records()
        inconsistent["python_full_suite"] = dict(
            inconsistent["python_full_suite"]
        )
        inconsistent["python_full_suite"]["parsed_counts"] = {
            "run": 552, "passed": 530, "skipped": 21,
        }
        mutations["unittest total mismatch"] = inconsistent

        all_skipped = _passing_prompt107_records()
        all_skipped["frontend_e2e"] = dict(all_skipped["frontend_e2e"])
        all_skipped["frontend_e2e"]["parsed_counts"] = {
            "passed": 0, "skipped": 25,
        }
        mutations["all skipped playwright"] = all_skipped

        for name, records in mutations.items():
            with self.subTest(name=name):
                self.assertEqual(build_short_report(records)["decision"], "NO-GO")

    def test_prompt107_auditor_rejects_missing_build_success_marker(self):
        records = _passing_prompt107_records()
        records["frontend_build"] = dict(records["frontend_build"])
        records["frontend_build"]["final_output_lines"] = []
        self.assertEqual(build_short_report(records)["decision"], "NO-GO")

    def test_prompt107_auditor_recomputes_unexpected_skip_reasons(self):
        records = _passing_prompt107_records()
        records["python_full_suite"] = dict(records["python_full_suite"])
        records["python_full_suite"]["optional_skip_reasons"] = [
            "verified local pack is required"
        ] * 20 + ["fabricated unapproved environment skip"]
        records["python_full_suite"]["unexpected_skip_reasons"] = []
        report = build_short_report(records)
        self.assertEqual(report["decision"], "NO-GO")

    def test_prompt107_pytest_count_parser_is_literal(self):
        self.assertEqual(
            parse_test_counts("7 passed, 3 skipped, 1 xfailed in 2.0s", "pytest"),
            {"passed": 7, "skipped": 3, "xfailed": 1},
        )
        self.assertEqual(
            parse_test_counts(
                "Ran 12 tests in 1.0s\n\nOK (skipped=2)", "unittest"
            ),
            {"run": 12, "skipped": 2, "passed": 10},
        )
        self.assertEqual(
            parse_test_counts("  13 passed\n  2 skipped (4.2s)", "playwright"),
            {"passed": 13, "skipped": 2},
        )

    def test_prompt107_timeout_is_recorded_and_cannot_go(self):
        timed_out = run_registered_command(CommandSpec(
            command_id="timeout-fixture",
            argv=(sys.executable, "-c", "import time; time.sleep(1)"),
            timeout_seconds=0,
        ))
        self.assertIsNone(timed_out["exit_code"])
        self.assertIn("TimeoutExpired", timed_out["execution_error"])

        records = _passing_prompt107_records()
        records["focused_scientific_verification"].update(
            maximum_identity_residual_mwh=0.0,
            exit_code=None,
            execution_error=timed_out["execution_error"],
        )
        self.assertEqual(build_short_report(records)["decision"], "NO-GO")

    def test_seeded_random_actual_force_ahead_matches_independent_cbc(self):
        rng = random.Random(279_2026)
        cases = 20
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ,
            {"SIMULATION_YEAR": "2025", "PHYSICAL_PERIOD_HOURS": "0.5"},
        ):
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full", batch_size=20)
            set_active_market_ledger(ledger)
            try:
                for period in range(cases):
                    vre_capacity = rng.uniform(5.0, 120.0)
                    gas_capacity = rng.uniform(50.0, 180.0)
                    storage_power = rng.uniform(5.0, 45.0)
                    demand = rng.uniform(10.0, vre_capacity + gas_capacity + storage_power + 20.0)
                    wind = ExpensiverenewableGenerator(
                        f"wind-{period}", rng.uniform(-5.0, 15.0), 0.0, 0.0,
                        0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                    )
                    wind.capacity_limit = vre_capacity
                    gas = GasGenerator(
                        f"gas-{period}", rng.uniform(25.0, 90.0), 0.0, 0.0,
                        gas_capacity, gas_capacity, rng.uniform(0.0, 20.0),
                        0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    )
                    battery = Battery(
                        f"battery-{period}", storage_power * 2.0, storage_power,
                        0.0, 0.0, 0.95, 0.9, 0.0,
                        capital_cost=100_000.0, battery_type="0.5c",
                    )
                    battery.prepare_operating_year(2025)
                    battery.set_stored_energy_var(-1, rng.uniform(0.0, storage_power * 2.0))
                    arrays = [defaultdict(float) for _ in range(4)]
                    ahead_market_bidding(
                        [wind, gas], [battery], demand, period, [],
                        arrays[0], arrays[1], arrays[2], arrays[3], 1.0,
                        retain_storage_tranche_history=False,
                    )
            finally:
                ledger.close()
                set_active_market_ledger(None)
            report = validate_declared_database(database)
            self.assertEqual(report["declared_rows"], cases)
            self.assertEqual(report["lp_supported_rows"], cases)
            self.assertEqual(report["lp_failed_rows"], 0)
            self.assertEqual(report["storage_transition_failed_rows"], 0)
            self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
