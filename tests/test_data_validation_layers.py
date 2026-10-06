"""P0-5a S9 (P6-11, P6-12): structural, chronology and plausibility layers and profile eligibility."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.data_pack_validation import normalize_unit, validate_data_pack
from gridform_core.dataset_slots import DATASET_SLOTS
from gridform_core.methodology import REFERENCE_PROFILE_ID, default_profile_id
from gridform_core.preflight import data_eligibility_issues
from tests.p0_5_fixtures import GBP1_PUBLIC1, VALUE_101_BASELINE, research_pack_roots

CORRECTED = default_profile_id()


class _PackCopy(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="value-validation-layers-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.pack = self.temp / "pack"
        shutil.copytree(VALUE_101_BASELINE, self.pack)
        self.manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))

    def _rehash(self, role: str) -> None:
        binding = self.manifest["bindings"][role]
        data = (self.pack / binding["uri"]).read_bytes()
        binding["sha256"] = hashlib.sha256(data).hexdigest()
        binding["bytes"] = len(data)

    def _scale_csv(self, role: str, factor: float | None = None, value: float | None = None) -> None:
        path = self.pack / self.manifest["bindings"][role]["uri"]
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            try:
                number = float(line)
            except ValueError:
                out.append(line)
                continue
            out.append(repr(value if value is not None else number * float(factor)))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        if role.startswith("demand."):
            # New bytes lose the legacy MWh/period label allowance; declare the MW contract.
            self.manifest["bindings"][role].update(
                unit="MW", input_unit_contract="value.demand-mw-half-hour/v1", interval_minutes=30)
        self._rehash(role)

    def _netcdf(self, role: str, action) -> None:
        import netCDF4

        path = self.pack / self.manifest["bindings"][role]["uri"]
        with netCDF4.Dataset(path, mode="a") as dataset:
            action(dataset)
        self._rehash(role)

    def report(self) -> dict:
        return validate_data_pack(self.pack, self.manifest, DATASET_SLOTS)


class TamperTests(_PackCopy):
    """Eight tamperings of a VALUE 101 copy, each found by the right layer (review P6-11)."""

    def assertLayer(self, report: dict, layer: str, code: str | None = None) -> None:
        if layer == "structural":
            self.assertFalse(report["valid"], report["errors"])
            return
        self.assertTrue(report["valid"], report["errors"])
        self.assertIn(code, report["layers"][layer]["codes"], report["layers"][layer])

    def test_untampered_copy_passes_every_layer(self) -> None:
        report = self.report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["layers"]["chronology"]["codes"], [])
        self.assertEqual(report["layers"]["plausibility"]["codes"], [])
        self.assertTrue(all(row["eligible"] for row in report["profile_eligibility"].values()))

    def test_demand_times_1000(self) -> None:
        self._scale_csv("demand.real", 1000.0)
        self.assertLayer(self.report(), "plausibility", "GF_DATA_PLAUSIBILITY_DEMAND")

    def test_forecast_times_0001(self) -> None:
        self._scale_csv("demand.forecast", 0.001)
        self.assertLayer(self.report(), "plausibility", "GF_DATA_PLAUSIBILITY_FORECAST")

    def test_price_times_100(self) -> None:
        self._scale_csv("market.france.price", 100.0)
        self.assertLayer(self.report(), "plausibility", "GF_DATA_PLAUSIBILITY_PRICE")

    def test_price_minus_one_million(self) -> None:
        self._scale_csv("market.belgium.price", value=-1e6)
        self.assertLayer(self.report(), "plausibility", "GF_DATA_PLAUSIBILITY_PRICE")

    def test_flow_times_minus_1000(self) -> None:
        self._scale_csv("market.france.profile", -1000.0)
        self.assertLayer(self.report(), "plausibility", "GF_DATA_PLAUSIBILITY_FLOW")

    def test_ssrd_nan(self) -> None:
        import numpy as np

        def nan(dataset):
            dataset.variables["ssrd"][:] = np.nan
        self._netcdf("weather.solar", nan)
        self.assertLayer(self.report(), "structural")

    def test_wind_units_in_centimetres(self) -> None:
        self._netcdf("weather.wind", lambda dataset: dataset.variables["wind_speed"].setncattr("units", "cm s**-1"))
        self.assertLayer(self.report(), "structural")

    def test_renamed_variable(self) -> None:
        self._netcdf("weather.wind", lambda dataset: dataset.renameVariable("wind_speed", "ws"))
        self.assertLayer(self.report(), "structural")

    def test_three_unit_spellings_pass(self) -> None:
        for spelling in ("m s**-1", "m/s", "m s-1"):
            with self.subTest(spelling=spelling):
                self._netcdf("weather.wind", lambda dataset: dataset.variables["wind_speed"].setncattr("units", spelling))
                self.assertTrue(self.report()["valid"])
        self.assertEqual(normalize_unit("J m**-2"), normalize_unit("J m-2"))

    def test_teaching_plausibility_findings_are_warnings(self) -> None:
        self._scale_csv("market.france.price", 100.0)
        report = self.report()
        corrected = report["profile_eligibility"][CORRECTED]
        self.assertTrue(corrected["eligible"])
        self.assertIn("GF_DATA_PLAUSIBILITY_PRICE", corrected["warning_codes"])

    def test_preflight_issues_name_their_layer(self) -> None:
        # Spec 11.1 (S-D1): the readiness card groups data findings by layer.
        self._scale_csv("market.france.price", 100.0)
        issues = data_eligibility_issues({"parameters": {"methodology.profile": CORRECTED}}, self.manifest, self.report())
        price = [row for row in issues if row["code"] == "GF_DATA_PLAUSIBILITY_PRICE"]
        self.assertEqual(len(price), 1, issues)
        self.assertEqual(price[0]["layer"], "plausibility")
        self.assertEqual(price[0]["scope"], "data")
        self.assertTrue(price[0]["message"].startswith("market.france.price: "), price[0]["message"])


class UnitContractTests(unittest.TestCase):
    def test_market_slots_carry_units(self) -> None:
        slots = {row["role"]: row for row in DATASET_SLOTS}
        for country in ("france", "belgium", "netherlands", "norway", "ireland"):
            self.assertEqual(slots[f"market.{country}.profile"]["unit"], "MW")
            self.assertEqual(slots[f"market.{country}.profile"]["interval_minutes"], 30)
            self.assertEqual(slots[f"market.{country}.price"]["unit"], "GBP/MWh")

    def test_network_builder_derives_the_interconnector_capacity(self) -> None:
        from scripts.build_value_101_network_pack import _interconnector_capacity_mw

        manifest = json.loads((VALUE_101_BASELINE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(_interconnector_capacity_mw(VALUE_101_BASELINE, manifest), 12.0)


class ListPacksTests(_PackCopy):
    def test_list_packs_reads_the_cache_not_netcdf(self) -> None:
        from backend import server

        packs = self.temp / "packs"
        packs.mkdir()
        shutil.copytree(self.pack, packs / self.manifest["id"])
        (packs / self.manifest["id"] / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        with patch.object(server, "PACKS_ROOT", packs), \
                patch.object(server, "VALIDATION_CACHE_ROOT", self.temp / "cache"), \
                patch("netCDF4.Dataset", side_effect=AssertionError("list_packs must not open NetCDF")):
            rows = server.list_packs()
        self.assertEqual(rows[0]["plausibility_status"], {"status": "not_evaluated"})
        report = validate_data_pack(packs / self.manifest["id"], self.manifest, DATASET_SLOTS)
        with patch.object(server, "PACKS_ROOT", packs), patch.object(server, "VALIDATION_CACHE_ROOT", self.temp / "cache"):
            server.write_validation_cache(self.manifest["id"], packs / self.manifest["id"], report)
            with patch("netCDF4.Dataset", side_effect=AssertionError("list_packs must not open NetCDF")):
                rows = server.list_packs()
        self.assertEqual(rows[0]["plausibility_status"]["status"], "passed")


class EligibilityTests(unittest.TestCase):
    """GBP1 public1: installable (structural), refused by the corrected preflight, usable by the doctoral one."""

    @classmethod
    def setUpClass(cls) -> None:
        roots = research_pack_roots()
        if GBP1_PUBLIC1 not in roots:
            raise unittest.SkipTest("set VALUE_P0_5_PACKS to the released GBP1 public1 pack directory")
        cls.root = roots[GBP1_PUBLIC1]
        cls.manifest = json.loads((cls.root / "manifest.json").read_text(encoding="utf-8"))
        cls.report = validate_data_pack(cls.root, cls.manifest, DATASET_SLOTS)

    def test_gbp1_is_structurally_valid(self) -> None:
        self.assertTrue(self.report["valid"], self.report["errors"])

    def test_corrected_preflight_reports_identity_currency_and_time(self) -> None:
        project = {"parameters": {"methodology.profile": CORRECTED}}
        errors = {row["code"] for row in data_eligibility_issues(project, self.manifest, self.report)
                  if row["severity"] == "error"}
        self.assertEqual(errors, {"GF_DATA_BOUNDARY_IDENTITY", "GF_DATA_PRICE_CURRENCY",
                                  "GF_DATA_LOCAL_TIME_WITHOUT_TIMESTAMPS", "GF_DATA_DST_ROW_ORDER"})
        self.assertFalse(self.report["profile_eligibility"][CORRECTED]["eligible"])

    def test_doctoral_preflight_only_warns(self) -> None:
        project = {"parameters": {"methodology.profile": REFERENCE_PROFILE_ID}}
        issues = data_eligibility_issues(project, self.manifest, self.report)
        self.assertTrue(issues)
        self.assertTrue(all(row["severity"] == "warning" for row in issues))
        self.assertTrue(self.report["profile_eligibility"][REFERENCE_PROFILE_ID]["eligible"])
        # P6-05: the legacy reading's forecast lead is evidence for the doctoral profile only.
        self.assertEqual(self.report["layers"]["evidence"]["forecast_lag_periods_by_reader"],
                         {"legacy-v1": 1, "declared-v2": 0})


if __name__ == "__main__":
    unittest.main()
