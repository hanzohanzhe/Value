import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from gridform_core.comparison_identity import build_comparison_identity
from gridform_core.methodology import resolve_methodology

from gridform_core.results_summary import (
    build_run_summary,
    compare_run_summaries,
    validate_vre_curtailment_attribution,
)


class ResultsSummaryTests(unittest.TestCase):
    @staticmethod
    def attribution(*, year=2025, period_count=17520) -> dict[str, object]:
        return {
            "schema_version": "value.vre-curtailment-run-evidence/v1",
            "contract_version": "value.vre-curtailment-attribution/v2",
            "attribution_method_id": "value.pro-rata-technology-bid-tranche/v1",
            "capability_status": "reconciled",
            "data_pack_id": "pack",
            "network_pack_id": "network",
            "initial_state_sha256": "a" * 64,
            "matched_counterfactual_proof": {
                "period_count": period_count,
                "period_sets_match": True,
                "realised_input_hashes_match": True,
                "period_identity_set_sha256": "b" * 64,
            },
            "counterfactual_realised_input_set_sha256": "c" * 64,
            "annual_totals": [{
                "year": year,
                "period_count": period_count,
                "available_mwh": 100.0,
                "economic_mwh": 12.0,
                "forecast_added_mwh": 0.0,
                "forecast_avoided_mwh": 0.0,
                "redispatch_added_mwh": 0.0,
                "redispatch_avoided_mwh": 0.0,
                "total_mwh": 12.0,
                "rate": 0.12,
                "redispatch_net_mwh": 0.0,
                "identity_residual_mwh": 0.0,
                "aggregate_tolerance_mwh": 1e-7,
            }],
            "maximum_absolute_period_residual_mwh": 0.0,
            "maximum_period_tolerance_mwh": 1e-7,
        }
    def summary(self, run_id, storage, cost="cost-v1", psm="psm", mode="full", periods=17520, *, balancing="copperplate", eligibility=None):
        result = {
            "run": {
                "run_id": run_id,
                "periods_per_year": periods,
                "scientific_status": "passed",
                "mode": mode,
                "start_year": 2025,
                "end_year": 2025,
            },
            "definitions": {"cost": cost, "carbon": "carbon-v1", "terminal_policy": "report_only", "currency_base_year": 2025},
            "modules": {"psm": psm, "storage_cost": storage, "investment": "i", "balancing": balancing},
            "annual": [{"year": 2025, "metrics": {"cem_system_cost_gbp": {"value": 1.0, "unit": "GBP"}}}],
        }
        # A controlled comparison must carry real frozen records, rather than
        # infer input equality from module IDs or absent fields.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            selected = {slot: module for slot, module in result["modules"].items() if module is not None}
            project = {"modules": selected, "parameters": {}, "selected_extensions": []}
            pack = {"bindings": {"demand": {"sha256": "a" * 64, "format": "csv"}}}
            modules = [{"slot": slot, "module_id": module, "module_version": "1", "contract_version": "v1", "entry_point": "test:Module", "source_sha256": hashlib.sha256(str(module).encode()).hexdigest()} for slot, module in selected.items()]
            snapshot = {"state": "ready", "project_sha256": digest(project), "pack_manifest_sha256": digest(pack), "modules": modules, "objects": [{"role": "demand", "sha256": "a" * 64}]}
            for relative, payload in [("input-snapshot/project.json", project), ("input-snapshot/pack/manifest.json", pack), ("input-snapshot/snapshot.json", snapshot)]:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload))
            status = {"mode": mode, "run_policy": {"start_year": 2025, "end_year": 2025, "periods_per_year": periods}}
            # Runs recorded after X0 S9 carry their methodology in the method dimension.
            resolved = {"scientific_parameters": {}, "runtime_controls": {}, "extensions": {"methodology": resolve_methodology().to_dict()}}
            result["comparison_identity"] = build_comparison_identity(root, status, resolved)
        if eligibility is not None:
            result["comparison_eligibility"] = eligibility
        return result

    def test_clean_storage_policy_comparison(self):
        result = compare_run_summaries([self.summary("a", "dynamic"), self.summary("b", "legacy")])
        self.assertTrue(result["clean_storage_policy_comparison"])
        self.assertTrue(result["causal_claim_allowed"])

    def test_definition_mismatch_blocks_delta(self):
        result = compare_run_summaries([self.summary("a", "dynamic"), self.summary("b", "legacy", cost="other")])
        self.assertFalse(result["metric_deltas_allowed"])
        self.assertFalse(result["causal_claim_allowed"])

    def test_perfect_foresight_is_not_a_tariff(self):
        result = compare_run_summaries([self.summary("a", "dynamic"), self.summary("b", None, psm="perfect")])
        self.assertEqual(result["storage_pricing_interpretation"], "not_applicable_different_psm_formulation")

    def test_tutorial_comparison_exposes_identity_but_withholds_annual_deltas(self):
        result = compare_run_summaries([
            self.summary("a", "dynamic", mode="tutorial", periods=48),
            self.summary("b", "legacy", mode="tutorial", periods=48),
        ])
        self.assertTrue(result["clean_storage_policy_comparison"])
        self.assertEqual(result["comparison_scope"], "teaching_diagnostic")
        self.assertFalse(result["causal_claim_allowed"])
        self.assertFalse(result["metric_deltas_allowed"])
        self.assertTrue(result["annual_metrics_withheld"])
        self.assertEqual(result["annual_comparison"], [])
        self.assertTrue(all(summary["annual"] == [] for summary in result["runs"]))
        self.assertIn("not annual economics", result["warning"].lower())

    def test_matched_network_pair_allows_network_cost_attribution(self):
        from gridform_core.comparison_eligibility import (
            COPPERPLATE_SCENARIO_DEMAND,
            SCENARIO_SCALED_ZONAL_SHARES,
            build_comparison_eligibility,
        )

        fixed = {"data_pack_id": "pack", "initial_state_sha256": "a" * 64}
        annual = ({"year": 2025, "input_identity_sha256": "b" * 64},)
        copperplate = build_comparison_eligibility(
            run_id="a",
            demand_authority_mode=COPPERPLATE_SCENARIO_DEMAND,
            fixed_inputs=fixed,
            annual_input_evidence=annual,
            network_treatment={"balancing_module_id": "copperplate"},
        )
        zonal = build_comparison_eligibility(
            run_id="b",
            demand_authority_mode=SCENARIO_SCALED_ZONAL_SHARES,
            fixed_inputs=fixed,
            annual_input_evidence=annual,
            network_treatment={"balancing_module_id": "zonal"},
        )
        result = compare_run_summaries([
            self.summary("a", "dynamic", balancing="copperplate", eligibility=copperplate),
            self.summary("b", "dynamic", balancing="zonal", eligibility=zonal),
        ])
        self.assertTrue(result["network_cost_attribution_allowed"])
        self.assertTrue(result["causal_claim_allowed"])
        self.assertEqual(
            result["network_comparison"]["reason_code"],
            "matched_network_treatment_pair",
        )

    def test_missing_attribution_is_null_in_annual_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "model-output"
            (output / "ledgers").mkdir(parents=True)
            (root / "status.json").write_text(json.dumps({
                "id": "annual-run", "mode": "full", "status": "completed",
                "run_policy": {"periods_per_year": 17520, "start_year": 2025, "end_year": 2025}, "results": [],
            }), encoding="utf-8")
            (output / "ledgers" / "annual-cost-ledger.json").write_text(json.dumps({
                "definition_id": "cost-v1",
                "years": [{"year": 2025, "lines": []}],
            }), encoding="utf-8")

            summary = build_run_summary(root)

        metrics = summary["annual"][0]["metrics"]
        self.assertIsNone(metrics["vre_curtailment_mwh"]["value"])
        self.assertIsNone(metrics["vre_curtailment_rate"]["value"])
        self.assertIsNone(metrics["redispatch_net_impact_mwh"]["value"])
        self.assertEqual(
            metrics["vre_curtailment_mwh"]["reason_code"],
            "vre_curtailment_attribution_artifact_missing",
        )

    def test_reconciled_attribution_populates_only_compact_annual_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "model-output"
            (output / "ledgers").mkdir(parents=True)
            (output / "network").mkdir(parents=True)
            (root / "status.json").write_text(json.dumps({
                "id": "annual-run", "mode": "full", "status": "completed",
                "run_policy": {"periods_per_year": 17520, "start_year": 2025, "end_year": 2025}, "results": [],
            }), encoding="utf-8")
            (output / "ledgers" / "annual-cost-ledger.json").write_text(json.dumps({
                "definition_id": "cost-v1",
                "years": [{"year": 2025, "lines": []}],
            }), encoding="utf-8")
            artifact = self.attribution()
            artifact["annual_totals"][0]["rate"] = 0.12  # type: ignore[index]
            (output / "network" / "vre-curtailment-attribution.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )

            summary = build_run_summary(root)

        metrics = summary["annual"][0]["metrics"]
        self.assertEqual(metrics["vre_curtailment_mwh"]["value"], 12.0)
        self.assertEqual(metrics["vre_curtailment_rate"]["value"], 0.12)
        self.assertEqual(metrics["redispatch_net_impact_mwh"]["value"], 0.0)
        self.assertEqual(metrics["vre_curtailment_mwh"]["status"], "reconciled")

    def test_partial_or_invalid_annual_evidence_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "model-output"
            (output / "ledgers").mkdir(parents=True)
            (output / "network").mkdir(parents=True)
            (root / "status.json").write_text(json.dumps({
                "id": "annual-run", "mode": "full", "status": "completed",
                "run_policy": {"periods_per_year": 17520, "start_year": 2025, "end_year": 2025}, "results": [],
            }), encoding="utf-8")
            (output / "ledgers" / "annual-cost-ledger.json").write_text(json.dumps({
                "definition_id": "cost-v1",
                "years": [{"year": 2025, "lines": []}],
            }), encoding="utf-8")
            artifact = self.attribution(period_count=12)
            artifact["matched_counterfactual_proof"]["period_count"] = 17520  # type: ignore[index]
            (output / "network" / "vre-curtailment-attribution.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )

            summary = build_run_summary(root)

        metrics = summary["annual"][0]["metrics"]
        self.assertIsNone(metrics["vre_curtailment_mwh"]["value"])
        self.assertEqual(
            metrics["vre_curtailment_mwh"]["reason_code"],
            "vre_curtailment_period_count_invalid",
        )

    def test_run_policy_years_not_ledger_rows_define_required_annual_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "model-output"
            (output / "ledgers").mkdir(parents=True)
            (output / "network").mkdir(parents=True)
            (root / "status.json").write_text(json.dumps({
                "id": "two-year-annual-run", "mode": "full", "status": "completed",
                "run_policy": {
                    "periods_per_year": 17520,
                    "start_year": 2025,
                    "end_year": 2026,
                },
                "results": [],
            }), encoding="utf-8")
            (output / "ledgers" / "annual-cost-ledger.json").write_text(json.dumps({
                "definition_id": "cost-v1",
                "years": [{"year": 2025, "lines": []}],
            }), encoding="utf-8")
            (output / "network" / "vre-curtailment-attribution.json").write_text(
                json.dumps(self.attribution()), encoding="utf-8"
            )

            summary = build_run_summary(root)

        metrics = summary["annual"][0]["metrics"]
        self.assertIsNone(metrics["vre_curtailment_mwh"]["value"])
        self.assertEqual(
            metrics["vre_curtailment_mwh"]["reason_code"],
            "vre_curtailment_counterfactual_proof_invalid",
        )

    def test_strict_validator_rejects_duplicate_expected_years(self) -> None:
        result = validate_vre_curtailment_attribution(
            self.attribution(),
            mode="full",
            periods_per_year=17520,
            expected_years=(2025, 2025),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reason_code"], "vre_curtailment_expected_year_set_invalid"
        )

    def test_strict_validator_recomputes_gross_annual_identity(self) -> None:
        artifact = self.attribution()
        artifact["annual_totals"][0]["economic_mwh"] = 13.0  # type: ignore[index]

        result = validate_vre_curtailment_attribution(
            artifact,
            mode="full",
            periods_per_year=17520,
            expected_years=(2025,),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reason_code"], "vre_curtailment_identity_residual_inconsistent"
        )

    def test_strict_validator_rejects_inconsistent_redispatch_net(self) -> None:
        artifact = self.attribution()
        artifact["annual_totals"][0]["redispatch_net_mwh"] = 999.0  # type: ignore[index]

        result = validate_vre_curtailment_attribution(
            artifact,
            mode="full",
            periods_per_year=17520,
            expected_years=(2025,),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reason_code"], "vre_curtailment_redispatch_net_inconsistent"
        )

    def test_strict_validator_rejects_run_maximum_residual_above_tolerance(self) -> None:
        artifact = self.attribution()
        artifact["maximum_absolute_period_residual_mwh"] = 1.0
        artifact["maximum_period_tolerance_mwh"] = 0.1

        result = validate_vre_curtailment_attribution(
            artifact,
            mode="full",
            periods_per_year=17520,
            expected_years=(2025,),
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(
            result["reason_code"], "vre_curtailment_maximum_period_residual_invalid"
        )

    def test_strict_validator_rejects_duplicate_missing_and_extra_annual_years(self) -> None:
        baseline = self.attribution()
        duplicate = self.attribution()
        duplicate["annual_totals"].append(dict(duplicate["annual_totals"][0]))  # type: ignore[index]
        missing = self.attribution()
        missing["annual_totals"] = []
        extra = self.attribution()
        extra_row = dict(extra["annual_totals"][0])  # type: ignore[index]
        extra_row["year"] = 2026
        extra["annual_totals"].append(extra_row)  # type: ignore[index]
        for artifact in (duplicate, missing, extra):
            with self.subTest(artifact=artifact):
                result = validate_vre_curtailment_attribution(
                    artifact,
                    mode="full",
                    periods_per_year=17520,
                    expected_years=(2025,),
                )
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(
                    result["reason_code"], "vre_curtailment_annual_year_set_invalid"
                )

    def test_strict_validator_accepts_complete_multi_year_evidence(self) -> None:
        artifact = self.attribution()
        second = dict(artifact["annual_totals"][0])  # type: ignore[index]
        second["year"] = 2026
        artifact["annual_totals"].append(second)  # type: ignore[index]
        artifact["matched_counterfactual_proof"]["period_count"] = 35040  # type: ignore[index]

        result = validate_vre_curtailment_attribution(
            artifact,
            mode="full",
            periods_per_year=17520,
            expected_years=(2025, 2026),
        )

        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(set(result["annual_by_year"]), {2025, 2026})

    def test_strict_validator_rejects_nonfinite_range_and_rate_values(self) -> None:
        cases = []
        nonfinite = self.attribution()
        nonfinite["annual_totals"][0]["redispatch_net_mwh"] = float("nan")  # type: ignore[index]
        cases.append((nonfinite, "vre_curtailment_annual_value_nonfinite"))
        range_invalid = self.attribution()
        range_invalid["annual_totals"][0]["total_mwh"] = 101.0  # type: ignore[index]
        cases.append((range_invalid, "vre_curtailment_annual_range_invalid"))
        rate_invalid = self.attribution()
        rate_invalid["annual_totals"][0]["rate"] = 0.11  # type: ignore[index]
        cases.append((rate_invalid, "vre_curtailment_rate_invalid"))
        for artifact, reason in cases:
            with self.subTest(reason=reason):
                result = validate_vre_curtailment_attribution(
                    artifact,
                    mode="full",
                    periods_per_year=17520,
                    expected_years=(2025,),
                )
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["reason_code"], reason)

    def test_frontend_serialization_uses_the_same_strict_attribution_validator(self) -> None:
        from backend.model_runner import _frontend_results

        exact = {
            "capacity_history": [{"Year": 2025}],
            "cem_cost_ledgers": [],
            "carbon_ledgers": [],
            "planning_summary": [],
            "investment_decisions": [],
            "system_cost_history": [{
                "Year": 2025,
                "Total_System_Cost_GBP": 1.0,
                "Cost_per_MWh_GBP": 1.0,
                "Total_Energy_Generated_MWh": 1.0,
                "Total_Levelized_Capital_Cost_GBP": 1.0,
                "Total_Operational_Cost_GBP": 1.0,
                "CM_Mechanism_Cost_Added_to_System_GBP": 0.0,
                "Decarbonization_Mechanism_Cost_Added_to_System_GBP": 0.0,
                "Total_Energy_Deficit_MWh": 0.0,
            }],
        }
        invalid = self.attribution()
        invalid["annual_totals"][0]["redispatch_net_mwh"] = 999.0  # type: ignore[index]

        result = _frontend_results(
            exact,
            {"investment": "i", "pipeline": "p", "vre_cap": "v", "storage_cap": "s"},
            invalid,
            mode="full",
            periods_per_year=17520,
            expected_years=(2025,),
        )

        self.assertIsNone(result[0]["metrics"]["vre_curtailment_mwh"])
        self.assertIsNone(result[0]["metrics"]["vre_curtailment_rate"])
        self.assertIsNone(result[0]["metrics"]["redispatch_net_impact_mwh"])
        self.assertEqual(
            result[0]["metrics"]["vre_curtailment_attribution_status"], "unavailable"
        )
        self.assertEqual(
            result[0]["metrics"]["vre_curtailment_attribution_reason_code"],
            "vre_curtailment_redispatch_net_inconsistent",
        )

    def test_mismatched_attribution_keeps_values_but_nulls_all_deltas(self) -> None:
        left = self.summary("a", "dynamic")
        right = self.summary("b", "legacy")
        left["vre_curtailment_attribution"] = self.attribution()
        right["vre_curtailment_attribution"] = self.attribution()
        right["vre_curtailment_attribution"]["attribution_method_id"] = "method-b"  # type: ignore[index]

        result = compare_run_summaries([left, right])

        metric = result["annual_comparison"][0]["metrics"]["cem_system_cost_gbp"]
        self.assertEqual([row["value"] for row in metric], [1.0, 1.0])
        self.assertEqual([row["delta_from_base"] for row in metric], [None, None])
        self.assertEqual(
            result["curtailment_comparison"]["reason_code"],
            "attribution_method_mismatch",
        )

    def test_three_matching_runs_keep_shared_base_deltas_enabled(self) -> None:
        summaries = [self.summary(run_id, "dynamic") for run_id in ("a", "b", "c")]
        for summary in summaries:
            summary["vre_curtailment_attribution"] = self.attribution()

        result = compare_run_summaries(summaries)

        self.assertTrue(result["metric_deltas_allowed"])
        values = result["annual_comparison"][0]["metrics"]["cem_system_cost_gbp"]
        self.assertEqual([item["delta_from_base"] for item in values], [0.0, 0.0, 0.0])

    def test_comparison_rejects_an_invalid_reconciled_label_but_keeps_raw_evidence(self) -> None:
        invalid = self.attribution(period_count=12)
        invalid["matched_counterfactual_proof"]["period_count"] = 17520  # type: ignore[index]
        left = self.summary("a", "dynamic")
        right = self.summary("b", "legacy")
        left["vre_curtailment_attribution"] = invalid
        right["vre_curtailment_attribution"] = self.attribution()

        result = compare_run_summaries([left, right])

        self.assertFalse(result["metric_deltas_allowed"])
        self.assertEqual(
            result["curtailment_comparison"]["reason_code"],
            "vre_curtailment_period_count_invalid",
        )
        self.assertEqual(
            result["curtailment_comparison"]["side_by_side"][0]["annual_totals"][0]["period_count"],
            12,
        )


if __name__ == "__main__":
    unittest.main()
