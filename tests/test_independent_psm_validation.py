from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from gridform_core.perfect_foresight_psm import PerfectForesightPSM
from gridform_core.v2.contracts import (
    ChronologicalPSMData,
    DispatchResource,
    OperatingState,
    PSMInput,
    StorageDispatchResource,
)
from gridform_validation.independent_oracle import (
    audit_solution,
    solve_chronology,
    solver_identity,
)


def case(periods: int, seed: int = 41) -> ChronologicalPSMData:
    rng = np.random.default_rng(seed)
    demand = 7.0 + rng.uniform(0.2, 2.0, periods)
    vre = np.clip(
        0.5 + 0.45 * np.sin(np.arange(periods) * 2 * np.pi / 24), 0, 1
    )
    import_cost = 35.0 + rng.uniform(0.1, 2.0, periods)
    return ChronologicalPSMData(
        tuple(f"p{index}" for index in range(periods)),
        tuple(float(value) for value in demand),
        (
            DispatchResource("wind", "wind", "vre", 10.0, 0.0, tuple(vre)),
            DispatchResource("import", "interconnector", "import", 3.0, 36.0, (1.0,), tuple(import_cost)),
            DispatchResource("ccgt", "ccgt", "thermal", 8.0, 72.0, (1.0,)),
        ),
        (
            StorageDispatchResource("battery", "1c", 2.0, 2.0, 4.0, 0.9, 0.9, 2.0, 1.5),
            StorageDispatchResource("pumped", "pumped_hydro", 1.0, 1.0, 6.0, 0.87, 0.87, 3.0, 0.0),
        ),
        10_000.0,
        terminal_soc_rule="cyclic",
    )


def production(data: ChronologicalPSMData, root: Path):
    artifact_root = root / "artifacts"
    model_input = PSMInput(
        "independent-validation",
        2025,
        "synthetic",
        OperatingState(2025, (), ()),
        1.0,
        {},
        chronology=data,
        extensions={"artifact_directory": str(artifact_root)},
    )
    result = PerfectForesightPSM().run(model_input)
    arrays = dict(np.load(artifact_root / "perfect-foresight-2025.npz"))
    return result, {
        "resource": arrays["resource_dispatch_mwh"],
        "charge": arrays["storage_charge_mwh"],
        "discharge": arrays["storage_discharge_mwh"],
        "soc": arrays["storage_soc_mwh"],
        "blackout": arrays["blackout_mwh"],
    }


class IndependentPSMValidationTests(unittest.TestCase):
    def test_distinct_pulp_cbc_oracle_is_available(self):
        identity = solver_identity()
        self.assertEqual(identity["solver"], "COIN-OR CBC")
        self.assertIn("PuLP", identity["modeler"])
        self.assertNotIn("HiGHS", identity["solver"])

    def test_24_and_168_hour_production_optima_match_independent_oracle(self):
        for periods in (24, 168):
            data = case(periods)
            with tempfile.TemporaryDirectory() as temporary:
                result, arrays = production(data, Path(temporary))
                oracle = solve_chronology(data, 1.0)
            objective = result.extensions["solver_diagnostics"]["reported_objective_gbp"]
            self.assertLessEqual(abs(objective - oracle.objective_gbp), 1e-4)
            self.assertLessEqual(oracle.max_balance_residual_mwh, 1e-6)
            self.assertLessEqual(oracle.max_soc_residual_mwh, 1e-6)
            self.assertTrue(audit_solution(data, 1.0, arrays)["feasible"])
            self.assertAlmostEqual(
                float(arrays["blackout"].sum()), float(oracle.blackout_mwh.sum()), places=6
            )

    def test_random_convex_cases_match(self):
        for seed in (7, 19, 101):
            data = case(24, seed)
            with tempfile.TemporaryDirectory() as temporary:
                result, _arrays = production(data, Path(temporary))
                oracle = solve_chronology(data, 1.0)
            self.assertLessEqual(
                abs(
                    result.extensions["solver_diagnostics"]["reported_objective_gbp"]
                    - oracle.objective_gbp
                ),
                1e-4,
            )

    def test_required_constraint_mutations_all_fail(self):
        data = case(24)
        with tempfile.TemporaryDirectory() as temporary:
            _result, base = production(data, Path(temporary))

        mutations = {}
        changed = {key: value.copy() for key, value in base.items()}
        changed["resource"][0, 0] += 1.0
        mutations["demand_balance"] = audit_solution(data, 1.0, changed)

        changed = {key: value.copy() for key, value in base.items()}
        battery = replace(data.storage[0], charge_efficiency=0.5)
        efficiency_data = replace(data, storage=(battery, data.storage[1]))
        mutations["storage_efficiency"] = audit_solution(efficiency_data, 1.0, changed)

        changed = {key: value.copy() for key, value in base.items()}
        changed["soc"][0, 0] = data.storage[0].energy_capacity_mwh + 1.0
        mutations["storage_energy_capacity"] = audit_solution(data, 1.0, changed)

        changed = {key: value.copy() for key, value in base.items()}
        changed["soc"][0, -1] += 1.0
        mutations["terminal_soc"] = audit_solution(data, 1.0, changed)

        changed = {key: value.copy() for key, value in base.items()}
        changed["resource"][1, 0] = data.resources[1].capacity_mw + 1.0
        mutations["import_bound"] = audit_solution(data, 1.0, changed)

        self.assertEqual(set(mutations), {
            "demand_balance", "storage_efficiency", "storage_energy_capacity",
            "terminal_soc", "import_bound",
        })
        for name, report in mutations.items():
            self.assertFalse(report["feasible"], name)


if __name__ == "__main__":
    unittest.main()
