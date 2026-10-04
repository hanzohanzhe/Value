from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class Prompt104ComparisonEligibilityTests(unittest.TestCase):
    def _module(self):
        from gridform_core import comparison_eligibility

        return comparison_eligibility

    def _evidence(self, real=(10.0, 12.0)):
        module = self._module()
        return module.build_psm_comparison_input_evidence(
            year=2025,
            period_ids=("p0", "p1"),
            real_demand_mwh=real,
            forecast_demand_mwh=(11.0, 13.0),
            availability_mwh_by_technology={
                "solar": (2.0, 1.0),
                "CCGT": (8.0, 8.0),
            },
        )

    def _artifact(self, mode: str, evidence=None):
        module = self._module()
        return module.build_comparison_eligibility(
            run_id=f"run-{mode}",
            demand_authority_mode=mode,
            fixed_inputs={
                "data_pack_id": "research-pack",
                "start_year": 2025,
                "end_year": 2025,
                "initial_state_sha256": "a" * 64,
                "scientific_parameters_sha256": "b" * 64,
                "modules": {
                    "psm": "value-staged-bid-at-cost-psm@5.1.0",
                    "storage_cost": "dynamic-annual-storage-cost@1.0.0",
                    "investment": "scheme-c-investment@1.0.0",
                },
            },
            annual_input_evidence=(evidence or self._evidence(),),
            network_treatment={"balancing_module_id": mode},
        )

    @staticmethod
    def _reconciled_curtailment_artifact(
        *,
        method: str = "method-a",
        period_identity: str = "b" * 64,
        realised_input_identity: str = "c" * 64,
    ) -> dict[str, object]:
        return {
            "schema_version": "value.vre-curtailment-run-evidence/v1",
            "contract_version": "value.vre-curtailment-attribution/v2",
            "attribution_method_id": method,
            "capability_status": "reconciled",
            "data_pack_id": "research-pack",
            "network_pack_id": "network-pack",
            "initial_state_sha256": "a" * 64,
            "matched_counterfactual_proof": {
                "period_count": 17520,
                "period_sets_match": True,
                "realised_input_hashes_match": True,
                "period_identity_set_sha256": period_identity,
            },
            "counterfactual_realised_input_set_sha256": realised_input_identity,
            "annual_totals": [{
                "year": 2025,
                "period_count": 17520,
                "available_mwh": 100.0,
                "total_mwh": 12.0,
                "rate": 0.12,
                "redispatch_net_mwh": -2.0,
                "identity_residual_mwh": 0.0,
                "aggregate_tolerance_mwh": 1e-7,
            }],
        }

    def test_matched_copperplate_and_scaled_zonal_have_same_identity(self) -> None:
        module = self._module()
        copperplate = self._artifact(module.COPPERPLATE_SCENARIO_DEMAND)
        zonal = self._artifact(module.SCENARIO_SCALED_ZONAL_SHARES)
        self.assertEqual(
            copperplate["matched_input_identity_sha256"],
            zonal["matched_input_identity_sha256"],
        )
        pair = module.evaluate_network_comparison((copperplate, zonal))
        self.assertTrue(pair["network_cost_attribution_allowed"])
        self.assertEqual(pair["reason_code"], "matched_network_treatment_pair")

    def test_changed_demand_blocks_network_cost_attribution(self) -> None:
        module = self._module()
        copperplate = self._artifact(module.COPPERPLATE_SCENARIO_DEMAND)
        zonal = self._artifact(
            module.SCENARIO_SCALED_ZONAL_SHARES,
            self._evidence(real=(10.0, 12.5)),
        )
        pair = module.evaluate_network_comparison((copperplate, zonal))
        self.assertFalse(pair["network_cost_attribution_allowed"])
        self.assertEqual(pair["reason_code"], "matched_input_identity_mismatch")

    def test_period_id_names_are_audited_but_do_not_break_position_matched_inputs(self) -> None:
        module = self._module()
        copperplate_evidence = self._evidence()
        zonal_evidence = module.build_psm_comparison_input_evidence(
            year=2025,
            period_ids=("2022-01-01:01", "2022-01-01:02"),
            real_demand_mwh=(10.0, 12.0),
            forecast_demand_mwh=(11.0, 13.0),
            availability_mwh_by_technology={
                "solar": (2.0, 1.0),
                "CCGT": (8.0, 8.0),
            },
        )
        self.assertNotEqual(
            copperplate_evidence["period_ids_sha256"],
            zonal_evidence["period_ids_sha256"],
        )
        self.assertEqual(
            copperplate_evidence["input_identity_sha256"],
            zonal_evidence["input_identity_sha256"],
        )

        pair = module.evaluate_network_comparison((
            self._artifact(module.COPPERPLATE_SCENARIO_DEMAND, copperplate_evidence),
            self._artifact(module.SCENARIO_SCALED_ZONAL_SHARES, zonal_evidence),
        ))

        self.assertTrue(pair["network_cost_attribution_allowed"])

    def test_absolute_network_demand_is_never_a_network_cost_attribution_pair(self) -> None:
        module = self._module()
        copperplate = self._artifact(module.COPPERPLATE_SCENARIO_DEMAND)
        absolute = self._artifact(module.NETWORK_PACK_ABSOLUTE_DEMAND)
        self.assertFalse(absolute["network_cost_attribution_candidate"])
        self.assertIn("Independent zonal-demand study", absolute["interpretation_label"])
        pair = module.evaluate_network_comparison((copperplate, absolute))
        self.assertFalse(pair["network_cost_attribution_allowed"])
        self.assertEqual(pair["reason_code"], "incompatible_demand_authority_modes")

    def test_artifact_writer_is_deterministic_and_machine_readable(self) -> None:
        module = self._module()
        artifact = self._artifact(module.SCENARIO_SCALED_ZONAL_SHARES)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "comparison-eligibility.json"
            module.write_comparison_eligibility(destination, artifact)
            loaded = module.load_comparison_eligibility(destination)
        self.assertEqual(loaded, artifact)

    def test_curtailment_delta_requires_matching_method_and_inputs(self) -> None:
        module = self._module()
        network_pair = {
            "network_cost_attribution_allowed": True,
            "reason_code": "matched_network_treatment_pair",
        }

        def attribution(method: str) -> dict[str, object]:
            return {
                "schema_version": "value.vre-curtailment-run-evidence/v1",
                "contract_version": "value.vre-curtailment-attribution/v2",
                "attribution_method_id": method,
                "capability_status": "reconciled",
                "data_pack_id": "research-pack",
                "network_pack_id": "network-pack",
                "initial_state_sha256": "a" * 64,
                "matched_counterfactual_proof": {
                    "period_identity_set_sha256": "b" * 64,
                },
                "counterfactual_realised_input_set_sha256": "c" * 64,
                "annual_totals": [{
                    "year": 2025,
                    "total_mwh": 12.0,
                    "rate": 0.1,
                    "redispatch_net_mwh": -2.0,
                }],
            }

        allowed = module.evaluate_curtailment_comparison(
            network_pair=network_pair,
            attribution_artifacts=(attribution("method-a"), attribution("method-a")),
        )
        blocked = module.evaluate_curtailment_comparison(
            network_pair=network_pair,
            attribution_artifacts=(attribution("method-a"), attribution("method-b")),
        )

        self.assertTrue(allowed["metric_deltas_allowed"])
        self.assertFalse(blocked["metric_deltas_allowed"])
        self.assertEqual(blocked["reason_code"], "attribution_method_mismatch")
        self.assertEqual(blocked["side_by_side"][0]["annual_totals"][0]["total_mwh"], 12.0)

    def test_missing_curtailment_artifact_has_an_explicit_reason(self) -> None:
        module = self._module()
        result = module.evaluate_curtailment_comparison(
            network_pair={"network_cost_attribution_allowed": True},
            attribution_artifacts=({}, {"schema_version": "value.vre-curtailment-run-evidence/v1"}),
        )
        self.assertFalse(result["metric_deltas_allowed"])
        self.assertEqual(result["reason_code"], "attribution_artifact_missing")

    def test_period_and_realised_input_identity_have_separate_mismatch_reasons(self) -> None:
        module = self._module()
        network_pair = {"network_cost_attribution_allowed": True}
        baseline = self._reconciled_curtailment_artifact()
        period_changed = self._reconciled_curtailment_artifact(period_identity="d" * 64)
        input_changed = self._reconciled_curtailment_artifact(realised_input_identity="e" * 64)

        period_result = module.evaluate_curtailment_comparison(
            network_pair=network_pair,
            attribution_artifacts=(baseline, period_changed),
        )
        input_result = module.evaluate_curtailment_comparison(
            network_pair=network_pair,
            attribution_artifacts=(baseline, input_changed),
        )

        self.assertEqual(period_result["reason_code"], "period_identity_mismatch")
        self.assertEqual(input_result["reason_code"], "realised_input_identity_mismatch")

    def test_three_to_six_matching_attribution_artifacts_are_comparable(self) -> None:
        module = self._module()
        for count in (3, 6):
            with self.subTest(count=count):
                result = module.evaluate_curtailment_comparison(
                    network_pair={"network_cost_attribution_allowed": False},
                    attribution_artifacts=tuple(
                        self._reconciled_curtailment_artifact()
                        for _ in range(count)
                    ),
                )
                self.assertTrue(result["metric_deltas_allowed"])


if __name__ == "__main__":
    unittest.main()
