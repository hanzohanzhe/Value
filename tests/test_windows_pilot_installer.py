from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_windows_pilot_installer.py"
AUDITOR = ROOT / "scripts" / "audit_value_101_release.py"
BOOTSTRAP = ROOT / "packaging" / "windows-pilot" / "ValueInstaller.cs"
PROGRESS_WINDOW = ROOT / "packaging" / "windows-pilot" / "ValueInstallerWindow.cs"
LAUNCHER = ROOT / "packaging" / "windows-pilot" / "start-portable.ps1"
MANIFEST = ROOT / "packaging" / "windows-pilot" / "product.json"


class WindowsPilotInstallerContractTests(unittest.TestCase):
    def test_bootstrapper_rejects_dot_segments_before_extracting_payload(self) -> None:
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        harness = r'''
using System;
using System.Reflection;

internal static class PayloadPathHarness
{
    [STAThread]
    private static int Main()
    {
        MethodInfo method = typeof(ValueInstaller).GetMethod(
            "IsSafePayloadName", BindingFlags.NonPublic | BindingFlags.Static);
        if (!(bool)method.Invoke(null, new object[] { "runtime/python/python.exe" })) return 10;
        if ((bool)method.Invoke(null, new object[] { "runtime/python/../../scripts/start.ps1" })) return 11;
        if ((bool)method.Invoke(null, new object[] { "runtime\\python\\python.exe" })) return 12;
        return 0;
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "PayloadPathHarness.cs"
            executable = temporary_root / "payload-path-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework), "/nologo", "/target:exe",
                    "/main:PayloadPathHarness", f"/out:{executable}",
                    "/reference:System.IO.Compression.dll",
                    "/reference:System.IO.Compression.FileSystem.dll",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(BOOTSTRAP), str(PROGRESS_WINDOW), str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            exercised = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)

    def test_portable_launcher_refuses_an_unowned_listener_before_starting_services(self) -> None:
        portable = ROOT / "scripts" / "start-portable-local.ps1"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, tempfile.TemporaryDirectory() as temporary:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 8766))
            listener.listen(1)
            temporary_root = Path(temporary)
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(portable),
                    "-Python",
                    str(temporary_root / "missing-python.exe"),
                    "-Node",
                    str(temporary_root / "missing-node.exe"),
                    "-StateRoot",
                    str(temporary_root / "state"),
                    "-NoBrowser",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Port 8766 is already in use", output)

    def test_progress_window_reports_real_stage_and_blocks_early_close(self) -> None:
        self.assertTrue(PROGRESS_WINDOW.is_file(), PROGRESS_WINDOW)
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        self.assertTrue(framework.is_file(), framework)
        harness = r'''
using System;
using System.Windows.Forms;

internal static class InstallerWindowHarness
{
    [STAThread]
    private static int Main()
    {
        using (var window = new ValueInstallerWindow())
        {
            window.UpdateProgress(42, "Extracting model files");
            var bar = (ProgressBar)window.Controls["installationProgress"];
            var status = (Label)window.Controls["installationStatus"];
            var close = (Button)window.Controls["closeInstaller"];
            if (bar.Value != 42) return 10;
            if (status.Text != "Extracting model files") return 11;
            if (window.ControlBox || close.Enabled) return 12;
            window.MarkComplete("VALUE is ready");
            if (bar.Value != 100 || status.Text != "VALUE is ready") return 13;
            if (!window.ControlBox || !close.Enabled) return 14;
        }
        return 0;
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "InstallerWindowHarness.cs"
            executable = temporary_root / "installer-window-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework),
                    "/nologo",
                    "/target:exe",
                    f"/out:{executable}",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(PROGRESS_WINDOW),
                    str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            exercised = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)

    def test_copy_application_skips_files_deleted_in_the_current_worktree(self) -> None:
        spec = spec_from_file_location("value_101_installer_builder", BUILDER)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            app = Path(temporary) / "app"
            source.mkdir()
            (source / "keep.txt").write_text("kept", "utf-8")
            (source / "source-release-manifest.json").write_text(
                json.dumps({"include": ["keep.txt", "source-release-manifest.json"]}),
                "utf-8",
            )
            tracked = SimpleNamespace(
                stdout=b"keep.txt\0deleted.txt\0source-release-manifest.json\0"
            )
            deleted = SimpleNamespace(stdout=b"deleted.txt\0")
            with patch.object(module, "EXTRA_RELEASE_FILES", ()), patch.object(
                module.subprocess, "run", side_effect=(tracked, deleted)
            ) as git_run:
                module.copy_application(source, app, Path("git"), copy_dist=False, copy_guide=False)
            self.assertEqual((app / "keep.txt").read_text("utf-8"), "kept")
            self.assertFalse((app / "deleted.txt").exists())
            for invocation in git_run.call_args_list:
                self.assertIn(
                    f"safe.directory={source.resolve().as_posix()}",
                    invocation.args[0],
                )

    def test_copy_application_excludes_previous_installer_outputs(self) -> None:
        spec = spec_from_file_location("value_101_installer_builder_dist", BUILDER)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            app = Path(temporary) / "app"
            (source / "dist" / "server").mkdir(parents=True)
            (source / "dist" / "client").mkdir(parents=True)
            (source / "dist" / "windows-pilot").mkdir(parents=True)
            (source / "dist" / "server" / "index.js").write_text("server", "utf-8")
            (source / "dist" / "client" / "app.js").write_text("client", "utf-8")
            (source / "dist" / "windows-pilot" / "previous.exe").write_bytes(b"recursive")
            (source / "source-release-manifest.json").write_text(
                json.dumps({"include": ["source-release-manifest.json"]}), "utf-8"
            )
            tracked = SimpleNamespace(stdout=b"source-release-manifest.json\0")
            deleted = SimpleNamespace(stdout=b"")
            with patch.object(module, "EXTRA_RELEASE_FILES", ()), patch.object(
                module.subprocess, "run", side_effect=(tracked, deleted)
            ):
                module.copy_application(source, app, Path("git"), copy_guide=False)
            self.assertEqual((app / "dist" / "server" / "index.js").read_text("utf-8"), "server")
            self.assertEqual((app / "dist" / "client" / "app.js").read_text("utf-8"), "client")
            self.assertFalse((app / "dist" / "windows-pilot").exists())

    def test_copy_application_excludes_repository_local_only_content(self) -> None:
        spec = spec_from_file_location("value_101_installer_builder_local_only", BUILDER)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            app = Path(temporary) / "app"
            private_fixture = source / "tests" / "fixtures" / "private.json.gz"
            private_fixture.parent.mkdir(parents=True)
            private_fixture.write_bytes(b"private research fixture")
            (source / "keep.txt").write_text("public", "utf-8")
            (source / "source-release-manifest.json").write_text(
                json.dumps(
                    {
                        "include": [
                            "keep.txt",
                            "source-release-manifest.json",
                            "tests",
                        ],
                        "local_only_source_content": [
                            {
                                "repository_path": "tests/fixtures/private.json.gz",
                                "distribution": "repository-local-only",
                            }
                        ]
                    }
                ),
                "utf-8",
            )
            tracked = SimpleNamespace(
                stdout=(
                    b"keep.txt\0source-release-manifest.json\0"
                    b"tests/fixtures/private.json.gz\0"
                )
            )
            deleted = SimpleNamespace(stdout=b"")
            with patch.object(module, "EXTRA_RELEASE_FILES", ()), patch.object(
                module.subprocess, "run", side_effect=(tracked, deleted)
            ):
                module.copy_application(source, app, Path("git"), copy_dist=False, copy_guide=False)
            self.assertEqual((app / "keep.txt").read_text("utf-8"), "public")
            self.assertTrue((app / "source-release-manifest.json").is_file())
            self.assertFalse((app / "tests" / "fixtures" / "private.json.gz").exists())

    def test_copy_application_uses_source_release_allowlist(self) -> None:
        spec = spec_from_file_location("value_101_installer_builder_allowlist", BUILDER)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            app = Path(temporary) / "app"
            (source / "app").mkdir(parents=True)
            (source / ".superpowers" / "sdd").mkdir(parents=True)
            (source / "app" / "keep.tsx").write_text("public", "utf-8")
            (source / ".superpowers" / "sdd" / "private.md").write_text(
                "local construction record", "utf-8"
            )
            (source / "source-release-manifest.json").write_text(
                json.dumps({"include": ["app", "source-release-manifest.json"]}),
                "utf-8",
            )
            tracked = SimpleNamespace(
                stdout=(
                    b"app/keep.tsx\0.superpowers/sdd/private.md\0"
                    b"source-release-manifest.json\0"
                )
            )
            deleted = SimpleNamespace(stdout=b"")
            with patch.object(module, "EXTRA_RELEASE_FILES", ()), patch.object(
                module.subprocess, "run", side_effect=(tracked, deleted)
            ):
                module.copy_application(
                    source, app, Path("git"), copy_dist=False, copy_guide=False
                )
            self.assertTrue((app / "app" / "keep.tsx").is_file())
            self.assertTrue((app / "source-release-manifest.json").is_file())
            self.assertFalse((app / ".superpowers").exists())

    def test_manifest_declares_formal_value_product(self) -> None:
        product = json.loads(MANIFEST.read_text("utf-8"))
        self.assertEqual(product["product_name"], "VALUE")
        self.assertEqual(product["install_scope"], "current-user")
        self.assertEqual(product["install_directory"], "%LOCALAPPDATA%/VALUE/app")
        self.assertEqual(product["state_directory"], "%LOCALAPPDATA%/VALUE/state")
        self.assertEqual(product["entrypoint"], "VALUE-Setup.exe")
        self.assertEqual(
            product["data_packs"],
            ["value-101-baseline-v1", "value-101-network-v1"],
        )
        self.assertTrue(product["bundled_python"])
        self.assertTrue(product["bundled_node"])
        self.assertFalse(product["administrator_required"])
        self.assertFalse(product["terminal_required"])
        self.assertFalse(product["internet_required_after_download"])
        self.assertTrue(product["progress_window"])

    def test_builder_emits_formal_value_names(self) -> None:
        source = BUILDER.read_text("utf-8")
        self.assertIn('OUTPUT_NAME = "VALUE-Setup.exe"', source)
        self.assertIn('PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"', source)
        self.assertIn('"packaging/windows-pilot/ValueInstaller.cs"', source)
        self.assertIn('"packaging/windows-pilot/ValueInstallerWindow.cs"', source)
        self.assertNotIn('OUTPUT_NAME = "VALUE-101-Setup.exe"', source)

    def test_release_auditor_requires_formal_value_installer_identity(self) -> None:
        source = AUDITOR.read_text("utf-8")
        self.assertIn('"packaging/windows-pilot/ValueInstaller.cs"', source)
        self.assertIn('"packaging/windows-pilot/ValueInstallerWindow.cs"', source)
        self.assertIn('PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"', source)
        self.assertIn('product.get("product_name") == "VALUE"', source)
        self.assertIn('product.get("entrypoint") == "VALUE-Setup.exe"', source)

    def test_builder_is_fail_closed_and_pins_runtime_downloads(self) -> None:
        source = BUILDER.read_text("utf-8")
        for required in (
            "python-3.10.11-embed-amd64.zip",
            "node-v22.22.0-win-x64.zip",
            "SHA256",
            "value-all-py310.lock",
            "VALUE-Setup.exe",
            "THIRD_PARTY_NOTICES.md",
            '"value-101-baseline-v1"',
            '"value-101-network-v1"',
            "VALUE_101_guide.pdf",
            "VALUE_101_TO_VALUE_UK_guide.pdf",
            "VALUE_Methodology.pdf",
            "START-HERE-VALUE-101-TO-VALUE-UK-Guide.pdf",
            "ValueInstaller.cs",
            "ValueInstallerWindow.cs",
            "VALUE-PAYLOAD-MANIFEST.json",
            "System.Drawing.dll",
        ):
            self.assertIn(required, source)
        self.assertNotIn("shell=True", source)
        self.assertIn('"--no-deps"', source)
        self.assertIn('site / "bin"', source)
        self.assertIn('line.startswith("../../bin/")', source)
        self.assertIn('RUNTIME_NODE_PACKAGES = ("vinext", "react", "react-dom", "react-server-dom-webpack", "scheduler")', source)
        self.assertIn('..\\\\..', source)
        self.assertIn('PYTHON_SHA256 = "608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d"', source)
        self.assertIn('NODE_SHA256 = "c97fa376d2becdc8863fcd3ca2dd9a83a9f3468ee7ccf7a6d076ec66a645c77a"', source)
        self.assertIn('"ls-files", "-z"', source)
        self.assertNotIn("shutil.copytree(source, app", source)
        self.assertIn('parser.add_argument("--git"', source)
        self.assertIn('source.resolve().as_posix()', source)

    def test_runtime_inventory_identity_is_path_order_independent(self) -> None:
        spec = spec_from_file_location("value_101_runtime_identity", BUILDER)
        assert spec and spec.loader
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        members = [
            {"path": "runtime/python/z.txt", "sha256": "b" * 64, "bytes": 2},
            {"path": "runtime/python/A.txt", "sha256": "a" * 64, "bytes": 1},
        ]
        self.assertEqual(
            module.runtime_inventory_identity(members),
            module.runtime_inventory_identity(list(reversed(members))),
        )

    def test_portable_launcher_uses_only_private_runtimes_and_state(self) -> None:
        source = LAUNCHER.read_text("utf-8")
        self.assertIn("runtime\\python\\python.exe", source)
        self.assertIn("runtime\\node\\node.exe", source)
        self.assertIn('Join-Path $env:LOCALAPPDATA "VALUE"', source)
        self.assertIn('$stateRoot = Join-Path $installRoot "state"', source)
        self.assertNotIn('"VALUE-101"', source)
        self.assertNotIn("Get-Command node", source)
        self.assertNotIn("py.exe", source)
        self.assertIn("diagnostics", source.lower())
        portable = (ROOT / "scripts" / "start-portable-local.ps1").read_text("utf-8")
        self.assertIn("http://127.0.0.1:8800", portable)
        self.assertIn("8766, 8800", portable)
        self.assertIn("Get-Command Get-NetTCPConnection", portable)
        self.assertIn("netstat", portable)
        self.assertIn("Stop-PortableProcesses", portable)
        self.assertIn("catch", portable)
        self.assertIn("backend-error.log", portable)
        self.assertIn("RedirectStandardError", portable)
        self.assertIn("$LASTEXITCODE -eq 0", portable)
        self.assertIn("$frontendScript = Join-Path", portable)
        self.assertIn('"`"$frontendScript`""', portable)

    def test_bootstrapper_creates_shortcuts_and_supports_uninstall(self) -> None:
        source = BOOTSTRAP.read_text("utf-8")
        for required in (
            "VALUE.lnk",
            "VALUE Guide.lnk",
            "Stop VALUE.lnk",
            "Uninstall VALUE.lnk",
            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
            "ProcessStartInfo",
        ):
            self.assertIn(required, source)
        self.assertIn("ZipArchive", source)
        self.assertIn('args[0] == "--audit-payload"', source)
        self.assertIn('args[0] == "--audit-payload-manifest"', source)
        self.assertIn("SHA256.Create()", source)
        self.assertIn("LocalApplicationData", source)
        self.assertIn("WorkingDirectory = Path.GetTempPath()", source)
        self.assertIn('Start(existingLauncher, "-Stop", true, 60000)', source)
        self.assertIn("The previous VALUE process did not stop cleanly; the old application was restarted.", source)
        self.assertIn('string previous = Path.Combine(Root, "app.previous")', source)
        self.assertIn("RollbackInstallation", source)
        self.assertIn("CleanupStagingApplication", source)
        self.assertIn("CompleteApplicationPromotion", source)
        self.assertIn("InstallationMetadataSnapshot.Capture", source)
        self.assertIn("RestartPreviousApplication", source)
        self.assertIn("catch (Exception metadataError)", source)
        self.assertLess(
            source.index("catch (Exception metadataError)"),
            source.index("using (metadata)"),
        )
        self.assertLess(
            source.index('int startCode = Start('),
            source.index("InstallNewMetadata()"),
        )
        self.assertLess(
            source.index("InstallNewMetadata()"),
            source.index("CompleteApplicationPromotion"),
        )
        self.assertNotIn('"VALUE-101"', source)

    def test_uninstall_cleanup_script_names_are_value_specific_and_unique(self) -> None:
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        harness = r'''
using System;
using System.IO;
using System.Reflection;

internal static class CleanupPathHarness
{
    [STAThread]
    private static int Main()
    {
        MethodInfo method = typeof(ValueInstaller).GetMethod(
            "CreateUninstallCleanupScript", BindingFlags.NonPublic | BindingFlags.Static);
        if (method == null) return 99;
        string first = (string)method.Invoke(null, null);
        string second = (string)method.Invoke(null, null);
        try
        {
            if (String.Equals(first, second, StringComparison.OrdinalIgnoreCase)) return 10;
            if (!Path.GetFileName(first).StartsWith("value-cleanup-", StringComparison.Ordinal)) return 11;
            if (!Path.GetFileName(second).StartsWith("value-cleanup-", StringComparison.Ordinal)) return 12;
            if (!first.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase)) return 13;
            if (!second.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase)) return 14;
            if (!File.Exists(first) || !File.Exists(second)) return 15;
            return 0;
        }
        finally
        {
            try { if (File.Exists(first)) File.Delete(first); } catch { }
            try { if (File.Exists(second)) File.Delete(second); } catch { }
        }
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "CleanupPathHarness.cs"
            executable = temporary_root / "cleanup-path-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework), "/nologo", "/target:exe",
                    "/main:CleanupPathHarness", f"/out:{executable}",
                    "/reference:System.IO.Compression.dll",
                    "/reference:System.IO.Compression.FileSystem.dll",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(BOOTSTRAP), str(PROGRESS_WINDOW), str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            exercised = subprocess.run(
                [str(executable)], capture_output=True, text=True, errors="replace", timeout=15
            )
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)

    def test_pre_promotion_failure_uses_strict_restart_path_exactly_once(self) -> None:
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        harness = r'''
using System;
using System.IO;
using System.Reflection;

internal static class PrePromotionRollbackHarness
{
    private static void Restart(MethodInfo method, string launcher, string workingDirectory)
    {
        try { method.Invoke(null, new object[] { launcher, workingDirectory }); }
        catch (TargetInvocationException error) { throw error.InnerException; }
    }

    [STAThread]
    private static int Main()
    {
        string root = Path.Combine(
            Path.GetTempPath(), "value-restart-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string missing = Path.Combine(root, "missing.ps1");
        string failing = Path.Combine(root, "failing.ps1");
        string succeeding = Path.Combine(root, "succeeding.ps1");
        string marker = Path.Combine(root, "restart-count.txt");
        File.WriteAllText(failing, "param([switch]$NoDialog)\r\nexit 7\r\n");
        File.WriteAllText(
            succeeding,
            "param([switch]$NoDialog)\r\nAdd-Content -LiteralPath '" +
            marker.Replace("'", "''") + "' -Value restart\r\nexit 0\r\n");
        MethodInfo restart = typeof(ValueInstaller).GetMethod(
            "RestartApplication", BindingFlags.NonPublic | BindingFlags.Static);
        if (restart == null) return 90;
        try
        {
            try
            {
                InstallationRollbackCoordinator.Execute(
                    false, true, null,
                    delegate { throw new IOException("staging cleanup failed"); },
                    null,
                    delegate { Restart(restart, missing, root); }
                );
                return 10;
            }
            catch (AggregateException error)
            {
                if (error.InnerExceptions.Count != 2) return 11;
                if (!(error.InnerExceptions[0] is IOException)) return 12;
                if (!(error.InnerExceptions[1] is FileNotFoundException)) return 13;
            }

            try
            {
                InstallationRollbackCoordinator.Execute(
                    false, true, null, null, null,
                    delegate { Restart(restart, failing, root); }
                );
                return 20;
            }
            catch (AggregateException error)
            {
                if (error.InnerExceptions.Count != 1) return 21;
                if (!(error.InnerExceptions[0] is InvalidOperationException)) return 22;
            }

            try
            {
                InstallationRollbackCoordinator.Execute(
                    false, true, null,
                    delegate { throw new IOException("staging cleanup failed"); },
                    null,
                    delegate { Restart(restart, succeeding, root); }
                );
                return 30;
            }
            catch (AggregateException error)
            {
                if (error.InnerExceptions.Count != 1) return 31;
                if (!(error.InnerExceptions[0] is IOException)) return 32;
            }
            if (!File.Exists(marker)) return 40;
            if (File.ReadAllLines(marker).Length != 1) return 41;
            return 0;
        }
        finally
        {
            try { if (Directory.Exists(root)) Directory.Delete(root, true); } catch { }
        }
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "PrePromotionRollbackHarness.cs"
            executable = temporary_root / "pre-promotion-rollback-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework), "/nologo", "/target:exe",
                    "/main:PrePromotionRollbackHarness", f"/out:{executable}",
                    "/reference:System.IO.Compression.dll",
                    "/reference:System.IO.Compression.FileSystem.dll",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(BOOTSTRAP), str(PROGRESS_WINDOW), str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            exercised = subprocess.run(
                [str(executable)], capture_output=True, text=True, errors="replace", timeout=15
            )
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)

    def test_formal_installer_never_targets_pilot_root(self) -> None:
        installer = BOOTSTRAP.read_text("utf-8")
        launcher = LAUNCHER.read_text("utf-8")
        self.assertNotIn('"VALUE-101"', installer)
        self.assertNotIn('"VALUE-101"', launcher)
        self.assertIn('"VALUE"', installer)
        self.assertIn('"VALUE"', launcher)

    def test_formal_installer_registry_version_matches_manifest(self) -> None:
        installer = BOOTSTRAP.read_text("utf-8")
        self.assertIn('key.SetValue("DisplayVersion", "0.6.0-alpha.2");', installer)

    def test_metadata_snapshot_restores_uninstaller_and_shortcut_files(self) -> None:
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        self.assertTrue(framework.is_file(), framework)
        harness = r'''
using System;
using System.IO;
using Microsoft.Win32;

internal static class MetadataRollbackHarness
{
    [STAThread]
    private static int Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "value101-metadata-" + Guid.NewGuid().ToString("N"));
        string desktop = Path.Combine(root, "desktop", "VALUE 101.lnk");
        string programs = Path.Combine(root, "programs", "VALUE 101");
        string uninstaller = Path.Combine(root, "Uninstall VALUE 101.exe");
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(desktop));
            Directory.CreateDirectory(programs);
            File.WriteAllText(desktop, "old desktop");
            File.WriteAllText(Path.Combine(programs, "old.lnk"), "old programs");
            File.WriteAllText(uninstaller, "old uninstaller");
            using (var snapshot = InstallationMetadataSnapshot.Capture(
                uninstaller, desktop, programs, ""))
            {
                File.WriteAllText(desktop, "new desktop");
                Directory.Delete(programs, true);
                Directory.CreateDirectory(programs);
                File.WriteAllText(Path.Combine(programs, "new.lnk"), "new programs");
                File.WriteAllText(uninstaller, "new uninstaller");
                snapshot.Restore();
            }
            if (File.ReadAllText(desktop) != "old desktop") return 10;
            if (File.ReadAllText(Path.Combine(programs, "old.lnk")) != "old programs") return 11;
            if (File.Exists(Path.Combine(programs, "new.lnk"))) return 12;
            if (File.ReadAllText(uninstaller) != "old uninstaller") return 13;
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().FullName + ": " + error.Message);
            return 50;
        }
        finally
        {
            try { if (Directory.Exists(root)) Directory.Delete(root, true); } catch { }
        }
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "MetadataRollbackHarness.cs"
            executable = temporary_root / "metadata-rollback-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework),
                    "/nologo",
                    "/target:exe",
                    "/main:MetadataRollbackHarness",
                    f"/out:{executable}",
                    "/reference:System.IO.Compression.dll",
                    "/reference:System.IO.Compression.FileSystem.dll",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(BOOTSTRAP),
                    str(PROGRESS_WINDOW),
                    str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            try:
                exercised = subprocess.run(
                    [str(executable)],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=15,
                )
            except subprocess.TimeoutExpired as error:
                self.fail(f"metadata harness timed out: stdout={error.stdout!r}; stderr={error.stderr!r}")
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)

    def test_rollback_runs_metadata_restore_after_app_failure_and_retains_failed_snapshot(self) -> None:
        framework = (
            Path(os.environ.get("WINDIR", r"C:\Windows"))
            / "Microsoft.NET"
            / "Framework64"
            / "v4.0.30319"
            / "csc.exe"
        )
        harness = r'''
using System;
using System.IO;

internal static class RollbackFailureHarness
{
    [STAThread]
    private static int Main()
    {
        bool metadataRestoreRan = false;
        bool aggregateRaised = false;
        try
        {
            InstallationRollbackCoordinator.Execute(
                true,
                false,
                delegate { throw new IOException("app rollback failed"); },
                null,
                delegate { metadataRestoreRan = true; },
                null
            );
        }
        catch (AggregateException) { aggregateRaised = true; }
        if (!metadataRestoreRan || !aggregateRaised) return 10;

        string root = Path.Combine(Path.GetTempPath(), "value101-retain-" + Guid.NewGuid().ToString("N"));
        string uninstaller = Path.Combine(root, "uninstaller.exe");
        Directory.CreateDirectory(root);
        File.WriteAllText(uninstaller, "old");
        string backup;
        using (var snapshot = InstallationMetadataSnapshot.Capture(
            uninstaller,
            Path.Combine(root, "desktop.lnk"),
            Path.Combine(root, "programs"),
            ""))
        {
            backup = snapshot.BackupLocation;
        }
        if (!Directory.Exists(backup)) return 11;
        Directory.Delete(backup, true);
        Directory.Delete(root, true);
        return 0;
    }
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            harness_path = temporary_root / "RollbackFailureHarness.cs"
            executable = temporary_root / "rollback-failure-harness.exe"
            harness_path.write_text(harness, "utf-8")
            compiled = subprocess.run(
                [
                    str(framework),
                    "/nologo",
                    "/target:exe",
                    "/main:RollbackFailureHarness",
                    f"/out:{executable}",
                    "/reference:System.IO.Compression.dll",
                    "/reference:System.IO.Compression.FileSystem.dll",
                    "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll",
                    str(BOOTSTRAP),
                    str(PROGRESS_WINDOW),
                    str(harness_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            exercised = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
            self.assertEqual(exercised.returncode, 0, exercised.stdout + exercised.stderr)


if __name__ == "__main__":
    unittest.main()
