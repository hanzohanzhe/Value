import unittest

from gridform_core.weather_demand_ensembles import (
    ExperimentDesign, ProfileRealisation, experiment_rates, normalize_half_hour_year,
)


class WeatherDemandEnsembleTests(unittest.TestCase):
    def fixture(self, profile_id, dimension, year):
        return ProfileRealisation(profile_id, f"sha-{profile_id}", dimension, year, "UTC", 30)

    def test_factorial_membership_is_deterministic_and_complete(self):
        design = ExperimentDesign(
            "d", (self.fixture("w1", "weather", 2018), self.fixture("w2", "weather", 2019)),
            (self.fixture("low", "demand", 2030), self.fixture("high", "demand", 2030)),
        )
        self.assertEqual(design.members(), design.members())
        self.assertEqual(len(design.members()), 4)

    def test_leap_normalisation_conserves_annual_energy(self):
        source = [1.0] * 17_568
        result = normalize_half_hour_year(source, source_periods=17_568)
        self.assertEqual(len(result), 17_520)
        self.assertAlmostEqual(sum(result), sum(source), places=7)
        with self.assertRaises(ValueError):
            normalize_half_hour_year([1.0] * 17_519, source_periods=17_519)

    def test_execution_and_adequacy_rates_are_distinct(self):
        rates = experiment_rates([
            {"status": "completed", "adequate": True},
            {"status": "completed", "adequate": False},
            {"status": "failed", "adequate": False},
        ])
        self.assertAlmostEqual(rates["execution_completion_rate"]["value"], 2 / 3)
        self.assertEqual(rates["adequacy_success_rate"]["value"], 0.5)


if __name__ == "__main__":
    unittest.main()
