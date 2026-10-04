import unittest

from gridform_core.ensembles import (
    EnsembleSpecification, aggregate_children, derive_child_seed,
    expected_capacity_summary,
)


class EnsembleTests(unittest.TestCase):
    def test_child_seed_is_reproducible_and_master_seed_sensitive(self):
        first = EnsembleSpecification("study", "project-sha", "seeded_stochastic", 42, 3, ("capacity_mw",), 2)
        second = EnsembleSpecification("study", "project-sha", "seeded_stochastic", 42, 3, ("capacity_mw",), 2)
        self.assertEqual(first.children(), second.children())
        self.assertNotEqual(derive_child_seed(42, "study", 0), derive_child_seed(43, "study", 0))
        self.assertEqual(first.base_project_revision, second.base_project_revision)

    def test_expected_capacity_does_not_fabricate_failures(self):
        result = expected_capacity_summary([
            {"capacity_mw": 100, "success_probability": 0.25},
            {"capacity_mw": 50, "success_probability": 0.5},
        ])
        self.assertEqual(result["probability_weighted_capacity_mw"], 50)
        self.assertEqual(result["realised_failed_projects"], "not_applicable")

    def test_failed_and_missing_children_are_explicit(self):
        spec = EnsembleSpecification("study", "project-sha", "seeded_stochastic", 5, 3, ("cost",))
        ids = [row["child_run_id"] for row in spec.children()]
        result = aggregate_children(spec, [
            {"child_run_id": ids[0], "status": "completed", "metrics": {"cost": 4}},
            {"child_run_id": ids[1], "status": "failed", "metrics": {}},
        ], metric_names=("cost",))
        self.assertEqual(result["completed_children"], 1)
        self.assertEqual(result["failed_child_run_ids"], [ids[1]])
        self.assertEqual(result["missing_child_run_ids"], [ids[2]])
        self.assertEqual(result["scientific_status"], "exploratory")


if __name__ == "__main__":
    unittest.main()
