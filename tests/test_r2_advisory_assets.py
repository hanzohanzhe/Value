"""R3-N7 (four-role R1 retest, DECISIONS A23): advisories about an asset class
apply only to Runs whose frozen fleet has such an asset.

The retest listed the high advisory "Nuclear started the year off ..." on a
VALUE 101 doctoral Run, which has no nuclear unit; the advisory text itself
says Runs without nuclear units are not affected.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from gridform_core import result_advisories
from gridform_core.result_advisories import evaluate_advisories, run_asset_classes


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "runs" / "pre-fix-dynamic-full"
NUCLEAR_IDS = {"fx8.nuclear-in-service-at-start"}


def _fleet(*generators: str) -> dict:
    return {
        "batteries": {"1c_battery": {"name": "1c_battery"}},
        "connections": {"Interconnect_France": {"name": "Interconnect_France"}},
        "electrolyzer": {},
        "generators": {name: {"name": name} for name in generators},
        "locations": {},
    }


class AdvisoryAssetFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        self.run_root = Path(folder) / "run"
        shutil.copytree(FIXTURE, self.run_root)
        self.status = json.loads((self.run_root / "status.json").read_text(encoding="utf-8"))
        result_advisories._ASSET_CACHE.clear()

    def _freeze_fleet(self, fleet: dict) -> None:
        pack = self.run_root / "input-snapshot" / "pack"
        (pack / "files" / "fleet__generators").mkdir(parents=True, exist_ok=True)
        (pack / "files" / "fleet__generators" / "fleet.json").write_text(json.dumps(fleet), encoding="utf-8")
        manifest = {"id": "value-101-baseline-v1", "bindings": {"fleet.generators": {"uri": "files/fleet__generators/fleet.json"}}}
        (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _ids(self) -> set[str]:
        return {row["id"] for row in evaluate_advisories(self.status, self.run_root)}

    def test_run_without_nuclear_gets_no_nuclear_advisory(self) -> None:
        self._freeze_fleet(_fleet("CCGT", "offshore1", "onshore_London", "solar_London"))
        self.assertEqual(
            run_asset_classes(self.run_root),
            frozenset({"ccgt", "offshore_wind", "onshore_wind", "solar", "battery_storage", "boundary_import"}),
        )
        ids = self._ids()
        self.assertFalse(NUCLEAR_IDS & ids)
        # Advisories without an asset predicate are unaffected.
        self.assertIn("p06.avoided-cost-downward-order", ids)

    def test_run_with_nuclear_keeps_the_advisory(self) -> None:
        self._freeze_fleet(_fleet("CCGT", "Nuclear", "Hydro_natural_flow"))
        self.assertTrue({"nuclear", "natural_flow_hydro"} <= run_asset_classes(self.run_root))
        self.assertTrue(NUCLEAR_IDS <= self._ids())

    def test_unreadable_fleet_keeps_the_advisory(self) -> None:
        self.assertIsNone(run_asset_classes(self.run_root))
        self.assertTrue(NUCLEAR_IDS <= self._ids())
        self._freeze_fleet({"not": "a fleet"})
        result_advisories._ASSET_CACHE.clear()
        self.assertIsNone(run_asset_classes(self.run_root))
        self.assertTrue(NUCLEAR_IDS <= self._ids())


if __name__ == "__main__":
    unittest.main()
