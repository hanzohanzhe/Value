import unittest

from gridform_core.scenario_comparison import _pair


def scenario(label, system_cost, storage_capacity):
    return {
        "label": label,
        "storage_cost_policy": label,
        "costs": {2025: {
            "Total_System_Cost_GBP": system_cost,
            "Cost_per_MWh_GBP": system_cost / 100.0,
            "Total_Operational_Cost_GBP": 20.0,
            "Total_Levelized_Capital_Cost_GBP": 80.0,
            "Total_Energy_Generated_MWh": 100.0,
        }},
        "capacities": {2025: {
            "Solar_Capacity_MW": 1.0,
            "Onshore_Capacity_MW": 2.0,
            "Offshore_Capacity_MW": 3.0,
            "Total_Storage_Capacity_MW": storage_capacity,
            "0.25c_battery_Capacity_MW": storage_capacity,
        }},
    }


class ScenarioComparisonTests(unittest.TestCase):
    def test_exact_pair_and_scientific_difference_are_distinguished(self):
        base = scenario("base", 100.0, 4.0)
        exact = _pair("exact", base, scenario("reference", 100.0, 4.0))
        changed = _pair("changed", scenario("dynamic", 110.0, 5.0), base)
        self.assertTrue(exact["all_declared_metrics_within_tolerance"])
        self.assertFalse(changed["all_declared_metrics_within_tolerance"])
        storage = next(row for row in changed["checks"] if row["metric"] == "Total_Storage_Capacity_MW")
        self.assertEqual(storage["unit"], "MW")
        self.assertEqual(storage["difference_left_minus_right"], 1.0)


if __name__ == "__main__":
    unittest.main()
