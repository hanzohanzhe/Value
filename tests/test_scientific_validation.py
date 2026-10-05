import unittest

from gridform_core.scientific_validation import (
    EXPECTED_DIFFERENCE,
    FAILED,
    NOT_EVALUATED,
    PASSED,
    RETAINED_COMPARISON_INFORMATIONAL,
    RETAINED_COMPARISON_REQUIRED,
    MechanismCheck,
    analytical_mechanism_checks,
    build_scientific_validation_report,
)


def _parity(passed=True, retained=None, **fields):
    """A stage-parity report with one executed, recomputable check (v3)."""

    row = {"stage": "contract_lifecycle", "year": None, "metric": "typed_result_years", "class": "contract",
           "actual": [2025], "expected": [2025] if passed else [2026], "absolute_tolerance": 0.0, "pass": passed}
    return {"schema_version": "value.stage-parity-report/v3", "contract_parity_passed": passed,
            "retained_numerical_parity_passed": retained, "checks": [row], **fields}


class ScientificValidationTests(unittest.TestCase):
    def test_analytical_mechanisms_pass_with_explicit_units(self):
        checks = analytical_mechanism_checks()
        self.assertGreaterEqual(len(checks), 10)
        self.assertTrue(all(item.passed for item in checks))
        self.assertTrue(all(item.unit for item in checks))

    def test_deliberate_mechanism_failure_blocks_publication(self):
        report = build_scientific_validation_report(
            mode="full",
            periods_per_year=17_520,
            parity_report=_parity(True, None),
            mechanism_checks=[MechanismCheck("deliberate_failure", 1.0, 2.0, "MW")],
        )
        self.assertEqual(report["analytical_mechanism_status"], FAILED)
        self.assertFalse(report["annual_economics_eligible"])
        self.assertEqual(report["scientific_validation_status"], FAILED)

    def test_missing_retained_comparison_is_not_evaluated(self):
        report = build_scientific_validation_report(
            mode="two_year_smoke",
            periods_per_year=2,
            parity_report=_parity(True, None),
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
        )
        self.assertEqual(report["execution_status"], PASSED)
        self.assertEqual(report["contract_validation_status"], PASSED)
        self.assertEqual(report["retained_numerical_comparison_status"], NOT_EVALUATED)
        self.assertEqual(report["scientific_validation_status"], NOT_EVALUATED)
        self.assertFalse(report["annual_economics_eligible"])

    def test_dynamic_policy_treats_retained_difference_as_scientific_evidence(self):
        report = build_scientific_validation_report(
            mode="full",
            periods_per_year=17_520,
            parity_report=_parity(True, False),
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
            retained_comparison_role=RETAINED_COMPARISON_INFORMATIONAL,
        )
        self.assertEqual(report["retained_numerical_comparison_status"], EXPECTED_DIFFERENCE)
        self.assertEqual(report["scientific_validation_status"], PASSED)
        self.assertTrue(report["annual_economics_eligible"])

    def test_legacy_reproduction_claim_still_fails_on_numerical_difference(self):
        report = build_scientific_validation_report(
            mode="full",
            periods_per_year=17_520,
            parity_report=_parity(True, False),
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
            retained_comparison_role=RETAINED_COMPARISON_REQUIRED,
        )
        self.assertEqual(report["retained_numerical_comparison_status"], FAILED)
        self.assertEqual(report["scientific_validation_status"], FAILED)

    def test_empty_mechanisms_are_not_evidence_of_success(self):
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520,
            parity_report=_parity(True, True),
            mechanism_checks=[],
        )
        self.assertEqual(report["analytical_mechanism_status"], NOT_EVALUATED)
        self.assertEqual(report["scientific_validation_status"], NOT_EVALUATED)
        self.assertFalse(report["annual_economics_eligible"])

    def test_truthy_strings_cannot_pass_a_contract_gate(self):
        for value in ("false", "true", 1, {"passed": True}):
            with self.subTest(value=value):
                report = build_scientific_validation_report(
                    mode="full", periods_per_year=17_520,
                    parity_report={**_parity(True, True), "contract_parity_passed": value},
                    mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
                )
                self.assertNotEqual(report["scientific_validation_status"], PASSED)
                self.assertFalse(report["annual_economics_eligible"])

    def test_a_bare_parity_claim_is_not_evidence(self):
        # P7-01: the review's reproduction call used to return passed.
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report={"contract_parity_passed": True})
        self.assertEqual(report["contract_validation_status"], NOT_EVALUATED)
        self.assertEqual(report["contract_validation"]["reason_code"], "GF_VALIDATION_CONTRACT_NOT_EXECUTED")
        self.assertEqual(report["scientific_validation_status"], NOT_EVALUATED)
        self.assertFalse(report["annual_economics_eligible"])
        self.assertEqual(report["schema_version"], "value.scientific-validation/v2")

    def test_contract_rows_are_recomputed_not_trusted(self):
        ok = [MechanismCheck("ok", 1.0, 1.0, "MW")]
        lying = _parity(True)
        lying["checks"][0]["expected"] = [2030]  # recorded pass=True, values differ
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=lying, mechanism_checks=ok)
        self.assertEqual(report["contract_validation_status"], FAILED)
        self.assertEqual(report["contract_validation"]["reason_code"], "GF_VALIDATION_CONTRACT_SELF_INCONSISTENT")
        self.assertEqual(report["scientific_validation_status"], FAILED)
        flag = _parity(True)
        flag["contract_parity_passed"] = False
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=flag, mechanism_checks=ok)
        self.assertEqual(report["contract_validation_status"], FAILED)
        numeric = _parity(True)
        numeric["checks"] = [{"actual": 1.0, "expected": 1.0 + 1e-3, "absolute_tolerance": 1e-6, "pass": False}]
        numeric["contract_parity_passed"] = False
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=numeric, mechanism_checks=ok)
        self.assertEqual(report["contract_validation_status"], FAILED)
        self.assertIsNone(report["contract_validation"]["reason_code"])
        malformed = _parity(True)
        malformed["checks"] = [{"metric": "no values", "pass": True}]
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=malformed, mechanism_checks=ok)
        self.assertEqual(report["contract_validation"]["reason_code"], "GF_VALIDATION_CONTRACT_CHECK_MALFORMED")

    def test_invariants_and_energy_balance_are_recomputed_and_reported(self):
        invariants = {"severity": "report", "status": "passed", "checks": [
            {"id": "run.demand_input_reconciliation", "class": "cross_path", "status": "failed"},
            {"id": "run.state_chain", "class": "integrity", "status": "passed"},
        ]}
        oracle = {"status": "failed", "reasons": ["GF_ENERGY_BALANCE_ENVELOPE_VIOLATED"],
                  "checks": [{"id": "period.envelope", "class": "independent", "status": "failed"}],
                  "metrics": {"periods": 4, "reported": {"adjusted_periods": 4, "sum_abs_adjustment_mwh": 47.35}},
                  "boundary": {"boundary_id": "default_psm_surplus_node_v1", "source": "registry"},
                  "stress": {"basis": "bounds", "stress_periods": 4, "possible_stress_periods": 4, "event_count": 2,
                             "by_year": [{"year": 2025, "stress_periods": 2, "event_count": 1,
                                          "shortfall_lower_mwh": 20.0, "shortfall_upper_mwh": 30.0},
                                         {"year": 2026, "stress_periods": 2, "event_count": 1,
                                          "shortfall_lower_mwh": 27.35, "shortfall_upper_mwh": 30.0}]}}
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=_parity(True, False),
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
            retained_comparison_role=RETAINED_COMPARISON_INFORMATIONAL,
            run_invariants=invariants, energy_balance=oracle)
        # Recomputed from the check rows, not the stored "passed".
        self.assertEqual(report["run_invariant_status"], FAILED)
        self.assertEqual(report["run_invariants"]["failed_checks"], ["run.demand_input_reconciliation"])
        self.assertEqual(report["energy_balance_status"], FAILED)
        self.assertEqual(report["energy_balance"]["compatibility_adjustment_periods"], 4)
        self.assertEqual(report["stress"]["stress_periods"], 4)
        self.assertEqual(report["stress"]["shortfall_basis"], "lower_bound")
        self.assertAlmostEqual(report["stress"]["shortfall_mwh"], 47.35)
        self.assertEqual(report["raw_invariants"]["status"], FAILED)
        codes = {row["code"] for row in report["validation_warnings"]}
        self.assertTrue({"GF_RUN_INVARIANTS_FAILED", "GF_ENERGY_BALANCE_FAILED",
                         "GF_COMPAT_ADJUSTMENT_PRESENT", "GF_STRESS_EVENTS_RECORDED"} <= codes)
        # Severity "report" until P0-4 S7: the scenario status is not gated.
        self.assertEqual(report["energy_balance"]["severity"], "report")
        self.assertEqual(report["scientific_validation_status"], PASSED)
        missing = build_scientific_validation_report(
            mode="full", periods_per_year=17_520, parity_report=_parity(True),
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")])
        self.assertEqual((missing["run_invariant_status"], missing["energy_balance_status"]),
                         (NOT_EVALUATED, NOT_EVALUATED))
        self.assertEqual(missing["raw_invariants"]["status"], NOT_EVALUATED)
        self.assertIsNone(missing["stress"])

    def test_nonfinite_unitless_or_boolean_comparisons_do_not_pass(self):
        for check in (MechanismCheck("inf", float("inf"), float("inf"), "MW"),
                      MechanismCheck("unitless", 1, 1, ""),
                      MechanismCheck("bool", True, True, "MW"),
                      MechanismCheck("negative_tolerance", 1, 1, "MW", -1)):
            with self.subTest(check=check):
                self.assertFalse(check.passed)


if __name__ == "__main__":
    unittest.main()
