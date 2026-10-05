"""docs/release/VERSION_LEDGER.json bookkeeping (C23)."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_version_ledger", ROOT / "scripts" / "check_version_ledger.py")
CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECK)


def _next_minor(version: str) -> str:
    major, minor, _patch = (int(part) for part in version.split("."))
    return f"{major}.{minor + 1}.0"


class VersionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = json.loads(CHECK.LEDGER.read_text(encoding="utf-8"))
        self.manifests = CHECK.load_manifests()

    def test_committed_ledger_matches_manifests_and_classes(self) -> None:
        self.assertEqual(CHECK.check(self.ledger, self.manifests), [])

    def _bumped(self, **bump):
        ledger = copy.deepcopy(self.ledger)
        manifests = copy.deepcopy(self.manifests)
        entry = ledger["modules"]["value-bid-at-cost-psm"]
        current = entry["current_version"]
        record = {"from": current, "to": _next_minor(current), "package": "P0-x", "correction_ids": ["p0-x.y"],
                  "reason": "test", "requires_user_opt_in": False, **bump}
        entry["bumps"].append(record)
        entry["current_version"] = record["to"]
        manifests["value-bid-at-cost-psm"]["version"] = record["to"]
        return ledger, manifests

    def test_valid_bump_chain_passes(self) -> None:
        ledger, manifests = self._bumped()
        self.assertEqual(CHECK.check(ledger, manifests, import_classes=False), [])

    def test_non_increasing_or_broken_chain_fails(self) -> None:
        ledger, manifests = self._bumped(to="5.0.9")
        self.assertTrue(any("does not increase" in error for error in CHECK.check(ledger, manifests, import_classes=False)))
        ledger, manifests = self._bumped(**{"from": "5.0.0"})
        self.assertTrue(any("does not continue" in error for error in CHECK.check(ledger, manifests, import_classes=False)))
        ledger, manifests = self._bumped(correction_ids=[])
        self.assertTrue(any("correction_ids" in error for error in CHECK.check(ledger, manifests, import_classes=False)))

    def test_manifest_drift_without_ledger_fails(self) -> None:
        manifests = copy.deepcopy(self.manifests)
        current = self.ledger["modules"]["value-bid-at-cost-psm"]["current_version"]
        manifests["value-bid-at-cost-psm"]["version"] = _next_minor(current)
        self.assertTrue(CHECK.check(self.ledger, manifests, import_classes=False))


if __name__ == "__main__":
    unittest.main()
