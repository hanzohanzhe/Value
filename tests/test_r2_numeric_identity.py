"""R3-N1 (four-role R1 retest, DECISIONS A23): numbers are saved in their
registry type and compared by value.

The retest saved the VALUE 101 baseline Study unchanged from the editor; the
editor sent ``market_configuration.voll_gbp_per_mwh`` as ``17000`` where the
saved revision had ``17000.0``.  That produced revision 2 with an empty change
summary, and the comparison page reported a configuration change between two
Runs whose market ledgers were byte-identical.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from gridform_core.comparison_identity import comparison_key, numeric_canonical, review_comparison_identities
from gridform_core.parameters import normalise_numeric_values
from gridform_core.results_summary import _differing_paths, changed_dimension_details
from gridform_core.study_market_config import resolve_market_configuration


ROOT = Path(__file__).resolve().parents[1]
MODULES = {"psm": "value-bid-at-cost-psm", "balancing": "", "weather_spatializer": ""}


def _summary(voll: object, *, other: dict | None = None) -> dict:
    config = {
        "parameters": {},
        "runtime_options": {},
        "scientific_parameters": {"market.voll_gbp_per_mwh": 17000.0},
        "runtime_controls": {},
        "extension_parameters": {},
        "market_configuration": {"voll_gbp_per_mwh": voll, "ledger_detail": "summary", **(other or {})},
        "solver_contract": None,
    }
    dimensions = {"data": {"pack": "x"}, "method": {"m": 1}, "config": config, "years": {"start_year": 2025, "end_year": 2025}, "scope": {"mode": "value_101_day"}}
    return {"comparison_identity": {"schema_version": "value.comparison-identity/v1", "dimensions": dimensions}}


class NumericComparisonTests(unittest.TestCase):
    def test_report_case_integral_float_and_int_do_not_differ(self) -> None:
        # The exact call of FOUR_ROLE_TEST_REPORT 10.6 returned
        # ['market_configuration.voll_gbp_per_mwh'] before the fix.
        paths = _differing_paths([
            {"market_configuration": {"voll_gbp_per_mwh": 17000.0}},
            {"market_configuration": {"voll_gbp_per_mwh": 17000}},
        ], 2)
        self.assertEqual(paths, [])

    def test_identity_review_reports_no_config_change(self) -> None:
        review = review_comparison_identities([_summary(17000.0), _summary(17000)])
        self.assertEqual(review["dimensions"]["config"]["status"], "same")
        self.assertEqual(review["changed_dimensions"], [])
        self.assertEqual(changed_dimension_details(review), {})

    def test_a_real_numeric_change_is_still_reported(self) -> None:
        review = review_comparison_identities([_summary(17000.0), _summary(17000.5)])
        self.assertEqual(review["changed_dimensions"], ["config"])
        self.assertEqual(
            changed_dimension_details(review)["config"]["paths"],
            ["market_configuration.voll_gbp_per_mwh"],
        )

    def test_canonical_form_keeps_booleans_and_fractions(self) -> None:
        self.assertEqual(numeric_canonical({"a": [1.0, 2.5, True, 0]}), {"a": [1, 2.5, True, 0]})
        self.assertNotEqual(comparison_key(True), comparison_key(1))
        self.assertNotEqual(comparison_key("17000"), comparison_key(17000))
        self.assertEqual(comparison_key(float("inf")), comparison_key(float("inf")))


class NumericSaveTests(unittest.TestCase):
    def test_market_configuration_voll_is_saved_as_float(self) -> None:
        resolved = resolve_market_configuration(MODULES, {}, {}, {"voll_gbp_per_mwh": 17000})
        self.assertIsInstance(resolved["voll_gbp_per_mwh"], float)
        self.assertEqual(json.dumps(resolved["voll_gbp_per_mwh"]), "17000.0")

    def test_float_registry_parameters_are_saved_as_float(self) -> None:
        values = normalise_numeric_values({
            "market.voll_gbp_per_mwh": 17000,
            "planning.defer_spread_years": 0,
            "expansion.vre_cap_fraction": True,
            "unknown.parameter": 3,
        })
        self.assertIsInstance(values["market.voll_gbp_per_mwh"], float)
        # Integer parameters stay ints; invalid and unknown values are left
        # for validation to report.
        self.assertIsInstance(values["planning.defer_spread_years"], int)
        self.assertIs(values["expansion.vre_cap_fraction"], True)
        self.assertEqual(values["unknown.parameter"], 3)

    def test_unchanged_save_with_an_int_voll_appends_no_revision(self) -> None:
        from backend import server
        from tests.local_api_harness import start_local_api

        project = {
            "id": "r3-n1-study",
            "name": "R3-N1 Study",
            "data_pack_id": "value-101-baseline-v1",
            "start_year": 2025,
            "end_year": 2025,
            "modules": {
                "psm": "value-bid-at-cost-psm", "storage_cost": "dynamic-annual-storage-cost",
                "investment": "agent-investment", "pipeline": "planning-pipeline",
                "vre_cap": "vre-expansion-cap", "storage_cap": "value-storage-expansion-policy",
                "transition": "value-annual-state-transition",
            },
            "parameters": {"planning.defer_spread_years": 0},
            "runtime_options": {"runtime.market_trace_level": "summary"},
        }
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            patches = (
                mock.patch.object(server, "PACKS_ROOT", ROOT / "data-packs"),
                mock.patch.object(server, "PROJECTS_ROOT", state / "projects"),
                mock.patch.object(server, "RUNS_ROOT", state / "runs"),
            )
            for item in patches:
                item.start()
            api = start_local_api(data_home=state, patch_state_roots=False)
            _httpd, origin, _session = api.start()

            def post(payload: dict) -> dict:
                request = urllib.request.Request(
                    origin + "/api/projects", data=json.dumps(payload).encode("utf-8"),
                    method="POST", headers={"Content-Type": "application/json"},
                )
                try:
                    return json.loads(urllib.request.urlopen(request, timeout=30).read())
                except urllib.error.HTTPError as exc:  # pragma: no cover - diagnostic
                    self.fail(exc.read().decode("utf-8"))

            try:
                first = post(project)["project"]
                self.assertEqual(first["revision_number"], 1)
                self.assertIsInstance(first["market_configuration"]["voll_gbp_per_mwh"], float)
                # What the editor sends back for an unchanged Study.
                again = json.loads(json.dumps(first))
                again["market_configuration"]["voll_gbp_per_mwh"] = 17000
                again["base_revision_sha256"] = first["revision_sha256"]
                second = post(again)["project"]
                self.assertEqual(second["revision_sha256"], first["revision_sha256"])
                self.assertEqual(second["revision_number"], 1)
                revisions = list((state / "projects" / project["id"] / "revisions").glob("*.json"))
                self.assertEqual(len(revisions), 1)
                # An int for a float registry parameter is no change either.
                again["parameters"] = {"planning.defer_spread_years": 0, "market.voll_gbp_per_mwh": 17000}
                third = post(again)["project"]
                self.assertEqual(third["revision_number"], 2)
                self.assertIsInstance(third["parameters"]["market.voll_gbp_per_mwh"], float)
                again["parameters"]["market.voll_gbp_per_mwh"] = 17000
                again["base_revision_sha256"] = third["revision_sha256"]
                fourth = post(again)["project"]
                self.assertEqual(fourth["revision_sha256"], third["revision_sha256"])
            finally:
                api.stop()
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
