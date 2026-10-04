from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from netCDF4 import Dataset

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.data_pack_validation import validate_data_pack
from scripts.build_value_101_packs import (
    BASELINE_PACK_ID,
    HIGH_DEMAND_PACK_ID,
    WINDY_PACK_ID,
    build_value_101_pack_family,
)
from scripts.install_synthetic_pack import install_builtin_packs


WIND_CHANGED_ROLES = {
    "weather.wind",
    "profiles.vre_onshore",
    "profiles.vre_offshore",
}
DEMAND_CHANGED_ROLES = {"demand.real", "demand.forecast"}


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest(pack: Path) -> dict[str, object]:
    return json.loads((pack / "manifest.json").read_text(encoding="utf-8"))


def _scientific_hashes(pack: Path) -> dict[str, str]:
    manifest = _manifest(pack)
    return {
        role: str(binding["sha256"])
        for role, binding in manifest["bindings"].items()
    }


def _csv_values(pack: Path, role: str) -> list[float]:
    manifest = _manifest(pack)
    binding = manifest["bindings"][role]
    rows = list(csv.reader((pack / binding["uri"]).read_text(encoding="utf-8").splitlines()))
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row[0]))
        except (IndexError, ValueError):
            continue
    return values


def _wind_speed_values(pack: Path) -> list[float]:
    manifest = _manifest(pack)
    binding = manifest["bindings"]["weather.wind"]
    with Dataset(pack / binding["uri"], "r") as dataset:
        return [float(value) for value in dataset.variables["wind_speed"][:, 0, 0]]


class Value101PackFamilyTests(unittest.TestCase):
    def test_family_is_complete_valid_cc0_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-family-") as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first_report = build_value_101_pack_family(first)
            build_value_101_pack_family(second)

            self.assertEqual(
                set(first_report["pack_ids"]),
                {BASELINE_PACK_ID, WINDY_PACK_ID, HIGH_DEMAND_PACK_ID},
            )
            self.assertEqual(_tree_hash(first), _tree_hash(second))
            for pack_id in (BASELINE_PACK_ID, WINDY_PACK_ID, HIGH_DEMAND_PACK_ID):
                pack = first / pack_id
                manifest = _manifest(pack)
                self.assertEqual(manifest["id"], pack_id)
                self.assertEqual(manifest["licence"], "CC0-1.0")
                self.assertEqual(manifest["country"], "SYNTHETIC")
                self.assertEqual(manifest["timezone"], "UTC")
                self.assertEqual(manifest["period_hours"], 0.5)
                self.assertEqual(manifest["periods_per_year"], 48)
                self.assertTrue(manifest["teaching_only"])
                self.assertFalse(manifest["annual_economics_eligible"])
                self.assertFalse(manifest["scientific_baseline_eligible"])
                self.assertEqual(len(manifest["bindings"]), len(DATASET_SLOTS))
                result = validate_data_pack(pack, manifest, DATASET_SLOTS)
                self.assertTrue(result["valid"], result["errors"])
                derivation = json.loads((pack / "derivation.json").read_text(encoding="utf-8"))
                self.assertEqual(derivation["licence"], "CC0-1.0")
                self.assertTrue(derivation["unchanged_role_hashes_match"])

    def test_windy_changes_only_wind_and_applies_one_availability_transform(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-windy-") as temporary:
            root = Path(temporary)
            build_value_101_pack_family(root)
            baseline = root / BASELINE_PACK_ID
            windy = root / WINDY_PACK_ID

            baseline_hashes = _scientific_hashes(baseline)
            windy_hashes = _scientific_hashes(windy)
            changed = {
                role for role in baseline_hashes
                if baseline_hashes[role] != windy_hashes[role]
            }
            self.assertEqual(changed, WIND_CHANGED_ROLES)

            for role in ("profiles.vre_onshore", "profiles.vre_offshore"):
                expected = [min(value * 1.35, 1.0) for value in _csv_values(baseline, role)]
                actual = _csv_values(windy, role)
                self.assertEqual(len(actual), len(expected))
                for observed, target in zip(actual, expected):
                    self.assertAlmostEqual(observed, target, places=9)

            baseline_speed = _wind_speed_values(baseline)
            windy_speed = _wind_speed_values(windy)
            expected_speed = [
                math.pow(3.0**3 + 1.35 * (speed**3 - 3.0**3), 1.0 / 3.0)
                for speed in baseline_speed
            ]
            for observed, target in zip(windy_speed, expected_speed):
                self.assertAlmostEqual(observed, target, places=9)

    def test_high_demand_changes_only_real_and_forecast_demand(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-demand-") as temporary:
            root = Path(temporary)
            build_value_101_pack_family(root)
            baseline = root / BASELINE_PACK_ID
            high_demand = root / HIGH_DEMAND_PACK_ID

            baseline_hashes = _scientific_hashes(baseline)
            demand_hashes = _scientific_hashes(high_demand)
            changed = {
                role for role in baseline_hashes
                if baseline_hashes[role] != demand_hashes[role]
            }
            self.assertEqual(changed, DEMAND_CHANGED_ROLES)
            for role in sorted(DEMAND_CHANGED_ROLES):
                expected = [value * 1.20 for value in _csv_values(baseline, role)]
                actual = _csv_values(high_demand, role)
                self.assertEqual(len(actual), len(expected))
                for observed, target in zip(actual, expected):
                    self.assertAlmostEqual(observed, target, places=9)

    def test_installer_is_idempotent_and_reports_identity_conflicts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-install-") as temporary:
            state_root = Path(temporary)
            first = {row["pack_id"]: row for row in install_builtin_packs(state_root)}
            for pack_id in (BASELINE_PACK_ID, WINDY_PACK_ID, HIGH_DEMAND_PACK_ID):
                self.assertEqual(first[pack_id]["status"], "installed")

            second = {row["pack_id"]: row for row in install_builtin_packs(state_root)}
            for pack_id in (BASELINE_PACK_ID, WINDY_PACK_ID, HIGH_DEMAND_PACK_ID):
                self.assertEqual(second[pack_id]["status"], "already_installed")

            manifest_path = state_root / "data-packs" / WINDY_PACK_ID / "manifest.json"
            conflicting_bytes = manifest_path.read_bytes().replace(
                b'"name": "VALUE 101 windy teaching data"',
                b'"name": "Local user revision"',
            )
            manifest_path.write_bytes(conflicting_bytes)
            third = {row["pack_id"]: row for row in install_builtin_packs(state_root)}
            self.assertEqual(third[WINDY_PACK_ID]["status"], "conflict_preserved")
            self.assertEqual(manifest_path.read_bytes(), conflicting_bytes)


if __name__ == "__main__":
    unittest.main()
