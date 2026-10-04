from __future__ import annotations

import copy
import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts" / "run_prompt125_output_context_gate.py"


def load_auditor():
    if not AUDITOR.is_file():
        raise AssertionError("Prompt 125 output/context auditor has not been implemented")
    spec = importlib.util.spec_from_file_location("prompt125_output_context_gate", AUDITOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passing_evidence() -> dict[str, dict[str, object]]:
    sha_a = "a" * 64
    sha_b = "b" * 64
    common_results = {
        "dispatch_sha256": "1" * 64,
        "soc_sha256": "2" * 64,
        "investment_sha256": "3" * 64,
        "cost_sha256": "4" * 64,
        "carbon_sha256": "5" * 64,
        "curtailment_sha256": "6" * 64,
    }
    return {
        "contracts": {
            "passed": True,
            "run_context_sha256": sha_a,
            "year_context_sha256": sha_b,
            "period_payload_contains_annual_or_static_input": False,
        },
        "ledger_v8": {
            "passed": True,
            "schema_version": "value.market-ledger/v8",
            "context_hashes_present": True,
            "staged_market_jsonl_found": False,
            "legacy_ledgers_byte_identical": True,
            "validator_valid": True,
            "validator_errors_count": 0,
        },
        "zonal_48_period": {
            "passed": True,
            "period_count": 48,
            "network_pack_validation_count": 1,
            "run_context_sha256": sha_a,
            "year_context_sha256": sha_b,
            "period_payload_contains_annual_or_static_input": False,
        },
        "zonal_336_period": {
            "passed": True,
            "period_count": 336,
            "incremental_byte_growth_linear": True,
            "period_payload_contains_annual_or_static_input": False,
            "actual_output_bytes": 700_000,
            "accepted_estimate_bytes": 1_000_000,
        },
        "two_year_state_coupling": {
            "passed": True,
            "years": [2025, 2026],
            "year_context_sha256": {"2025": sha_a, "2026": sha_b},
            "commissioned_asset_id": "commissioned:project-2025",
            "commissioned_asset_in_2026_psm": True,
        },
        "trace_science_equivalence": {
            "passed": True,
            "summary_science_root": sha_a,
            "full_science_root": sha_a,
            "summary_results": common_results,
            "full_results": dict(common_results),
        },
        "failure_bundle": {
            "passed": True,
            "profiles": {
                profile: {"complete": True, "fallback_used": False}
                for profile in ("off", "summary", "full")
            },
        },
        "preflight_estimate": {
            "passed": True,
            "actual_output_bytes": 700_000,
            "accepted_estimate_bytes": 1_000_000,
            "insufficient_space_refused": True,
            "calibration_mutated_official_state": False,
        },
        "frontend_bounded_access": {
            "passed": True,
            "bounded_pagination": True,
            "truthful_trace_coverage": True,
            "on_demand_export": True,
            "unbounded_access_path_found": False,
        },
    }


class Prompt125OutputContextGateTests(unittest.TestCase):
    def test_context_registry_reader_uses_real_v8_context_scope_schema(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE context_registry("
                    "context_scope TEXT NOT NULL, year INTEGER NOT NULL, "
                    "schema_version TEXT NOT NULL, sha256 TEXT NOT NULL, "
                    "artifact_path TEXT NOT NULL, PRIMARY KEY(context_scope, year))"
                )
                connection.executemany(
                    "INSERT INTO context_registry VALUES(?,?,?,?,?)",
                    (
                        ("run", 0, "value.run-static-context/v1", "a" * 64, "market/context/run-context.json"),
                        ("year", 2025, "value.year-context/v1", "b" * 64, "market/context/year-2025.json"),
                    ),
                )
                connection.commit()

            rows = auditor._read_context_registry(database)

        self.assertEqual(
            rows,
            [
                {
                    "context_scope": "run", "year": 0,
                    "schema_version": "value.run-static-context/v1",
                    "sha256": "a" * 64,
                    "artifact_path": "market/context/run-context.json",
                },
                {
                    "context_scope": "year", "year": 2025,
                    "schema_version": "value.year-context/v1",
                    "sha256": "b" * 64,
                    "artifact_path": "market/context/year-2025.json",
                },
            ],
        )

    def test_report_has_exact_named_gates_and_pending_evidence_denies_restart(self) -> None:
        auditor = load_auditor()
        evidence = {name: {"passed": False} for name in auditor.REQUIRED_GATES}

        report = auditor.audit_evidence(evidence)

        required = {
            "contracts", "ledger_v8", "zonal_48_period", "zonal_336_period",
            "two_year_state_coupling", "trace_science_equivalence",
            "failure_bundle", "preflight_estimate", "frontend_bounded_access",
        }
        self.assertEqual(set(report["gates"]), required)
        self.assertFalse(report["ten_year_restart_authorised"])

    def test_all_nine_machine_readable_gates_are_required_for_restart(self) -> None:
        auditor = load_auditor()
        report = auditor.audit_evidence(passing_evidence())

        self.assertTrue(all(gate["passed"] for gate in report["gates"].values()))
        self.assertTrue(report["ten_year_restart_authorised"])
        self.assertIsNone(report["first_blocker"])

    def test_named_contract_violations_fail_closed(self) -> None:
        auditor = load_auditor()
        mutations = (
            ("contracts", "run_context_sha256", ""),
            ("ledger_v8", "staged_market_jsonl_found", True),
            ("zonal_336_period", "incremental_byte_growth_linear", False),
            ("trace_science_equivalence", "full_science_root", "f" * 64),
            ("failure_bundle", "profiles", {"summary": {"complete": False, "fallback_used": False}}),
            ("preflight_estimate", "actual_output_bytes", 1_000_001),
            ("frontend_bounded_access", "unbounded_access_path_found", True),
        )
        for gate, field, value in mutations:
            with self.subTest(gate=gate, field=field):
                evidence = copy.deepcopy(passing_evidence())
                evidence[gate][field] = value
                report = auditor.audit_evidence(evidence)
                self.assertFalse(report["gates"][gate]["passed"])
                self.assertFalse(report["ten_year_restart_authorised"])
                self.assertEqual(report["first_blocker"]["gate"], gate)

    def test_ledger_validator_failure_is_a_fail_closed_ledger_blocker(self) -> None:
        auditor = load_auditor()
        evidence = passing_evidence()
        evidence["ledger_v8"].update({
            "passed": True,
            "validator_valid": False,
            "validator_errors_count": 96,
        })

        report = auditor.audit_evidence(evidence)

        self.assertFalse(report["gates"]["ledger_v8"]["passed"])
        self.assertIn(
            "authoritative_ledger_validator_failed",
            report["gates"]["ledger_v8"]["issues"],
        )
        self.assertEqual(report["first_blocker"]["gate"], "ledger_v8")
        self.assertFalse(report["ten_year_restart_authorised"])

    def test_zonal_48_keeps_contracts_passed_when_only_ledger_validator_fails(self) -> None:
        auditor = load_auditor()
        run = {
            "passed": False,
            "period_count": 48,
            "network_pack_validation_count": 1,
            "run_context_sha256": "a" * 64,
            "year_context_sha256": "b" * 64,
            "period_payload_contains_annual_or_static_input": False,
            "max_period_payload_bytes": 1172,
            "context_registry": [{"context_scope": "run"}, {"context_scope": "year"}],
            "staged_market_jsonl_found": False,
            "database_sha256": "c" * 64,
            "science_root_by_year": {"2025": "d" * 64},
            "evidence_root_by_year": {"2025": "e" * 64},
            "ledger_validation": {
                "valid": False,
                "errors": [f"validator-error-{index}" for index in range(96)],
            },
        }

        with patch.object(auditor, "_run_zonal", return_value=run):
            produced = auditor._gate_zonal_48({})
        report = auditor.audit_evidence({**passing_evidence(), **produced})

        self.assertTrue(report["gates"]["contracts"]["passed"])
        self.assertFalse(report["gates"]["ledger_v8"]["passed"])
        self.assertFalse(report["gates"]["zonal_48_period"]["passed"])
        self.assertEqual(produced["ledger_v8"]["validator_errors_count"], 96)
        self.assertEqual(report["first_blocker"]["gate"], "ledger_v8")

    def test_persist_recounts_validator_errors_from_retained_zonal_48_database(self) -> None:
        auditor = load_auditor()
        evidence = passing_evidence()
        evidence["ledger_v8"].update({
            "passed": False,
            "validator_valid": False,
            "validator_errors_count": 97,
        })
        evidence["zonal_48_period"]["passed"] = False
        errors = (
            [f"period_integrity_science_projection_mismatch:2025:{period}" for period in range(48)]
            + [f"period_integrity_previous_science_mismatch:2025:{period}" for period in range(1, 48)]
            + ["year_integrity_science_root_mismatch:2025"]
        )
        with tempfile.TemporaryDirectory() as folder:
            output_root = Path(folder) / "zonal-48-attempt-2"
            database = output_root / "market" / "market.sqlite"
            database.parent.mkdir(parents=True)
            database.touch()
            evidence["zonal_48_period"]["output_root"] = str(output_root)
            json_path = Path(folder) / "report.json"
            markdown_path = Path(folder) / "report.md"
            with patch(
                "gridform_core.market_ledger.validate_market_ledger_file",
                return_value={"valid": False, "errors": errors},
            ):
                report = auditor._persist(evidence, [], json_path, markdown_path)

        self.assertTrue(report["gates"]["contracts"]["passed"])
        self.assertEqual(report["first_blocker"]["gate"], "ledger_v8")
        self.assertEqual(report["first_blocker"]["validator_errors_count"], 96)
        self.assertEqual(report["raw_evidence"]["ledger_v8"]["validator_errors_count"], 96)


if __name__ == "__main__":
    unittest.main()
