"""R3-1 (decision A24-1): the extra hour of the shared hourly solar profile ``sa.csv``.

R029 public1 and GBP1 public1 bind the same ``sa.csv`` (sha256
``15ef49b3...578e``) with 8761 hourly values and no interval declaration.
``scripts/audit_hourly_solar_profile.py`` shows against ERA5 2022 ssrd that
rows 0..8759 are the 2022 stamps and the last row (a night zero) is the stamp
2023-01-01T00:00Z.  The local revisions (R029 public2, GBP1 public2 @v3) bind
the first 8760 rows, byte for byte, declare the VRE profiles hourly and record
the dropped row.  Every existing reading used only the first 8760 rows, so no
number changes; the public1 packs, and the doctoral reading, are untouched.

The research-pack case needs ``VALUE_P0_5_PACKS`` with R029 public1.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from scripts import build_value_uk_pack_revision as builder

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "dev" / "p0-reports" / "r31-solar" / "sa_8761_evidence.json"
R029_PUBLIC2 = "value-uk-calendar-vx-trade001-public2"
SOLAR = "profiles.vre_solar"
SOLAR_URI = "files/profiles__vre_solar/sa.csv"


def _solar_bytes(rows: int = 8761) -> bytes:
    """A toy hourly solar profile in the source format (CRLF, '0' at night, a night zero last)."""

    values = []
    for hour in range(rows):
        h = hour % 24
        values.append("0" if h < 8 or h > 16 else repr(round(0.1 * (1 + (h - 8) * (16 - h)) / 17.0, 9)))
    return ("\r\n".join(values) + "\r\n").encode("ascii")


def _rule_for(data: bytes) -> dict[str, dict]:
    rule = json.loads(json.dumps(builder.ROW_REVISIONS[builder.SOLAR_8761_SHA256]))
    return {hashlib.sha256(data).hexdigest(): rule}


def _bind(pack: Path, manifest: dict, role: str, relative: str, payload: bytes, **fields) -> None:
    path = pack / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    manifest["bindings"][role] = {"uri": relative, "sha256": hashlib.sha256(payload).hexdigest(),
                                  "bytes": len(payload), "unit": "p.u.", **fields}


def _toy_r029(root: Path, solar: bytes) -> Path:
    pack = root / "r029-public1"
    manifest = {"id": builder.R029_PUBLIC1_ID, "name": "toy R029", "country": "GB", "timezone": "UTC",
                "period_hours": 0.5, "periods_per_year": 17520,
                "weather_calendar_reconstruction": {"audit_uri": "files/weather__calendar_audit/audit.json"},
                "bindings": {}}
    _bind(pack, manifest, SOLAR, SOLAR_URI, solar, transformation="toy solar")
    wind = ("\r\n".join("0.5" for _ in range(8760)) + "\r\n").encode("ascii")
    _bind(pack, manifest, "profiles.vre_onshore", "files/profiles__vre_onshore/wa.csv", wind)
    _bind(pack, manifest, "profiles.vre_offshore", "files/profiles__vre_offshore/we.csv", wind)
    demand = ("demand_mw\n" + "\n".join("20000" for _ in range(17520)) + "\n").encode("ascii")
    _bind(pack, manifest, "demand.real", "files/demand__utc_2022/actual_mw.csv", demand, csv_header=True,
          csv_column="demand_mw", chronology_uri="files/demand__utc_2022/chronology.csv")
    (pack / "files/demand__utc_2022/chronology.csv").write_text("period\n0\n", encoding="utf-8")
    (pack / "files/weather__calendar_audit").mkdir(parents=True)
    (pack / "files/weather__calendar_audit/audit.json").write_text('{"status": "PASS"}', encoding="utf-8")
    (pack / "RIGHTS.json").write_text("{}", encoding="utf-8")
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return pack


class RowRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_rule_drops_exactly_the_last_row_byte_for_byte(self):
        data = _solar_bytes()
        source = self.root / "sa.csv"
        source.write_bytes(data)
        rule = next(iter(_rule_for(data).values()))
        record = builder.revise_rows(source, self.root / "out" / "sa.csv", rule)
        revised = (self.root / "out" / "sa.csv").read_bytes()
        self.assertEqual(revised, b"".join(data.splitlines(keepends=True)[:8760]))
        self.assertEqual(len(revised.splitlines()), 8760)
        self.assertTrue(revised.endswith(b"\r\n"))
        self.assertEqual(record["source_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(record["dropped_rows"], [{"index": 8760, "line": 8761, "text": "0",
                                                  "era5_stamp_utc": "2023-01-01T00:00:00Z"}])
        self.assertEqual((record["source_rows"], record["result_rows"], record["decision"]), (8761, 8760, "A24-1"))

    def test_the_rule_refuses_a_different_object(self):
        rule = next(iter(_rule_for(b"").values()))
        short = self.root / "short.csv"
        short.write_bytes(_solar_bytes(8760))
        with self.assertRaisesRegex(SystemExit, "8760 rows"):
            builder.revise_rows(short, self.root / "o1.csv", rule)
        lit = bytearray(_solar_bytes())
        lit[-3:] = b"1\r\n"            # the last row is not the night zero the rule names
        odd = self.root / "odd.csv"
        odd.write_bytes(bytes(lit))
        with self.assertRaisesRegex(SystemExit, "row 8760"):
            builder.revise_rows(odd, self.root / "o2.csv", rule)

    def test_r029_public2_revises_the_solar_object_and_carries_every_other_file(self):
        data = _solar_bytes()
        public1 = _toy_r029(self.root, data)
        out = self.root / "r029-public2"
        with mock.patch.object(builder, "ROW_REVISIONS", _rule_for(data)):
            result = builder.build_r029(public1, out, link="hardlink")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            for _ in range(2):
                self.assertEqual(builder.main(["--pack", "r029-public2", "--approved", str(public1),
                                               "--out", str(out), "--check"]), 0)
        self.assertEqual((result["pack_id"], manifest["id"], manifest["pack_class"]),
                         (R029_PUBLIC2, R029_PUBLIC2, "scientific_reference"))
        self.assertEqual(manifest["derivation"]["row_revisions"], [SOLAR])
        self.assertEqual(manifest["derivation"]["parent_pack_id"], builder.R029_PUBLIC1_ID)
        self.assertEqual(manifest["weather_calendar_reconstruction"],
                         {"audit_uri": "files/weather__calendar_audit/audit.json"})
        solar = manifest["bindings"][SOLAR]
        self.assertEqual(solar["interval_minutes"], 60)
        self.assertEqual(solar["row_revision"]["source_sha256"], hashlib.sha256(data).hexdigest())
        self.assertIn("A24-1", solar["transformation"])
        self.assertEqual(len((out / SOLAR_URI).read_bytes().splitlines()), 8760)
        for role in ("profiles.vre_onshore", "profiles.vre_offshore"):
            self.assertEqual(manifest["bindings"][role]["interval_minutes"], 60)
        for role, binding in manifest["bindings"].items():
            self.assertEqual(hashlib.sha256((out / binding["uri"]).read_bytes()).hexdigest(), binding["sha256"], role)
        # Every other file is the public1 file (hardlinked here), the public1 solar object is untouched.
        for path in public1.rglob("*"):
            relative = path.relative_to(public1).as_posix()
            if path.is_file() and relative not in ("manifest.json", SOLAR_URI):
                self.assertTrue(os.path.samefile(path, out / relative), relative)
        self.assertFalse(os.path.samefile(public1 / SOLAR_URI, out / SOLAR_URI))
        self.assertEqual((public1 / SOLAR_URI).read_bytes(), data)

    def test_r029_public2_refuses_a_pack_without_the_8761_row_object(self):
        public1 = _toy_r029(self.root, _solar_bytes())
        with self.assertRaisesRegex(SystemExit, "8761-row solar profile"):
            builder.build_r029(public1, self.root / "out")      # the real rule: the toy sha does not match
        wrong = self.root / "wrong"
        wrong.mkdir()
        (wrong / "manifest.json").write_text('{"id": "value-uk-open-data-pack-v1", "bindings": {}}', encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "R029 public1"):
            builder.build_r029(wrong, self.root / "out2")

    def test_every_reading_of_the_revised_object_equals_the_reading_of_the_8761_row_object(self):
        from gridform_core.data_method import policy_for_profile, read_role

        data = _solar_bytes()
        public1 = _toy_r029(self.root, data)
        out = self.root / "r029-public2"
        with mock.patch.object(builder, "ROW_REVISIONS", _rule_for(data)):
            builder.build_r029(public1, out, link="hardlink")
        revised = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        original = json.loads((public1 / "manifest.json").read_text(encoding="utf-8"))
        declared_original = json.loads(json.dumps(original))
        declared_original["bindings"][SOLAR]["interval_minutes"] = 60
        corrected = read_role(out, revised, SOLAR, policy_for_profile("value-corrected", revised), periods=17520)
        before = read_role(public1, declared_original, SOLAR,
                           policy_for_profile("value-corrected", declared_original), periods=17520)
        doctoral = read_role(public1, original, SOLAR,
                             policy_for_profile("doctoral-lineage-0.6.0a2", original), periods=17520)
        doctoral_revised = read_role(out, revised, SOLAR,
                                     policy_for_profile("doctoral-lineage-0.6.0a2", revised), periods=17520)
        self.assertEqual(len(corrected.values), 17520)
        np.testing.assert_array_equal(corrected.values, before.values)
        np.testing.assert_array_equal(corrected.values, doctoral.values)
        np.testing.assert_array_equal(doctoral_revised.values, doctoral.values)
        # Undeclared, the 8761-row object is refused by the strict corrected reader (the defect itself).
        with self.assertRaisesRegex(Exception, "GF_DATA_SHORT_SERIES"):
            read_role(public1, original, SOLAR, policy_for_profile("value-corrected", original), periods=17520)

    def test_the_kernel_vre_cap_bisection_is_unchanged(self):
        from gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_investment_support import (
            critical_capacity_for_threshold,
        )

        data = _solar_bytes()
        full, trimmed = self.root / "full.csv", self.root / "trimmed.csv"
        full.write_bytes(data)
        trimmed.write_bytes(b"".join(data.splitlines(keepends=True)[:8760]))
        demand = self.root / "demand.csv"
        rng = np.random.default_rng(7)
        demand.write_text("demand\n" + "\n".join(f"{v:.1f}" for v in 20000 + 5000 * rng.random(17520)) + "\n",
                          encoding="utf-8")
        self.assertEqual(critical_capacity_for_threshold(demand, full), critical_capacity_for_threshold(demand, trimmed))

    def test_gbp1_public2_v3_binds_the_revised_solar_object(self):
        from tests.test_p05b_pack_revision import _toy_packs

        data = _solar_bytes()
        base, approved = _toy_packs(self.root)
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        _bind(base, manifest, SOLAR, SOLAR_URI, data)
        (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(builder, "ROW_REVISIONS", _rule_for(data)):
            builder.build(base, approved, self.root / "public2", link="hardlink")
        built = json.loads((self.root / "public2" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(built["derivation"]["builder"], "scripts/build_value_uk_pack_revision.py@v3")
        self.assertEqual(built["derivation"]["row_revisions"], [SOLAR])
        solar = built["bindings"][SOLAR]
        self.assertEqual((solar["interval_minutes"], solar["row_revision"]["result_rows"]), (60, 8760))
        self.assertEqual(hashlib.sha256((self.root / "public2" / SOLAR_URI).read_bytes()).hexdigest(), solar["sha256"])
        self.assertEqual((base / SOLAR_URI).read_bytes(), data)


class RegistrationTests(unittest.TestCase):
    def test_r029_public2_is_a_locally_registered_scientific_reference(self):
        from gridform_core import methodology
        from gridform_core.data_method import policy_for_profile

        self.assertEqual(methodology.KNOWN_PACK_CLASSES[R029_PUBLIC2], "scientific_reference")
        self.assertEqual(builder.R029_PACK_ID, R029_PUBLIC2)
        policy = policy_for_profile("value-corrected", {"id": R029_PUBLIC2})
        self.assertEqual((policy.pack_class, policy.strictness), ("scientific_reference", "strict"))
        # The doctoral profile pins its packs and does not support R029 (public1 or public2).
        for pack_id in (builder.R029_PUBLIC1_ID, R029_PUBLIC2):
            self.assertTrue(methodology.combination_violations(
                methodology.REFERENCE_PROFILE_ID, data_packs=[({"id": pack_id, "bindings": {}}, None)]))
            self.assertEqual(methodology.combination_violations(
                "value-corrected", data_packs=[({"id": pack_id, "bindings": {}}, None)]), [])

    def test_r029_public2_is_not_id_keyed(self):
        from gridform_core import pack_source_identity

        self.assertNotIn(R029_PUBLIC2, pack_source_identity.ID_KEYED_PACK_IDS)

    def test_data_corrections_that_name_r029_also_name_r029_public2(self):
        catalogue = json.loads((ROOT / "gridform_core/data/methodology/corrections/p05.json").read_text(encoding="utf-8"))
        for row in catalogue["corrections"]:
            packs = row["applies_when"].get("data_packs_any", [])
            if builder.R029_PUBLIC1_ID in packs:
                self.assertIn(R029_PUBLIC2, packs, row["id"])

    def test_the_rule_matches_the_committed_evidence(self):
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        rule = builder.ROW_REVISIONS[builder.SOLAR_8761_SHA256]
        self.assertEqual(evidence["profile"]["sha256"], builder.SOLAR_8761_SHA256)
        self.assertEqual(evidence["profile"]["rows"], rule["source_rows"])
        self.assertEqual((evidence["best_lag"], evidence["weekly_best_lags"], evidence["weeks"]), (0, [0], 52))
        lag0 = next(row for row in evidence["whole_year_by_lag"] if row["lag"] == 0)
        self.assertEqual(lag0["light_in_the_dark"], 0)
        self.assertTrue(all(row["correlation"] < lag0["correlation"] - 0.03
                            for row in evidence["whole_year_by_lag"] if row["lag"] != 0))
        self.assertEqual(evidence["era5"]["first_stamp"], "2022-01-01T00:00:00Z")
        self.assertEqual(evidence["era5"]["last_stamp"], "2022-12-31T23:00:00Z")
        self.assertEqual(evidence["era5_span"]["inclusive_slice_hours"], 8761)
        self.assertEqual(evidence["era5_span"]["domain_max_ssrd_at_last_stamp_j_per_m2"], 0.0)
        dropped = rule["dropped_rows"][0]
        self.assertEqual((evidence["finding"]["extra_row_index"], evidence["finding"]["extra_row_value"],
                          evidence["finding"]["era5_stamp_of_extra_row"]),
                         (dropped["index"], dropped["text"], dropped["era5_stamp_utc"]))
        self.assertEqual(rule["evidence"], EVIDENCE.relative_to(ROOT).as_posix())


class AuditScriptTests(unittest.TestCase):
    """scripts/audit_hourly_solar_profile.py on a toy ERA5 file."""

    def _era5(self, path: Path, start: str, hours: int) -> np.ndarray:
        import pandas as pd
        import xarray as xr

        stamps = pd.date_range(start, periods=hours, freq="h")
        hour = stamps.hour.to_numpy()
        day = stamps.dayofyear.to_numpy()
        # Accumulated over the hour ending at the stamp: light from 09:00 to 16:00 stamps, varying by day.
        daylight = np.where((hour >= 9) & (hour <= 16), (1 + np.sin(day / 7.0)) * 1e5 * (1 + (hour - 9) * (16 - hour)), 0.0)
        field = np.repeat(daylight[:, None, None], 4, axis=1).reshape(hours, 2, 2)
        ds = xr.Dataset({"ssrd": (("valid_time", "latitude", "longitude"), field)},
                        coords={"valid_time": stamps, "latitude": [55.0, 52.0], "longitude": [-2.0, 0.0]})
        ds.to_netcdf(path)
        return daylight

    def test_a_trailing_extra_stamp_is_found(self):
        from scripts import audit_hourly_solar_profile as audit

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            year = self._era5(root / "2022.nc", "2022-01-01", 8760)
            self._era5(root / "span.nc", "2022-01-01", 8760 + 48)
            profile = root / "sa.csv"
            values = list(year / year.max()) + [0.0]
            profile.write_text("\r\n".join(f"{v:.9g}" for v in values) + "\r\n", encoding="ascii")
            result = audit.audit(profile, root / "2022.nc", 2022, root / "span.nc")
            self.assertEqual((result["best_lag"], result["weekly_best_lags"]), (0, [0]))
            self.assertEqual(result["finding"]["extra_row_index"], 8760)
            self.assertEqual(result["era5_span"]["inclusive_slice_hours"], 8761)
            # A leading extra row instead moves the best lag to +1 and no trailing finding is made.
            profile.write_text("\r\n".join(f"{v:.9g}" for v in [0.0] + values[:-1]) + "\r\n", encoding="ascii")
            shifted = audit.audit(profile, root / "2022.nc", 2022)
            self.assertEqual(shifted["best_lag"], 1)
            self.assertNotIn("finding", shifted)


def _research_r029() -> Path | None:
    from tests.p0_5_fixtures import research_pack_roots

    return research_pack_roots().get("r029-public1")


class ResearchPackTests(unittest.TestCase):
    @unittest.skipUnless(_research_r029(), "needs VALUE_P0_5_PACKS with R029 public1")
    def test_r029_public2_from_the_released_public1(self):
        from gridform_core.data_method import policy_for_profile, read_role

        public1 = _research_r029()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "r029-public2"
            builder.build_r029(public1, out, link="symlink")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            original = json.loads((public1 / "manifest.json").read_text(encoding="utf-8"))
            solar = manifest["bindings"][SOLAR]
            self.assertEqual(solar["row_revision"]["source_sha256"], builder.SOLAR_8761_SHA256)
            self.assertEqual(solar["sha256"], "ae4b95772a0be4f493dbf2190278309e96eaf2bf279bbec40cf3d08d8525b306")
            corrected = read_role(out, manifest, SOLAR, policy_for_profile("value-corrected", manifest), periods=17520)
            doctoral = read_role(public1, original, SOLAR,
                                 policy_for_profile("doctoral-lineage-0.6.0a2", original), periods=17520)
            np.testing.assert_array_equal(corrected.values, doctoral.values)
            changed = sorted(role for role in manifest["bindings"]
                             if manifest["bindings"][role]["sha256"] != original["bindings"][role]["sha256"])
            self.assertEqual(changed, [SOLAR])


if __name__ == "__main__":
    unittest.main()
