import unittest

from gridform_core.catalog import MODULE_REGISTRY
from gridform_core.v2.projects import migrate_project_v1, parse_project


MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "storage_cost": "dynamic-annual-storage-cost",
}


class ProjectMigrationV2Tests(unittest.TestCase):
    def test_v1_parameters_become_explicit_overrides(self):
        old = {
            "schema_version": "value.project/v1",
            "id": "p", "name": "P", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2026, "modules": MODULES,
            "parameters": {"scenario": "existing_decarb_base"},
            "updated_at": "2026-07-22T00:00:00+01:00",
        }
        migrated = migrate_project_v1(old)
        self.assertEqual(migrated["schema_version"], "value.project/v2")
        self.assertEqual(migrated["parameter_overrides"], old["parameters"])
        self.assertEqual(migrated["modules"], MODULES)
        parsed = parse_project(old, MODULE_REGISTRY)
        self.assertEqual(parsed.migrated_from, "value.project/v1")
        self.assertEqual(parsed.modules, MODULES)

    def test_v2_is_parsed_without_v1_reinterpretation(self):
        value = {
            "schema_version": "value.project/v2",
            "id": "p", "name": "P", "data_pack_id": "pack",
            "start_year": 2025, "end_year": 2026, "modules": MODULES,
            "parameter_overrides": {"planning.success_mode": "expected"},
            "runtime_controls": {"market_trace_level": "summary"},
            "extensions": {},
        }
        parsed = parse_project(value, MODULE_REGISTRY)
        self.assertIsNone(parsed.migrated_from)
        self.assertEqual(parsed.runtime_controls["market_trace_level"], "summary")


if __name__ == "__main__":
    unittest.main()
