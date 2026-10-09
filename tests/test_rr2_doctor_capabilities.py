"""The environment doctor imports and accepts the capabilities the installer passes (RR-2).

scripts/install-value.ps1 runs ``doctor.py --capability value-native`` or
``--capability doctoral-reproduction``; the user guides document
``--capability value-native``.  The doctor used to import a constant that no
longer exists, so it failed before parsing its arguments.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("value_doctor_under_test", DOCTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DoctorCapabilityTests(unittest.TestCase):
    def test_report_for_each_installer_capability(self) -> None:
        doctor = _load_doctor()
        with tempfile.TemporaryDirectory() as tmp:
            for capability in ("value-native", "doctoral-reproduction"):
                payload = doctor.report(Path(tmp), api_port=0, website_port=0, capability=capability)
                self.assertEqual(payload["selected_capability"], capability)
                checks = payload["checks"]
                self.assertIn("value_native_capability", checks)
                self.assertIn("doctoral_reproduction_capability", checks)
                self.assertEqual(checks["value_native_capability"]["optional"], capability != "value-native")
                self.assertEqual(
                    checks["doctoral_reproduction_capability"]["optional"],
                    capability != "doctoral-reproduction",
                )

    def test_command_line_accepts_installer_choices(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, "-B", str(DOCTOR), "--help"],
            capture_output=True, text=True, env=env, cwd=ROOT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("value-native", result.stdout)
        self.assertIn("doctoral-reproduction", result.stdout)


if __name__ == "__main__":
    unittest.main()
