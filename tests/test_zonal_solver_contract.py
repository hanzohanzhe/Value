import copy
import hashlib
import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import gridform_core.zonal_solver_contract as solver_contract_module

from gridform_core.zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    ObjectiveLockDiagnostic,
    ZonalSolverContractError,
    classify_lock,
    compute_lock_tolerance,
    solver_stack_identity,
    summarise_solver_diagnostics,
    validate_stored_lock_evidence,
    validate_solver_settings,
)


_CANDIDATE_SHA = (
    "ea7abc641063940981f8d231335373b6609973889bd2c2ecf4c68328c56262b3"
)


def _registry_entry(
    *,
    registry_id: str = "scipy-1.8.1-highs-ea7abc64",
    status: str = "candidate",
    sha256: str = _CANDIDATE_SHA,
) -> dict[str, object]:
    return {
        "registry_id": registry_id,
        "module_id": "value-zonal-redispatch-balancing",
        "module_version": "2.0.0",
        "solver_contract_version": "value.zonal-lexicographic-gbp1/v3",
        "scipy_version": "1.8.1",
        "highs_binary_sha256": sha256,
        "highs_identity": f"scipy-embedded-highs:{sha256}",
        "status": status,
        "evidence_references": [
            "tests.test_prompt103_zonal_validation:pending_objective_lock_resolution"
        ],
    }


def _registry_payload(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "value.solver-validation-registry/v1",
        "entries": entries,
    }


class ZonalSolverSettingsTests(unittest.TestCase):
    def test_default_contract_is_the_validated_baseline(self):
        settings = DEFAULT_ZONAL_SOLVER_SETTINGS

        self.assertEqual(settings.schema_version, "value.network-solver-contract/v3")
        self.assertEqual(settings.contract_version, "value.zonal-lexicographic-gbp1/v3")
        self.assertEqual(settings.validated_ceilings["primary_bid_cost_gbp"], 1.0)
        self.assertEqual(settings.absolute_ceilings["primary_bid_cost_gbp"], 1.0)
        self.assertEqual(settings.method, "highs-ds")
        self.assertEqual(settings.primal_feasibility_tolerance, 1e-9)
        self.assertEqual(settings.dual_feasibility_tolerance, 1e-9)
        self.assertIs(settings.presolve, True)
        self.assertIs(settings.is_builtin_default, True)

    def test_nondefault_settings_are_valid_but_not_builtin_validated(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["method"] = "highs-ipm"
        payload["ipm_optimality_tolerance"] = 1e-10
        payload["is_builtin_default"] = False
        payload["requires_acknowledgement"] = True

        settings = validate_solver_settings(payload)

        self.assertIs(settings.is_builtin_default, False)
        self.assertIs(settings.requires_acknowledgement, True)

    def test_recorded_reference_threshold_cannot_be_overridden(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["absolute_ceilings"]["primary_bid_cost_gbp"] = 1.01

        with self.assertRaisesRegex(ValueError, "recorded reference threshold"):
            validate_solver_settings(payload)

    def test_primary_validated_ceiling_is_fixed_by_gbp1_study_policy(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["validated_ceilings"]["primary_bid_cost_gbp"] = 0.999
        payload["is_builtin_default"] = False
        payload["requires_acknowledgement"] = True

        with self.assertRaisesRegex(ValueError, "fixed at GBP 1"):
            validate_solver_settings(payload)

    def test_supplied_derived_flags_must_match_validated_values(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["method"] = "highs"

        with self.assertRaisesRegex(ValueError, "is_builtin_default"):
            validate_solver_settings(payload)

    def test_range_endpoints_are_accepted_and_out_of_range_values_are_rejected(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload.update({
            "primal_feasibility_tolerance": 1e-10,
            "dual_feasibility_tolerance": 1e-7,
            "ipm_optimality_tolerance": 1e-12,
            "is_builtin_default": False,
            "requires_acknowledgement": True,
        })
        self.assertEqual(validate_solver_settings(payload).ipm_optimality_tolerance, 1e-12)

        payload["primal_feasibility_tolerance"] = 1e-11
        with self.assertRaisesRegex(ValueError, "primal_feasibility_tolerance"):
            validate_solver_settings(payload)

    def test_serialized_settings_round_trip_as_json_and_maps_are_immutable(self):
        payload = json.loads(json.dumps(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()))
        settings = validate_solver_settings(payload)
        self.assertEqual(settings.to_dict(), DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        with self.assertRaises(TypeError):
            settings.validated_ceilings["primary_bid_cost_gbp"] = 0.02

    def test_schema_requires_all_public_fields_and_recorded_reference_thresholds(self):
        schema_path = Path(__file__).parents[1] / "gridform_core" / "data" / "contracts" / "network-solver-contract-v3.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()))
        self.assertEqual(schema["properties"]["method"]["enum"], ["highs-ds", "highs-ipm", "highs"])
        self.assertIn("absolute_ceilings", schema["$defs"])
        absolute = schema["$defs"].get("absolute_ceilings", {"properties": {}})["properties"]
        self.assertEqual(absolute["primary_bid_cost_gbp"].get("const"), 1.0)
        self.assertEqual(absolute["secondary_schedule_deviation_mwh"].get("const"), 0.01)
        self.assertEqual(absolute["physical_throughput_mwh"].get("const"), 0.01)


class LockFormulaTests(unittest.TestCase):
    def test_lock_tolerance_uses_largest_declared_term(self):
        result = compute_lock_tolerance(
            coefficients=np.array([2.0, -3.0, 0.0]),
            optimum=np.array([4.0, 5.0, 7.0]),
            unit_floor=1e-8,
            solver_tolerance=1e-9,
        )
        self.assertEqual(result.nonzero_terms, 2)
        self.assertEqual(result.absolute_term_scale, 23.0)
        self.assertAlmostEqual(
            result.tolerance,
            max(1e-8, 23e-9, result.gamma_n * 23.0),
        )

    def test_zero_optimum_uses_coefficient_norm_for_bound_canonicalisation(self):
        coefficients = np.array([17_000.0, 2.0, -3.0, 0.0])

        result = compute_lock_tolerance(
            coefficients=coefficients,
            optimum=np.zeros(4),
            unit_floor=1e-8,
            solver_tolerance=1e-8,
        )

        self.assertAlmostEqual(
            result.tolerance,
            (17_000.0 + 2.0 + 3.0) * 1e-8,
        )

    def test_nonfinite_inputs_and_empty_objectives_are_hard_failures(self):
        with self.assertRaisesRegex(ZonalSolverContractError, "GF_ZONAL_LOCK_TOLERANCE_INVALID"):
            compute_lock_tolerance(np.array([0.0]), np.array([1.0]), 1e-8, 1e-9)
        with self.assertRaisesRegex(ZonalSolverContractError, "GF_ZONAL_LOCK_TOLERANCE_INVALID"):
            compute_lock_tolerance(np.array([math.inf]), np.array([1.0]), 1e-8, 1e-9)

    def test_classification_thresholds_are_one_sided(self):
        self.assertEqual(classify_lock(0.0005, 0.001, 0.01, 0.10, 0.10).status, "GO")
        self.assertEqual(classify_lock(0.002, 0.002, 0.01, 0.10, 0.10).status, "GO_WITH_NUMERICAL_WARNING")
        self.assertEqual(classify_lock(0.011, 0.012, 0.01, 0.10, 0.10).status, "COMPLETED_WITH_NUMERICAL_WARNING")
        self.assertEqual(
            classify_lock(0.11, 0.12, 0.01, 0.10, 0.10).status,
            "COMPLETED_WITH_NUMERICAL_WARNING",
        )

    def test_tolerance_above_reference_threshold_completes_with_warning(self):
        classification = classify_lock(
            degradation=0.11,
            computed_tolerance=0.12,
            validated_ceiling=0.01,
            warning_fraction=0.10,
            absolute_ceiling=0.10,
        )

        self.assertEqual(
            classification.status,
            "COMPLETED_WITH_NUMERICAL_WARNING",
        )
        self.assertFalse(classification.is_solver_validated)

    def test_observed_degradation_cannot_exceed_its_computed_tolerance(self):
        with self.assertRaisesRegex(ZonalSolverContractError, "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION"):
            classify_lock(0.002, 0.001, 0.01, 0.10, 0.10)

    def test_gbp1_hard_acceptance_boundary(self):
        for degradation in (0.999, 1.0):
            result = classify_lock(degradation, 1.0, 1.0, 0.10, 1.0)
            self.assertTrue(result.is_solver_validated)
        with self.assertRaisesRegex(
            ZonalSolverContractError, "GF_ZONAL_OBJECTIVE_LOCK_VIOLATION"
        ):
            classify_lock(1.001, 1.0, 1.0, 0.10, 1.0)


class DiagnosticsTests(unittest.TestCase):
    def test_v3_stored_primary_evidence_requires_exact_gbp1_policy_tuple(self):
        row = {
            "solver_contract_version": "value.zonal-lexicographic-gbp1/v3",
            "phase_id": "primary_bid_cost",
            "objective_unit": "GBP",
            "method": "highs-ds",
            "primal_feasibility_tolerance": 1e-9,
            "dual_feasibility_tolerance": 1e-9,
            "ipm_optimality_tolerance": None,
            "highs_binary_sha256": "a" * 64,
            "highs_identity": f"scipy-embedded-highs:{'a' * 64}",
            "optimum": 10.0,
            "achieved_final_value": 10.999,
            "degradation": 0.999,
            "computed_tolerance": 1.0,
            "warning_ceiling": 0.1,
            "validated_ceiling": 1.0,
            "absolute_ceiling": 1.0,
            "validation_class": "GO_WITH_NUMERICAL_WARNING",
        }
        self.assertEqual(validate_stored_lock_evidence(row).errors, ())
        for field, bad_value in (
            ("computed_tolerance", 0.999),
            ("validated_ceiling", 1.001),
            ("absolute_ceiling", float("inf")),
        ):
            bad = dict(row)
            bad[field] = bad_value
            self.assertIn(
                "solver_diagnostics_gbp1_policy_mismatch",
                validate_stored_lock_evidence(bad).errors,
            )
        bad_class = dict(row)
        bad_class["validation_class"] = "GO"
        self.assertIn(
            "solver_diagnostics_validation_class_mismatch",
            validate_stored_lock_evidence(bad_class).errors,
        )

    def test_summary_groups_locked_phases_and_uses_worst_period_status(self):
        rows = (
            ObjectiveLockDiagnostic(
                phase_id="primary_bid_cost_gbp", objective_unit="GBP", optimum=10.0,
                achieved_final_value=10.0005, degradation=0.0005, computed_tolerance=0.001,
                validated_ceiling=0.01, absolute_ceiling=0.1, nonzero_terms=3,
                absolute_term_scale=25.0, validation_class="GO",
            ),
            ObjectiveLockDiagnostic(
                phase_id="primary_bid_cost_gbp", objective_unit="GBP", optimum=10.0,
                achieved_final_value=10.002, degradation=0.002, computed_tolerance=0.002,
                validated_ceiling=0.01, absolute_ceiling=0.1, nonzero_terms=3,
                absolute_term_scale=25.0, validation_class="GO_WITH_NUMERICAL_WARNING",
            ),
            ObjectiveLockDiagnostic(
                phase_id="secondary_schedule_deviation_mwh", objective_unit="MWh", optimum=1.0,
                achieved_final_value=1.011, degradation=0.011, computed_tolerance=0.012,
                validated_ceiling=0.01, absolute_ceiling=0.1, nonzero_terms=2,
                absolute_term_scale=3.0, validation_class="COMPLETED_WITH_NUMERICAL_WARNING",
            ),
        )

        summary = summarise_solver_diagnostics(rows)

        self.assertEqual(summary["study_status"], "COMPLETED_WITH_NUMERICAL_WARNING")
        self.assertEqual(summary["phases"]["primary_bid_cost_gbp"], {
            "max_tolerance": 0.002,
            "max_degradation": 0.002,
            "periods_above_warning_fraction": 1,
            "periods_above_validated_ceiling": 0,
            "cumulative_absolute_degradation": 0.0025,
        })

    def test_summary_uses_each_diagnostic_effective_warning_fraction(self):
        row = ObjectiveLockDiagnostic(
            phase_id="primary_bid_cost", objective_unit="GBP", optimum=10.0,
            achieved_final_value=10.0005, degradation=0.0005,
            computed_tolerance=0.0005, validated_ceiling=0.01,
            absolute_ceiling=0.1, nonzero_terms=3,
            absolute_term_scale=25.0, validation_class="GO_WITH_NUMERICAL_WARNING",
            warning_fraction=0.01,
        )

        summary = summarise_solver_diagnostics((row,))

        self.assertEqual(
            summary["phases"]["primary_bid_cost"]["periods_above_warning_fraction"],
            1,
        )


class SolverStackIdentityTests(unittest.TestCase):
    def test_identity_hashes_the_embedded_highs_extension_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "_highs_wrapper.pyd"
            binary.write_bytes(b"known-highs-binary")
            scipy = SimpleNamespace(__version__="1.8.1")
            highs_wrapper = SimpleNamespace(__file__=str(binary))
            with patch(
                "gridform_core.zonal_solver_contract.importlib.import_module",
                side_effect=[scipy, highs_wrapper],
            ):
                identity = solver_stack_identity()

        digest = hashlib.sha256(b"known-highs-binary").hexdigest()
        self.assertEqual(identity.scipy_version, "1.8.1")
        self.assertEqual(identity.highs_binary_sha256, digest)
        self.assertEqual(identity.highs_identity, f"scipy-embedded-highs:{digest}")


class SolverValidationRegistryTests(unittest.TestCase):
    def _write_registry(
        self,
        folder: str,
        payload: dict[str, object],
    ) -> Path:
        path = Path(folder) / "solver-validation-registry-v1.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_source_controlled_registry_records_runtime_binary_as_candidate_only(
        self,
    ) -> None:
        loader = getattr(
            solver_contract_module,
            "load_solver_validation_registry",
            None,
        )
        self.assertTrue(callable(loader))

        entries = loader()

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].highs_binary_sha256, _CANDIDATE_SHA)
        self.assertEqual(
            entries[0].highs_identity,
            f"scipy-embedded-highs:{_CANDIDATE_SHA}",
        )
        self.assertEqual(entries[0].status, "candidate")
        self.assertFalse(any(entry.status == "validated" for entry in entries))

    def test_only_explicitly_validated_registry_entry_matches(self) -> None:
        loader = getattr(
            solver_contract_module,
            "load_solver_validation_registry",
            None,
        )
        matcher = getattr(
            solver_contract_module,
            "solver_stack_is_validated",
            None,
        )
        self.assertTrue(callable(loader))
        self.assertTrue(callable(matcher))
        candidate = loader()[0]
        stack = {
            "module_id": candidate.module_id,
            "module_version": candidate.module_version,
            "solver_contract_version": candidate.solver_contract_version,
            "scipy_version": candidate.scipy_version,
            "highs_binary_sha256": candidate.highs_binary_sha256,
            "highs_identity": candidate.highs_identity,
        }

        self.assertFalse(matcher((candidate,), **stack))
        self.assertTrue(matcher((replace(candidate, status="validated"),), **stack))
        self.assertFalse(
            matcher(
                (replace(candidate, status="validated"),),
                **{
                    **stack,
                    "highs_binary_sha256": "f" * 64,
                    "highs_identity": "scipy-embedded-highs:" + "f" * 64,
                },
            )
        )

    def test_registry_loader_fails_closed_on_malformed_or_duplicate_entries(
        self,
    ) -> None:
        loader = getattr(
            solver_contract_module,
            "load_solver_validation_registry",
            None,
        )
        self.assertTrue(callable(loader))
        malformed_payloads = {
            "wrong_schema": {
                **_registry_payload([_registry_entry()]),
                "schema_version": "value.solver-validation-registry/v2",
            },
            "unknown_top_level_field": {
                **_registry_payload([_registry_entry()]),
                "promote_runtime": True,
            },
            "unknown_entry_field": _registry_payload(
                [{**_registry_entry(), "runtime_discovered": True}]
            ),
            "unknown_status": _registry_payload(
                [_registry_entry(status="approved")]
            ),
            "empty_evidence": _registry_payload(
                [{**_registry_entry(), "evidence_references": []}]
            ),
            "identity_sha_mismatch": _registry_payload(
                [{**_registry_entry(), "highs_identity": "scipy-embedded-highs:" + "f" * 64}]
            ),
            "duplicate_registry_id": _registry_payload(
                [_registry_entry(), _registry_entry()]
            ),
            "duplicate_stack": _registry_payload(
                [
                    _registry_entry(),
                    _registry_entry(registry_id="same-stack-different-id"),
                ]
            ),
        }
        with tempfile.TemporaryDirectory() as folder:
            for name, payload in malformed_payloads.items():
                with self.subTest(name=name):
                    path = self._write_registry(folder, payload)
                    with self.assertRaises(ValueError):
                        loader(path)


if __name__ == "__main__":
    unittest.main()
