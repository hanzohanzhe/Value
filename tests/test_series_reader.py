"""P0-5a S1-S4: the declarative series reader, the data policy and the universal reading corrections.

Toys are hand-checkable; the GBP1/R029 checks run when ``VALUE_P0_5_PACKS``
points at the released public1 pack directories (tests/p0_5_fixtures.py).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from gridform_core import series_reader as sr
from gridform_core.data_method import (
    BoundaryIdentityError,
    policy_for_profile,
    read_boundary,
    read_role,
)
from gridform_core.methodology import REFERENCE_PROFILE_ID, default_profile_id
from tests.p0_5_fixtures import GBP1_PUBLIC1, R029_PUBLIC1, VALUE_101_BASELINE, research_pack_roots

CORRECTED = default_profile_id()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class _Temp(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="value-series-reader-"))
        self.addCleanup(shutil.rmtree, self.temp, True)


class DeclaredColumnTests(_Temp):
    """P6-01: an R029-style 7-column file (period first) is read by its declared column."""

    def _r029_like(self) -> Path:
        rows = ["period,flow_mw,price_gbp_per_mwh,source_price_hour_utc,price_half_hour,source_price_csv_line,source_flow_csv_line"]
        for period in range(48):
            rows.append(f"{period},{-100 + 3 * period},{60.5 + period % 7},2022-01-01T00:00:00Z,{period % 2},{61370 + period // 2},{period + 2}")
        return _write(self.temp / "Belgium.csv", "\n".join(rows) + "\n")

    def test_declared_column_is_read_in_both_modes(self) -> None:
        path = self._r029_like()
        spec = sr.SeriesSpec.from_binding("market.belgium.price", {"csv_column": "price_gbp_per_mwh", "csv_header": True})
        for mode in sr.MODES:
            with self.subTest(mode=mode):
                values = sr.read_series(path, spec, mode=mode, legacy_header=None).values
                self.assertEqual(values[:3].tolist(), [60.5, 61.5, 62.5])
                self.assertEqual(values.size, 48)

    def test_undeclared_multi_column_is_refused(self) -> None:
        path = self._r029_like()
        spec = sr.SeriesSpec.from_binding("market.belgium.price", {})
        with self.assertRaises(sr.SeriesReadError) as legacy:
            sr.read_series(path, spec, mode=sr.LEGACY, legacy_header=0)
        self.assertEqual(legacy.exception.code, "GF_DATA_INDEX_COLUMN")
        with self.assertRaises(sr.SeriesReadError) as strict:
            sr.read_series(path, spec, mode=sr.DECLARED, strictness=sr.STRICT)
        self.assertEqual(strict.exception.code, "GF_DATA_AMBIGUOUS_COLUMN")

    def test_missing_declared_column_is_an_error(self) -> None:
        path = self._r029_like()
        spec = sr.SeriesSpec.from_binding("market.belgium.price", {"csv_column": "price_eur"})
        with self.assertRaises(sr.SeriesReadError) as raised:
            sr.read_series(path, spec)
        self.assertEqual(raised.exception.code, "GF_DATA_COLUMN_MISSING")


class DeclaredReaderTests(_Temp):
    """P6-05 (corrected only): a headerless BOM file keeps its first value under declared-v2."""

    def test_bom_numeric_first_row(self) -> None:
        path = self.temp / "2022fd.csv"
        path.write_bytes(b"\xef\xbb\xbf21560\n21970\n21503\n")
        spec = sr.SeriesSpec.from_binding("demand.forecast", {})
        declared = sr.read_series(path, spec, mode=sr.DECLARED, strictness=sr.STRICT).values
        legacy = sr.read_series(path, spec, mode=sr.LEGACY, legacy_header=0).values
        self.assertEqual(declared.tolist(), [21560.0, 21970.0, 21503.0])
        self.assertEqual(legacy.tolist(), [21970.0, 21503.0])

    def test_profiles_select_the_reader(self) -> None:
        manifest = json.loads((VALUE_101_BASELINE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(policy_for_profile(REFERENCE_PROFILE_ID, manifest).reader_mode, sr.LEGACY)
        corrected = policy_for_profile(CORRECTED, manifest)
        self.assertEqual((corrected.reader_mode, corrected.clock_mode), (sr.DECLARED, sr.DECLARED))
        self.assertEqual(corrected.pack_class, "teaching")
        self.assertTrue(corrected.fail_closed)
        self.assertFalse(policy_for_profile(REFERENCE_PROFILE_ID, manifest).fail_closed)


class ClockTests(unittest.TestCase):
    """P6-07 (corrected only): the clock takes the resolution before truncating."""

    def _daily_peak(self) -> np.ndarray:
        day = np.sin(np.linspace(0.0, np.pi, 48)) * (np.arange(48) <= 47)
        day = np.roll(np.exp(-((np.arange(48) - 24) ** 2) / 20.0), 0)
        return np.tile(day, 365)

    def test_short_window_keeps_half_hour_resolution(self) -> None:
        values = self._daily_peak()
        spec = sr.SeriesSpec(role="profiles.vre_solar")
        declared = sr.align_clock(values, 48, spec, mode=sr.DECLARED)
        legacy = sr.align_clock(values, 48, spec, mode=sr.LEGACY, hourly_repeat=True)
        self.assertEqual(int(np.argmax(declared)), 24)
        self.assertEqual(int(np.argmax(legacy)), 46)
        full = sr.align_clock(values, 17_520, spec, mode=sr.LEGACY, hourly_repeat=True)
        self.assertTrue(np.array_equal(full, sr.align_clock(values, 17_520, spec, mode=sr.DECLARED)))

    def test_hourly_and_leap_year_sources(self) -> None:
        hourly = np.arange(8760, dtype=float)
        out = sr.align_clock(hourly, 6, sr.SeriesSpec(role="profiles.vre_solar"), mode=sr.DECLARED)
        self.assertEqual(out.tolist(), [0.0, 0.0, 1.0, 1.0, 2.0, 2.0])
        leap = np.ones(17_568)
        leap[59 * 48:60 * 48] = 5.0
        price = sr.align_clock(leap, 17_520, sr.SeriesSpec(role="market.france.price"), mode=sr.DECLARED)
        self.assertEqual(price.size, 17_520)
        self.assertEqual(float(price.max()), 1.0)  # 29 February removed
        demand = sr.align_clock(leap, 17_520, sr.SeriesSpec(role="demand.real"), mode=sr.DECLARED)
        self.assertAlmostEqual(float(demand.sum()), float(leap.sum()), places=6)  # energy conserved

    def test_short_series_needs_a_cyclic_declaration_when_strict(self) -> None:
        short = np.arange(10, dtype=float)
        with self.assertRaises(sr.SeriesReadError) as raised:
            sr.align_clock(short, 20, sr.SeriesSpec(role="demand.real"), mode=sr.DECLARED, strictness=sr.STRICT)
        self.assertEqual(raised.exception.code, "GF_DATA_SHORT_SERIES")
        wrapped = sr.align_clock(short, 20, sr.SeriesSpec(role="market.france.price", cyclic=True),
                                 mode=sr.DECLARED, strictness=sr.STRICT)
        self.assertEqual(wrapped[10:12].tolist(), [0.0, 1.0])


class RegistryRepairTests(_Temp):
    """P6-02 / P6-04 (universal, decision A5): registry-asserted semantics of verified objects."""

    def test_eur_hourly_price_becomes_half_hourly_gbp(self) -> None:
        path = _write(self.temp / "Belgium_price.csv",
                      "Country,Datetime (UTC),Datetime (Local),Price (EUR/MWhe)\n"
                      "Belgium,2022/1/1 0:00,2022/1/1 1:00,110\nBelgium,2022/1/1 1:00,2022/1/1 2:00,220\n"
                      "Belgium,2022/1/1 2:00,2022/1/1 3:00,330\n")
        registry = {"fields": {
            "csv_header": {"status": "registry_asserted", "value": True},
            "csv_column": {"status": "registry_asserted", "value": "Price (EUR/MWhe)"},
            "currency": {"status": "registry_asserted", "value": "EUR"},
            "eur_per_gbp": {"status": "registry_asserted", "value": 1.1},
            "fx_basis": {"status": "registry_asserted", "value": "toy"},
            "interval_minutes": {"status": "registry_asserted", "value": 60},
        }, "correction_ids": ["p05.belgium-price-currency"]}
        spec = sr.SeriesSpec.from_binding("market.belgium.price", {"unit": "GBP/MWh"}, registry=registry)
        for mode in sr.MODES:
            with self.subTest(mode=mode):
                read = sr.read_series(path, spec, mode=mode, legacy_header=None)
                self.assertTrue(np.allclose(read.values, [100, 100, 200, 200, 300, 300], atol=1e-9))
                self.assertIn("p05.belgium-price-currency", read.correction_ids)
                clocked = sr.align_clock(read.values, 6, spec, mode=mode, cyclic_default=True)
                self.assertTrue(np.allclose(clocked, [100, 100, 200, 200, 300, 300], atol=1e-9))

    def test_eur_without_rate_is_refused(self) -> None:
        path = _write(self.temp / "eur.csv", "price\n110\n")
        spec = sr.SeriesSpec.from_binding("market.belgium.price", {"currency": "EUR"})
        with self.assertRaises(sr.SeriesReadError) as raised:
            sr.read_series(path, spec)
        self.assertEqual(raised.exception.code, "GF_DATA_PRICE_CURRENCY")

    def test_dst_row_repair(self) -> None:
        values = np.array([1.0, 2.0, 2.0, 3.0, 4.0, 7.0])
        repaired, notes = sr.apply_row_repairs(values, {"drop_source_rows": [1], "interpolate_gaps": [{"at": 4, "count": 2}]})
        self.assertEqual(repaired.tolist(), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        self.assertEqual(len(notes), 2)

    def test_registry_needs_a_verified_hash(self) -> None:
        path = _write(self.temp / "x.csv", "1\n2\n")
        self.assertIsNone(sr.registry_entry(path, {"sha256": "0" * 64}))
        self.assertIsNone(sr.registry_entry(path, {}))


class BoundaryIdentityTests(_Temp):
    """P6-03 (universal): interconnector flow files are assigned by NESO line identity."""

    def _pack(self, belgium_header: str, netherlands_header: str) -> tuple[Path, dict]:
        pack = self.temp / "pack"
        shutil.copytree(VALUE_101_BASELINE, pack)
        manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
        for country, header, base in (("belgium", belgium_header, 1.0), ("netherlands", netherlands_header, 2.0)):
            binding = manifest["bindings"][f"market.{country}.profile"]
            rows = [header, *(repr(base + 0.001 * (row % 100)) for row in range(17_520))]
            (pack / binding["uri"]).write_text("\n".join(rows) + "\n", encoding="utf-8")
            binding.pop("sha256", None)
        return pack, manifest

    def test_swapped_files_are_read_for_their_own_line(self) -> None:
        pack, manifest = self._pack("BRITNED_FLOW", "NEMO_FLOW")
        for profile in (REFERENCE_PROFILE_ID, CORRECTED):
            with self.subTest(profile=profile):
                boundary = read_boundary(pack, manifest, policy_for_profile(profile, manifest), periods=48)
                self.assertEqual(float(boundary.countries["belgium"].flow_mw[0]), 2.0)      # NEMO file
                self.assertEqual(float(boundary.countries["netherlands"].flow_mw[0]), 1.0)  # BRITNED file
                self.assertTrue(all(row["rebound"] for row in boundary.identity))

    def test_unresolvable_identity_fails(self) -> None:
        pack, manifest = self._pack("BRITNED_FLOW", "BRITNED_FLOW")
        with self.assertRaises(BoundaryIdentityError):
            read_boundary(pack, manifest, policy_for_profile(REFERENCE_PROFILE_ID, manifest), periods=48)


class TeachingPackTests(unittest.TestCase):
    def test_value_101_reading_is_the_same_under_both_profiles_on_the_full_year(self) -> None:
        manifest = json.loads((VALUE_101_BASELINE / "manifest.json").read_text(encoding="utf-8"))
        for role in ("demand.real", "demand.forecast", "profiles.vre_solar", "market.france.profile", "market.france.price"):
            with self.subTest(role=role):
                frozen = read_role(VALUE_101_BASELINE, manifest, role, policy_for_profile(REFERENCE_PROFILE_ID, manifest),
                                   periods=17_520).values
                corrected = read_role(VALUE_101_BASELINE, manifest, role, policy_for_profile(CORRECTED, manifest),
                                      periods=17_520).values
                self.assertTrue(np.array_equal(frozen, corrected))


class ResearchPackTests(unittest.TestCase):
    """GBP1 public1 read with the universal corrections equals the audited R029 series."""

    @classmethod
    def setUpClass(cls) -> None:
        roots = research_pack_roots()
        if not {GBP1_PUBLIC1, R029_PUBLIC1} <= set(roots):
            raise unittest.SkipTest("set VALUE_P0_5_PACKS to the released GBP1 and R029 public1 pack directories")
        cls.gbp1, cls.r029 = roots[GBP1_PUBLIC1], roots[R029_PUBLIC1]
        cls.m_gbp1 = json.loads((cls.gbp1 / "manifest.json").read_text(encoding="utf-8"))
        cls.m_r029 = json.loads((cls.r029 / "manifest.json").read_text(encoding="utf-8"))

    def test_r029_belgium_is_read_from_its_declared_column(self) -> None:
        for profile in (REFERENCE_PROFILE_ID, CORRECTED):
            boundary = read_boundary(self.r029, self.m_r029, policy_for_profile(profile, self.m_r029), periods=17_520)
            belgium = boundary.countries["belgium"]
            self.assertAlmostEqual(float(np.mean(belgium.price_gbp_per_mwh)), 222.2926, delta=1e-3)
            self.assertLessEqual(float(np.max(np.abs(belgium.flow_mw))), 1100.0)
            self.assertGreater(float(np.max(-belgium.flow_mw)), 0.0)  # an export envelope exists

    def test_gbp1_boundary_and_demand_equal_r029_in_both_profiles(self) -> None:
        for profile in (REFERENCE_PROFILE_ID, CORRECTED):
            with self.subTest(profile=profile):
                gbp1 = read_boundary(self.gbp1, self.m_gbp1, policy_for_profile(profile, self.m_gbp1), periods=17_520)
                r029 = read_boundary(self.r029, self.m_r029, policy_for_profile(profile, self.m_r029), periods=17_520)
                self.assertTrue(np.allclose(gbp1.countries["belgium"].price_gbp_per_mwh,
                                            r029.countries["belgium"].price_gbp_per_mwh, atol=1e-9))
                for country in ("belgium", "netherlands"):
                    self.assertTrue(np.array_equal(gbp1.countries[country].flow_mw, r029.countries[country].flow_mw))
                real = read_role(self.gbp1, self.m_gbp1, "demand.real", policy_for_profile(profile, self.m_gbp1),
                                 periods=17_520).values
                utc = read_role(self.r029, self.m_r029, "demand.real", policy_for_profile(profile, self.m_r029),
                                periods=17_520).values
                self.assertTrue(np.allclose(real, utc, atol=1e-9))

    def test_doctoral_forecast_keeps_its_frozen_lead(self) -> None:
        doctoral = read_role(self.gbp1, self.m_gbp1, "demand.forecast",
                             policy_for_profile(REFERENCE_PROFILE_ID, self.m_gbp1), periods=17_520).values
        corrected = read_role(self.gbp1, self.m_gbp1, "demand.forecast",
                              policy_for_profile(CORRECTED, self.m_gbp1), periods=17_520).values
        self.assertEqual(float(corrected[0]), 21560.0)
        self.assertTrue(np.allclose(doctoral[:-1], corrected[1:], atol=1e-9))


if __name__ == "__main__":
    unittest.main()
