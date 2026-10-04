import unittest

from gridform_core.cem_identity import load_cem_identity
from gridform_core.cem_investment_policy import investment_mode, load_investment_eligibility


class CemIdentityTests(unittest.TestCase):
    def test_public_cem_declares_relationship_instead_of_hidden_parity(self):
        identity = load_cem_identity()
        self.assertEqual(identity["model_id"], "force-cem-v1")
        self.assertFalse(identity["numerical_reproduction_claim"])
        self.assertEqual(
            identity["relationship_to_retained_scheme_c"],
            "scheme_c_derived_declared_divergence",
        )
        self.assertGreaterEqual(len(identity["decision_stages"]), 7)

    def test_every_decision_stage_names_remaining_difference(self):
        for stage in load_cem_identity()["decision_stages"]:
            self.assertTrue(stage["status"])
            self.assertTrue(stage["remaining_difference"])

    def test_expansion_eligibility_is_explicit_and_hydro_is_site_constrained(self):
        policy = load_investment_eligibility()
        self.assertEqual(policy["default_mode"], "denied")
        self.assertEqual(investment_mode("solar"), "headroom_required")
        self.assertEqual(investment_mode("CCGT"), "explicit_uncapped")
        self.assertEqual(investment_mode("Nuclear"), "denied")
        self.assertEqual(investment_mode("pumped_hydro"), "site_data_required")
        self.assertEqual(investment_mode("Hydro_natural_flow"), "site_data_required")
        self.assertEqual(investment_mode("not-a-technology"), "denied")


if __name__ == "__main__":
    unittest.main()
