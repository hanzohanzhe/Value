from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check-value-101.ps1"
STARTER = ROOT / "scripts" / "start-portable-local.ps1"
STOPPER = ROOT / "scripts" / "stop-local.ps1"
PACK_IDS = (
    "value-101-baseline-v1",
    "value-101-windy-v1",
    "value-101-high-demand-v1",
    "value-101-network-v1",
)


def run_powershell(
    script: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def create_checker_fixture(root: Path) -> None:
    app = root / "app"
    for relative in (
        "runtime/python/python.exe",
        "runtime/node/node.exe",
        "dist/server/index.js",
        "START-HERE-VALUE-101-Guide.pdf",
    ):
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    for pack_id in PACK_IDS:
        source = ROOT / "data-packs" / pack_id / "manifest.json"
        destination = root / "state" / "data-packs" / pack_id / "manifest.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


class Value101LauncherTests(unittest.TestCase):
    def test_preflight_entrypoint_and_checker_exist(self) -> None:
        self.assertTrue(CHECKER.is_file())
        entrypoint = ROOT / "check-value-101.cmd"
        self.assertTrue(entrypoint.is_file())
        self.assertIn("check-value-101.ps1", entrypoint.read_text("utf-8").lower())

    def test_checker_is_read_only_and_covers_pilot_gates(self) -> None:
        source = CHECKER.read_text("utf-8")
        for mutation in (
            "New-Item",
            "Set-Content",
            "Remove-Item",
            "Copy-Item",
            "npm install",
            "pip install",
        ):
            self.assertNotIn(mutation, source)
        for required in (
            "Private Python 3.10",
            "Private Node runtime",
            "VALUE-101-Guide.pdf",
            "dist\\server\\index.js",
            *PACK_IDS,
            "8766",
            "8800",
        ):
            self.assertIn(required, source)
        self.assertNotRegex(source, r"https?://(?!127\.0\.0\.1)")

    def test_missing_install_is_a_named_failure_with_a_plain_action(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-check-") as temporary:
            result = run_powershell(CHECKER, "-InstallRoot", temporary, "-Json")
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        python = next(check for check in report["checks"] if check["id"] == "python")
        self.assertEqual(python["status"], "fail")
        self.assertIn("Reinstall VALUE-101-Setup.exe", report["action"])
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_checker_accepts_the_current_pilot_layout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-check-") as temporary:
            root = Path(temporary)
            create_checker_fixture(root)
            result = run_powershell(CHECKER, "-InstallRoot", str(root), "-Json")
        report = json.loads(result.stdout)
        checks = {check["id"]: check for check in report["checks"]}
        for check_id in ("python", "node", "frontend", "guide"):
            self.assertEqual(checks[check_id]["status"], "pass", checks[check_id])
        for pack_id in PACK_IDS:
            self.assertEqual(checks[f"pack_{pack_id}"]["status"], "pass")

    def test_stop_ignores_a_reused_pid_and_remains_repeatable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-stop-") as temporary:
            state = Path(temporary)
            (state / "local-services.json").write_text(
                json.dumps({"backend_pid": os.getpid(), "frontend_pid": os.getpid()}),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["VALUE_DATA_HOME"] = temporary
            first = run_powershell(STOPPER, env=env)
            second = run_powershell(STOPPER, env=env)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse((state / "local-services.json").exists())
            self.assertGreater(os.getpid(), 0)

    def test_stop_has_a_fail_closed_path_fallback_when_cim_is_unavailable(self) -> None:
        source = STOPPER.read_text("utf-8")
        for required in (
            "Get-Process -Id",
            "Test-PortOwnedByProcess",
            "runtime\\python\\python.exe",
            "runtime\\node\\node.exe",
            "$process.WaitForExit(30000)",
            "did not stop cleanly",
            "exit 1",
        ):
            self.assertIn(required, source)
        self.assertNotIn("Wait-Process -Id", source)
        self.assertLess(
            source.index('taskkill.exe /PID'),
            source.index('Remove-Item -LiteralPath $pidFile'),
        )

    def test_portable_launcher_uses_owned_private_runtime_and_refuses_ports(self) -> None:
        source = STARTER.read_text("utf-8")
        self.assertIn("[Parameter(Mandatory=$true)][string]$Python", source)
        self.assertIn("[Parameter(Mandatory=$true)][string]$Node", source)
        self.assertIn("netstat.exe", source)
        self.assertIn("Port $port is already in use", source)
        self.assertIn("local-services.json", source)
        self.assertNotIn("force-castle-101-v1", source)
        self.assertNotIn("taskkill.exe", source)

    def test_tutorial_progress_survives_refresh_and_runbook_matches_pilot(self) -> None:
        learn = (ROOT / "app" / "features" / "learn" / "Value101Learn.tsx").read_text("utf-8")
        runbook = (ROOT / "docs" / "tutorial" / "JOHN_PILOT_RUNBOOK.md").read_text("utf-8")
        self.assertIn("window.localStorage.getItem", learn)
        self.assertIn("window.localStorage.setItem", learn)
        self.assertIn("VALUE-101-Setup.exe", runbook)
        self.assertIn("within 30 minutes", runbook)

    def test_first_lesson_must_be_opened_and_completed_explicitly(self) -> None:
        learn = (ROOT / "app" / "features" / "learn" / "Value101Learn.tsx").read_text("utf-8")
        contract = (ROOT / "app" / "features" / "learn" / "value101.ts").read_text("utf-8")

        self.assertIn("useState(false)", learn)
        self.assertIn("Open lesson", learn)
        self.assertIn("Review lesson", learn)
        self.assertIn("Continue", learn)
        self.assertIn("descriptor.concepts.map", learn)
        self.assertIn("lessonRef.current?.scrollIntoView", learn)
        self.assertIn("lessonRef.current?.focus", learn)
        self.assertIn("lessonTrigger.current?.focus", learn)
        self.assertIn("setLessonOpen(true)", learn)
        self.assertIn('mark("building-blocks")', learn)
        self.assertIn("value.101.progress.v1", contract)


if __name__ == "__main__":
    unittest.main()
