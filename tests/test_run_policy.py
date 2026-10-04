import unittest

from gridform_core.application import _years_for_mode
from gridform_core.run_policy import RUN_POLICIES, resolve_run_policy


PROJECT = {"start_year": 2025, "end_year": 2034}


class RunPolicyTests(unittest.TestCase):
    def test_all_entry_modes_have_one_policy(self):
        self.assertEqual(set(RUN_POLICIES), {
            "smoke", "two_year_smoke", "validation_24h", "validation_168h",
            "tutorial", "two_year", "full",
        })
        expected = {
            "smoke": (2025, 2025, 2),
            "two_year_smoke": (2025, 2026, 2),
            "validation_24h": (2025, 2025, 48),
            "validation_168h": (2025, 2025, 336),
            "tutorial": (2025, 2026, 48),
            "two_year": (2025, 2026, 17_520),
            "full": (2025, 2034, 17_520),
        }
        for mode, values in expected.items():
            with self.subTest(mode=mode):
                project = (
                    {"start_year": 2025, "end_year": 2026}
                    if mode == "tutorial"
                    else PROJECT
                )
                self.assertEqual(_years_for_mode(project, mode), values)
                policy = resolve_run_policy(mode)
                self.assertEqual(
                    policy.to_dict(project)["total_periods"],
                    values[2] * (values[1] - values[0] + 1),
                )

    def test_short_modes_cannot_publish_annual_economics(self):
        self.assertFalse(resolve_run_policy("smoke").annual_economics_candidate)
        self.assertFalse(resolve_run_policy("two_year_smoke").annual_economics_candidate)
        self.assertFalse(resolve_run_policy("validation_24h").annual_economics_candidate)
        self.assertFalse(resolve_run_policy("validation_168h").annual_economics_candidate)
        self.assertFalse(resolve_run_policy("tutorial").annual_economics_candidate)
        self.assertTrue(resolve_run_policy("two_year").annual_economics_candidate)

    def test_only_independent_validation_modes_require_pre_clearing_declarations(self):
        required = {
            mode for mode, policy in RUN_POLICIES.items()
            if policy.requires_declared_clearing_inputs
        }
        self.assertEqual(required, {"validation_24h", "validation_168h"})

    def test_two_year_mode_rejects_one_year_project(self):
        with self.assertRaisesRegex(ValueError, "at least two years"):
            resolve_run_policy("two_year").years({"start_year": 2025, "end_year": 2025})


if __name__ == "__main__":
    unittest.main()
