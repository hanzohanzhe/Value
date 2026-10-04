"""Synthetic gate tests; their passing is not dispatch-comparison evidence."""
import copy
import unittest

from gridform_core import scientific_validation as validation
from gridform_core.doctoral_contract import thesis96_contract_identity


SMALL = ("source_oracle", "units", "physical_dispatch", "settlement", "investment",
         "planning", "commissioning", "weather", "nuclear_policy", "checkpoint_identity")
MONTH = SMALL + ("month_resume",)
YEAR = MONTH + ("annual_dispatch", "annual_cashflow", "annual_cost_carbon", "annual_funding")
TWO = YEAR + ("cross_year_state", "ownership_transitions", "capacity_pipeline", "two_year_dispatch")
TEN = TWO + ("ten_year_dispatch",)


class DoctoralReleaseGateTests(unittest.TestCase):
    def evidence(self):
        identity = {"thesis_sha256": thesis96_contract_identity()["source_sha256"],
            "candidate_sha256": "a" * 64, "oracle_sha256": "b" * 64, "inputs_sha256": "c" * 64}
        checks = {name: {"status": "passed", "artifact_sha256": "d" * 64,
            "comparisons": [{"id": name + ".fixture", "actual": 1.0, "expected": 1.0,
                             "unit": "MWh", "absolute_tolerance": 1e-9}]} for name in TEN}
        return {"schema_version": "value.doctoral-alignment-evidence/v1", "identity": identity,
            "engineering_tests_passed": True, "checks": checks, "exceptions": [],
            "unresolved_gates": [],
            "annual_coverage": [{"year": y, "period_count": 17520, "period_hours": .5,
                "start_period_index": 0, "end_period_index_exclusive": 17520,
                "annual_complete": True} for y in range(2025, 2035)]}

    def evaluate(self, evidence, tier="ten-year", expected=None):
        self.assertTrue(hasattr(validation, "validate_alignment_evidence"),
                        "strict doctoral evidence gate is not implemented")
        return validation.validate_alignment_evidence(evidence,
            expected_identity=expected or self.evidence()["identity"], required_tier=tier)

    def test_missing_or_unevaluated_annual_check_never_passes(self):
        for replacement in (None, {"status": "not_evaluated"}, {"status": "passed", "comparisons": []}):
            evidence = self.evidence()
            if replacement is None:
                del evidence["checks"]["annual_dispatch"]
            else:
                evidence["checks"]["annual_dispatch"] = replacement
            with self.subTest(replacement=replacement):
                result = self.evaluate(evidence)
                self.assertFalse(result["annual_verified"])
                self.assertFalse(result["multiyear_verified"])
                self.assertIn("annual_dispatch", result["blocking_checks"])

    def test_reported_pass_is_recomputed_from_raw_numbers_and_units(self):
        for field, value in (("actual", 2), ("unit", ""), ("actual", float("inf")), ("actual", True)):
            evidence = self.evidence()
            evidence["checks"]["settlement"]["comparisons"][0][field] = value
            with self.subTest(field=field, value=value):
                result = self.evaluate(evidence)
                self.assertNotEqual(result["validation_status"], "passed")
                self.assertIn("settlement", result["blocking_checks"])

    def test_wrong_identity_or_undeclared_exception_is_rejected(self):
        evidence = self.evidence()
        evidence["identity"]["candidate_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            self.evaluate(evidence)
        evidence = self.evidence()
        evidence["exceptions"] = ["F12"]
        with self.assertRaisesRegex(ValueError, "undeclared_exception"):
            self.evaluate(evidence)

    def test_complete_coverage_cannot_be_replaced_by_a_boolean_claim(self):
        for change in ({"period_count": 2}, {"annual_complete": "true"}, {"period_hours": 1}):
            evidence = self.evidence()
            evidence["annual_coverage"][0].update(change)
            with self.subTest(change=change):
                result = self.evaluate(evidence)
                self.assertFalse(result["multiyear_verified"])
                self.assertIn("annual_coverage", result["blocking_checks"])

    def test_small_scope_does_not_advertise_annual_or_multiyear_success(self):
        evidence = self.evidence()
        evidence["checks"] = {name: evidence["checks"][name] for name in SMALL}
        evidence["annual_coverage"] = []
        result = self.evaluate(evidence, "small")
        self.assertEqual(result["validation_status"], "passed")
        self.assertTrue(result["scoped_parity_passed"])
        self.assertFalse(result["annual_verified"])
        self.assertFalse(result["multiyear_verified"])

    def test_unresolved_scientific_gate_blocks_even_complete_fixture(self):
        evidence = self.evidence()
        evidence["unresolved_gates"] = ["storage_12_percent"]
        result = self.evaluate(evidence)
        self.assertNotEqual(result["validation_status"], "passed")
        self.assertIn("storage_12_percent", result["blocking_checks"])
        self.assertFalse(result["multiyear_verified"])

    def test_valid_synthetic_ten_year_record_exercises_positive_branch(self):
        result = self.evaluate(self.evidence())
        self.assertEqual(result["validation_status"], "passed")
        self.assertTrue(result["annual_verified"])
        self.assertTrue(result["multiyear_verified"])
        self.assertEqual(result["release_status"], "full_multiyear_verified")


if __name__ == "__main__":
    unittest.main()
