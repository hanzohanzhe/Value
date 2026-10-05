"""P0-5b S11: GBP1 public2 local builder and the boundary flow-sign audit (toy packs; nothing is uploaded)."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import audit_boundary_flow_sign as audit
from scripts import build_value_uk_pack_revision as builder

COUNTRIES = builder.COUNTRIES
NET = {"belgium": 2.0, "france": -3.0, "ireland": 1.0, "netherlands": 1.5, "norway": 2.5}  # TWh, + = import
PERIODS = 48


def _write(pack: Path, manifest: dict, role: str, relative: str, payload: str, **fields) -> None:
    path = pack / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    manifest["bindings"][role] = {"uri": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **fields}


def _toy_packs(root: Path) -> tuple[Path, Path]:
    base, approved = root / "base", root / "approved"
    base_manifest = {"id": "value-uk-open-data-pack-v1", "country": "GB", "timezone": "Europe/London", "bindings": {}}
    for role in builder.REBOUND_ROLES:
        _write(base, base_manifest, role, f"files/{role.replace('.', '__')}/legacy.csv", "x\n1\n")
    _write(base, base_manifest, "weather.solar", "files/weather__solar/solar.nc", "nc-solar")
    _write(base, base_manifest, "weather.wind", "files/weather__wind/wind.nc", "nc-wind")
    _write(base, base_manifest, "fleet.generators", "files/fleet__generators/fleet.json", "{}")
    approved_manifest = {"id": "value-uk-calendar-vx-trade001", "bindings": {}}
    for role in ("demand.real", "demand.forecast"):
        _write(approved, approved_manifest, role, f"files/demand__utc_2022/{role.split('.')[1]}.csv",
               "demand_mw\n" + "\n".join("20000" for _ in range(PERIODS)) + "\n", csv_header=True, unit="MW")
    for country in COUNTRIES:
        flow = NET[country] * 1e6 / (PERIODS * 0.5)
        payload = "period,flow_mw,price_gbp_per_mwh\n" + "".join(f"{p},{flow},50.0\n" for p in range(PERIODS))
        for kind, column in (("profile", "flow_mw"), ("price", "price_gbp_per_mwh")):
            _write(approved, approved_manifest, f"market.{country}.{kind}",
                   f"files/interconnectors__approved_r03/{country}.csv", payload, csv_column=column,
                   csv_header=True, eur_per_gbp=1.1, source_version="Ember 2022; approved fixed EUR/GBP 1.1")
    for pack, manifest in ((base, base_manifest), (approved, approved_manifest)):
        (pack / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return base, approved


def _reference(root: Path, net: dict) -> Path:
    path = root / "reference.json"
    path.write_text(json.dumps({"schema_version": audit.REFERENCE_SCHEMA, "year": 2022,
                                "source": "toy", "net_import_twh": net}), encoding="utf-8")
    return path


class PackRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base, self.approved = _toy_packs(self.root)

    def test_build_rebinds_and_declares_and_check_is_reproducible(self):
        out = self.root / "public2"
        first = builder.build(self.base, self.approved, out)
        self.assertEqual(first["flow_sign_status"], "not_source_verified")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], builder.PACK_ID)
        france = manifest["bindings"]["market.france.profile"]
        self.assertEqual((france["csv_column"], france["currency"], france["interval_minutes"]), ("flow_mw", "GBP", 30))
        self.assertEqual(france["flow_sign"], builder.UNVERIFIED_SIGN)
        self.assertEqual(manifest["bindings"]["weather.solar"]["time_convention"], "accumulation_end_of_hour")
        self.assertEqual(manifest["bindings"]["weather.wind"]["time_convention"], "instantaneous")
        for role, binding in manifest["bindings"].items():
            self.assertEqual(hashlib.sha256((out / binding["uri"]).read_bytes()).hexdigest(), binding["sha256"], role)
        for _ in range(2):
            self.assertEqual(builder.main(["--base", str(self.base), "--approved", str(self.approved),
                                           "--out", str(out), "--check"]), 0)

    def test_flow_sign_is_verified_only_with_matching_audit_evidence(self):
        out = self.root / "public2"
        builder.build(self.base, self.approved, out)
        evidence = audit.audit(out, _reference(self.root, NET))
        self.assertTrue(evidence["verified"])
        verified = builder.build(self.base, self.approved, self.root / "verified", flow_evidence=evidence)
        self.assertEqual(verified["flow_sign_status"], "verified")
        manifest = json.loads((self.root / "verified" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["bindings"]["market.norway.profile"]["flow_sign"], builder.VERIFIED_SIGN)

    def test_a_flipped_country_sign_is_inconsistent(self):
        out = self.root / "public2"
        builder.build(self.base, self.approved, out)
        flipped = dict(NET, france=-NET["france"])
        evidence = audit.audit(out, _reference(self.root, flipped))
        self.assertFalse(evidence["verified"])
        self.assertFalse(evidence["countries"]["france"]["consistent"])
        self.assertTrue(evidence["countries"]["belgium"]["consistent"])
        result = builder.build(self.base, self.approved, self.root / "unverified", flow_evidence=evidence)
        self.assertEqual(result["flow_sign_status"], "not_source_verified")

    def test_a_tampered_source_object_is_refused(self):
        target = self.approved / "files/interconnectors__approved_r03/france.csv"
        target.write_text(target.read_text(encoding="utf-8") + "48,0,0\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            builder.build(self.base, self.approved, self.root / "public2")


if __name__ == "__main__":
    unittest.main()
