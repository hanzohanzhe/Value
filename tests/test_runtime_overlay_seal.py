"""RUNTIME_OVERLAY v2: per-file sealing of the Scheme C runtime kernel (X0 S5)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh import runtime_overlay as overlay
from gridform_core.errors import CompatibilityError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("seal_runtime_overlay", ROOT / "scripts" / "seal_runtime_overlay.py")
SEAL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SEAL)


class RuntimeOverlaySealTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name) / "scheme_c"
        self.root.mkdir()
        for name in ("compat", "runtime_compat"):
            shutil.copytree(overlay.ROOT / name, self.root / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(overlay.ROOT / "RUNTIME_OVERLAY.json", self.root / "RUNTIME_OVERLAY.json")
        overlay.clear_runtime_overlay_cache()
        self.addCleanup(overlay.clear_runtime_overlay_cache)

    def _seal(self, *arguments: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return SEAL.main(["--root", str(self.root), *arguments])

    def test_repository_overlay_is_v2_and_verifies(self) -> None:
        report = overlay.verify_runtime_overlay()
        self.assertTrue(report["verified"])
        self.assertEqual(report["schema_version"], overlay.SCHEMA_V2)
        self.assertEqual(report["required_bindings"], ["weather.solar", "weather.wind"])
        manifest = json.loads(overlay.MANIFEST_PATH.read_text(encoding="utf-8"))
        kinds = {row["path"]: row["kind"] for row in manifest["runtime_files"]}
        self.assertEqual(kinds["modular_simulation_model.py"], "value_instrumentation")
        self.assertEqual(kinds["storage_cost.py"], "value_instrumentation")
        self.assertEqual(kinds["config.py"], "mechanical_substitution")
        self.assertEqual(kinds["scenarios_v2/decarbonization_cost_scenarios_v2.csv"], "data")
        self.assertEqual(kinds["case3.py"], "source_identical")

    def test_changed_registered_python_or_csv_fails(self) -> None:
        self.assertEqual(overlay.inspect_runtime_overlay(self.root)["errors"], [])
        kernel = self.root / "runtime_compat" / "modular_simulation_model.py"
        kernel.write_bytes(kernel.read_bytes() + b"\n# edit\n")
        with self.assertRaises(CompatibilityError):
            overlay.verify_runtime_overlay(self.root)
        kernel.write_bytes(kernel.read_bytes()[: -len(b"\n# edit\n")])
        self.assertEqual(overlay.inspect_runtime_overlay(self.root)["errors"], [])
        data = self.root / "runtime_compat" / "scenarios_v2" / "decarbonization_cost_scenarios_v2.csv"
        data.write_bytes(data.read_bytes() + b"x")
        errors = overlay.inspect_runtime_overlay(self.root)["errors"]
        self.assertTrue(any("decarbonization_cost_scenarios_v2.csv" in error for error in errors), errors)

    def test_unregistered_python_fails_but_generated_files_only_warn(self) -> None:
        (self.root / "runtime_compat" / "new_helper.py").write_text("X = 1\n", encoding="utf-8")
        errors = overlay.inspect_runtime_overlay(self.root)["errors"]
        self.assertTrue(any("new_helper.py: unregistered" in error for error in errors), errors)
        (self.root / "runtime_compat" / "new_helper.py").unlink()
        cache = self.root / "runtime_compat" / "__pycache__"
        cache.mkdir()
        (cache / "case3.cpython-310.pyc").write_bytes(b"\0")
        generated = self.root / "runtime_compat" / "market_trace_outputs"
        generated.mkdir()
        (generated / "trace.csv").write_text("a\n", encoding="utf-8")
        report = overlay.inspect_runtime_overlay(self.root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["warnings"]), 2)

    def test_retained_source_must_stay_byte_identical(self) -> None:
        source = self.root / "compat" / "case3.py"
        source.write_bytes(source.read_bytes() + b"#")
        errors = overlay.inspect_runtime_overlay(self.root)["errors"]
        self.assertTrue(any("compat" in error for error in errors), errors)

    def test_seal_with_correction_registers_edits_and_new_modules(self) -> None:
        kernel = self.root / "runtime_compat" / "modular_simulation_model.py"
        kernel.write_bytes(kernel.read_bytes() + b"\n# p0 edit\n")
        (self.root / "runtime_compat" / "energy_contract.py").write_text("Y = 2\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self._seal("--correction", "Not-An-Id")
        self.assertEqual(self._seal("--correction", "p06.realise-period"), 0)
        manifest = json.loads((self.root / "RUNTIME_OVERLAY.json").read_text(encoding="utf-8"))
        rows = {row["path"]: row for row in manifest["runtime_files"]}
        self.assertEqual(rows["modular_simulation_model.py"]["kind"], "declared_runtime_edit")
        self.assertEqual(rows["modular_simulation_model.py"]["previous_kind"], "value_instrumentation")
        self.assertEqual(rows["modular_simulation_model.py"]["correction_ids"], ["p06.realise-period"])
        self.assertEqual(rows["energy_contract.py"]["kind"], "value_added_module")
        self.assertEqual(overlay.inspect_runtime_overlay(self.root)["errors"], [])
        self.assertEqual(self._seal("--verify"), 0)

    def test_declared_edit_without_correction_id_is_rejected(self) -> None:
        path = self.root / "RUNTIME_OVERLAY.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["runtime_files"][0]["kind"] = "declared_runtime_edit"
        manifest["runtime_files"][0]["correction_ids"] = []
        path.write_text(json.dumps(manifest), encoding="utf-8")
        errors = overlay.inspect_runtime_overlay(self.root)["errors"]
        self.assertTrue(any("without correction ids" in error for error in errors), errors)

    def test_entry_verification_is_cached(self) -> None:
        first = overlay.ensure_runtime_overlay_sealed(self.root)
        self.assertTrue(first["verified"])
        started = time.perf_counter()
        for _ in range(20):
            overlay.ensure_runtime_overlay_sealed(self.root)
        self.assertLess((time.perf_counter() - started) / 20, 0.005)
        # A cached result does not re-read the tree until the cache is cleared.
        kernel = self.root / "runtime_compat" / "case3.py"
        kernel.write_bytes(kernel.read_bytes() + b"#")
        self.assertTrue(overlay.ensure_runtime_overlay_sealed(self.root)["verified"])
        overlay.clear_runtime_overlay_cache()
        with self.assertRaises(CompatibilityError):
            overlay.ensure_runtime_overlay_sealed(self.root)


if __name__ == "__main__":
    unittest.main()
