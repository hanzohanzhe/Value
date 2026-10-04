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
            parity_report={"contract_parity_passed": True, "retained_numerical_parity_passed": None},
            mechanism_checks=[MechanismCheck("deliberate_failure", 1.0, 2.0, "MW")],
        )
        self.assertEqual(report["analytical_mechanism_status"], FAILED)
        self.assertFalse(report["annual_economics_eligible"])
        self.assertEqual(report["scientific_validation_status"], FAILED)

    def test_missing_retained_comparison_is_not_evaluated(self):
        report = build_scientific_validation_report(
            mode="two_year_smoke",
            periods_per_year=2,
            parity_report={"contract_parity_passed": True, "retained_numerical_parity_passed": None},
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
            parity_report={"contract_parity_passed": True, "retained_numerical_parity_passed": False},
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
            parity_report={"contract_parity_passed": True, "retained_numerical_parity_passed": False},
            mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
            retained_comparison_role=RETAINED_COMPARISON_REQUIRED,
        )
        self.assertEqual(report["retained_numerical_comparison_status"], FAILED)
        self.assertEqual(report["scientific_validation_status"], FAILED)

    def test_empty_mechanisms_are_not_evidence_of_success(self):
        report = build_scientific_validation_report(
            mode="full", periods_per_year=17_520,
            parity_report={"contract_parity_passed": True, "retained_numerical_parity_passed": True},
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
                    parity_report={"contract_parity_passed": value, "retained_numerical_parity_passed": True},
                    mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
                )
                self.assertNotEqual(report["scientific_validation_status"], PASSED)
                self.assertFalse(report["annual_economics_eligible"])

    def test_nonfinite_unitless_or_boolean_comparisons_do_not_pass(self):
        for check in (MechanismCheck("inf", float("inf"), float("inf"), "MW"),
                      MechanismCheck("unitless", 1, 1, ""),
                      MechanismCheck("bool", True, True, "MW"),
                      MechanismCheck("negative_tolerance", 1, 1, "MW", -1)):
            with self.subTest(check=check):
                self.assertFalse(check.passed)


if __name__ == "__main__":
    unittest.main()
