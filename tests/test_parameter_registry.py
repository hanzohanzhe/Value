import json
import unittest
from pathlib import Path

from gridform_core.parameters import (
    ParameterValidationError,
    SchemeCLegacyParameterAdapter,
    parameter_schema,
    resolve_scheme_c_parameters,
    scheme_c_model_card,
)
from gridform_core.cost_ledger import CEM_SYSTEM_COST_DEFINITION


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"


@unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
class ParameterRegistryTests(unittest.TestCase):
    def test_defaults_reproduce_pre_registry_effective_values(self):
        resolved = resolve_scheme_c_parameters(PACK)
        p, r = resolved.scientific.values, resolved.runtime.values
        self.assertEqual(p["planning.success_mode"], "expected")
        self.assertTrue(p["planning.include_uncertain_projects"])
        self.assertTrue(p["planning.zombie_filter_enabled"])
        self.assertEqual(p["planning.zombie_status_stale_year"], 2015)
        self.assertEqual(p["planning.defer_spread_years"], 3)
        self.assertEqual(p["expansion.vre_cap_fraction"], 0.20)
        self.assertEqual(p["expansion.storage_cap_fraction"], 0.20)
        self.assertEqual(p["expansion.storage_credit_method"], "scheme_c")
        self.assertEqual(p["storage.virtual_pool_energy_mwh"], 1_000_000_000.0)
        self.assertEqual(p["clock.period_hours"], 0.5)
        self.assertEqual(p["market.bid_multiplier"], 1.0)
        self.assertEqual(p["cost.system_boundary"], CEM_SYSTEM_COST_DEFINITION)
        self.assertEqual(r["runtime.market_trace_level"], "summary")
        self.assertFalse(r["runtime.market_balance_diagnostic"])
        self.assertFalse(resolved.warnings)

    def test_invalid_types_ranges_enums_unknowns_and_fixed_overrides_fail(self):
        cases = (
            {"planning.random_seed": "42"},
            {"expansion.vre_cap_fraction": 1.1},
            {"planning.success_mode": "maybe"},
            {"model.topology": "network"},
            {"not.a.parameter": 1},
            {"runtime.market_trace_level": "full"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ParameterValidationError):
                    resolve_scheme_c_parameters(PACK, overrides)

    def test_runtime_and_scientific_options_are_separate(self):
        resolved = resolve_scheme_c_parameters(
            PACK,
            {"planning.success_mode": "stochastic", "planning.random_seed": 73},
            {
                "runtime.market_trace_level": "full",
                "runtime.market_balance_diagnostic": True,
                "runtime.artifact_batch_size": 10,
            },
            periods_per_year=2,
        )
        env = SchemeCLegacyParameterAdapter(resolved).environment(start_year=2025)
        self.assertEqual(env["MODEL_SUCCESS_MODE"], "lottery")
        self.assertEqual(env["MODEL_SUCCESS_RANDOM_SEED"], "73")
        self.assertEqual(env["SAVE_MARKET_TRACE"], "0")
        self.assertEqual(env["MARKET_LEDGER_LEVEL"], "full")
        self.assertEqual(env["MARKET_BALANCE_DIAGNOSTIC"], "1")
        payload = resolved.to_dict()
        self.assertEqual(payload["runtime_options"]["runtime.periods_per_year"], 2)
        self.assertNotIn("runtime.market_trace_level", payload["scientific_parameters"])

    def test_bid_multiplier_is_explicitly_experimental(self):
        resolved = resolve_scheme_c_parameters(PACK, {"market.bid_multiplier": 1.05})
        self.assertTrue(resolved.warnings)
        self.assertFalse(scheme_c_model_card(resolved)["strict_bid_at_cost"])

    def test_api_schema_has_validation_and_precedence_metadata(self):
        schema = parameter_schema()
        self.assertEqual(schema["schema_version"], "value.parameter-registry/v1")
        rows = {row["id"]: row for row in schema["parameters"]}
        success = rows["planning.success_mode"]
        self.assertEqual(
            success["allowed_values"],
            ("expected", "stochastic", "expected_capacity", "seeded_stochastic"),
        )
        self.assertEqual(success["visibility"], "advanced")
        self.assertIn("project_override", success["source_precedence"])
        self.assertEqual(rows["model.topology"]["source_precedence"], ["module_fixed"])
        self.assertEqual(rows["cost.system_boundary"]["default"], CEM_SYSTEM_COST_DEFINITION)
        json.dumps(schema)


if __name__ == "__main__":
    unittest.main()
