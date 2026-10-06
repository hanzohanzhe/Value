"""The module catalogue is built on first use, never at import (P0-2 S5, G4-02)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.module_lifecycle_fixtures import forget_external_code, write_external_module

ROOT = Path(__file__).resolve().parents[1]
# sha256 of the canonical JSON of DATASET_SLOTS as it stood at the P0-2 move
# (35aadb3 content).  A package that changes dataset_slots.py updates this
# constant in the same commit and says so in the message (C27).
# P0-5a S10: interconnector unit contract (market.*.profile MW/30 min,
# market.*.price GBP/MWh); 35aadb3 value 4f8c2695cefc6d75...
# FX6 (A16-2, four-role S-D3): market.*.profile labels say "interconnector
# availability (+ import / - export)" instead of "import availability";
# P0-5a S10 value 1cbb27d6ca0a3f34...
DATASET_SLOTS_SHA256 = "7695775c0c37b4449ccb0fa9dfcc699185c6b8b05a0e16a25c8d0e3d2343ce4d"


def _python(code: str, data_home: Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update(VALUE_DATA_HOME=str(data_home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=ROOT, env=environment,
        capture_output=True, text=True, timeout=180,
    )


class LazyCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-p02-catalog-")
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        self.modules = self.home / "modules"

    def test_worker_import_chain_never_loads_the_catalog(self) -> None:
        write_external_module(self.modules, "p02-broken", "p02_broken_catalog",
                              prefix="raise RuntimeError('broken at import')\n")
        result = _python(
            "import sys, backend.worker_entry, backend.model_runner\n"
            "print('catalog' if 'gridform_core.catalog' in sys.modules else 'no-catalog')\n",
            self.home,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "no-catalog")

    def test_importing_the_catalog_with_a_broken_module_does_not_fail(self) -> None:
        write_external_module(self.modules, "p02-broken", "p02_broken_catalog",
                              prefix="raise SystemExit(9)\n")
        result = _python(
            "import gridform_core.catalog as catalog\n"
            "snapshot = catalog.get_catalog_snapshot()\n"
            "print(snapshot['quarantine']['status'], [row['id'] for row in snapshot['quarantine']['entries']])\n",
            self.home,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "degraded ['p02-broken']")

    def test_legacy_from_imports_still_work(self) -> None:
        result = _python(
            "from gridform_core.catalog import (DATASET_SLOTS, MODULES, MODULE_REGISTRY,\n"
            "    MODULE_SLOT_BY_ID, REQUIRED_MODULE_SLOTS)\n"
            "from gridform_core import catalog, dataset_slots\n"
            "assert DATASET_SLOTS is dataset_slots.DATASET_SLOTS\n"
            "assert MODULE_REGISTRY is catalog.get_catalog_snapshot()['registry']\n"
            "assert MODULE_SLOT_BY_ID['value-bid-at-cost-psm'] == 'psm'\n"
            "assert 'psm' in REQUIRED_MODULE_SLOTS and MODULES\n"
            "print('ok')\n",
            self.home,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip().splitlines()[-1], "ok")

    def test_dataset_slots_content_is_unchanged(self) -> None:
        from gridform_core import catalog
        from gridform_core.dataset_slots import DATASET_SLOTS

        digest = hashlib.sha256(json.dumps(
            DATASET_SLOTS, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        self.assertEqual(digest, DATASET_SLOTS_SHA256)
        self.assertIs(catalog.DATASET_SLOTS, DATASET_SLOTS)

    def test_unknown_names_still_raise_attribute_error(self) -> None:
        from gridform_core import catalog

        with self.assertRaises(AttributeError):
            catalog.NOT_A_CATALOG_NAME  # noqa: B018

    def test_snapshot_is_cached_until_refresh(self) -> None:
        from gridform_core import catalog

        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}), \
                patch.object(catalog, "_SNAPSHOT", None):
            first = catalog.get_catalog_snapshot()
            self.assertIs(catalog.get_catalog_snapshot(), first)
            self.assertIsNot(catalog.get_catalog_snapshot(refresh=True), first)

    def test_refresh_and_module_lifecycle_interleave_without_deadlock(self) -> None:
        import gridform_core.module_quarantine as quarantine
        from gridform_core import catalog
        from gridform_core.module_installation import set_module_enabled

        write_external_module(self.modules, "p02-toggle", "p02_toggle_catalog")
        self.addCleanup(forget_external_code, self.modules, ("p02_toggle_catalog",))
        errors: list[BaseException] = []

        def refresh() -> None:
            try:
                for _ in range(10):
                    catalog.get_catalog_snapshot(refresh=True)
            except BaseException as exc:  # pragma: no cover - reported below
                errors.append(exc)

        def toggle() -> None:
            try:
                for index in range(20):
                    set_module_enabled("p02-toggle", index % 2 == 1, modules_root=self.modules)
            except BaseException as exc:  # pragma: no cover - reported below
                errors.append(exc)

        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}), \
                patch.object(catalog, "_SNAPSHOT", None), \
                patch.object(quarantine, "verify_after_write", lambda *a, **k: None):
            threads = [threading.Thread(target=refresh), threading.Thread(target=toggle)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)
                self.assertFalse(thread.is_alive(), "catalogue refresh and module lifecycle deadlocked")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
