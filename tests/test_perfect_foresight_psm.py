from __future__ import annotations

import unittest

from gridform_core.perfect_foresight_psm import (
    PerfectForesightInputError,
    PerfectForesightPSM,
)
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)


def psm_input(
    demand,
    resources,
    storage=(),
    *,
    terminal="cyclic",
    allow_blackout=True,
    voll=10_000.0,
):
    periods = len(demand)
    return PSMInput(
        "test-run",
        2025,
        "synthetic",
        OperatingState(2025, (), ()),
        1.0,
        {},
        chronology=ChronologicalPSMData(
            tuple(f"p{index}" for index in range(periods)),
            tuple(float(value) for value in demand),
            tuple(resources),
            tuple(storage),
            voll,
            terminal_soc_rule=terminal,
            allow_blackout=allow_blackout,
        ),
    )


class PerfectForesightPSMTests(unittest.TestCase):
    def test_thermal_import_merit_order_and_blackout(self):
        model_input = psm_input(
            [12.0],
            [
                DispatchResource("thermal", "ccgt", "thermal", 5, 50, (1,)),
                DispatchResource("import", "interconnector", "import", 5, 30, (1,)),
            ],
        )
        result = PerfectForesightPSM().run(model_input)
        self.assertAlmostEqual(result.generation_mwh_by_asset["import"], 5.0)
        self.assertAlmostEqual(result.generation_mwh_by_asset["thermal"], 5.0)
        self.assertAlmostEqual(result.total_blackout_mwh, 2.0)
        self.assertAlmostEqual(result.total_operational_cost_gbp, 20_400.0)
        self.assertAlmostEqual(result.period_summaries[0].energy_balance_residual_mwh, 0.0)

    def test_vre_curtailment_and_storage_arbitrage(self):
        model_input = psm_input(
            [5.0, 10.0],
            [
                DispatchResource("vre", "wind", "vre", 10, 0, (1, 0)),
                DispatchResource("thermal", "ccgt", "thermal", 10, 100, (1, 1)),
            ],
            [StorageDispatchResource("battery", "1c", 5, 5, 5, 1.0, 1.0, 0.0, 2.0)],
        )
        result = PerfectForesightPSM().run(model_input)
        diagnostics = result.extensions["solver_diagnostics"]
        self.assertAlmostEqual(result.period_summaries[0].storage_charge_mwh, 5.0, places=6)
        self.assertAlmostEqual(result.period_summaries[1].storage_discharge_mwh, 5.0, places=6)
        self.assertAlmostEqual(result.total_excess_mwh, 0.0, places=6)
        self.assertLessEqual(diagnostics["max_simultaneous_charge_discharge_mwh"], 1e-7)
        self.assertAlmostEqual(
            result.extensions["physical_operating_cost_components_gbp"]["storage_variable_degradation"],
            10.0,
        )

    def test_efficiency_and_energy_limit(self):
        model_input = psm_input(
            [0.0, 4.0],
            [
                DispatchResource("vre", "wind", "vre", 10, 0, (1, 0)),
                DispatchResource("thermal", "ccgt", "thermal", 10, 100, (1, 1)),
            ],
            [StorageDispatchResource("battery", "1c", 10, 10, 4, 0.8, 0.5, 0.0)],
        )
        result = PerfectForesightPSM().run(model_input)
        self.assertAlmostEqual(result.period_summaries[0].storage_charge_mwh, 5.0, places=6)
        self.assertAlmostEqual(result.period_summaries[1].storage_discharge_mwh, 2.0, places=6)
        self.assertAlmostEqual(result.generation_mwh_by_asset["thermal"], 2.0, places=6)

    def test_24_and_168_hour_chronologies(self):
        for periods in (24, 168):
            demand = [5.0] * periods
            availability = tuple(1.0 if index % 24 < 12 else 0.0 for index in range(periods))
            model_input = psm_input(
                demand,
                [
                    DispatchResource("solar", "solar", "vre", 8, 0, availability),
                    DispatchResource("thermal", "ccgt", "thermal", 10, 70, (1,)),
                ],
                [StorageDispatchResource("pumped", "pumped_hydro", 2, 2, 8, 0.87, 0.87, 4.0, 0.0)],
            )
            result = PerfectForesightPSM().run(model_input)
            self.assertEqual(len(result.period_summaries), periods)
            self.assertLessEqual(
                result.extensions["solver_diagnostics"]["max_constraint_residual_mwh"],
                1e-6,
            )
            self.assertEqual(
                result.extensions["physical_operating_cost_components_gbp"]["storage_variable_degradation"],
                0.0,
            )

    def test_negative_cost_regime_is_rejected(self):
        model_input = psm_input(
            [1.0],
            [DispatchResource("bad", "thermal", "thermal", 2, -1, (1,))],
        )
        with self.assertRaisesRegex(PerfectForesightInputError, "Negative-cost"):
            PerfectForesightPSM().run(model_input)

    def test_storage_offer_policy_is_not_applied(self):
        model_input = psm_input(
            [1.0],
            [DispatchResource("thermal", "thermal", "thermal", 1, 1, (1,))],
        )
        result = PerfectForesightPSM().run(model_input)
        self.assertEqual(result.extensions["storage_offer_rule"], "not_applicable")


if __name__ == "__main__":
    unittest.main()

