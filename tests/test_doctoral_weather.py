"""Regression tests for the actual native chronology boundary, not a CSV mock."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

from gridform_core.canonical_psm_data import build_chronology
from gridform_core.data_method import run_policy
from gridform_core.v2.contracts import AssetStateV2, OperatingState, ResolvedRun, YearState
from gridform_core.v2.orchestrator import json_checkpoint_writer, load_json_checkpoint
from gridform_core.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


class DoctoralWeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pack = Path(self.temp.name) / "pack"
        shutil.copytree(ROOT / "data-packs/value-synthetic-contract-pack-v1", self.pack)
        self.manifest = json.loads((self.pack / "manifest.json").read_text())
        self.manifest["id"] = "value-uk-open-data-pack-v1"
        self.fleet = {"generators": {}, "batteries": {}, "connections": {},
                      "electrolyzer": {}, "locations": {
                          "Nottingham": {"lat": 53.0, "lon": -1.0},
                          "London": {"lat": 51.0, "lon": -1.0},
                          "offshore1": {"lat": 53.0, "lon": 1.0}}}
        for name in ("solar_Nottingham", "solar_London", "onshore_Nottingham", "offshore1"):
            self.fleet["generators"][name] = {"name": name, "capacity_multiplier": 10}
        fleet_path = self.pack / self.manifest["bindings"]["fleet.generators"]["uri"]
        fleet_path.write_text(json.dumps(self.fleet))
        self.assets = tuple(AssetStateV2(name, tech, 100.0) for name, tech in (
            ("solar_Nottingham", "solar"), ("solar_London", "solar"),
            ("onshore_Nottingham", "onshore"), ("offshore1", "offshore")))
        self.write_weather()

    def write_weather(self, *, four_dimensional=False, uv=False):
        for role in ("weather.wind", "weather.solar"):
            path = self.pack / (role + ".nc")
            with Dataset(path, "w") as ds:
                for key, length in (("latitude", 2), ("longitude", 2), ("time", 4)):
                    ds.createDimension(key, length)
                ds.createVariable("latitude", "f8", ("latitude",))[:] = [53., 51.]
                ds.createVariable("longitude", "f8", ("longitude",))[:] = [-1., 1.]
                dims = ("time", "latitude", "longitude")
                if four_dimensional:
                    ds.createDimension("day", 2)
                    ds.createDimension("hour", 2)
                    dims = ("latitude", "longitude", "day", "hour")
                a = np.zeros((4, 2, 2))
                if role.endswith("wind"):
                    a[:, 0, 0] = [2., 9.7, 25., 25.1]
                    a[:, 0, 1] = [3., 10.5, 30., 30.1]
                    name = "u100" if uv else "wind_speed"
                    # If wind_speed is present it must take precedence over u/v.
                    ds.createVariable("v100", "f8", dims)[:] = 0
                    if not uv:
                        ds.createVariable("u100", "f8", dims)[:] = 0
                else:
                    name = "ssrd"
                    a[:, 0, 0] = [3600., 7200., 1_800_000., 3_600_000.]
                    a[:, 1, 0] = [0., 360_000., 900_000., 0.]
                if four_dimensional:
                    a = a.transpose(1, 2, 0).reshape(2, 2, 2, 2)
                ds.createVariable(name, "f8", dims)[:] = a
            self.manifest["bindings"][role] = {
                "uri": path.name, "format": "nc", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def chronology(self, periods=8, assets=None, period_hours=0.5):
        return build_chronology(self.pack, self.manifest,
            OperatingState(2025, self.assets if assets is None else assets, ()),
            periods=periods, period_hours=period_hours, data_policy=run_policy(self.manifest))

    def test_real_dispatch_uses_distinct_site_profiles_and_original_curve_boundaries(self):
        rows = {r.asset_id: r for r in self.chronology().resources}
        self.assertEqual(rows["solar_Nottingham"].availability,
                         (0., 0., .002, .002, .5, .5, 1., 1.))
        self.assertEqual(rows["solar_London"].availability,
                         (0., 0., .1, .1, .25, .25, 0., 0.))
        self.assertEqual(rows["onshore_Nottingham"].availability, (0., 0., 1., 1., 1., 1., 0., 0.))
        self.assertEqual(rows["offshore1"].availability, (0., 0., 1., 1., 1., 1., 0., 0.))
        self.assertTrue(all(rows[a.asset_id].capacity_mw == a.capacity_mw for a in self.assets))

    def test_hourly_repeat_is_not_bypassed_when_requested_periods_equal_source_rows(self):
        rows = {r.asset_id: r for r in self.chronology(periods=4).resources}
        self.assertEqual(rows["solar_Nottingham"].availability, (0., 0., .002, .002))

    def test_four_dimensional_layout_and_uv_fallback_preserve_clock(self):
        self.write_weather(four_dimensional=True, uv=True)
        rows = {r.asset_id: r for r in self.chronology(periods=10).resources}
        self.assertEqual(rows["onshore_Nottingham"].availability,
                         (0., 0., 1., 1., 1., 1., 0., 0., 0., 0.))
        self.assertEqual(rows["solar_London"].availability[:8], (0., 0., .1, .1, .25, .25, 0., 0.))

    def test_missing_weather_does_not_silently_fall_back_to_csv(self):
        self.manifest["bindings"]["weather.wind"]["uri"] = "missing.nc"
        with self.assertRaisesRegex(ValueError, "missing|weather"):
            self.chronology()

    def test_content_hash_mismatch_is_rejected_before_profiles_are_used(self):
        self.manifest["bindings"]["weather.wind"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash|SHA|sha256"):
            self.chronology()

    def test_new_asset_inherits_explicit_weather_owner_not_a_technology_average(self):
        assets = (AssetStateV2("commissioned:investment-1", "solar", 50.,
                              extensions={"investment_owner_id": "solar_London"}),)
        row = self.chronology(assets=assets).resources[0]
        self.assertEqual(row.availability, (0., 0., .1, .1, .25, .25, 0., 0.))
        self.assertEqual(row.extensions["weather_profile"]["source_asset_id"], "solar_London")

    def test_unmapped_asset_and_non_half_hour_clock_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "weather.*identity|weather.*mapping"):
            self.chronology(assets=(AssetStateV2("unmapped", "solar", 1.),))
        with self.assertRaisesRegex(ValueError, "half.hour|0.5"):
            self.chronology(period_hours=1.)

    def test_investment_headroom_is_not_changed_by_site_weather(self):
        before = self.chronology().extensions["vre_expansion_headroom_mw_by_technology"]
        self.write_weather(four_dimensional=True)
        after = self.chronology().extensions["vre_expansion_headroom_mw_by_technology"]
        self.assertEqual(before, after)

    def test_original_solar_upper_cutoff_is_not_replaced_by_clipping_to_one(self):
        path = self.pack / "weather.solar.nc"
        with Dataset(path, "a") as ds:
            ds.variables["ssrd"][:, 0, 0] = [36_000_000., 36_000_001., 3600., 3601.]
        self.manifest["bindings"]["weather.solar"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = {r.asset_id: r for r in self.chronology().resources}
        self.assertEqual(rows["solar_Nottingham"].availability[:6], (10., 10., 0., 0., 0., 0.))

    def test_missing_or_nonfinite_site_values_are_not_replaced_or_averaged(self):
        path = self.pack / "weather.wind.nc"
        for bad in (np.nan, np.inf, np.ma.masked):
            with self.subTest(value=str(bad)):
                with Dataset(path, "a") as ds:
                    ds.variables["wind_speed"][0, 0, 0] = bad
                self.manifest["bindings"]["weather.wind"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "weather"):
                    self.chronology()

    def test_changed_weather_identity_cannot_resume_an_old_annual_checkpoint(self):
        old = ResolvedRun("run", "study", "scenario", "pack", 2025, 2034, {}, {}, {})
        folder = Path(self.temp.name) / "checkpoints"
        json_checkpoint_writer(folder, old)(YearState(2026, (), ()))
        changed = replace(old, extensions={"dispatch_weather_identity": {"method_id": "value.doctoral-site-weather/v1"}})
        with self.assertRaisesRegex(ContractError, "identity"):
            load_json_checkpoint(folder / "state-2026.json", changed)

    def test_interior_wind_speeds_use_original_cubic_not_linear_interpolation(self):
        path = self.pack / "weather.wind.nc"
        with Dataset(path, "a") as ds:
            ds.variables["wind_speed"][:, 0, 0] = [3., 5., 7., 9.]
            ds.variables["wind_speed"][:, 0, 1] = [3., 5., 7., 9.]
        self.manifest["bindings"]["weather.wind"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = {r.asset_id: r for r in self.chronology().resources}
        for name, rated in (("onshore_Nottingham", 9.7), ("offshore1", 10.5)):
            expected = tuple(value for speed in (3., 5., 7., 9.)
                             for value in [(speed**3 - 3**3) / (rated**3 - 3**3)] * 2)
            np.testing.assert_allclose(rows[name].availability, expected, rtol=0, atol=1e-15)

    def test_weather_identity_is_in_monthly_run_context_without_mutating_project(self):
        from gridform_core.application import build_run_static_context
        from gridform_core.module_context import canonical_context_sha256
        old = ResolvedRun("run", "study", "scenario", "pack", 2025, 2034, {}, {"clock.period_hours": .5}, {})
        changed = replace(old, extensions={"dispatch_weather_identity": {"method_id": "site-v1"}})
        project = {"market_configuration": {"ledger_detail": "summary"}}
        graph = SimpleNamespace(manifests_by_slot={}, to_dict=lambda: {})
        args = dict(project=project, pack_manifest={}, pack_manifest_sha256="a" * 64,
                    resolution_graph=graph, network_pack=None)
        before = build_run_static_context(resolved=old, **args)
        after = build_run_static_context(resolved=changed, **args)
        self.assertNotEqual(canonical_context_sha256(before), canonical_context_sha256(after))
        self.assertEqual(project, {"market_configuration": {"ledger_detail": "summary"}})

    def test_real_application_entry_attaches_weather_identity_even_with_stored_revision(self):
        from gridform_core.application import run_project_application
        manifest = dict(self.manifest, id="value-synthetic-contract-pack-v1")
        (self.pack / "manifest.json").write_text(json.dumps(manifest))
        project = json.loads((ROOT / "tests/fixtures/prompt08_audit_project.json").read_text())
        project["data_pack_id"] = manifest["id"]
        project["revision_sha256"] = "a" * 64
        with patch("gridform_core.application._run_native_project", side_effect=lambda **args: args["resolved"]) as native:
            resolved = run_project_application(project, run_id="weather-entry-test", pack_root=self.pack,
                output_dir=Path(self.temp.name) / "output", mode="smoke")
        self.assertEqual(native.call_count, 1)
        identity = resolved.extensions["dispatch_weather_identity"]
        self.assertEqual(identity["method_id"], "value.doctoral-site-weather/v1")
        for name in ("doctoral_weather.py", "canonical_psm_data.py", "doctoral_weather_mapping.py",
                     "builtin/scheme_c_1000twh/v2_module_definitions.py",
                     "builtin/scheme_c_1000twh/runtime_compat/map_projects_to_generators_by_location.py"):
            self.assertEqual(identity["source_sha256"][name],
                hashlib.sha256((ROOT / "gridform_core" / name).read_bytes()).hexdigest())

    def test_project_fingerprint_records_weather_implementation_identity(self):
        from gridform_core.project_revision import canonical_project_payload
        from gridform_core.v2.module_manifest import workspace_registry
        payload = canonical_project_payload({"modules": {}}, workspace_registry(ROOT / "modules"), self.manifest)
        self.assertEqual(payload["dispatch_weather_identity"]["method_id"], "value.doctoral-site-weather/v1")

    def test_preflight_context_without_run_extension_matches_weather_runtime_context(self):
        from gridform_core.application import build_run_static_context
        from gridform_core.doctoral_weather import weather_execution_identity
        from gridform_core.module_context import canonical_context_sha256
        old = ResolvedRun("run", "study", "scenario", "pack", 2025, 2034, {}, {"clock.period_hours": .5}, {})
        current = replace(old, extensions={"dispatch_weather_identity": weather_execution_identity()})
        graph = SimpleNamespace(manifests_by_slot={}, to_dict=lambda: {})
        args = dict(project={}, pack_manifest=self.manifest, pack_manifest_sha256="a" * 64,
                    resolution_graph=graph, network_pack=None)
        preflight = build_run_static_context(resolved=old, **args)
        runtime = build_run_static_context(resolved=current, **args)
        self.assertEqual(canonical_context_sha256(preflight), canonical_context_sha256(runtime))
        self.assertEqual(preflight.market_configuration["dispatch_weather_identity"], weather_execution_identity())


if __name__ == "__main__":
    unittest.main()
