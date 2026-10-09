"""P0-5b corrected-profile data science (plan 4.5 S5-S8; decisions Q15, A1).

Weather v2 time conventions (P6-06), literature VRE loss factors (P6-08, no
statistical calibration), nuclear / natural-flow hydro availability (P5-09,
P5-10, values PENDING AUTHOR REVIEW), raw boundary prices, the kernel
receiving the canonical arrays, and the keyed kernel weather cache (P7-02).

GBP1 checks need the research pack: set ``VALUE_P0_5_PACKS`` as for
``tests.test_series_reader`` (``<gbp1-national>:<r029-public1>``).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from gridform_core import firm_availability as firm
from gridform_core import site_weather as sw
from gridform_core.doctoral_weather import site_weather_profiles
from gridform_core.doctoral_weather_mapping import representative_sites
from gridform_core.v2.contracts import AssetStateV2

ROOT = Path(__file__).resolve().parents[1]
PACK_101 = ROOT / "data-packs" / "value-101-baseline-v1"
CORRECTED = "value-corrected"
DOCTORAL = "doctoral-lineage-0.6.0a2"
CORRECTED_METHOD = sw.SiteWeatherMethod("v2", True, True)  # F2 (A13) added the solar plane-of-array step


def _gbp1_root() -> Path | None:
    spec = os.environ.get("VALUE_P0_5_PACKS", "")
    root = Path(spec.split(":")[0]) if spec else None
    return root if root is not None and (root / "manifest.json").is_file() else None


def _pack(root: Path):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest["bindings"]
    fleet = json.loads((root / bindings["fleet.generators"]["uri"]).read_text(encoding="utf-8"))
    roles = ("weather.solar", "weather.wind")
    return manifest, fleet, {
        "paths": {role: root / bindings[role]["uri"] for role in roles},
        "hashes": {role: bindings[role]["sha256"] for role in roles},
        "bindings": {role: bindings[role] for role in roles},
    }


def _profiles(root: Path, method, periods=17520):
    _, fleet, files = _pack(root)
    sites = representative_sites(fleet)
    return sites, sw.site_cf_by_source(**files, sites=sites, sources=list(sites), periods=periods, method=method)


def _centroid(values: np.ndarray) -> float:
    tod = (np.arange(len(values)) % 48) / 2 + 0.25
    return float((values * tod).sum() / values.sum())


class WeatherClockTests(unittest.TestCase):
    def test_hour_index_conventions(self):
        np.testing.assert_array_equal(sw.hour_index(6, 24, "v1", sw.ACCUMULATION_END), [0, 0, 1, 1, 2, 2])
        np.testing.assert_array_equal(sw.hour_index(6, 24, "v2", sw.ACCUMULATION_END), [1, 1, 2, 2, 3, 3])
        np.testing.assert_array_equal(sw.hour_index(6, 24, "v2", sw.INSTANT), [0, 1, 1, 2, 2, 3])
        # Wrap in source order.
        np.testing.assert_array_equal(sw.hour_index(4, 2, "v2", sw.ACCUMULATION_END), [1, 1, 0, 0])

    def test_time_convention_declared_then_grib_then_instant(self):
        accum = SimpleNamespace(GRIB_stepType="accum")
        self.assertEqual(sw.variable_time_convention(None, accum), sw.ACCUMULATION_END)
        self.assertEqual(sw.variable_time_convention({}, SimpleNamespace()), sw.INSTANT)
        self.assertEqual(sw.variable_time_convention({"time_convention": sw.INSTANT}, accum), sw.INSTANT)
        with self.assertRaises(ValueError):
            sw.variable_time_convention({"time_convention": "hour_start"}, accum)

    def test_profiles_select_the_method(self):
        self.assertTrue(sw.method_for_profile(DOCTORAL).frozen)
        self.assertEqual(sw.method_for_profile(DOCTORAL).method_id, sw.WEATHER_V1)
        self.assertEqual(sw.method_for_profile(CORRECTED), CORRECTED_METHOD)

    def test_frozen_shared_conversion_equals_the_doctoral_adapter(self):
        """v1 through site_cf_by_source equals the 35aadb3 adapter path (rtol 1e-12)."""

        _, fleet, files = _pack(PACK_101)
        sites = representative_sites(fleet)
        assets = [AssetStateV2(name, site["technology"], 10.0) for name, site in sites.items()]
        legacy = site_weather_profiles(paths=files["paths"], hashes=files["hashes"], fleet=fleet,
                                       assets=assets, periods=200, period_hours=0.5)
        shared = sw.site_cf_by_source(**files, sites=sites, sources=list(sites), periods=200, method=sw.FROZEN)
        self.assertEqual(set(legacy), set(shared))
        for name in sites:
            np.testing.assert_allclose(np.asarray(legacy[name][0]), shared[name][0], rtol=1e-12, atol=0)
            self.assertEqual(legacy[name][1]["method_id"], sw.WEATHER_V1)

    def test_value_101_solar_centroid_is_noon_under_v2(self):
        sites, frozen = _profiles(PACK_101, sw.FROZEN)
        _, corrected = _profiles(PACK_101, CORRECTED_METHOD)
        name = next(n for n in sites if sites[n]["technology"] == "solar")
        self.assertAlmostEqual(_centroid(frozen[name][0]), 12.5, places=6)
        self.assertLess(abs(_centroid(corrected[name][0]) - 12.0), 0.15)

    @unittest.skipUnless(_gbp1_root(), "set VALUE_P0_5_PACKS to the GBP1 national pack")
    def test_gbp1_london_centroid_and_winter_solstice(self):
        """M5 gate (1): centroid 12.00 +- 0.15 UTC; 21 December first nonzero <= 08:30."""

        sites, corrected = _profiles(_gbp1_root(), CORRECTED_METHOD)
        london = corrected["solar_London"][0]
        self.assertLess(abs(_centroid(london) - 12.0), 0.15)
        solstice = london[354 * 48:355 * 48]
        nonzero = np.nonzero(solstice)[0]
        self.assertLessEqual(nonzero[0] / 2, 8.5)
        self.assertGreaterEqual((nonzero[-1] + 1) / 2, 15.5)
        self.assertEqual(corrected["solar_London"][1]["time_convention"], sw.ACCUMULATION_END)
        self.assertEqual(corrected["onshore_London"][1]["time_convention"], sw.INSTANT)


class LossFactorTests(unittest.TestCase):
    def test_table_multipliers_are_the_product_of_cited_components(self):
        table = sw.load_loss_factors()
        self.assertTrue(table["status"].startswith("AUTHOR ACCEPTED (DECISIONS A9"))
        for technology in sw.VRE:
            entry = table["technologies"][technology]
            self.assertAlmostEqual(entry["multiplier"], float(np.prod([c["central"] for c in entry["components"]])), 12)
            for component in entry["components"]:
                self.assertTrue(component["source_ids"])
                self.assertTrue(set(component["source_ids"]) <= set(table["sources"]))
        self.assertEqual(CORRECTED_METHOD.multiplier("onshore"), 0.90307)
        self.assertEqual(CORRECTED_METHOD.multiplier("offshore"), 0.814968)
        self.assertEqual(CORRECTED_METHOD.multiplier("solar"), 0.83)
        self.assertEqual(sw.FROZEN.multiplier("offshore"), 1.0)

    def test_power_curve_reference_point(self):
        self.assertAlmostEqual(sw.wind_unit_output(8.0, onshore=True) / 20, 0.5476, places=4)

    def test_losses_scale_the_shape_without_calibration(self):
        sites, no_loss = _profiles(PACK_101, sw.SiteWeatherMethod("v2", False), periods=500)
        _, loss = _profiles(PACK_101, CORRECTED_METHOD, periods=500)
        for name, site in sites.items():
            np.testing.assert_allclose(loss[name][0], no_loss[name][0] * CORRECTED_METHOD.multiplier(site["technology"]),
                                       rtol=1e-12, atol=0)
            self.assertEqual(loss[name][1]["loss_multiplier"], CORRECTED_METHOD.multiplier(site["technology"]))

    def test_corrected_canonical_adapter_uses_the_shared_arrays(self):
        _, fleet, files = _pack(PACK_101)
        sites = representative_sites(fleet)
        assets = [AssetStateV2(name, site["technology"], 10.0) for name, site in sites.items()]
        mapped = site_weather_profiles(paths=files["paths"], hashes=files["hashes"], fleet=fleet, assets=assets,
                                       periods=300, period_hours=0.5, method=CORRECTED_METHOD,
                                       bindings=files["bindings"])
        _, shared = _profiles(PACK_101, CORRECTED_METHOD, periods=300)
        for name in sites:
            self.assertEqual(mapped[name][1]["availability_sha256"], shared[name][1]["availability_sha256"])
            self.assertEqual(mapped[name][1]["method_id"], CORRECTED_METHOD.method_id)


class FirmAvailabilityTests(unittest.TestCase):
    def test_profiles(self):
        self.assertTrue(firm.enabled_for_profile(CORRECTED))
        self.assertFalse(firm.enabled_for_profile(DOCTORAL))

    def test_heysham_1_ends_in_march_2030(self):
        values, evidence = firm.asset_availability(asset_id="nuclear:heysham-1", technology="Nuclear",
                                                   capacity_mw=1155.0, year=2030, periods=17520)
        expected = 0.668 * 1060.0 / 1155.0
        self.assertEqual(evidence["generation_end_period"], 4320)
        self.assertTrue(np.all(values[:4320] == expected))
        self.assertTrue(np.all(values[4320:] == 0.0))
        before, evidence = firm.asset_availability(asset_id="nuclear:heysham-1", technology="Nuclear",
                                                   capacity_mw=1155.0, year=2029, periods=17520)
        self.assertNotIn("generation_end_period", evidence)
        self.assertAlmostEqual(float(before.mean()), expected, 12)
        self.assertEqual(evidence["status"], firm.table_status())

    def test_fallbacks(self):
        sizewell, _ = firm.nuclear_load_factor("nuclear:sizewell-b", 1198.0)
        self.assertAlmostEqual(sizewell, 0.801, 12)
        planned, evidence = firm.nuclear_load_factor("hinkley-point-c-unit-1", 1630.0)
        self.assertEqual((planned, evidence["basis"]), (0.801, "planned_project_reactor_type"))
        national, evidence = firm.nuclear_load_factor("Nuclear", 5883.0)
        self.assertEqual((national, evidence["basis"]), (0.723, "national_aggregate"))

    def test_hydro_annual_mean_and_kernel_identity(self):
        # P0-5b values (flat shape); the A14 values are tested in tests.test_f2_corrected_data.
        values, evidence = firm.asset_availability(asset_id="Hydro_natural_flow", technology="Hydro_natural_flow",
                                                   capacity_mw=2000.0, year=2026, periods=17520, method=firm.P05B)
        self.assertAlmostEqual(float(values.mean()), 0.334, 12)
        assets = [AssetStateV2("nuclear:heysham-1", "Nuclear", 1155.0), AssetStateV2("nuclear:sizewell-b", "Nuclear", 1198.0),
                  AssetStateV2("Hydro_natural_flow", "Hydro_natural_flow", 2000.0), AssetStateV2("gas", "CCGT", 500.0)]
        kernel = firm.kernel_availability(assets, year=2030, periods=17520)
        self.assertEqual(set(kernel), {"Nuclear", "Hydro_natural_flow"})
        energy = sum(firm.asset_availability(asset_id=a.asset_id, technology=a.technology, capacity_mw=a.capacity_mw,
                                             year=2030, periods=17520)[0] * a.capacity_mw for a in assets[:2])
        np.testing.assert_allclose(kernel["Nuclear"] * (1155.0 + 1198.0), energy, rtol=0, atol=1e-9)
        self.assertIsNone(firm.asset_availability(asset_id="gas", technology="CCGT", capacity_mw=1.0, year=2030, periods=4))

    def test_month_calendar(self):
        months = firm.month_of_period(17520)
        self.assertEqual(int(months[0]), 0)
        self.assertEqual(int(months[firm.first_period_of_month(4)]), 3)
        self.assertEqual(int(months[firm.first_period_of_month(4) - 1]), 2)
        self.assertEqual(int(months[-1]), 11)


class RawBoundaryPriceTests(unittest.TestCase):
    def test_profiles(self):
        from gridform_core.canonical_psm_data import _raw_boundary_price

        self.assertTrue(_raw_boundary_price(CORRECTED))
        self.assertFalse(_raw_boundary_price(DOCTORAL))


class KernelInjectionTests(unittest.TestCase):
    def test_assign_period_and_length_guard(self):
        from gridform_core.builtin.scheme_c_1000twh import kernel_injection as ki

        solar = SimpleNamespace(name="solar_London", capacity_multiplier=100.0, capacity_limit=0.0)
        wind = SimpleNamespace(name="offshore1", capacity_multiplier=5.0, capacity_limit=0.0)
        nuclear = SimpleNamespace(name="Nuclear", capacity_limit=1000.0)
        inputs = ki.KernelSiteInputs({"solar_London": np.array([0.5, 0.25]), "offshore1": np.array([1.0, 0.1])},
                                     {"Nuclear": np.array([0.8, 0.0])})
        bound = ki.active_site_inputs(SimpleNamespace(kernel_site_inputs=inputs), [solar, wind, nuclear], 2)
        ki.assign_period(bound, 1)
        self.assertEqual((solar.capacity_limit, nuclear.capacity_limit), (25.0, 0.0))
        self.assertAlmostEqual(wind.capacity_limit, 5.0 * 20.0 * 0.1, 12)
        ki.assign_period(bound, 0)
        self.assertEqual(nuclear.capacity_limit, 800.0)
        self.assertIsNone(ki.active_site_inputs(SimpleNamespace(), [solar], 2))
        with self.assertRaises(ValueError):
            ki.active_site_inputs(SimpleNamespace(kernel_site_inputs=inputs), [solar], 3)

    def test_kernel_receives_the_canonical_arrays(self):
        """Corrected: the kernel's 43-site style arrays hash-equal the canonical adapter's; doctoral: no injection."""

        from gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm import SchemeCNativePSM

        manifest, _, _ = _pack(PACK_101)
        model_input = SimpleNamespace(operating_state=SimpleNamespace(assets=()), year=2025)
        doctoral = SchemeCNativePSM._kernel_site_inputs(PACK_101, manifest, SimpleNamespace(profile_id=DOCTORAL),
                                                        model_input, 96)
        self.assertIsNone(doctoral)
        corrected = SchemeCNativePSM._kernel_site_inputs(PACK_101, manifest, SimpleNamespace(profile_id=CORRECTED),
                                                         model_input, 96)
        _, shared = _profiles(PACK_101, CORRECTED_METHOD, periods=96)
        self.assertEqual(set(corrected.vre_cf), set(shared))
        for name, (values, evidence) in shared.items():
            self.assertEqual(hashlib.sha256(np.asarray(corrected.vre_cf[name], dtype="<f8").tobytes()).hexdigest(),
                             evidence["availability_sha256"])
        self.assertEqual(corrected.evidence["site_weather"]["method_id"], CORRECTED_METHOD.method_id)


class WeatherCacheKeyTests(unittest.TestCase):
    def test_key_follows_path_and_content_stamp(self):
        from gridform_core.builtin.scheme_c_1000twh.kernel_injection import weather_cache_key

        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / "a.nc", Path(temp) / "b.nc"
            first.write_bytes(b"one")
            second.write_bytes(b"one")
            key = weather_cache_key(str(first), str(second))
            self.assertEqual(key, weather_cache_key(str(first), str(second)))
            self.assertNotEqual(key, weather_cache_key(str(second), str(first)))
            first.write_bytes(b"other content")
            self.assertNotEqual(key, weather_cache_key(str(first), str(second)))

    def test_kernel_discards_a_cache_built_from_other_files(self):
        source = (ROOT / "gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py").read_text(
            encoding="utf-8")
        self.assertIn("_WEATHER_LIMIT_CACHE[0] != _weather_key", source)
        self.assertIn(") = _WEATHER_LIMIT_CACHE[1]", source)


class AdvisoryTests(unittest.TestCase):
    """S12: each new advisory hits an ERA5 research-pack run without the correction, and nothing else."""

    def test_rules_hit_and_do_not_misfire(self):
        from gridform_core.methodology import load_catalogue
        from gridform_core.result_advisories import _applies

        corrections = load_catalogue().corrections
        gbp1 = {"modules": {"value-bid-at-cost-psm"}, "mode": "two_year", "data_pack": "value-uk-open-data-pack-v1",
                "engine": ""}
        teaching = dict(gbp1, data_pack="value-101-baseline-v1")
        for correction_id in ("p05.weather-time-convention", "p05.vre-loss-factors", "p05.firm-availability"):
            correction = corrections[correction_id]
            self.assertIsNotNone(correction.advisory)
            self.assertTrue(_applies(correction.applies_when, gbp1), correction_id)
            self.assertFalse(_applies(correction.applies_when, teaching), correction_id)
        self.assertIsNone(corrections["p05.raw-boundary-price"].advisory)
        # A corrected run applies the corrections, so their advisories are skipped (evaluate_advisories).
        from gridform_core.methodology import resolve_methodology

        corrected = resolve_methodology(CORRECTED)
        doctoral = resolve_methodology(DOCTORAL)
        for correction_id in ("p05.weather-time-convention", "p05.vre-loss-factors", "p05.firm-availability",
                              "p05.raw-boundary-price"):
            self.assertIn(correction_id, corrected.applied_correction_ids)
            self.assertNotIn(correction_id, doctoral.applied_correction_ids)
        self.assertIn("p05.weather-cache-key", doctoral.applied_correction_ids)


if __name__ == "__main__":
    unittest.main()
