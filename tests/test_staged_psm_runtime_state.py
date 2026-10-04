import json
import unittest

from gridform_core.builtin.scheme_c_1000twh.psm_runtime_state import (
    StagedPeriodOutcome,
    StagedPSMRuntimeState,
)


def _summary(period: int) -> dict[str, object]:
    return {
        "period_id": f"2025-p{period}",
        "year": 2025,
        "period": period,
        "market_stage": "balancing",
        "forecast_demand_mwh": 10.0 + period,
        "real_demand_mwh": 11.0 + period,
        "accepted_supply_mwh": 11.0 + period,
        "storage_charge_mwh": 1.0,
        "storage_discharge_mwh": 2.0,
        "vre_available_mwh": 4.0,
        "vre_accepted_mwh": 3.0,
        "curtailed_mwh": 1.0,
        "import_mwh": 0.5,
        "clearing_price_gbp_per_mwh": 50.0,
        "physical_resource_cost_gbp": 100.0,
        "market_payment_gbp": 550.0,
        "blackout_mwh": 0.0,
        "energy_balance_residual_mwh": 0.0,
        "schema_version": "value.period-summary/v2",
        "units": {
            "energy": "MWh/period",
            "price": "GBP/MWh",
            "cost": "GBP",
        },
    }


def _solver_row(period: int) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "year": 2025,
        "period": period,
        "period_id": f"2025-p{period}",
        "phase_id": "primary_bid_cost",
        "module_id": "value-zonal-redispatch-balancing",
        "module_version": "2.0.0",
        "solver_contract_version": "value.zonal-lexicographic/v2",
        "scipy_version": "1.15.0",
        "highs_identity": f"scipy-embedded-highs:{'c' * 64}",
        "highs_binary_sha256": "c" * 64,
        "method": "highs-ds",
        "presolve": True,
        "primal_feasibility_tolerance": 1e-7,
        "dual_feasibility_tolerance": 1e-7,
        "ipm_optimality_tolerance": None,
        "objective_unit": "GBP",
        "optimum": 100.0 + period,
        "achieved_final_value": 100.0 + period,
        "degradation": 0.0,
        "computed_tolerance": 1e-6,
        "warning_ceiling": 1e-5,
        "validated_ceiling": 1e-4,
        "absolute_ceiling": 1e-3,
        "nonzero_term_count": 2,
        "absolute_term_scale": 100.0,
        "validation_class": "GO",
        "error_code": None,
        "declared_input_sha256": ("a" if period == 0 else "b") * 64,
    }


def _outcome(period: int) -> StagedPeriodOutcome:
    period_id = f"2025-p{period}"
    input_hash = ("a" if period == 0 else "b") * 64
    return StagedPeriodOutcome(
        run_id="run-1",
        year=2025,
        period_index=period,
        summary=_summary(period),
        ahead_result_sha256=("d" if period == 0 else "e") * 64,
        balancing_result_sha256=input_hash,
        post_period_soc_mwh_by_asset={"battery": 8.0 - period},
        storage_cost_state_by_asset={
            "battery": {
                "schema_version": "value.storage-cost-runtime-state/v1",
                "prepared_year": 2025,
                "pricing_basis": "previous_year_sales",
                "current": {
                    "year": 2025,
                    "sold_energy_mwh": 2.0 * (period + 1),
                    "dwell_weighted_sold_mwh_periods": 4.0 * (period + 1),
                },
            }
        },
        balancing_state={
            "schema_version": "value.zonal-redispatch-runtime-state/v1",
            "next_period_index": period + 1,
            "consumed_inputs": [
                {
                    "period_index": index,
                    "input_sha256": ("a" if index == 0 else "b") * 64,
                }
                for index in range(period + 1)
            ],
        },
        generation_mwh_by_asset={"wind": 3.0 + period},
        income_gbp_by_owner={"owner": 20.0 + period},
        operating_cost_gbp=100.0 + period,
        operating_cost_gbp_by_class={"wind": 5.0 + period},
        total_blackout_mwh=0.1 * period,
        total_excess_mwh=0.2 * period,
        total_export_mwh=0.3 * period,
        national_settlement_gbp_by_owner={"owner": 15.0 + period},
        redispatch_settlement_gbp_by_owner={"owner": 5.0 + period},
        actual_storage_discharge_mwh_by_asset={"battery": 2.0 + period},
        final_dispatch_mwh_by_physical_asset={"wind-zone": 3.0 + period},
        last_soc_mwh_by_base_asset={"battery": 8.0 - period},
        zonal_account_totals_gbp={"system_resource_cost_gbp": 100.0 + period},
        reliability_period_rows=(
            {
                "year": 2025,
                "period": period,
                "load_shedding_mwh_by_zone": {"gb": 0.1 * period},
            },
        ),
        solver_diagnostic_rows=(_solver_row(period),),
    )


class StagedPSMRuntimeStateTests(unittest.TestCase):
    def test_initial_uses_canonical_empty_balancing_state(self) -> None:
        state = StagedPSMRuntimeState.initial(
            run_id="run-1", year=2025, soc_mwh_by_asset={}
        )

        self.assertEqual(
            state.balancing_state,
            {
                "schema_version": "value.zonal-redispatch-runtime-state/v1",
                "next_period_index": 0,
                "consumed_inputs": (),
            },
        )

    def test_json_round_trip_resumes_with_identical_annual_result_inputs(self) -> None:
        first = _outcome(0)
        second = _outcome(1)
        initial = StagedPSMRuntimeState.initial(
            run_id="run-1",
            year=2025,
            soc_mwh_by_asset={"battery": 9.0},
            storage_cost_state_by_asset={},
            balancing_state={
                "schema_version": "value.zonal-redispatch-runtime-state/v1",
                "next_period_index": 0,
                "consumed_inputs": [],
            },
        )
        after_first = initial.apply_period(first)
        uninterrupted = after_first.apply_period(second)

        restored = StagedPSMRuntimeState.from_dict(
            json.loads(json.dumps(after_first.to_dict(), sort_keys=True))
        )

        self.assertEqual(restored.apply_period(second).to_dict(), uninterrupted.to_dict())
        self.assertEqual(uninterrupted.summaries, (_summary(0), _summary(1)))
        self.assertEqual(uninterrupted.storage_cost_state_by_asset, second.storage_cost_state_by_asset)
        self.assertEqual(uninterrupted.balancing_state, second.balancing_state)
        self.assertEqual(uninterrupted.solver_diagnostic_rows, (_solver_row(0), _solver_row(1)))
        self.assertEqual(uninterrupted.final_dispatch_mwh_by_physical_asset, {"wind-zone": 7.0})

    def test_rejects_discontinuous_or_non_json_runtime_state(self) -> None:
        initial = StagedPSMRuntimeState.initial(
            run_id="run-1", year=2025, soc_mwh_by_asset={}
        )
        bad = _outcome(1)
        with self.assertRaisesRegex(ValueError, "next period"):
            initial.apply_period(bad)
        payload = initial.to_dict()
        payload["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            StagedPSMRuntimeState.from_dict(payload)
        payload = initial.to_dict()
        payload["operating_cost_gbp"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            StagedPSMRuntimeState.from_dict(payload)

    def test_rejects_changed_identity_and_duplicate_period_ids(self) -> None:
        initial = StagedPSMRuntimeState.initial(
            run_id="run-1", year=2025, soc_mwh_by_asset={}
        )
        first = initial.apply_period(_outcome(0))
        duplicate = _outcome(1).to_dict()
        duplicate["summary"] = _summary(0)
        duplicate["summary"]["period"] = 1
        duplicate["solver_diagnostic_rows"][0]["period_id"] = "2025-p0"
        with self.assertRaisesRegex(ValueError, "duplicate period_id"):
            first.apply_period(StagedPeriodOutcome.from_dict(duplicate))
        changed = _outcome(1).to_dict()
        changed["run_id"] = "other-run"
        with self.assertRaisesRegex(ValueError, "run"):
            first.apply_period(StagedPeriodOutcome.from_dict(changed))

    def test_rejects_mismatched_nested_balancing_state(self) -> None:
        state = StagedPSMRuntimeState.initial(
            run_id="run-1", year=2025, soc_mwh_by_asset={}
        ).apply_period(_outcome(0))
        mutations = (
            ("schema_version", "wrong-schema"),
            ("next_period_index", 0),
        )
        for field_name, value in mutations:
            with self.subTest(field_name=field_name):
                payload = state.to_dict()
                payload["balancing_state"][field_name] = value
                with self.assertRaises(ValueError):
                    StagedPSMRuntimeState.from_dict(payload)

        payload = state.to_dict()
        payload["balancing_state"]["consumed_inputs"][0]["input_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            StagedPSMRuntimeState.from_dict(payload)

    def test_rejects_foreign_or_out_of_order_annual_evidence(self) -> None:
        outcome_payload = _outcome(0).to_dict()
        for field_name, value in (
            ("run_id", "foreign-run"),
            ("year", 2026),
            ("period", 1),
            ("period_id", "foreign-period"),
        ):
            with self.subTest(solver_field=field_name):
                payload = json.loads(json.dumps(outcome_payload))
                payload["solver_diagnostic_rows"][0][field_name] = value
                with self.assertRaises(ValueError):
                    StagedPeriodOutcome.from_dict(payload)

        reliability = json.loads(json.dumps(outcome_payload))
        reliability["reliability_period_rows"][0]["period"] = 1
        with self.assertRaises(ValueError):
            StagedPeriodOutcome.from_dict(reliability)

        initial = StagedPSMRuntimeState.initial(
            run_id="run-1", year=2025, soc_mwh_by_asset={}
        )
        aggregate = initial.apply_period(_outcome(0)).apply_period(_outcome(1)).to_dict()
        aggregate_mutations = (
            (
                "reordered solver evidence",
                lambda item: item["solver_diagnostic_rows"].reverse(),
            ),
            (
                "future solver evidence",
                lambda item: item["solver_diagnostic_rows"][1].update(period=2),
            ),
            (
                "skipped reliability evidence",
                lambda item: item["reliability_period_rows"].pop(0),
            ),
            (
                "future reliability evidence",
                lambda item: item["reliability_period_rows"][1].update(period=2),
            ),
        )
        for label, mutate in aggregate_mutations:
            with self.subTest(aggregate_evidence=label):
                invalid = json.loads(json.dumps(aggregate))
                mutate(invalid)
                with self.assertRaises(ValueError):
                    StagedPSMRuntimeState.from_dict(invalid)

    def test_nested_json_is_detached_from_caller_aliases(self) -> None:
        payload = _outcome(0).to_dict()
        outcome = StagedPeriodOutcome.from_dict(payload)
        before = outcome.to_dict()

        payload["summary"]["units"]["energy"] = "corrupted"
        payload["balancing_state"]["consumed_inputs"][0]["input_sha256"] = "f" * 64
        payload["storage_cost_state_by_asset"]["battery"]["current"][
            "sold_energy_mwh"
        ] = float("nan")
        payload["reliability_period_rows"][0]["load_shedding_mwh_by_zone"][
            "gb"
        ] = 99.0

        self.assertEqual(outcome.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
