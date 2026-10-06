"""F2: corrected-profile solar plane-of-array (A13), nuclear month retirement (A10) and hydro (A14).

Hand-computable solar geometry (equinox and solstice noon at 51.5 N), the
Erbs correlation, the Hay-Davies transposition of one period, the horizontal
identity (tilt 0 returns GHI), a synthetic clear-sky annual sanity check and,
with the research pack (``VALUE_P0_5_PACKS``), the GBP1 annual energy check.
"""

from __future__ import annotations

import json
import math
import os
import unittest
from pathlib import Path

import numpy as np

from gridform_core import firm_availability as firm
from gridform_core import site_weather as sw
from gridform_core import solar_irradiance as si
from gridform_core.doctoral_weather_mapping import representative_sites
from gridform_core.v2.contracts import AssetStateV2

ROOT = Path(__file__).resolve().parents[1]
PACK_101 = ROOT / "data-packs" / "value-101-baseline-v1"
CORRECTED = "value-corrected"
DOCTORAL = "doctoral-lineage-0.6.0a2"
P05B_METHOD = sw.SiteWeatherMethod("v2", True)
F2_METHOD = sw.SiteWeatherMethod("v2", True, True)
DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def _gbp1_root() -> Path | None:
    spec = os.environ.get("VALUE_P0_5_PACKS", "")
    root = Path(spec.split(":")[0]) if spec else None
    return root if root is not None and (root / "manifest.json").is_file() else None


def _pack(root: Path):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest["bindings"]
    fleet = json.loads((root / bindings["fleet.generators"]["uri"]).read_text(encoding="utf-8"))
    roles = ("weather.solar", "weather.wind")
    return fleet, {
        "paths": {role: root / bindings[role]["uri"] for role in roles},
        "hashes": {role: bindings[role]["sha256"] for role in roles},
        "bindings": {role: bindings[role] for role in roles},
    }


def _profiles(root: Path, method, *, solar_only=False, periods=17520):
    fleet, files = _pack(root)
    sites = representative_sites(fleet)
    names = [n for n in sites if sites[n]["technology"] == "solar"] if solar_only else list(sites)
    return sites, sw.site_cf_by_source(**files, sites=sites, sources=names, periods=periods, method=method)


def _erbs(kt: float) -> float:
    if kt <= 0.22:
        return 1.0 - 0.09 * kt
    if kt <= 0.80:
        return 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    return 0.165


class SolarGeometryTests(unittest.TestCase):
    def test_equinox_noon_at_51_5_faces_a_latitude_tilted_plane(self):
        """Declination 0, hour angle 0: zenith = 51.5 deg; a plane tilted 51.5 deg faces the sun."""

        cos_z, cos_theta = si.incidence_cosines(51.5, 0.0, 0.0, 51.5)
        self.assertAlmostEqual(float(cos_z), math.cos(math.radians(51.5)), 12)   # 0.622515
        self.assertAlmostEqual(float(cos_z), 0.6225146, 6)
        self.assertAlmostEqual(float(cos_theta), 1.0, 12)
        _, horizontal = si.incidence_cosines(51.5, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(float(horizontal), float(cos_z), 12)

    def test_solstice_noon_and_equinox_sunset(self):
        decl = math.radians(23.45)
        cos_z, cos_theta = si.incidence_cosines(51.5, decl, 0.0, 36.0)
        self.assertAlmostEqual(math.degrees(math.acos(float(cos_z))), 51.5 - 23.45, 9)       # 28.05 deg
        self.assertAlmostEqual(math.degrees(math.acos(float(cos_theta))), abs(51.5 - 36.0 - 23.45), 9)  # 7.95 deg
        sunset, _ = si.incidence_cosines(51.5, 0.0, math.radians(90.0), 0.0)
        self.assertAlmostEqual(float(sunset), 0.0, 12)

    def test_spencer_series_reference_days(self):
        self.assertLess(abs(math.degrees(float(si.declination(80)))), 0.5)      # 21 March
        self.assertAlmostEqual(math.degrees(float(si.declination(172))), 23.45, delta=0.05)
        self.assertAlmostEqual(math.degrees(float(si.declination(355))), -23.42, delta=0.05)
        self.assertAlmostEqual(float(si.equation_of_time_minutes(42)), -14.2, delta=0.2)   # 11 February
        self.assertAlmostEqual(float(si.equation_of_time_minutes(307)), 16.4, delta=0.2)   # 3 November
        self.assertAlmostEqual(float(si.eccentricity_factor(1)), 1.035, delta=0.001)      # perihelion side
        self.assertAlmostEqual(float(si.eccentricity_factor(185)), 0.967, delta=0.001)    # aphelion side

    def test_hour_angle_and_model_clock(self):
        doy = 80
        noon = 12.0 - float(si.equation_of_time_minutes(doy)) / 60.0
        self.assertAlmostEqual(float(si.hour_angle(noon, 0.0, doy)), 0.0, 12)
        self.assertAlmostEqual(math.degrees(float(si.hour_angle(noon + 1.0, 0.0, doy))), 15.0, 9)
        # 15 deg east reaches solar noon one hour earlier in UTC.
        self.assertAlmostEqual(float(si.hour_angle(noon - 1.0, 15.0, doy)), 0.0, 12)
        day, hours = si.period_clock(17521)
        self.assertEqual((int(day[0]), float(hours[0])), (1, 0.25))
        self.assertEqual((int(day[47]), float(hours[47])), (1, 23.75))
        self.assertEqual((int(day[48]), int(day[17519]), int(day[17520])), (2, 365, 1))

    def test_jacobson_jadhav_optimal_tilt(self):
        self.assertAlmostEqual(si.optimal_tilt_jacobson_jadhav(51.5), 36.03, delta=0.01)
        self.assertAlmostEqual(si.optimal_tilt_jacobson_jadhav(0.0), 1.3793, 12)
        with self.assertRaises(ValueError):
            si.optimal_tilt_jacobson_jadhav(70.0)


class DecompositionTransposition(unittest.TestCase):
    def test_erbs_correlation_values(self):
        np.testing.assert_allclose(si.erbs_diffuse_fraction([0.1, 0.5, 0.9]), [0.991, 0.65915, 0.165], atol=1e-12)
        self.assertLess(abs(float(si.erbs_diffuse_fraction(0.22)) - float(si.erbs_diffuse_fraction(0.2200001))), 1e-3)

    def test_one_period_at_equinox_noon_by_hand(self):
        """GHI 0.6 kW m-2 at solar noon of day 80, 51.5 N, 0 E, tilt 51.5 deg (cos incidence ~ 1)."""

        parameters = sw.plane_of_array_parameters()
        doy = 80
        noon = 12.0 - float(si.equation_of_time_minutes(doy)) / 60.0
        poa, _ = si.plane_of_array(np.array([0.6]), latitude_deg=51.5, longitude_deg=0.0, parameters=parameters,
                                   tilt_deg=51.5, day_of_year=np.array([doy]), utc_hours=np.array([noon]))
        # Independent scalar arithmetic: declination ~0 at day 80 (Spencer: -0.066 deg).
        cos_z = math.cos(math.radians(51.5 + 0.066))
        i0n = 1.361 * 1.0079                       # solar constant x eccentricity factor of day 80
        kt = 0.6 / (i0n * cos_z)                   # 0.7020
        kd = _erbs(kt)
        dhi, bhi = kd * 0.6, (1 - kd) * 0.6
        dni = bhi / cos_z
        ai = dni / i0n
        rb = 1.0 / cos_z                           # cos incidence = cos(declination) ~ 1
        sky = (1 + math.cos(math.radians(51.5))) / 2
        ground = 0.6 * 0.2 * (1 - math.cos(math.radians(51.5))) / 2
        expected = bhi * rb + dhi * (ai * rb + (1 - ai) * sky) + ground
        self.assertAlmostEqual(float(poa[0]), expected, delta=2e-3 * expected)
        self.assertGreater(float(poa[0]), 0.6)     # facing the sun beats the horizontal plane

    def test_low_sun_is_isotropic_and_tilt_zero_returns_ghi(self):
        parameters = sw.plane_of_array_parameters()
        poa, _ = si.plane_of_array(np.array([0.05]), latitude_deg=51.5, longitude_deg=0.0, parameters=parameters,
                                   tilt_deg=36.0, day_of_year=np.array([80]), utc_hours=np.array([0.25]))
        cos_beta = math.cos(math.radians(36.0))
        self.assertAlmostEqual(float(poa[0]), 0.05 * ((1 + cos_beta) / 2 + 0.2 * (1 - cos_beta) / 2), 12)
        rng = np.random.default_rng(7)
        ghi = rng.uniform(0.0, 0.9, 17520)
        flat, evidence = si.plane_of_array(ghi, latitude_deg=55.0, longitude_deg=-3.0, parameters=parameters,
                                           tilt_deg=0.0)
        np.testing.assert_allclose(flat, ghi, rtol=1e-12, atol=1e-15)
        self.assertAlmostEqual(evidence["poa_to_ghi_ratio"], 1.0, 12)

    def test_clear_sky_annual_sanity(self):
        """Synthetic clear-ish sky (kt 0.65 whenever the sun is up) over a year at London.

        Annual horizontal energy is plausible for a cloud-free UK year, the
        latitude-optimal plane gains 15-35 %, and the best tilt in 5-degree
        steps lies between 30 and 50 degrees.
        """

        parameters = sw.plane_of_array_parameters()
        day, hours = si.period_clock(17520)
        cos_z, _ = si.incidence_cosines(51.5, si.declination(day), si.hour_angle(hours, -0.13, day), 0.0)
        ghi = 0.65 * 1.361 * si.eccentricity_factor(day) * np.clip(cos_z, 0.0, None)
        annual_ghi = float(ghi.sum()) * 0.5
        self.assertTrue(1300.0 < annual_ghi < 1900.0, annual_ghi)
        gains = {}
        for tilt in range(0, 75, 5):
            _, evidence = si.plane_of_array(ghi, latitude_deg=51.5, longitude_deg=-0.13, parameters=parameters,
                                            tilt_deg=float(tilt))
            gains[tilt] = evidence["poa_to_ghi_ratio"]
        best = max(gains, key=gains.get)
        self.assertTrue(30 <= best <= 50, gains)
        optimum = si.optimal_tilt_jacobson_jadhav(51.5)
        _, evidence = si.plane_of_array(ghi, latitude_deg=51.5, longitude_deg=-0.13, parameters=parameters)
        self.assertAlmostEqual(evidence["tilt_deg"], optimum, 12)
        self.assertTrue(1.15 < evidence["poa_to_ghi_ratio"] < 1.35, evidence)


class PlaneOfArrayTests(unittest.TestCase):
    def test_profiles_and_method_ids(self):
        self.assertEqual(sw.method_for_profile(CORRECTED), F2_METHOD)
        self.assertEqual(sw.method_for_profile(DOCTORAL), sw.FROZEN)
        self.assertEqual(P05B_METHOD.method_id, "value.site-weather/v2+clock-v2+losses-v1")
        self.assertEqual(F2_METHOD.method_id, "value.site-weather/v2+clock-v2+losses-v1+solar-poa-v1")
        self.assertTrue(sw.FROZEN.frozen and not F2_METHOD.frozen)
        self.assertEqual(sw.method_for_correction_ids(["p05.weather-time-convention", "p05.vre-loss-factors"]),
                         P05B_METHOD)
        self.assertEqual(sw.method_for_correction_ids([]), sw.FROZEN)
        table = sw.load_loss_factors()["solar_plane_of_array"]
        self.assertEqual((table["tilt_rule"], table["albedo"], table["decomposition"], table["transposition"]),
                         ("jacobson-jadhav-2018", 0.2, "erbs-1982", "hay-davies-1980"))
        sources = sw.load_loss_factors()["sources"]
        for key in ("tilt_source_ids", "albedo_source_ids", "solar_constant_source_ids", "decomposition_source_ids",
                    "transposition_source_ids", "geometry_source_ids"):
            self.assertTrue(set(table[key]) <= set(sources), key)

    def test_applies_only_to_era5_accumulations_on_the_v2_clock(self):
        self.assertTrue(sw.plane_of_array_applies(F2_METHOD, sw.ACCUMULATION_END)[0])
        self.assertFalse(sw.plane_of_array_applies(F2_METHOD, sw.INSTANT)[0])
        self.assertFalse(sw.plane_of_array_applies(sw.SiteWeatherMethod("v1", True, True), sw.ACCUMULATION_END)[0])
        self.assertFalse(sw.plane_of_array_applies(P05B_METHOD, sw.ACCUMULATION_END)[0])

    def test_value_101_synthetic_solar_keeps_the_horizontal_ratio(self):
        """VALUE 101 samples are not ERA5 accumulations (about 1 kW m-2 at a December noon)."""

        sites, p05b = _profiles(PACK_101, P05B_METHOD, periods=1000)
        _, f2 = _profiles(PACK_101, F2_METHOD, periods=1000)
        for name, site in sites.items():
            np.testing.assert_array_equal(f2[name][0], p05b[name][0])
            if site["technology"] == "solar":
                self.assertEqual(f2[name][1]["solar_plane_of_array"]["applied"], False)
                self.assertIn("not an ERA5 hourly accumulation", f2[name][1]["solar_plane_of_array"]["reason"])

    def test_era5_like_source_is_transposed_then_scaled_by_pr(self):
        """A one-site ERA5-style accumulation: values = min(POA x 0.83, 1), geometry at the period midpoint."""

        from types import SimpleNamespace
        from unittest import mock

        periods = 96
        hourly = np.zeros(48)
        hourly[8:17] = [0.1, 0.3, 0.5, 0.6, 0.65, 0.6, 0.5, 0.3, 0.1]   # value stamped at the END of the hour
        evidence = {"grid_latitude": 51.5, "grid_longitude": 0.0, "source_variable": "ssrd", "curve": "x",
                    "source_hour_count": 48, "time_convention": sw.ACCUMULATION_END}
        sites = {"solar_Test": {"technology": "solar", "lat": 51.5, "lon": 0.0}}
        with mock.patch.object(sw, "verified_sha256", lambda path, expected: "sha"), \
                mock.patch.object(sw, "hourly_unit_cf", lambda *a, **k: (hourly, dict(evidence))), \
                mock.patch.dict("sys.modules", {"netCDF4": SimpleNamespace(Dataset=lambda *a, **k: _NullDataset())}):
            result = sw.site_cf_by_source(paths={"weather.solar": Path("x.nc")}, hashes={"weather.solar": "sha"},
                                          bindings=None, sites=sites, sources=["solar_Test"], periods=periods,
                                          method=F2_METHOD)
        values, item = result["solar_Test"]
        ghi = hourly[sw.hour_index(periods, 48, "v2", sw.ACCUMULATION_END)]
        poa, _ = si.plane_of_array(ghi, latitude_deg=51.5, longitude_deg=0.0, parameters=sw.plane_of_array_parameters())
        np.testing.assert_allclose(values, np.minimum(poa * 0.83, 1.0), rtol=1e-12, atol=0)
        self.assertTrue(item["solar_plane_of_array"]["applied"])
        self.assertAlmostEqual(item["solar_plane_of_array"]["tilt_deg"], si.optimal_tilt_jacobson_jadhav(51.5), 12)
        self.assertEqual(item["method_id"], F2_METHOD.method_id)
        # Period 16 (08:00-08:30 UTC, geometry at 08:15) takes the value stamped 09:00 (the hour 08-09).
        self.assertEqual((float(ghi[16]), float(ghi[17])), (float(hourly[9]), float(hourly[9])))
        self.assertEqual(float(ghi[14]), float(hourly[8]))

    @unittest.skipUnless(_gbp1_root(), "set VALUE_P0_5_PACKS to the GBP1 national pack")
    def test_gbp1_annual_energy_sanity(self):
        """GBP1 (ERA5 2020-2024 climatology): plausible GHI, a modest tilt gain, solar CF near DUKES."""

        sites, horizontal = _profiles(_gbp1_root(), sw.SiteWeatherMethod("v2", False), solar_only=True)
        _, f2 = _profiles(_gbp1_root(), F2_METHOD, solar_only=True)
        for name in horizontal:
            ghi_kwh = float(horizontal[name][0].sum()) * 0.5
            self.assertTrue(850.0 < ghi_kwh < 1250.0, (name, ghi_kwh))
            poa = f2[name][1]["solar_plane_of_array"]
            self.assertTrue(poa["applied"])
            self.assertTrue(1.0 < poa["poa_to_ghi_ratio"] < 1.25, (name, poa))
            self.assertTrue(35.0 < poa["tilt_deg"] < 38.5, (name, poa))
        cf = sw.annual_capacity_factors(f2, sites)["solar"]
        self.assertAlmostEqual(cf, 0.1065, delta=0.0005)
        london = f2["solar_London"][0]
        tod = (np.arange(len(london)) % 48) / 2 + 0.25
        self.assertLess(abs(float((london * tod).sum() / london.sum()) - 12.0), 0.15)


class _NullDataset:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class NuclearGenerationEndTests(unittest.TestCase):
    def test_heysham_2_and_torness_retire_in_march_2030(self):
        for station, mw in (("heysham-2", 1230.0), ("torness", 1190.0)):
            values, evidence = firm.asset_availability(asset_id=f"nuclear:{station}", technology="Nuclear",
                                                       capacity_mw=mw, year=2030, periods=17520)
            self.assertEqual(evidence["generation_end_period"], 4320)
            self.assertTrue(np.all(values[4320:] == 0.0))
            self.assertTrue(np.all(values[:4320] > 0.7))
            self.assertEqual(firm.announced_generation_end(station), "2030-03")
            # P0-5b behaviour (no month): the whole of 2030 stays available.
            old, evidence = firm.asset_availability(asset_id=f"nuclear:{station}", technology="Nuclear",
                                                    capacity_mw=mw, year=2030, periods=17520, method=firm.P05B)
            self.assertNotIn("generation_end_period", evidence)
            self.assertTrue(np.all(old > 0.7))
            self.assertEqual(firm.announced_generation_end(station, firm.P05B), "2030")

    def test_station_values_unchanged_and_reviewed(self):
        """A14: the station values are approved unchanged (reference statistics 1.4a, 3 decimals)."""

        stations = firm.load_table()["nuclear"]["stations"]
        self.assertEqual({k: v["pris_load_factor"] for k, v in stations.items()},
                         {"heysham-1": 0.668, "hartlepool": 0.689, "heysham-2": 0.752, "torness": 0.792,
                          "sizewell-b": 0.801})
        self.assertTrue(firm.table_status().startswith("AUTHOR REVIEWED"))
        _, evidence = firm.asset_availability(asset_id="nuclear:sizewell-b", technology="Nuclear",
                                              capacity_mw=1198.0, year=2055, periods=17520)
        self.assertNotIn("generation_end_period", evidence)   # "2055" has no month: whole year
        self.assertEqual(evidence["status"], firm.table_status())

    def test_profile_switches(self):
        self.assertEqual(firm.method_for_profile(CORRECTED), firm.LATEST)
        self.assertEqual(firm.method_for_profile(DOCTORAL), firm.P05B)
        self.assertFalse(firm.enabled_for_profile(DOCTORAL))


class HydroLoadFactorTests(unittest.TestCase):
    SHAPE = [1.3851, 1.3851, 1.3851, 0.6582, 0.6582, 0.6582, 0.6776, 0.6776, 0.6776, 1.2791, 1.2791, 1.2791]

    def test_a14_values_and_period_weighted_mean(self):
        values, evidence = firm.asset_availability(asset_id="Hydro_natural_flow", technology="Hydro_natural_flow",
                                                   capacity_mw=2000.0, year=2030, periods=17520)
        self.assertEqual(evidence["load_factor"], 0.3487)
        self.assertAlmostEqual(sum(self.SHAPE) / 12.0, 1.0, 12)
        months = firm.month_of_period(17520)
        np.testing.assert_allclose(values, 0.3487 * np.asarray(self.SHAPE)[months], rtol=0, atol=1e-15)
        weighted = float(np.dot(self.SHAPE, DAYS)) / 365.0          # 0.99883 on the 365-day calendar
        self.assertAlmostEqual(weighted, 0.998826, 6)
        self.assertAlmostEqual(float(values.mean()), 0.3487 * weighted, 12)
        old, _ = firm.asset_availability(asset_id="Hydro_natural_flow", technology="Hydro_natural_flow",
                                         capacity_mw=2000.0, year=2030, periods=17520, method=firm.P05B)
        self.assertAlmostEqual(float(old.mean()), 0.334, 12)

    def test_gbp1_hydro_energy_within_15_percent_of_dukes(self):
        """A14 acceptance: 2000 MW of GBP1 natural-flow hydro vs DUKES 6.2 2019-2024 mean 5.77 TWh."""

        values, _ = firm.asset_availability(asset_id="Hydro_natural_flow", technology="Hydro_natural_flow",
                                            capacity_mw=2000.0, year=2030, periods=17520)
        twh = float(values.sum()) * 2000.0 * 0.5 / 1e6
        self.assertAlmostEqual(twh, 6.102, delta=0.001)
        self.assertLess(abs(twh / 5.77 - 1.0), 0.15)

    def test_kernel_identity_with_new_values(self):
        assets = [AssetStateV2("nuclear:torness", "Nuclear", 1190.0), AssetStateV2("nuclear:sizewell-b", "Nuclear", 1198.0),
                  AssetStateV2("Hydro_natural_flow", "Hydro_natural_flow", 2000.0)]
        kernel = firm.kernel_availability(assets, year=2030, periods=17520)
        energy = sum(firm.asset_availability(asset_id=a.asset_id, technology=a.technology, capacity_mw=a.capacity_mw,
                                             year=2030, periods=17520)[0] * a.capacity_mw for a in assets[:2])
        np.testing.assert_allclose(kernel["Nuclear"] * (1190.0 + 1198.0), energy, rtol=0, atol=1e-9)
        hydro, _ = firm.asset_availability(asset_id="Hydro_natural_flow", technology="Hydro_natural_flow",
                                           capacity_mw=2000.0, year=2030, periods=17520)
        np.testing.assert_allclose(kernel["Hydro_natural_flow"], hydro, rtol=0, atol=1e-15)


if __name__ == "__main__":
    unittest.main()
