"""The documented CLI (python -m gridform_core.application) exits 0 (P7-24)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gridform_core.value_101 import value_101_study

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-101-baseline-v1"


class ApplicationCliTests(unittest.TestCase):
    def _run_cli(self, mode: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / "project.json"
        project.write_text(json.dumps(value_101_study()), encoding="utf-8")
        output = root / "output"
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(root / "pycache"),
                "VALUE_DATA_HOME": str(root / "data"),
                "PYTHONPATH": str(ROOT),
            }
        )
        completed = subprocess.run(
            [
                sys.executable, "-B", "-m", "gridform_core.application",
                "--project", str(project),
                "--pack", str(PACK),
                "--output", str(output),
                "--mode", mode,
                "--run-id", f"cli-{mode}",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        return completed, output

    def _summary(self, completed: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, completed.stdout)
        return json.loads(lines[-1])

    def test_annual_smoke_reports_one_year(self) -> None:
        completed, output = self._run_cli("smoke")
        summary = self._summary(completed)
        self.assertEqual(summary["engine"], "value-annual-orchestrator/v2")
        self.assertEqual(summary["years"], 1)
        self.assertEqual(Path(summary["output"]), output.resolve())
        provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
        self.assertTrue(provenance["runtime_overlay"]["verified"])

    def test_psm_only_value_101_day_exits_zero_with_valid_json(self) -> None:
        completed, output = self._run_cli("value_101_day")
        summary = self._summary(completed)
        self.assertEqual(summary["engine"], "value-psm-only/v1")
        self.assertEqual(summary["years"], 0)
        provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
        self.assertTrue(provenance["runtime_overlay"]["verified"])


if __name__ == "__main__":
    unittest.main()
